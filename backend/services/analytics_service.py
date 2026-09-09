"""调研答卷回收与研究数据分析。"""

from __future__ import annotations

from collections import Counter
from typing import Any

from ..models import SurveyResponse, WrappedSurvey


def validate_answers(survey: WrappedSurvey, answers: dict[str, Any]) -> None:
    """校验答卷完整性，并阻止写入不属于该问卷的选项值。"""

    valid_ids = {question.question_id for question in survey.questions}
    unknown_ids = sorted(set(answers) - valid_ids)
    if unknown_ids:
        raise ValueError(f"存在不属于当前问卷的题目：{', '.join(unknown_ids)}")

    missing_ids: list[str] = []
    for question in survey.questions:
        value = answers.get(question.question_id)
        if question.question_type == "multiple_choice":
            is_empty = not isinstance(value, list) or not value
        elif question.question_type == "text":
            is_empty = not isinstance(value, str) or not value.strip()
        else:
            is_empty = value is None or value == ""
        if question.question_id not in answers or is_empty:
            if question.required:
                missing_ids.append(question.question_id)
            continue

        if question.options:
            values = value if isinstance(value, list) else [value]
            invalid_values = [
                str(item) for item in values if str(item) not in question.options
            ]
            if invalid_values:
                raise ValueError(
                    f"题目 {question.question_id} 包含无效选项：{', '.join(invalid_values)}"
                )

    if missing_ids:
        raise ValueError(f"请完成必答题：{', '.join(missing_ids)}")


def calculate_result_type(
    survey: WrappedSurvey, answers: dict[str, Any]
) -> dict[str, str]:
    """使用稳定的本地规则生成趣味结果，避免客户端伪造结果类型。"""

    result_types = survey.result_types or [
        {"name": "探索型", "description": "你愿意尝试新体验。"}
    ]
    score = sum(
        len(value) if isinstance(value, list) else int(bool(value))
        for value in answers.values()
    )
    return result_types[score % len(result_types)]


def build_response(
    survey: WrappedSurvey, answers: dict[str, Any], result_type: str
) -> SurveyResponse:
    """根据题目映射，把展示题答案还原为研究标签答案。"""

    research_answers: dict[str, Any] = {}
    for question in survey.questions:
        if question.question_id in answers and question.research_tag:
            research_answers[question.research_tag] = answers[question.question_id]
    return SurveyResponse(survey.survey_name, answers, result_type, research_answers)


def summarize_responses(
    survey: WrappedSurvey, responses: list[SurveyResponse]
) -> dict[str, Any]:
    """生成页面图表和报告所需的汇总数据。"""

    option_counts: dict[str, dict[str, int]] = {}
    for question in survey.questions:
        values = [
            response.answers.get(question.question_id)
            for response in responses
            if response.answers.get(question.question_id) not in (None, "")
        ]
        counts: Counter[str] = Counter()
        for value in values:
            if isinstance(value, list):
                counts.update(str(item) for item in value)
            else:
                counts[str(value)] += 1
        option_counts[question.question_id] = dict(counts)
    return {
        "response_count": len(responses),
        "result_counts": dict(Counter(response.result_type for response in responses)),
        "option_counts": option_counts,
        "research_tags": sorted(
            {question.research_tag for question in survey.questions if question.research_tag}
        ),
    }
