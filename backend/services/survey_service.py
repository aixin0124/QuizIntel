"""问卷导入和大模型包装服务。

正式运行路径只调用真实大模型，不提供无密钥的本地替代结果。
"""

from __future__ import annotations

import csv
import io
import json
import math
import re
from html.parser import HTMLParser
from typing import Any
from urllib.parse import unquote, urlparse

import requests

from ..models import SurveyQuestion, WrappedQuestion, WrappedSurvey
from .llm_service import LLMService


# 人格和风格测评需要多个题目交叉验证，避免单题对结果影响过大。
MIN_GENERATED_QUESTIONS = 12


class _WJXQuestionHTMLParser(HTMLParser):
    """提取问卷星公开页面中的标题、题干和选项。"""

    _void_tags = {
        "area",
        "base",
        "br",
        "col",
        "embed",
        "hr",
        "img",
        "input",
        "link",
        "meta",
        "param",
        "source",
        "track",
        "wbr",
    }

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.title_depth: int | None = None
        self.title_parts: list[str] = []
        self.question_capture_depth: int | None = None
        self.question_parts: list[str] = []
        self.option_capture_depth: int | None = None
        self.option_parts: list[str] = []
        self.option_fallback = ""
        self.current: dict[str, Any] | None = None
        self.field_depth: int | None = None
        self.fields: list[dict[str, Any]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = {key.lower(): value or "" for key, value in attrs}
        classes = set(attributes.get("class", "").split())
        is_void = tag.lower() in self._void_tags
        if tag.lower() == "br":
            if self.question_capture_depth is not None:
                self.question_parts.append(" ")
            if self.option_capture_depth is not None:
                self.option_parts.append(" ")

        if (
            self.current is None
            and tag.lower() == "div"
            and "field" in classes
            and attributes.get("topic")
        ):
            self.current = {
                "question_id": f"q{attributes['topic'].strip()}",
                "topic": attributes["topic"].strip(),
                "required": _parse_bool(attributes.get("req", "1")),
                "field_type": attributes.get("type", "").strip(),
                "question_parts": [],
                "options": [],
                "option_fallbacks": [],
                "input_types": [],
                "has_textarea": False,
                "has_select": False,
            }
            self.field_depth = self.depth + 1

        if self.current is not None:
            if tag.lower() == "input":
                input_type = attributes.get("type", "").lower().strip()
                if input_type != "hidden":
                    self.current["input_types"].append(input_type)
            elif tag.lower() == "textarea":
                self.current["has_textarea"] = True
            elif tag.lower() == "select":
                self.current["has_select"] = True

        if tag.lower() == "title":
            self.title_depth = self.depth + 1
            self.title_parts = []
        elif tag.lower() == "h1" and (
            attributes.get("id") == "htitle" or "htitle" in classes
        ):
            self.title_depth = self.depth + 1
            self.title_parts = []
        elif self.current is not None and "topichtml" in classes:
            self.question_capture_depth = self.depth + 1
            self.question_parts = []
        elif (
            self.current is not None
            and "label" in classes
            and "field-label" not in classes
        ):
            self.option_capture_depth = self.depth + 1
            self.option_parts = []
            self.option_fallback = unquote(attributes.get("dit", ""))

        if not is_void:
            self.depth += 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in self._void_tags:
            return

        if self.option_capture_depth == self.depth:
            option = _clean_wjx_text("".join(self.option_parts))
            if not option:
                option = _clean_wjx_text(self.option_fallback)
            if option and self.current is not None:
                self.current["options"].append(option)
            self.option_capture_depth = None
            self.option_parts = []
            self.option_fallback = ""

        if self.question_capture_depth == self.depth:
            if self.current is not None:
                self.current["question_parts"] = list(self.question_parts)
            self.question_capture_depth = None
            self.question_parts = []

        if self.title_depth == self.depth:
            self.title_depth = None

        if self.field_depth == self.depth and self.current is not None:
            self.fields.append(self.current)
            self.current = None
            self.field_depth = None

        self.depth -= 1

    def handle_data(self, data: str) -> None:
        if self.title_depth is not None and self.depth >= self.title_depth:
            self.title_parts.append(data)
        if (
            self.question_capture_depth is not None
            and self.depth >= self.question_capture_depth
        ):
            self.question_parts.append(data)
        if self.option_capture_depth is not None and self.depth >= self.option_capture_depth:
            self.option_parts.append(data)

    @property
    def title(self) -> str:
        return _clean_wjx_text("".join(self.title_parts))


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


def parse_wjx_url(url: str) -> tuple[str, list[SurveyQuestion]]:
    """读取问卷星公开链接，并转换为统一的原始题目结构。"""

    normalized_url = _validate_wjx_url(url)
    try:
        response = requests.get(
            normalized_url,
            headers={
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/140.0 Safari/537.36"
                ),
            },
            timeout=20,
            allow_redirects=True,
        )
        response.raise_for_status()
    except requests.Timeout as exc:
        raise ValueError("问卷星页面请求超时，请稍后重试。") from exc
    except requests.RequestException as exc:
        raise ValueError(f"问卷星页面请求失败：{exc}") from exc

    final_url = str(response.url or normalized_url)
    _validate_wjx_url(final_url)
    if "checkstatus.aspx" in final_url.lower():
        raise ValueError(
            "问卷星返回了校验或不可用页面，可能已停止收集、需要登录或限制访问。"
            "请确认链接可以直接公开填写，或改用问卷星导出的文件。"
        )
    if len(response.content) > 8 * 1024 * 1024:
        raise ValueError("问卷星页面超过 8 MB，暂不支持解析。")

    encoding = response.encoding or "utf-8"
    content = response.content.decode(encoding, errors="replace")
    return parse_wjx_html(content, final_url)


def parse_wjx_html(content: str, source_url: str = "") -> tuple[str, list[SurveyQuestion]]:
    """解析问卷星页面 HTML，支持常见单选、多选和填空题。"""

    parser = _WJXQuestionHTMLParser()
    try:
        parser.feed(content)
        parser.close()
    except Exception as exc:
        raise ValueError("问卷星页面结构无法解析。") from exc

    questions: list[SurveyQuestion] = []
    for index, field in enumerate(parser.fields, 1):
        question_text = _clean_wjx_text("".join(field["question_parts"]))
        if not question_text:
            continue
        options = _unique_strings(field["options"])
        question_type = _wjx_question_type(field)
        question_id = str(field.get("question_id") or f"q{index}")
        questions.append(
            SurveyQuestion(
                question_id=question_id,
                text=question_text,
                question_type=question_type,
                options=options if question_type != "text" else [],
                research_tag="",
                required=bool(field.get("required", True)),
            )
        )

    if not questions:
        if _looks_like_wjx_unavailable_page(content):
            raise ValueError(
                "问卷星页面当前不可访问，可能已停止收集、需要校验或仅限特定用户访问。"
                "请确认链接可以公开填写，或改用问卷星导出的文件。"
            )
        suffix = f"（{source_url}）" if source_url else ""
        raise ValueError(f"没有识别到可导入的题目{suffix}。")

    title = parser.title or "问卷星问卷"
    return title, _validate_questions(questions)


def _validate_wjx_url(value: str) -> str:
    """限制链接只能访问问卷星域名，避免把解析接口变成任意地址抓取器。"""

    parsed = urlparse(value.strip())
    hostname = (parsed.hostname or "").lower().rstrip(".")
    if parsed.scheme not in {"http", "https"} or not hostname:
        raise ValueError("请输入有效的问卷星 http(s) 链接。")
    if parsed.username or parsed.password:
        raise ValueError("问卷星链接不能包含账号或密码。")
    if not (hostname == "wjx.cn" or hostname.endswith(".wjx.cn")):
        raise ValueError("目前只支持问卷星域名的链接，例如 v.wjx.cn/vm/xxx.aspx。")
    return parsed.geturl()


def _wjx_question_type(field: dict[str, Any]) -> str:
    """根据问卷星字段中的控件和题型标记判断题型。"""

    input_types = set(field.get("input_types", []))
    if "checkbox" in input_types or field.get("field_type") == "4":
        return "multiple_choice"
    if (
        field.get("has_textarea")
        or input_types.intersection({"text", "number", "email", "tel", "url", "date"})
    ):
        return "text"
    if field.get("field_type") in {"1", "2"} and not field.get("options"):
        return "text"
    return "single_choice"


def _clean_wjx_text(value: str) -> str:
    """清理页面换行和不可见空格，保留题目原始语义。"""

    return re.sub(r"\s+", " ", value.replace("\xa0", " ")).strip()


def _unique_strings(values: list[str]) -> list[str]:
    """按出现顺序去重页面中重复渲染的选项。"""

    return list(dict.fromkeys(value for value in values if value))


def _looks_like_wjx_unavailable_page(content: str) -> bool:
    """识别问卷星的停止、校验等提示页。"""

    lowered = content.lower()
    return any(
        marker in lowered
        for marker in (
            "checkstatus.aspx",
            "问卷已停止",
            "问卷已暂停",
            "问卷不存在",
            "当前问卷",
            "停止收集",
            "停止填写",
            "divinfo",
        )
    )


def build_wrapped_survey(
    questions: list[SurveyQuestion],
    brand_goal: str,
    theme_hint: str,
    llm_service: LLMService | None = None,
) -> WrappedSurvey:
    """调用大模型生成互动包装。"""

    service = llm_service or LLMService()
    if llm_service is None:
        raw = _generate_staged_survey(service, questions, brand_goal, theme_hint)
    else:
        # 测试替身和第三方调用方仍可使用旧的单请求接口。
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
    wrapped = _normalize_wrapped_survey(raw, questions, brand_goal, theme_hint)
    wrapped.source = "llm"
    return wrapped


def _generate_staged_survey(
    service: LLMService,
    questions: list[SurveyQuestion],
    brand_goal: str,
    theme_hint: str,
) -> dict[str, Any]:
    """拆分主题分析和题目生成，降低长 JSON 请求的超时概率。"""

    source_material = [
        {
            "question_id": question.question_id,
            "text": question.text,
            "options": question.options,
            "research_tag": question.research_tag,
        }
        for question in questions
    ]
    blueprint_material = [
        {
            "question_id": question.question_id,
            "research_tag": question.research_tag,
            "text": question.text[:80],
        }
        for question in questions
    ]
    try:
        blueprint = service.generate_json(
            _blueprint_system_prompt(),
            json.dumps(
                {
                    "brand_goal": brand_goal,
                    "theme_hint": theme_hint,
                    "research_material": blueprint_material,
                    "required_output": _blueprint_schema(),
                },
                ensure_ascii=False,
                indent=2,
            ),
        )
    except RuntimeError as exc:
        raise RuntimeError(f"主题分析阶段失败：{exc}") from exc
    dimensions = _normalize_dimensions(blueprint.get("dimensions", []))
    if not dimensions:
        raise ValueError("模型没有生成有效的主题分析维度")

    question_prompt = json.dumps(
        {
            "brand_goal": brand_goal,
            "theme_hint": theme_hint,
            "dimensions": dimensions,
            "research_material": source_material,
            "required_output": _question_schema(),
        },
        ensure_ascii=False,
        indent=2,
    )
    try:
        question_result = service.generate_json(
            _question_system_prompt(),
            question_prompt,
        )
    except RuntimeError as exc:
        raise RuntimeError(f"互动题生成阶段失败：{exc}") from exc

    # 部分模型会忽略题量要求，返回过短结果；补发一次明确的纠偏请求。
    raw_questions = question_result.get("questions", [])
    if not isinstance(raw_questions, list) or len(raw_questions) < MIN_GENERATED_QUESTIONS:
        try:
            question_result = service.generate_json(
                _question_system_prompt()
                + f"上一版题目数量不足。必须重新生成至少 {MIN_GENERATED_QUESTIONS} 道题，"
                "不要复用上一版的题目数量。",
                question_prompt,
            )
        except RuntimeError as exc:
            raise RuntimeError(f"互动题补生成阶段失败：{exc}") from exc

    return {
        "survey_name": blueprint.get("survey_name"),
        "theme": blueprint.get("theme"),
        "tagline": blueprint.get("tagline"),
        "intro": blueprint.get("intro"),
        "disclosure": blueprint.get("disclosure"),
        "analysis_method": blueprint.get("analysis_method"),
        "dimensions": dimensions,
        "result_types": blueprint.get("result_types", []),
        "questions": question_result.get("questions", []),
    }


def wrapped_survey_from_dict(payload: dict[str, Any]) -> WrappedSurvey:
    """从数据库 JSON 恢复包装方案。"""

    dimensions = _normalize_dimensions(payload.get("dimensions", []))
    return WrappedSurvey(
        survey_name=str(payload["survey_name"]),
        theme=str(payload["theme"]),
        tagline=str(payload["tagline"]),
        intro=str(payload["intro"]),
        disclosure=str(payload["disclosure"]),
        result_types=_normalize_result_types(payload.get("result_types", []), dimensions),
        questions=[
            WrappedQuestion(
                question_id=str(item["question_id"]),
                public_text=str(item["public_text"]),
                question_type=str(item["question_type"]),
                options=[str(option) for option in item.get("options", [])],
                research_tag=str(item.get("research_tag", "")),
                source_text=str(item.get("source_text", "")),
                required=bool(item.get("required", True)),
                research_refs=_string_list(item.get("research_refs", [])),
                option_scores=_normalize_option_scores(item.get("option_scores", {})),
                dimension_weights=_normalize_number_map(
                    item.get("dimension_weights", {})
                ),
                rationale=str(item.get("rationale", "")),
            )
            for item in payload.get("questions", [])
        ],
        brand_goal=str(payload.get("brand_goal", "")),
        source=str(payload.get("source", "llm")),
        dimensions=dimensions,
        analysis_method=str(payload.get("analysis_method", "")),
    )


def _system_prompt() -> str:
    return (
        "你是资深互动测评设计师、消费者研究员和心理测量顾问。"
        "你的任务不是把原问卷换几个同义词，而是围绕用户指定的互动主题，"
        "重新设计一份有场景、有选择取舍、有明确区分逻辑的短测评。"
        "导入的原始题目和选项只是研究参考，可以被合并、拆分、舍弃或转化，"
        "生成题目数量不需要与原题一致。"
        "survey_name 和 theme 必须围绕用户提供的 theme_hint 生成，不能改成无关主题；"
        "survey_name 应直接体现 theme_hint，优先使用“主题 + 测评”的清晰标题。"
        "\n\n"
        "通用设计原则："
        "\n1. 主题优先：先定义主题真正要测的行为维度，再写题目。"
        "品牌目标中的价格、渠道、购买偏好等研究字段不能直接冒充人格结论；"
        "它们应作为情境素材或研究映射保留。"
        "\n2. 题目要像真实场景中的选择题，而不是传统量表。优先使用聊天、"
        "约会、购物、旅行、工作协作、突发状况、礼物、冲突、边界和取舍等具体情境，"
        "让不同选项体现不同倾向，避免每道题都明显对应某个维度。"
        f"\n3. 生成一份完整的短测评，必须生成恰好 {MIN_GENERATED_QUESTIONS} 道题，"
        "题目数量由主题复杂度和分析可靠性决定，不需要与导入题目数量一致；"
        "单选为主，可少量多选，避免开放文本题，"
        "因为文本无法稳定评分。每道题 3 至 4 个有画面的选项。"
        "\n4. 如果主题本身是人格、风格或偏好测评，选择与主题匹配的主流研究框架或行业框架，"
        "并在 analysis_method 中说明使用了什么维度以及非临床边界。"
        "例如恋爱主题可以参考爱情风格、亲密关系行为、沟通和边界等框架；"
        "消费主题可以测量探索、价值权衡、品牌信任、冲动和仪式感；"
        "职场主题可以测量协作、决策、反馈和风险偏好。不要把不相关框架硬套到主题上。"
        "\n5. 必须输出可复算的评分规则：每道题的 option_scores 给出每个选项在各维度上的"
        "-1 到 1 分值，dimension_weights 给出题目权重。不能用答案数量取模。"
        "\n6. 结果类型生成 4 个相互区分的画像。每个画像必须提供 personality_reference，"
        "格式为“形容词 + 名词”，例如“谨慎清醒的关系观察者”，不要包含“你是”。"
        "description 必须是一段 180 至 220 字的中文人格解析，重点描写人物性格、"
        "心理活动、行为惯性和关系/场景中的取舍，不要只写一句概括；"
        "strengths 和 watchouts 各 1 至 2 条，advice 不超过 50 字。"
        "结果描述要能结合用户选择解释，不能只写空泛夸赞。"
        "\n7. 通过 research_refs 把真正有研究关联的互动题映射回原题 question_id，"
        "一题可以对应多道原题，也可以没有直接映射。research_tag 只写研究字段，"
        "不要让它主导人格类型。"
        "\n8. 不能伪装成医学诊断、临床心理测试或科学定论，disclosure 必须说明娱乐和研究边界。"
        "\n9. 隐匿结果线索：如果主题要求动物、星座、职业、角色等结果类型，"
        "结果名称可以在提交后揭晓，但 survey_name、theme、tagline、intro、题面和选项中"
        "不得提前出现具体结果名称、结果类别、emoji、动物名、动物叫声或“像某某”之类提示。"
        "特别是动物主题，选项只能写人的真实行为、决策、优先级和反应，"
        "禁止写“像猎豹一样”“狐狸型”“安静的猫”等比喻。"
        "\n10. 降低可猜测性：每道题的选项都要有合理性和吸引力，长度、语气和价值判断尽量平衡；"
        "不要把“立即行动/完全不行动”“冲动/理性”这种极端标签直接摆在对立两端。"
        "\n\n只输出合法 JSON，不要 Markdown，不要解释 JSON 之外的内容。"
    )


def _blueprint_system_prompt() -> str:
    return (
        "你是专业的主题测评策划师。请先为用户指定主题建立一个通用、非临床的分析蓝图，"
        "不要复述原始问卷。根据主题选择 3 至 5 个真正相关的行为维度，并生成 4 个互相区分的结果画像。"
        "survey_name 和 theme 必须与 theme_hint 保持一致，survey_name 应直接使用 theme_hint 作为标题核心。"
        "原始题目只作为市场研究参考。只输出合法 JSON。"
        "dimensions 的每个字段保持简短；result_types 必须恰好 4 个，且每个都必须有"
        "覆盖全部 dimension key 的 dimension_profile，取值 -1 到 1；4 个画像的维度坐标"
        "要明显拉开，不能集中在同一个象限。每个画像必须提供 personality_reference，"
        "格式为“形容词 + 名词”，例如“谨慎清醒的关系观察者”，不要包含“你是”。"
        "description 必须是一段 180 至 220 字的中文人格解析，重点描写人物性格、"
        "心理活动、行为惯性和具体情境中的取舍；strengths 和 watchouts 各 1 至 2 条，"
        "advice 不超过 50 字。"
        "如果结果是动物、星座、职业或角色，具体结果名称只保留在 result_types 中，"
        "不要放进 survey_name、theme、tagline、intro 或 analysis_method；"
        "用户应当在答题时无法直接猜出结果类别。"
        "不要使用“你最像什么”“测测你是哪一类”这类直接暴露结果形式的标题。"
    )


def _question_system_prompt() -> str:
    return (
        "你是专业的互动测评题目设计师。围绕给定主题和分析维度，生成恰好 12 道有画面的场景选择题。"
        "12 道题是最低要求，不得只生成 6 至 8 道；每个分析维度至少由 2 道题交叉测量。"
        "题目应体现选择取舍，不能只是改写原题；单选为主，可少量多选，每题 3 至 4 个选项。"
        "原始题目只用于研究参考，互动题可以合并、转化或不映射。"
        "每个选项都必须有 -1 到 1 的维度评分，确保后端可以复算结果；rationale 不超过 40 字。"
        "题面和选项必须只描述人的行为、选择和反应，不得出现任何结果标签或暗示。"
        "禁止出现动物名、动物叫声、动物 emoji、“像某某”“某某型”等表达；"
        "不要使用“哪种人格”“你是哪一类”“你属于什么类型”“你的性格是”等"
        "直接暴露测量意图的问法。"
        "各选项要同样自然、没有明显正确答案，避免一眼看出哪个选项对应哪个维度。"
        "只输出合法 JSON，不要 Markdown。"
    )


def _output_schema() -> dict[str, Any]:
    return {
        "survey_name": "测评名称",
        "theme": "主题名称",
        "tagline": "一句吸引人的副标题",
        "intro": "测评介绍",
        "disclosure": "透明告知文案",
        "analysis_method": "本主题采用的分析框架、维度和解释边界",
        "dimensions": [
            {
                "key": "唯一英文键",
                "name": "维度名称",
                "description": "这个维度测量什么",
                "high_pole": "高分表现",
                "low_pole": "低分表现",
            }
        ],
        "question_count": MIN_GENERATED_QUESTIONS,
        "result_types": [
            {
                "name": "类型名称",
                "personality_reference": "形容词 + 名词，例如谨慎清醒的关系观察者",
                "description": "180 至 220 字的人格解析长文本",
                "dimension_profile": {"dimension_key": 0.8},
                "strengths": ["优势"],
                "watchouts": ["可能的盲点"],
                "advice": "具体建议",
            }
        ],
        "questions": [
            {
                "question_id": "互动题 ID，例如 iq1",
                "public_text": "场景化、轻松、有画面的题面",
                "question_type": "single_choice/multiple_choice/scale",
                "options": ["选项"],
                "research_refs": ["原题目 ID，可为空"],
                "research_tag": "关联的研究标签，可为空",
                "source_text": "关联原题摘要，没有直接关联时为空",
                "rationale": "为什么这道题能区分主题维度，不超过 40 字",
                "dimension_weights": {"dimension_key": 1.0},
                "option_scores": {
                    "选项": {"dimension_key": 0.8},
                },
            }
        ],
    }


def _blueprint_schema() -> dict[str, Any]:
    return {
        "survey_name": "测评名称",
        "theme": "主题名称",
        "tagline": "一句吸引人的副标题",
        "intro": "测评介绍",
        "disclosure": "娱乐和研究边界告知",
        "analysis_method": "本主题采用的分析框架和解释边界",
        "dimensions": [
            {
                "key": "唯一英文键",
                "name": "维度名称",
                "description": "维度含义",
                "high_pole": "高分表现",
                "low_pole": "低分表现",
            }
        ],
        "result_types": [
            {
                "name": "结果类型",
                "personality_reference": "形容词 + 名词，例如谨慎清醒的关系观察者",
                "description": "180 至 220 字的人格解析长文本",
                "dimension_profile": {"dimension_key": 0.8},
                "strengths": ["优势"],
                "watchouts": ["盲点"],
                "advice": "建议",
            }
        ],
    }


def _question_schema() -> dict[str, Any]:
    return {
        "question_count": MIN_GENERATED_QUESTIONS,
        "questions": [
            {
                "question_id": "互动题 ID，例如 iq1",
                "public_text": "场景化题面",
                "question_type": "single_choice/multiple_choice",
                "options": ["选项"],
                "research_refs": ["原题目 ID，可为空"],
                "research_tag": "关联研究标签，可为空",
                "source_text": "关联原题摘要，可为空",
                "rationale": "区分维度的理由",
                "dimension_weights": {"dimension_key": 1.0},
                "option_scores": {"选项": {"dimension_key": 0.8}},
            }
        ]
    }


def _normalize_wrapped_survey(
    raw: dict[str, Any],
    originals: list[SurveyQuestion],
    brand_goal: str,
    theme_hint: str,
) -> WrappedSurvey:
    original_map = {question.question_id: question for question in originals}
    dimensions = _normalize_dimensions(raw.get("dimensions", []))

    # 没有新评分协议时兼容历史数据；新生成的问卷走主题驱动的互动题流程。
    if not dimensions:
        return _normalize_legacy_wrapped_survey(raw, originals, brand_goal, theme_hint)

    wrapped_questions: list[WrappedQuestion] = []
    used_ids: set[str] = set()
    for index, raw_question in enumerate(raw.get("questions", []), 1):
        if not isinstance(raw_question, dict):
            continue
        public_text = str(raw_question.get("public_text") or "").strip()
        if not public_text:
            continue
        question_id = str(raw_question.get("question_id") or f"iq{index}").strip()
        if not question_id or question_id in used_ids:
            question_id = f"iq{index}"
        used_ids.add(question_id)

        refs = [
            ref
            for ref in _string_list(raw_question.get("research_refs", []))
            if ref in original_map
        ]
        source_questions = [original_map[ref] for ref in refs]
        source_text = str(raw_question.get("source_text") or "").strip()
        if not source_text and source_questions:
            source_text = "；".join(question.text for question in source_questions)

        raw_tag = raw_question.get("research_tag", "")
        tags = _string_list(raw_tag)
        if not tags:
            tags = [
                question.research_tag
                for question in source_questions
                if question.research_tag
            ]

        options = _normalize_options(raw_question.get("options", []))
        raw_scores = _normalize_option_scores(
            raw_question.get("option_scores", raw_question.get("scores", {}))
        )
        option_scores = {option: raw_scores.get(option, {}) for option in options}

        wrapped_questions.append(
            WrappedQuestion(
                question_id=question_id,
                public_text=public_text,
                question_type=_normalize_type(
                    str(raw_question.get("question_type") or "single_choice")
                ),
                options=options,
                research_tag="、".join(dict.fromkeys(tags)),
                source_text=source_text,
                required=_parse_bool(raw_question.get("required", True)),
                research_refs=refs,
                option_scores=option_scores,
                dimension_weights=_normalize_number_map(
                    raw_question.get("dimension_weights", {})
                ),
                rationale=str(raw_question.get("rationale", "")),
            )
        )

    if len(wrapped_questions) < MIN_GENERATED_QUESTIONS:
        raise ValueError(
            f"模型生成的互动题目不足 {MIN_GENERATED_QUESTIONS} 道，"
            "请重试生成，以保证人格维度有足够的交叉题目。"
        )
    result_types = _normalize_result_types(raw.get("result_types", []), dimensions)
    if len(result_types) < 4:
        raise ValueError("模型生成的结果画像不足 4 个，请重试生成以保证结果区分度。")

    return WrappedSurvey(
        survey_name=_build_survey_title(theme_hint),
        theme=_clean_theme_hint(theme_hint),
        tagline=str(raw.get("tagline") or "花一分钟，看看你是哪一型"),
        intro=str(raw.get("intro") or "根据你的选择生成一个轻量趣味结果。"),
        disclosure=str(
            raw.get("disclosure")
            or "本测评仅供娱乐，部分题目用于市场研究，结果不构成心理或医学判断。"
        ),
        result_types=result_types,
        questions=wrapped_questions,
        brand_goal=brand_goal,
        source="llm",
        dimensions=dimensions,
        analysis_method=str(
            raw.get("analysis_method")
            or "根据多个主题行为维度综合计算，结果仅供娱乐和研究参考。"
        ),
    )


def _normalize_legacy_wrapped_survey(
    raw: dict[str, Any],
    originals: list[SurveyQuestion],
    brand_goal: str,
    theme_hint: str,
) -> WrappedSurvey:
    """兼容 v1 数据，避免历史问卷因新增评分字段无法读取。"""

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
                question_type=original.question_type,
                options=original.options
                or [str(item) for item in raw_question.get("options", [])],
                research_tag=original.research_tag,
                source_text=original.text,
                required=original.required,
                research_refs=[original.question_id],
            )
        )
    return WrappedSurvey(
        survey_name=_build_survey_title(theme_hint),
        theme=_clean_theme_hint(theme_hint),
        tagline=str(raw.get("tagline") or "花一分钟，看看你是哪一型"),
        intro=str(raw.get("intro") or "根据你的选择生成一个轻量趣味结果。"),
        disclosure=str(
            raw.get("disclosure")
            or "本测评仅供娱乐，部分题目用于市场研究，结果不构成心理或医学判断。"
        ),
        result_types=_normalize_result_types(raw.get("result_types", []))
        or [{"name": "探索型", "description": "你愿意尝试新鲜事物。"}],
        questions=wrapped_questions,
        brand_goal=brand_goal,
        source="llm",
        analysis_method="历史版本按结果类型兼容计算，建议重新生成以启用主题人格分析。",
    )


def _clean_theme_hint(theme_hint: str) -> str:
    """清理主题输入，作为标题和主题展示的统一来源。"""

    return " ".join(theme_hint.split()).strip("。.!！?？")


def _build_survey_title(theme_hint: str) -> str:
    """用用户主题生成稳定标题，避免模型标题偏离包装方向。"""

    theme = _clean_theme_hint(theme_hint)
    if not theme:
        return "趣味测评"
    if theme.endswith(("测评", "问卷", "测试")):
        return theme
    return f"{theme}测评"


def _string_list(value: Any) -> list[str]:
    """把模型可能返回的字符串或数组统一为非空字符串数组。"""

    if isinstance(value, str):
        return [item.strip() for item in value.replace("；", ",").split(",") if item.strip()]
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    return []


def _normalize_number_map(value: Any) -> dict[str, float]:
    """过滤评分字段，避免模型输出非数字破坏本地计算。"""

    if not isinstance(value, dict):
        return {}
    normalized: dict[str, float] = {}
    for key, item in value.items():
        try:
            normalized[str(key)] = max(-1.0, min(1.0, float(item)))
        except (TypeError, ValueError):
            continue
    return normalized


def _normalize_option_scores(value: Any) -> dict[str, dict[str, float]]:
    """统一选项到维度评分映射。"""

    if not isinstance(value, dict):
        return {}
    return {
        str(option): _normalize_number_map(scores)
        for option, scores in value.items()
        if isinstance(scores, dict)
    }


def _normalize_dimensions(value: Any) -> list[dict[str, Any]]:
    """保留主题维度的解释信息，并为缺失字段提供稳定默认值。"""

    if not isinstance(value, list):
        return []
    dimensions: list[dict[str, Any]] = []
    used_keys: set[str] = set()
    for index, item in enumerate(value, 1):
        if not isinstance(item, dict):
            continue
        key = str(item.get("key") or f"dimension_{index}").strip()
        if not key or key in used_keys:
            key = f"dimension_{index}"
        used_keys.add(key)
        dimensions.append(
            {
                "key": key,
                "name": str(item.get("name") or key),
                "description": str(item.get("description") or ""),
                "high_pole": str(item.get("high_pole") or "更高"),
                "low_pole": str(item.get("low_pole") or "更低"),
            }
        )
    return dimensions


def _normalize_result_types(
    value: Any,
    dimensions: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """统一结果类型结构，并保证新问卷每个人格都有可区分的维度坐标。"""

    if not isinstance(value, list):
        return []
    result_types: list[dict[str, Any]] = []
    dimension_keys = [
        str(item.get("key"))
        for item in dimensions or []
        if item.get("key")
    ]
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            continue
        profile = _normalize_number_map(item.get("dimension_profile", {}))
        if dimension_keys:
            fallback_profile = _fallback_dimension_profile(
                index, max(len(value), 1), dimension_keys
            )
            profile = {
                key: profile.get(key, fallback_profile[key])
                for key in dimension_keys
            }
        result_types.append(
            {
                "name": str(item.get("name") or "探索型"),
                "personality_reference": str(
                    item.get("personality_reference")
                    or item.get("reference")
                    or item.get("summary_reference")
                    or ""
                ),
                "description": str(item.get("description") or ""),
                "dimension_profile": profile,
                "strengths": _string_list(item.get("strengths", [])),
                "watchouts": _string_list(item.get("watchouts", [])),
                "advice": str(item.get("advice") or ""),
            }
        )
    if dimension_keys and not _result_profiles_are_distinct(
        result_types, dimension_keys
    ):
        for index, item in enumerate(result_types):
            item["dimension_profile"] = _fallback_dimension_profile(
                index, max(len(result_types), 1), dimension_keys
            )
    return result_types


def _result_profiles_are_distinct(
    result_types: list[dict[str, Any]],
    dimension_keys: list[str],
) -> bool:
    """检查人格画像坐标是否真的拉开，避免所有类型挤在同一位置。"""

    if len(result_types) < 2:
        return False
    profiles = [
        {
            key: _number(item.get("dimension_profile", {}).get(key, 0.0))
            for key in dimension_keys
        }
        for item in result_types
    ]
    rounded_profiles = {
        tuple(round(profile[key], 2) for key in dimension_keys)
        for profile in profiles
    }
    if len(rounded_profiles) < len(profiles):
        return False
    distances = [
        sum(
            (left[key] - right[key]) ** 2
            for key in dimension_keys
        )
        for left_index, left in enumerate(profiles)
        for right in profiles[left_index + 1 :]
    ]
    return bool(distances) and min(distances) >= 0.25


def _number(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _fallback_dimension_profile(
    index: int,
    total: int,
    dimension_keys: list[str],
) -> dict[str, float]:
    """为缺失画像坐标的人格生成分散的默认坐标，避免所有答案都命中同一类型。"""

    if not dimension_keys:
        return {}
    if len(dimension_keys) == 1:
        if total <= 1:
            values = [0.0]
        else:
            values = [
                -0.85 + 1.7 * position / (total - 1)
                for position in range(total)
            ]
        return {dimension_keys[0]: round(values[index], 3)}

    angle = 2 * math.pi * index / max(total, 1)
    if len(dimension_keys) == 2:
        return {
            dimension_keys[0]: round(0.85 * math.cos(angle), 3),
            dimension_keys[1]: round(0.85 * math.sin(angle), 3),
        }
    return {
        key: round(0.85 * math.cos(angle + 2 * math.pi * offset / len(dimension_keys)), 3)
        for offset, key in enumerate(dimension_keys)
    }


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
