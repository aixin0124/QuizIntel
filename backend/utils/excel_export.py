"""生成不依赖第三方 Java 运行时的 XLSX 调研完整报表。"""

from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape, quoteattr

from ..models import WrappedSurvey


def build_research_xlsx(
    survey: WrappedSurvey,
    response_rows: list[dict],
    summary: dict | None = None,
    analysis: dict | None = None,
) -> bytes:
    """生成 Excel 可直接打开的工作簿，包含分析结论、准确统计和答卷明细。"""

    summary = summary or {}
    analysis = analysis or {}
    sheets = _build_sheets(survey, response_rows, summary, analysis)

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        files = {
            "[Content_Types].xml": _content_types(len(sheets)),
            "_rels/.rels": _root_relationships(),
            "xl/workbook.xml": _workbook([name for name, _rows in sheets]),
            "xl/_rels/workbook.xml.rels": _workbook_relationships(len(sheets)),
            "xl/styles.xml": _styles(),
        }
        for index, (_name, rows) in enumerate(sheets, 1):
            files[f"xl/worksheets/sheet{index}.xml"] = _worksheet(rows)
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


def _build_sheets(
    survey: WrappedSurvey,
    response_rows: list[dict],
    summary: dict,
    analysis: dict,
) -> list[tuple[str, list[list[object]]]]:
    """组织工作簿的多个分析工作表。"""

    research_tags = analysis.get("research_tags") or summary.get("research_tags") or []
    overview_rows = [
        ["字段", "内容"],
        ["问卷名称", survey.survey_name],
        ["调研目标", analysis.get("research_goal") or survey.brand_goal or survey.theme],
        ["包装主题", analysis.get("theme") or survey.theme],
        ["有效答卷数", analysis.get("response_count", summary.get("response_count", 0))],
        ["生成时间", analysis.get("generated_at", "")],
        ["分析方法", analysis.get("analysis_method") or survey.analysis_method],
        ["研究标签", "、".join(research_tags)],
        ["调研结论", analysis.get("research_conclusion", "")],
        ["总结小结", analysis.get("long_summary", "")],
        ["分析边界", analysis.get("limitations", "")],
    ]

    finding_rows = [["序号", "关键发现"]]
    for index, finding in enumerate(analysis.get("key_findings", []) or [], 1):
        finding_rows.append([index, finding])
    if len(finding_rows) == 1:
        finding_rows.append(["", "暂无最终分析，请先结束问卷生成分析。"])

    dimension_rows = [
        [
            "维度键",
            "维度名称",
            "维度说明",
            "高分表现",
            "低分表现",
            "指数",
            "平均分",
            "覆盖答卷",
            "正向人数",
            "中性人数",
            "负向人数",
            "映射研究标签",
            "关联题目",
            "维度结论",
        ]
    ]
    dimensions = analysis.get("dimensions") or summary.get("dimension_stats") or []
    for dimension in dimensions:
        dimension_rows.append(
            [
                dimension.get("key", ""),
                dimension.get("name", ""),
                dimension.get("description", ""),
                dimension.get("high_pole", ""),
                dimension.get("low_pole", ""),
                _empty_if_none(dimension.get("index")),
                _empty_if_none(dimension.get("score")),
                dimension.get("coverage_count", 0),
                _empty_if_none(dimension.get("positive_count")),
                _empty_if_none(dimension.get("neutral_count")),
                _empty_if_none(dimension.get("negative_count")),
                "、".join(dimension.get("mapped_research_tags", []) or []),
                "、".join(dimension.get("mapped_question_ids", []) or []),
                dimension.get("conclusion", ""),
            ]
        )

    question_rows = [
        [
            "题目编号",
            "研究标签",
            "互动题目",
            "原始题目",
            "题型",
            "覆盖答卷",
            "答题率",
            "选项",
            "人数",
            "比例",
            "维度键",
            "研究参考题",
        ]
    ]
    question_map = {question.question_id: question for question in survey.questions}
    questions = analysis.get("questions") or summary.get("question_stats") or []
    for question_stat in questions:
        question = question_map.get(str(question_stat.get("question_id", "")))
        options = question_stat.get("options") or [{"option": "暂无", "count": 0, "percentage": 0}]
        for option in options:
            question_rows.append(
                [
                    question_stat.get("question_id", ""),
                    question_stat.get("research_tag") or (question.research_tag if question else ""),
                    question_stat.get("question") or (question.public_text if question else ""),
                    question.source_text if question else "",
                    question_stat.get("question_type") or (question.question_type if question else ""),
                    question_stat.get("answered_count", 0),
                    question_stat.get("answer_rate", 0),
                    option.get("option", ""),
                    option.get("count", 0),
                    option.get("percentage", 0),
                    "、".join(question_stat.get("dimension_keys", []) or []),
                    "、".join(question_stat.get("research_refs", []) or []),
                ]
            )

    result_rows = [
        [
            "结果类型",
            "人数",
            "比例",
            "人格参考",
            "画像说明",
            "维度画像",
            "优势",
            "风险提醒",
            "建议",
        ]
    ]
    result_types = analysis.get("result_types") or summary.get("result_types") or []
    if result_types:
        for item in result_types:
            result_rows.append(
                [
                    item.get("name", ""),
                    item.get("count", 0),
                    item.get("percentage", 0),
                    item.get("personality_reference") or item.get("reference", ""),
                    item.get("description", ""),
                    _format_mapping(item.get("dimension_profile", {})),
                    "、".join(item.get("strengths", []) or []),
                    "、".join(item.get("watchouts", []) or []),
                    item.get("advice", ""),
                ]
            )
    else:
        for name, count in (summary.get("result_counts") or {}).items():
            result_rows.append([name, count, "", "", "", "", "", "", ""])

    mapping_rows = [
        [
            "题目编号",
            "原始题目",
            "互动题目",
            "题型",
            "研究标签",
            "研究参考题",
            "是否必答",
            "映射理由",
            "维度权重",
            "选项评分映射",
        ]
    ]
    for question in survey.questions:
        mapping_rows.append(
            [
                question.question_id,
                question.source_text,
                question.public_text,
                question.question_type,
                question.research_tag or "-",
                "、".join(question.research_refs),
                question.required,
                question.rationale,
                _format_mapping(question.dimension_weights),
                _format_nested_mapping(question.option_scores),
            ]
        )

    dimension_definitions = {
        str(item.get("key")): item
        for item in survey.dimensions
        if item.get("key")
    }
    response_dimension_keys = set(dimension_definitions)
    for row in response_rows:
        response_dimension_keys.update(
            str(key) for key in (row.get("dimension_scores") or {})
        )
    dimension_keys = sorted(response_dimension_keys)
    answer_rows = [["答卷编号", "提交时间", "结果类型"]]
    answer_rows[0].extend(question.research_tag or question.question_id for question in survey.questions)
    answer_rows[0].extend(f"研究答案：{tag}" for tag in research_tags)
    answer_rows[0].extend(
        f"维度分数：{dimension_definitions.get(key, {}).get('name') or key}"
        for key in dimension_keys
    )
    answer_rows[0].extend(["结果解析", "优势", "可以留意", "建议", "证据"])
    for row in response_rows:
        values = [row["id"], row["created_at"], row["result_type"]]
        values.extend(
            _display_value(row["answers"].get(question.question_id))
            for question in survey.questions
        )
        values.extend(
            _display_value(row.get("research_answers", {}).get(tag))
            for tag in research_tags
        )
        values.extend(
            _empty_if_none((row.get("dimension_scores") or {}).get(key))
            for key in dimension_keys
        )
        response_analysis = row.get("analysis") or {}
        evidence = response_analysis.get("evidence") or []
        evidence_text = "；".join(
            f"{item.get('question', '')}｜{item.get('answer', '')}｜{item.get('reason', '')}"
            for item in evidence
            if isinstance(item, dict)
        )
        values.extend(
            [
                response_analysis.get("summary", ""),
                "、".join(response_analysis.get("strengths", []) or []),
                "、".join(response_analysis.get("watchouts", []) or []),
                response_analysis.get("advice", ""),
                evidence_text,
            ]
        )
        answer_rows.append(values)

    return [
        ("报告概览", overview_rows),
        ("关键发现", finding_rows),
        ("维度分析", dimension_rows),
        ("题目统计", question_rows),
        ("结果画像分布", result_rows),
        ("题目映射", mapping_rows),
        ("答卷明细", answer_rows),
    ]


def _display_value(value: object) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value)
    return "" if value is None else str(value)


def _worksheet(rows: list[list[object]]) -> str:
    row_xml: list[str] = []
    for row_number, row in enumerate(rows, 1):
        cells = []
        for column_number, value in enumerate(row, 1):
            reference = f"{_column_name(column_number)}{row_number}"
            text = escape(str(value))
            cells.append(
                f'<c r="{reference}" t="inlineStr"><is><t>{text}</t></is></c>'
            )
        row_xml.append(f'<row r="{row_number}">' + "".join(cells) + "</row>")
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<sheetViews><sheetView workbookViewId="0"><pane ySplit="1" topLeftCell="A2" activePane="bottomLeft" state="frozen"/></sheetView></sheetViews>'
        "<sheetData>" + "".join(row_xml) + "</sheetData></worksheet>"
    )


def _column_name(number: int) -> str:
    name = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _content_types(sheet_count: int) -> str:
    worksheet_overrides = "".join(
        f'<Override PartName="/xl/worksheets/sheet{index}.xml" '
        'ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        for index in range(1, sheet_count + 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        f"{worksheet_overrides}"
        '<Override PartName="/xl/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"/>'
        "</Types>"
    )


def _root_relationships() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        "</Relationships>"
    )


def _workbook(sheet_names: list[str]) -> str:
    sheets = "".join(
        f'<sheet name={quoteattr(name[:31])} sheetId="{index}" r:id="rId{index}"/>'
        for index, name in enumerate(sheet_names, 1)
    )
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        f"<sheets>{sheets}</sheets>"
        "</workbook>"
    )


def _workbook_relationships(sheet_count: int) -> str:
    worksheet_relationships = "".join(
        f'<Relationship Id="rId{index}" '
        'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" '
        f'Target="worksheets/sheet{index}.xml"/>'
        for index in range(1, sheet_count + 1)
    )
    style_id = sheet_count + 1
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        f"{worksheet_relationships}"
        f'<Relationship Id="rId{style_id}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
        "</Relationships>"
    )


def _styles() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<styleSheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
        '<fonts count="1"><font><sz val="11"/><name val="Microsoft YaHei"/></font></fonts>'
        '<fills count="2"><fill><patternFill patternType="none"/></fill><fill><patternFill patternType="gray125"/></fill></fills>'
        '<borders count="1"><border><left/><right/><top/><bottom/><diagonal/></border></borders>'
        '<cellXfs count="1"><xf numFmtId="0" fontId="0" fillId="0" borderId="0"/></cellXfs>'
        "</styleSheet>"
    )


def _empty_if_none(value: object) -> object:
    return "" if value is None else value


def _format_mapping(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    return "；".join(f"{key}:{item}" for key, item in value.items())


def _format_nested_mapping(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    parts: list[str] = []
    for option, scores in value.items():
        if isinstance(scores, dict):
            parts.append(f"{option} -> {_format_mapping(scores)}")
        else:
            parts.append(f"{option} -> {scores}")
    return "；".join(parts)
