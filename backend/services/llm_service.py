"""OpenAI 兼容大模型接口封装。"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

import requests

from ..config import settings


class LLMService:
    """调用大模型生成结构化问卷包装。"""

    def generate_json(self, system_prompt: str, user_prompt: str) -> dict[str, Any]:
        if not settings.has_llm:
            raise RuntimeError("未配置 LLM_API_KEY 或可用的模型服务")

        try:
            content = self._generate_with_primary(system_prompt, user_prompt)
        except Exception as primary_exc:
            if not settings.has_llm_fallback:
                raise
            try:
                content = self._generate_with_chat_completions(
                    system_prompt,
                    user_prompt,
                    api_key=settings.llm_fallback_api_key,
                    base_url=settings.llm_fallback_base_url,
                    model=settings.llm_fallback_model,
                )
            except Exception as fallback_exc:
                raise RuntimeError(
                    "主模型调用失败，基元律动兜底接口也调用失败："
                    f"主模型错误：{primary_exc}；"
                    f"基元律动错误：{fallback_exc}"
                ) from fallback_exc
        return _parse_json_object(str(content))

    def _generate_with_primary(self, system_prompt: str, user_prompt: str) -> str:
        """按主配置调用模型。"""

        if settings.llm_wire_api in {"responses", "response"}:
            return self._generate_with_responses(system_prompt, user_prompt)
        if settings.llm_wire_api in {"chat", "chat_completions", "completions"}:
            return self._generate_with_chat_completions(system_prompt, user_prompt)
        raise RuntimeError(
            f"不支持的模型协议：{settings.llm_wire_api}。"
            "可选值为 responses 或 chat_completions。"
        )

    def _generate_with_responses(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> str:
        """调用 OpenAI Responses API。"""

        request_body: dict[str, Any] = {
            "model": model or settings.llm_model,
            "instructions": system_prompt,
            "input": user_prompt,
            "store": False,
            "max_output_tokens": settings.llm_max_output_tokens,
        }
        if settings.llm_reasoning_effort:
            request_body["reasoning"] = {"effort": settings.llm_reasoning_effort}
        data = self._post_json(
            "/responses",
            request_body,
            api_key=api_key,
            base_url=base_url,
        )
        return _extract_response_text(data)

    def _generate_with_chat_completions(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        api_key: str | None = None,
        base_url: str | None = None,
        model: str | None = None,
    ) -> str:
        """兼容本地模型和旧版 OpenAI 兼容服务。"""

        data = self._post_json(
            "/chat/completions",
            {
                "model": model or settings.llm_model,
                "temperature": 0.75,
                "max_tokens": settings.llm_max_output_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            },
            api_key=api_key,
            base_url=base_url,
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

    def _post_json(
        self,
        path: str,
        request_body: dict[str, Any],
        *,
        api_key: str | None = None,
        base_url: str | None = None,
    ) -> dict[str, Any]:
        """发送请求，并在代理不接受 reasoning 参数时做一次兼容重试。"""

        headers = {"Content-Type": "application/json"}
        request_api_key = api_key if api_key is not None else settings.llm_api_key
        request_base_url = base_url or settings.llm_base_url
        if request_api_key:
            headers["Authorization"] = f"Bearer {request_api_key}"
        url = _build_endpoint_url(request_base_url, path)
        response: requests.Response | None = None
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
        except requests.Timeout as exc:
            raise RuntimeError(
                f"模型接口请求超时（{settings.request_timeout} 秒）：{url}。"
                "可降低模型推理强度，或适当提高 REQUEST_TIMEOUT。"
            ) from exc
        except requests.RequestException as exc:
            status = response.status_code if response is not None else "网络错误"
            detail = _response_detail(response)
            raise RuntimeError(
                f"模型接口请求失败（{status}）：{detail or url}。"
                "请检查 API 协议、模型名称和服务状态。"
            ) from exc
        try:
            data = response.json()
        except ValueError as exc:
            raise RuntimeError(
                f"模型接口返回的内容不是合法 JSON（HTTP {response.status_code}）："
                f"{_response_detail(response)}"
            ) from exc
        if not isinstance(data, dict):
            raise RuntimeError("模型接口返回的 JSON 根节点必须是对象")
        return data


def _build_endpoint_url(base_url: str, path: str) -> str:
    """兼容根地址和已经包含 /v1 的 OpenAI 兼容服务。"""

    base = base_url.rstrip("/")
    normalized_path = path.strip("/")
    base_path = urlparse(base).path.rstrip("/")
    if normalized_path == "chat/completions" and not base_path.endswith("/v1"):
        return f"{base}/v1/{normalized_path}"
    return f"{base}/{normalized_path}"


def _response_detail(response: requests.Response | None) -> str:
    """提取简短的服务端错误，避免把网关整页 HTML 原样返回给用户。"""

    if response is None:
        return ""
    try:
        payload = response.json()
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict):
                message = error.get("message") or error.get("detail")
                if message:
                    return str(message)[:500]
            for key in ("message", "detail"):
                if payload.get(key):
                    return str(payload[key])[:500]
    except ValueError:
        pass
    title_match = re.search(r"<title>\s*(.*?)\s*</title>", response.text, re.I | re.S)
    if title_match:
        return " ".join(title_match.group(1).split())[:200]
    text = " ".join(response.text.split())
    return text[:500]


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
