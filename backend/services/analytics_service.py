"""调研答卷回收与研究数据分析。"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
import json
from typing import Any

from ..models import SurveyResponse, WrappedSurvey
from .llm_service import LLMService


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

    if not isinstance(profile, dict):
        profile = {}
    profile_keys = {str(key) for key in profile}
    keys = set(scores) | profile_keys
    if not keys:
        return 0.0
    missing_penalty = 0.25 * len(keys - profile_keys)
    return sum(
        (scores.get(key, 0.0) - _number(profile.get(key, 0.0))) ** 2
        for key in keys
    ) + missing_penalty


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

    facts = build_research_facts(survey, responses)
    return {
        "response_count": facts["response_count"],
        "result_counts": facts["result_counts"],
        "option_counts": {
            question["question_id"]: {
                item["option"]: item["count"] for item in question["options"]
            }
            for question in facts["questions"]
        },
        "research_tags": facts["research_tags"],
        "result_types": facts["result_types"],
        "dimension_stats": facts["dimensions"],
        "question_stats": facts["questions"],
    }


def build_research_facts(
    survey: WrappedSurvey, responses: list[SurveyResponse]
) -> dict[str, Any]:
    """按题目映射计算研究事实，所有人数和比例都由本地代码产生。"""

    question_facts: list[dict[str, Any]] = []
    for question in survey.questions:
        answered_count = 0
        counts: Counter[str] = Counter()
        for response in responses:
            value = response.answers.get(question.question_id)
            values = _answer_values(value)
            if not values:
                continue
            answered_count += 1
            counts.update(values)

        option_labels = list(question.options)
        option_labels.extend(
            option for option in counts if option not in option_labels
        )
        question_facts.append(
            {
                "question_id": question.question_id,
                "question": question.public_text,
                "research_tag": question.research_tag,
                "research_refs": list(question.research_refs),
                "question_type": question.question_type,
                "answered_count": answered_count,
                "answer_rate": _percentage(answered_count, len(responses)),
                "options": [
                    {
                        "option": option,
                        "count": counts.get(option, 0),
                        "percentage": _percentage(counts.get(option, 0), answered_count),
                    }
                    for option in option_labels
                ],
                "dimension_keys": _question_dimension_keys(question),
            }
        )

    dimensions = _build_dimension_facts(survey, responses, question_facts)
    result_types = _build_result_type_facts(survey, responses)
    return {
        "research_goal": survey.brand_goal,
        "theme": survey.theme,
        "response_count": len(responses),
        "result_counts": {
            item["name"]: item["count"] for item in result_types
        },
        "result_types": result_types,
        "research_tags": sorted(
            {
                question.research_tag
                for question in survey.questions
                if question.research_tag
            }
        ),
        "dimensions": dimensions,
        "questions": question_facts,
    }


def build_research_analysis(
    survey: WrappedSurvey,
    responses: list[SurveyResponse],
    llm_service: LLMService | None = None,
) -> dict[str, Any]:
    """调用 AI 解读研究事实，并保留本地计算的准确数据。"""

    facts = build_research_facts(survey, responses)
    if not facts["response_count"]:
        raise ValueError("至少需要 1 份有效答卷后才能开始数据分析。")

    service = llm_service or LLMService()
    raw = service.generate_json(
        _research_analysis_system_prompt(),
        json.dumps(
            {
                "research_goal": survey.brand_goal,
                "theme": survey.theme,
                "analysis_method": survey.analysis_method,
                "facts": facts,
                "required_output": _research_analysis_schema(),
            },
            ensure_ascii=False,
            indent=2,
        ),
    )
    return _normalize_research_analysis(raw, survey, facts)


def _build_dimension_facts(
    survey: WrappedSurvey,
    responses: list[SurveyResponse],
    question_facts: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """聚合主题维度，并兼容没有新评分维度的历史问卷。"""

    dimension_definitions = [
        item for item in survey.dimensions if item.get("key")
    ]
    if not dimension_definitions:
        tags = [
            tag for tag in sorted(
                {
                    question.research_tag
                    for question in survey.questions
                    if question.research_tag
                }
            )
            if tag
        ]
        return [
            {
                "key": f"research_tag_{index}",
                "name": tag,
                "description": "按原始研究标签聚合的答卷分布。",
                "score": None,
                "index": None,
                "positive_count": None,
                "neutral_count": None,
                "negative_count": None,
                "coverage_count": sum(
                    item["answered_count"]
                    for item in question_facts
                    if item["research_tag"] == tag
                ),
                "mapped_question_ids": [
                    item["question_id"]
                    for item in question_facts
                    if item["research_tag"] == tag
                ],
                "mapped_research_tags": [tag],
            }
            for index, tag in enumerate(tags, 1)
        ]

    score_rows: dict[str, list[float]] = {
        str(item["key"]): [] for item in dimension_definitions
    }
    coverage_counts = {key: 0 for key in score_rows}
    for response in responses:
        scores = calculate_dimension_scores(survey, response.answers)
        for key in score_rows:
            mapped_questions = [
                question
                for question in survey.questions
                if key in _question_dimension_keys(question)
            ]
            has_answer = any(
                _answer_values(response.answers.get(question.question_id))
                for question in mapped_questions
            )
            if not has_answer:
                continue
            score_rows[key].append(scores.get(key, 0.0))
            coverage_counts[key] += 1

    result: list[dict[str, Any]] = []
    for definition in dimension_definitions:
        key = str(definition["key"])
        values = score_rows[key]
        average = round(sum(values) / len(values), 3) if values else 0.0
        result.append(
            {
                "key": key,
                "name": str(definition.get("name") or key),
                "description": str(definition.get("description") or ""),
                "high_pole": str(definition.get("high_pole") or "偏高"),
                "low_pole": str(definition.get("low_pole") or "偏低"),
                "score": average,
                "index": round((average + 1) * 50, 1),
                "positive_count": sum(value >= 0.35 for value in values),
                "neutral_count": sum(-0.35 < value < 0.35 for value in values),
                "negative_count": sum(value <= -0.35 for value in values),
                "coverage_count": coverage_counts[key],
                "mapped_question_ids": [
                    item["question_id"]
                    for item in question_facts
                    if key in item["dimension_keys"]
                ],
                "mapped_research_tags": sorted(
                    {
                        item["research_tag"]
                        for item in question_facts
                        if key in item["dimension_keys"] and item["research_tag"]
                    }
                ),
            }
        )
    return result


def _build_result_type_facts(
    survey: WrappedSurvey,
    responses: list[SurveyResponse],
) -> list[dict[str, Any]]:
    """列出全部人格画像及样本分布，包含当前无人命中的类型。"""

    counts = Counter(response.result_type for response in responses)
    total = len(responses)
    result: list[dict[str, Any]] = []
    seen_names: set[str] = set()
    for item in survey.result_types:
        name = str(item.get("name") or "未命名类型")
        seen_names.add(name)
        result.append(
            {
                "name": name,
                "description": str(item.get("description") or ""),
                "dimension_profile": _normalize_profile(item.get("dimension_profile", {})),
                "strengths": _string_list(item.get("strengths", [])),
                "watchouts": _string_list(item.get("watchouts", [])),
                "advice": str(item.get("advice") or ""),
                "count": counts.get(name, 0),
                "percentage": _percentage(counts.get(name, 0), total),
            }
        )

    for name, count in counts.items():
        if name in seen_names:
            continue
        result.append(
            {
                "name": name,
                "description": "",
                "dimension_profile": {},
                "strengths": [],
                "watchouts": [],
                "advice": "",
                "count": count,
                "percentage": _percentage(count, total),
            }
        )
    return result


def _normalize_research_analysis(
    raw: dict[str, Any],
    survey: WrappedSurvey,
    facts: dict[str, Any],
) -> dict[str, Any]:
    """把 AI 的解释文字绑定到本地事实，避免模型改写人数和比例。"""

    raw_dimension_map = {
        str(item.get("key")): str(item.get("conclusion") or "").strip()
        for item in raw.get("dimension_conclusions", [])
        if isinstance(item, dict) and item.get("key")
    }
    dimensions = [
        {
            **dimension,
            "conclusion": raw_dimension_map.get(
                dimension["key"],
                "当前样本在该维度上的回答呈现出一定差异，建议结合具体选项分布理解。",
            ),
        }
        for dimension in facts["dimensions"]
    ]
    key_findings = _string_list(raw.get("key_findings", []))[:6]
    if not key_findings:
        key_findings = _default_key_findings(facts)

    conclusion = str(raw.get("research_conclusion") or "").strip()
    if not conclusion:
        conclusion = _default_research_conclusion(survey, facts)
    long_summary = str(raw.get("long_summary") or "").strip()
    if not long_summary:
        long_summary = _default_long_summary(survey, facts)
    limitations = str(raw.get("limitations") or "").strip()
    if not limitations:
        limitations = (
            "本结论基于当前已收集的匿名答卷，适合用于识别样本中的倾向和差异，"
            "不应直接外推为全部目标人群的总体结论。"
        )

    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "research_goal": survey.brand_goal,
        "theme": survey.theme,
        "response_count": facts["response_count"],
        "result_counts": facts["result_counts"],
        "result_types": facts["result_types"],
        "research_tags": facts["research_tags"],
        "dimensions": dimensions,
        "questions": facts["questions"],
        "key_findings": key_findings,
        "research_conclusion": conclusion,
        "long_summary": long_summary,
        "limitations": limitations,
        "analysis_method": survey.analysis_method
        or "按题目映射和主题维度对匿名答卷进行描述性统计与综合解读。",
    }


def _research_analysis_system_prompt() -> str:
    return (
        "你是资深市场研究分析师。请围绕用户给出的调研目标，对已经统计好的匿名问卷事实进行综合解读。"
        "调研目标是唯一的主要主题，不能把互动结果类型当成研究目标，也不能偏离目标另起主题。"
        "facts.result_types 是本问卷完整的人格画像清单，包含未被任何答卷命中的类型；"
        "分析时必须知道这些类型的总范围，但不要把互动人格标签替代调研目标。"
        "必须根据题目映射和 dimensions 分维度分析，结合 questions 中的选项分布说明差异。"
        "输入中的人数、比例、指数和答卷数已经由系统准确计算，禁止修改、四舍五入重算或虚构任何数字；"
        "输出文字中尽量不要重复具体数字，数字由系统表格展示。"
        "不要把相关性写成因果关系，不要把当前样本写成全部人群，不要输出医学、心理诊断或未经调查支持的结论。"
        "key_findings 输出 3 至 6 条有决策价值的文字；dimension_conclusions 必须覆盖每个维度，"
        "每条说明该维度在当前调研目标下意味着什么；research_conclusion 是面向调研目标的结论；"
        "long_summary 必须是一段完整、连贯、较长的中文总结，包含样本特征、主要维度差异、"
        "题目映射呈现出的行为或需求、对调研目标的启示和谨慎边界；limitations 说明样本和方法边界。"
        "只输出合法 JSON，不要 Markdown，不要解释 JSON 之外的内容。"
    )


def _research_analysis_schema() -> dict[str, Any]:
    return {
        "key_findings": ["面向调研目标的关键发现"],
        "dimension_conclusions": [
            {"key": "必须与输入 dimensions 的 key 一致", "conclusion": "维度解释"}
        ],
        "research_conclusion": "围绕调研目标的综合结论",
        "long_summary": "较长的中文段落总结",
        "limitations": "样本和方法边界",
    }


def _question_dimension_keys(question: Any) -> list[str]:
    """读取题目评分映射中的维度键。"""

    keys = set(str(key) for key in question.dimension_weights if key)
    for scores in question.option_scores.values():
        keys.update(str(key) for key in scores if key)
    return sorted(keys)


def _normalize_profile(value: Any) -> dict[str, float]:
    """把结果画像坐标统一为数值字典，用于分析 facts。"""

    if not isinstance(value, dict):
        return {}
    return {str(key): _number(item) for key, item in value.items()}


def _answer_values(value: Any) -> list[str]:
    """把单选、多选和文本答案统一为可计数的字符串列表。"""

    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if value is None:
        return []
    text = str(value).strip()
    return [text] if text else []


def _percentage(count: int, total: int) -> float:
    if not total:
        return 0.0
    return round(count / total * 100, 1)


def _default_key_findings(facts: dict[str, Any]) -> list[str]:
    """模型缺少关键发现时，提供不改变数字的保守文字。"""

    findings: list[str] = []
    for dimension in facts["dimensions"][:3]:
        if dimension["score"] is None:
            findings.append(
                f"「{dimension['name']}」维度已按题目映射完成分组统计，"
                "可结合下方选项分布观察样本差异。"
            )
            continue
        if dimension["score"] >= 0.35:
            signal = dimension.get("high_pole") or "偏高"
        elif dimension["score"] <= -0.35:
            signal = dimension.get("low_pole") or "偏低"
        else:
            signal = "处于中间区间"
        findings.append(f"「{dimension['name']}」整体呈现{signal}倾向。")
    return findings or ["当前样本已完成统计，建议结合题目分布阅读具体发现。"]


def _default_research_conclusion(
    survey: WrappedSurvey, facts: dict[str, Any]
) -> str:
    return (
        f"围绕“{survey.brand_goal}”，当前样本已经完成按题目映射和主题维度的描述性统计。"
        "整体结论应以各维度指数、覆盖样本和具体选项分布共同判断，适合用于发现需求重点和后续研究方向。"
    )


def _default_long_summary(survey: WrappedSurvey, facts: dict[str, Any]) -> str:
    dimension_names = "、".join(
        str(item["name"]) for item in facts["dimensions"][:5]
    ) or "题目映射维度"
    return (
        f"本次调研以“{survey.brand_goal}”为主要分析目标，基于当前收集的匿名答卷，"
        f"围绕{dimension_names}等维度对回答进行了归类和统计。结果同时保留了每道映射题的选项人数、"
        "答题覆盖和比例，能够帮助研究者区分总体倾向与具体需求表现。阅读结论时，应先结合维度指数"
        "判断样本的大方向，再回到题目选项分布观察不同回答之间的差异，避免只依据单个问题做判断。"
        "这些结果适合支持产品定位、内容设计或后续访谈提纲的形成，但当前样本仍然只代表已参与答题的人群，"
        "不能替代更大范围的抽样调查或因果验证。"
    )


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value.strip()] if value.strip() else []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []
