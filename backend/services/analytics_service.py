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
) -> dict[str, Any]:
    """根据主题维度评分匹配结果，避免客户端伪造结果类型。"""

    result_types = survey.result_types or [
        {"name": "探索型", "description": "你愿意尝试新体验。"}
    ]
    if not survey.dimensions:
        # 兼容第一版已经保存的问卷，新问卷不会再走答案数量取模逻辑。
        score = sum(
            len(value) if isinstance(value, list) else int(bool(value))
            for value in answers.values()
        )
        return result_types[score % len(result_types)]

    dimension_scores = calculate_dimension_scores(survey, answers)
    result = min(
        result_types,
        key=lambda item: _profile_distance(
            dimension_scores,
            item.get("dimension_profile", {}),
        ),
    )
    analysis = build_result_analysis(survey, answers, result, dimension_scores)
    enriched = dict(result)
    enriched["dimension_scores"] = dimension_scores
    enriched["analysis"] = analysis
    return enriched


def calculate_dimension_scores(
    survey: WrappedSurvey, answers: dict[str, Any]
) -> dict[str, float]:
    """把每道互动题的选项贡献聚合为 -1 到 1 的主题维度分数。"""

    dimension_keys = [
        str(dimension.get("key"))
        for dimension in survey.dimensions
        if dimension.get("key")
    ]
    totals = {key: 0.0 for key in dimension_keys}
    weights = {key: 0.0 for key in dimension_keys}

    for question in survey.questions:
        value = answers.get(question.question_id)
        selected_options = value if isinstance(value, list) else [value]
        selected_options = [
            str(option)
            for option in selected_options
            if option is not None and str(option).strip()
        ]
        if not selected_options:
            continue

        option_contributions: list[dict[str, float]] = []
        for option in selected_options:
            option_contributions.append(question.option_scores.get(option, {}))
        if not option_contributions:
            continue

        # 多选题取平均，避免多选数量本身把分数无意义地放大。
        configured_dimensions: set[str] = set()
        for item in option_contributions:
            configured_dimensions.update(item)

        for key in dimension_keys:
            if key not in configured_dimensions:
                continue
            score = sum(item.get(key, 0.0) for item in option_contributions)
            score /= len(option_contributions)
            question_weight = question.dimension_weights.get(key, 1.0)
            if question_weight == 0:
                continue
            totals[key] += score * question_weight
            weights[key] += abs(question_weight)

    return {
        key: round(totals[key] / weights[key], 3) if weights[key] else 0.0
        for key in dimension_keys
    }


def build_result_analysis(
    survey: WrappedSurvey,
    answers: dict[str, Any],
    result: dict[str, Any],
    dimension_scores: dict[str, float],
) -> dict[str, Any]:
    """生成面向答题者的证据、维度拆解和行动建议。"""

    dimension_map = {
        str(item.get("key")): item
        for item in survey.dimensions
        if item.get("key")
    }
    breakdown: list[dict[str, Any]] = []
    for key, score in dimension_scores.items():
        dimension = dimension_map.get(key, {})
        if score >= 0.35:
            signal = str(dimension.get("high_pole") or "偏高")
        elif score <= -0.35:
            signal = str(dimension.get("low_pole") or "偏低")
        else:
            signal = "保持弹性"
        breakdown.append(
            {
                "key": key,
                "name": str(dimension.get("name") or key),
                "score": score,
                "signal": signal,
                "description": str(dimension.get("description") or ""),
            }
        )

    evidence: list[dict[str, str]] = []
    for question in survey.questions:
        value = answers.get(question.question_id)
        selected = value if isinstance(value, list) else [value]
        selected = [
            str(option)
            for option in selected
            if option is not None and str(option).strip()
        ]
        if not selected:
            continue
        scores = [
            question.option_scores.get(option, {})
            for option in selected
        ]
        contribution_by_dimension: dict[str, float] = {}
        for key in dimension_scores:
            contribution_by_dimension[key] = sum(
                item.get(key, 0.0) for item in scores
            ) / max(len(scores), 1)
        if contribution_by_dimension:
            key, contribution = max(
                contribution_by_dimension.items(),
                key=lambda pair: abs(pair[1]),
            )
            dimension = dimension_map.get(key, {})
            direction = (
                str(dimension.get("high_pole") or "偏高")
                if contribution >= 0
                else str(dimension.get("low_pole") or "偏低")
            )
            reason = (
                f"这项选择让「{dimension.get('name') or key}」更接近{direction}侧，"
                "与最终画像形成了直接证据。"
            )
        else:
            reason = "这项选择参与了整体主题判断。"
        evidence.append(
            {
                "question": question.public_text,
                "answer": "、".join(selected),
                "reason": reason,
                "rationale": question.rationale,
            }
        )
    evidence.sort(key=lambda item: len(item["reason"]), reverse=True)

    strengths = _string_list(result.get("strengths", []))
    watchouts = _string_list(result.get("watchouts", []))
    advice = str(result.get("advice") or "").strip()
    if not strengths:
        strengths = [
            item["signal"]
            for item in breakdown
            if item["score"] >= 0.35
        ][:3]
    if not watchouts:
        watchouts = [
            f"「{item['name']}」目前更偏向中间区间，可以留意具体情境下的变化。"
            for item in breakdown
            if abs(item["score"]) < 0.35
        ][:2]
    if not advice:
        advice = "把这份结果当作自我观察的起点，结合具体场景判断是否符合你最近的状态。"

    return {
        "summary": str(result.get("description") or ""),
        "dimension_breakdown": breakdown,
        "evidence": evidence[:4],
        "strengths": strengths,
        "watchouts": watchouts,
        "advice": advice,
    }


def _profile_distance(
    scores: dict[str, float], profile: Any
) -> float:
    """计算用户维度画像与结果类型画像的距离。"""

    if not isinstance(profile, dict) or not profile:
        return 0.0
    return sum(
        (scores.get(str(key), 0.0) - _number(value)) ** 2
        for key, value in profile.items()
    )


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def build_response(
    survey: WrappedSurvey,
    answers: dict[str, Any],
    result_type: str,
    dimension_scores: dict[str, float] | None = None,
    analysis: dict[str, Any] | None = None,
) -> SurveyResponse:
    """根据题目映射，把展示题答案还原为研究标签答案。"""

    research_answers: dict[str, Any] = {}
    for question in survey.questions:
        if question.question_id in answers and question.research_tag:
            research_answers[question.research_tag] = answers[question.question_id]
    return SurveyResponse(
        survey.survey_name,
        answers,
        result_type,
        research_answers,
        dimension_scores or {},
        analysis or {},
    )


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
