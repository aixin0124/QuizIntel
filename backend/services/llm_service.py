"""OpenAI 兼容大模型接口封装。"""

from __future__ import annotations

import json
from typing import Any

import requests

from ..config import settings


class LLMService:
    """调用大模型生成结构化问卷包装。"""

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if not settings.has_llm:
            raise RuntimeError("未配置 LLM_API_KEY 或可用的模型服务")

        if settings.llm_wire_api in {"responses", "response"}:
            content = self._generate_with_responses(system_prompt, user_prompt)
        elif settings.llm_wire_api in {"chat", "chat_completions", "completions"}:
            content = self._generate_with_chat_completions(
                system_prompt, user_prompt
            )
        else:
            raise RuntimeError(
                f"不支持的模型协议：{settings.llm_wire_api}。"
                "可选值为 responses 或 chat_completions。"
            )
        return _parse_json_object(str(content))

    def _generate_with_responses(self, system_prompt: str, user_prompt: str) -> str:
        """调用 OpenAI Responses API。"""

        request_body: dict[str, Any] = {
            "model": settings.llm_model,
            "instructions": system_prompt,
            "input": user_prompt,
            "store": False,
            "max_output_tokens": settings.llm_max_output_tokens,
        }
        if settings.llm_reasoning_effort:
            request_body["reasoning"] = {"effort": settings.llm_reasoning_effort}
        data = self._post_json("/responses", request_body)
        return _extract_response_text(data)

    def _generate_with_chat_completions(
        self, system_prompt: str, user_prompt: str
    ) -> str:
        """兼容本地模型和旧版 OpenAI 兼容服务。"""

        data = self._post_json(
            "/chat/completions",
            {
                "model": settings.llm_model,
                "temperature": 0.75,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
        )
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError(
                "模型接口返回格式不符合 Chat Completions 规范"
            ) from exc
        if isinstance(content, list):
            content = "".join(str(part.get("text", "")) for part in content)
        return str(content)

    def _post_json(self, path: str, request_body: dict[str, Any]) -> dict[str, Any]:
        """发送请求，并在代理不接受 reasoning 参数时做一次兼容重试。"""

        headers = {"Content-Type": "application/json"}
        if settings.llm_api_key:
            headers["Authorization"] = f"Bearer {settings.llm_api_key}"
        url = f"{settings.llm_base_url.rstrip('/')}/{path.lstrip('/')}"
        try:
            response = requests.post(
                url,
                headers=headers,
                json=request_body,
                timeout=settings.request_timeout,
            )
            if response.status_code in {400, 422} and "reasoning" in request_body:
                fallback_body = dict(request_body)
                fallback_body.pop("reasoning", None)
                response = requests.post(
                    url,
                    headers=headers,
                    json=fallback_body,
                    timeout=settings.request_timeout,
                )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise RuntimeError(
                f"模型接口请求失败：{settings.llm_base_url}。"
                "请检查 API 地址、模型名称和密钥是否匹配。"
            ) from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError("模型接口返回的内容不是合法 JSON") from exc
        if not isinstance(data, dict):
            raise RuntimeError("模型接口返回的 JSON 根节点必须是对象")
        return data


def _extract_response_text(data: dict[str, Any]) -> str:
    """兼容 Responses API 的 output_text 和 output 数组格式。"""

    output_text = data.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text

    text_parts: list[str] = []
    for item in data.get("output", []):
        if not isinstance(item, dict):
            continue
        content = item.get("content", [])
        if isinstance(content, str):
            text_parts.append(content)
            continue
        if not isinstance(content, list):
            continue
        for part in content:
            if isinstance(part, dict) and isinstance(part.get("text"), str):
                text_parts.append(part["text"])
    if text_parts:
        return "".join(text_parts)
    raise RuntimeError("Responses API 返回中没有找到模型文本内容")


def _parse_json_object(content: str) -> dict[str, Any]:
    """兼容模型返回 Markdown 代码围栏。"""

    cleaned = content.strip()
    if "</think>" in cleaned:
        cleaned = cleaned.rsplit("</think>", 1)[-1].strip()
    if cleaned.startswith("```"):
        cleaned = cleaned[3:]
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
        cleaned = cleaned.strip().rstrip("`").strip()
    try:
        result = json.loads(cleaned)
    except json.JSONDecodeError:
        # 部分本地模型会在 JSON 前后补充一句解释，尝试定位第一个对象。
        start = cleaned.find("{")
        if start < 0:
            raise
        result, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    if not isinstance(result, dict):
        raise ValueError("模型返回的 JSON 根节点必须是对象")
    return result
