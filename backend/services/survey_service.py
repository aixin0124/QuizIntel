"""问卷导入和大模型包装服务。

正式运行路径只调用真实大模型，不提供无密钥的本地替代结果。
"""

from __future__ import annotations

import csv
import io
import json
from typing import Any

from ..models import SurveyQuestion, WrappedQuestion, WrappedSurvey
from .llm_service import LLMService


def parse_survey_text(content: str, file_name: str = "") -> list[SurveyQuestion]:
    """解析 JSON 或常见 CSV 导出的问卷文本。"""

    text = content.lstrip("\ufeff").strip()
    if not text:
        return []
    if file_name.lower().endswith(".json") or text.startswith("["):
        raw_items = json.loads(text)
        if not isinstance(raw_items, list):
            raise ValueError("JSON 问卷必须是数组")
        questions = [
            _question_from_dict(item, index) for index, item in enumerate(raw_items, 1)
        ]
        return _validate_questions(questions)

    reader = csv.DictReader(io.StringIO(text))
    questions: list[SurveyQuestion] = []
    for index, row in enumerate(reader, 1):
        normalized = {
            str(key).strip().lower(): str(value or "").strip()
            for key, value in row.items()
        }
        question_text = (
            normalized.get("question")
            or normalized.get("题目")
            or normalized.get("text")
        )
        if not question_text:
            continue
        raw_options = normalized.get("options") or normalized.get("选项") or ""
        options = [
            item.strip()
            for item in raw_options.replace("；", "|").split("|")
            if item.strip()
        ]
        questions.append(
            SurveyQuestion(
                question_id=normalized.get("id") or f"q{index}",
                text=question_text,
                question_type=_normalize_type(
                    normalized.get("type") or normalized.get("题型") or "single_choice"
                ),
                options=options,
                research_tag=normalized.get("research_tag")
                or normalized.get("研究标签")
                or "",
                required=_parse_bool(normalized.get("required") or normalized.get("必答")),
            )
        )
    return _validate_questions(questions)


def build_wrapped_survey(
    questions: list[SurveyQuestion],
    brand_goal: str,
    theme_hint: str,
    llm_service: LLMService | None = None,
) -> WrappedSurvey:
    """调用大模型生成互动包装。"""

    service = llm_service or LLMService()
    raw = service.generate_json(
        _system_prompt(),
        json.dumps(
            {
                "brand_goal": brand_goal,
                "theme_hint": theme_hint,
                "questions": [question.to_dict() for question in questions],
                "required_output": _output_schema(),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    wrapped = _normalize_wrapped_survey(raw, questions, brand_goal)
    wrapped.source = "llm"
    return wrapped


def wrapped_survey_from_dict(payload: dict[str, Any]) -> WrappedSurvey:
    """从数据库 JSON 恢复包装方案。"""

    return WrappedSurvey(
        survey_name=str(payload["survey_name"]),
        theme=str(payload["theme"]),
        tagline=str(payload["tagline"]),
        intro=str(payload["intro"]),
        disclosure=str(payload["disclosure"]),
        result_types=[
            {
                "name": str(item.get("name", "")),
                "description": str(item.get("description", "")),
            }
            for item in payload.get("result_types", [])
        ],
        questions=[
            WrappedQuestion(
                question_id=str(item["question_id"]),
                public_text=str(item["public_text"]),
                question_type=str(item["question_type"]),
                options=[str(option) for option in item.get("options", [])],
                research_tag=str(item.get("research_tag", "")),
                source_text=str(item.get("source_text", "")),
                required=bool(item.get("required", True)),
            )
            for item in payload.get("questions", [])
        ],
        brand_goal=str(payload.get("brand_goal", "")),
        source=str(payload.get("source", "llm")),
    )


def _system_prompt() -> str:
    return (
        "你是互动式市场调研策划师。请把普通调研题目包装为轻量娱乐测评，"
        "但不能伪装成医学诊断、临床心理测试或承诺科学测量。必须保留每个原始题目的研究含义，"
        "通过 question_id 建立映射。只输出合法 JSON。"
    )


def _output_schema() -> dict[str, Any]:
    return {
        "survey_name": "测评名称",
        "theme": "主题，例如恋爱象限",
        "tagline": "一句吸引人的副标题",
        "intro": "测评介绍",
        "disclosure": "透明告知文案",
        "result_types": [{"name": "类型名称", "description": "结果描述"}],
        "questions": [
            {
                "question_id": "必须使用原题目 ID",
                "public_text": "包装后的题目",
                "question_type": "single_choice/multiple_choice/scale/text",
                "options": ["选项"],
                "research_tag": "原研究标签",
            }
        ],
    }


def _normalize_wrapped_survey(
    raw: dict[str, Any], originals: list[SurveyQuestion], brand_goal: str
) -> WrappedSurvey:
    original_map = {question.question_id: question for question in originals}
    raw_question_map = {
        str(item.get("question_id", "")): item
        for item in raw.get("questions", [])
        if isinstance(item, dict)
    }
    wrapped_questions: list[WrappedQuestion] = []
    for original in originals:
        raw_question = raw_question_map.get(original.question_id, {})
        wrapped_questions.append(
            WrappedQuestion(
                question_id=original.question_id,
                public_text=str(raw_question.get("public_text") or original.text),
                # 研究字段的选项编码必须与原问卷一致，避免模型改写选项后污染统计。
                question_type=original.question_type,
                options=original.options
                or [str(item) for item in raw_question.get("options", [])],
                research_tag=original.research_tag,
                source_text=original.text,
                required=original.required,
            )
        )
    return WrappedSurvey(
        survey_name=str(raw.get("survey_name") or "趣味测评"),
        theme=str(raw.get("theme") or "你的隐藏属性"),
        tagline=str(raw.get("tagline") or "花一分钟，看看你是哪一型"),
        intro=str(raw.get("intro") or "根据你的选择生成一个轻量趣味结果。"),
        disclosure=str(
            raw.get("disclosure")
            or "本测评仅供娱乐，部分题目用于市场研究，结果不构成心理或医学判断。"
        ),
        result_types=[
            {
                "name": str(item.get("name", "探索型")),
                "description": str(item.get("description", "")),
            }
            for item in raw.get("result_types", [])
        ]
        or [{"name": "探索型", "description": "你愿意尝试新鲜事物。"}],
        questions=wrapped_questions,
        brand_goal=brand_goal,
        source="llm",
    )


def _question_from_dict(item: dict[str, Any], index: int) -> SurveyQuestion:
    if not isinstance(item, dict):
        raise ValueError(f"第 {index} 道题必须是对象")
    return SurveyQuestion(
        question_id=str(item.get("question_id") or item.get("id") or f"q{index}"),
        text=str(item.get("text") or item.get("question") or item.get("题目") or ""),
        question_type=_normalize_type(
            str(item.get("question_type") or item.get("type") or "single_choice")
        ),
        options=_normalize_options(item.get("options", [])),
        research_tag=str(item.get("research_tag") or item.get("tag") or ""),
        required=_parse_bool(item.get("required", True)),
    )


def _normalize_options(raw_options: Any) -> list[str]:
    """兼容 JSON 数组和导入文件中的分隔字符串。"""

    if isinstance(raw_options, str):
        return [item.strip() for item in raw_options.replace("；", "|").split("|") if item.strip()]
    if isinstance(raw_options, list):
        return [str(item).strip() for item in raw_options if str(item).strip()]
    return []


def _parse_bool(value: Any) -> bool:
    """把 CSV 中常见的中英文必答标记统一为布尔值。"""

    if value is None or str(value).strip() == "":
        return True
    return str(value).strip().lower() not in {"0", "false", "no", "否", "选填", "可选"}


def _validate_questions(questions: list[SurveyQuestion]) -> list[SurveyQuestion]:
    """拒绝空题目和重复编号，保证后续答卷映射唯一。"""

    valid_questions = [question for question in questions if question.text.strip()]
    if not valid_questions:
        return []
    ids = [question.question_id for question in valid_questions]
    if any(not question_id.strip() for question_id in ids):
        raise ValueError("题目编号不能为空")
    duplicates = sorted({question_id for question_id in ids if ids.count(question_id) > 1})
    if duplicates:
        raise ValueError(f"题目编号重复：{', '.join(duplicates)}")
    return valid_questions


def _normalize_type(value: str) -> str:
    lowered = value.lower().strip()
    if lowered in {"multiple", "multiple_choice", "多选题"}:
        return "multiple_choice"
    if lowered in {"scale", "评分题", "量表题"}:
        return "scale"
    if lowered in {"text", "填空题", "文本题"}:
        return "text"
    return "single_choice"
