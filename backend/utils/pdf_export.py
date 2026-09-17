"""调研报告 PDF 导出。"""

from __future__ import annotations

from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFError, TTFont
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from ..models import WrappedSurvey


def build_research_pdf(survey: WrappedSurvey, summary: dict) -> bytes:
    """生成包含完整分析、准确统计和题目明细的 PDF。"""

    buffer = BytesIO()
    document = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=16 * mm,
        leftMargin=16 * mm,
        topMargin=14 * mm,
        bottomMargin=14 * mm,
    )
    font_name = _register_chinese_font()
    styles = getSampleStyleSheet()
    title = ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontName=font_name,
        fontSize=18,
        leading=24,
    )
    body = ParagraphStyle(
        "ReportBody",
        parent=styles["BodyText"],
        fontName=font_name,
        fontSize=9,
        leading=14,
    )
    section = ParagraphStyle(
        "ReportSection",
        parent=body,
        fontSize=12,
        leading=17,
        spaceBefore=10,
        spaceAfter=5,
    )
    subsection = ParagraphStyle(
        "ReportSubsection",
        parent=body,
        fontSize=10,
        leading=15,
        spaceBefore=7,
        spaceAfter=3,
    )
    small = ParagraphStyle(
        "ReportSmall",
        parent=body,
        fontSize=8,
        leading=11,
    )
    story = [
        Paragraph(f"{escape(survey.survey_name)}｜调研报告", title),
        Paragraph(f"调研目标：{escape(survey.brand_goal or survey.theme)}", body),
        Paragraph(f"包装主题：{escape(survey.theme)}", body),
        Paragraph(f"有效答卷数：{summary.get('response_count', 0)}", body),
        Spacer(1, 8),
    ]
    analysis = summary.get("analysis") or {}

    story.append(Paragraph("一、报告概览", section))
    overview_rows = [
        ["字段", "内容"],
        ["调研目标", analysis.get("research_goal") or survey.brand_goal or survey.theme],
        ["包装主题", analysis.get("theme") or survey.theme],
        ["分析方法", analysis.get("analysis_method") or survey.analysis_method or "-"],
        ["生成时间", analysis.get("generated_at") or "-"],
    ]
    overview_table = Table(
        _paragraph_rows(overview_rows, small),
        colWidths=[30 * mm, 139 * mm],
        repeatRows=1,
    )
    overview_table.setStyle(_table_style(font_name))
    story.extend([overview_table, Spacer(1, 7)])

    if analysis:
        story.extend(
            [
                Paragraph("二、调研结论", section),
                Paragraph(
                    escape(str(analysis.get("research_conclusion") or "")),
                    body,
                ),
                Paragraph("总结小结", section),
                Paragraph(escape(str(analysis.get("long_summary") or "")), body),
            ]
        )
        findings = analysis.get("key_findings") or []
        if findings:
            story.append(Paragraph("关键发现", section))
            story.extend(
                Paragraph(f"{index}. {escape(str(item))}", body)
                for index, item in enumerate(findings, 1)
            )

    result_types = analysis.get("result_types") or summary.get("result_types") or []
    if result_types or summary.get("result_counts"):
        story.append(Paragraph("三、结果画像分布", section))
        result_rows = [["结果类型", "人数", "比例", "人格参考", "画像说明"]]
        if result_types:
            for item in result_types:
                result_rows.append(
                    [
                        item.get("name", ""),
                        item.get("count", 0),
                        f"{item.get('percentage', 0)}%",
                        item.get("personality_reference") or item.get("reference", ""),
                        item.get("description", ""),
                    ]
                )
        else:
            total = summary.get("response_count", 0)
            for name, count in summary.get("result_counts", {}).items():
                percentage = round(count / total * 100, 1) if total else 0
                result_rows.append([name, count, f"{percentage}%", "", ""])
        result_table = Table(
            _paragraph_rows(result_rows, small),
            colWidths=[29 * mm, 16 * mm, 17 * mm, 29 * mm, 78 * mm],
            repeatRows=1,
        )
        result_table.setStyle(_table_style(font_name))
        story.extend([result_table, Spacer(1, 7)])

        if result_types:
            story.append(Paragraph("画像详情", subsection))
            detail_rows = [["结果类型", "维度画像", "优势", "风险提醒", "建议"]]
            for item in result_types:
                detail_rows.append(
                    [
                        item.get("name", ""),
                        _format_mapping(item.get("dimension_profile", {})),
                        _join_values(item.get("strengths", [])),
                        _join_values(item.get("watchouts", [])),
                        item.get("advice", ""),
                    ]
                )
            detail_table = Table(
                _paragraph_rows(detail_rows, small),
                colWidths=[25 * mm, 35 * mm, 37 * mm, 37 * mm, 35 * mm],
                repeatRows=1,
            )
            detail_table.setStyle(_table_style(font_name))
            story.extend([detail_table, Spacer(1, 7)])

        dimensions = analysis.get("dimensions") or []
        if dimensions:
            story.append(Paragraph("四、按映射维度拆分分析", section))
            dimension_rows = [["分析维度", "定义与方向", "指数/均分", "样本计数", "映射", "维度结论"]]
            for dimension in dimensions:
                index = dimension.get("index")
                dimension_rows.append(
                    [
                        _format_lines(
                            [
                                f"名称：{dimension.get('name') or ''}",
                                f"键：{dimension.get('key') or '-'}",
                            ]
                        ),
                        _format_lines(
                            [
                                f"说明：{dimension.get('description') or '-'}",
                                f"高分：{dimension.get('high_pole') or '-'}",
                                f"低分：{dimension.get('low_pole') or '-'}",
                            ]
                        ),
                        _format_lines(
                            [
                                f"指数：{_value_or_dash(index)}",
                                f"均分：{_value_or_dash(dimension.get('score'))}",
                            ]
                        ),
                        _format_lines(
                            [
                                f"覆盖：{dimension.get('coverage_count', 0)} / {summary.get('response_count', 0)}",
                                f"正向：{_value_or_dash(dimension.get('positive_count'))}",
                                f"中性：{_value_or_dash(dimension.get('neutral_count'))}",
                                f"负向：{_value_or_dash(dimension.get('negative_count'))}",
                            ]
                        ),
                        _format_lines(
                            [
                                f"标签：{_join_values(dimension.get('mapped_research_tags', [])) or '-'}",
                                f"题目：{_join_values(dimension.get('mapped_question_ids', [])) or '-'}",
                            ]
                        ),
                        str(dimension.get("conclusion") or ""),
                    ]
                )
            dimension_table = Table(
                _paragraph_rows(dimension_rows, small),
                colWidths=[22 * mm, 34 * mm, 22 * mm, 26 * mm, 32 * mm, 33 * mm],
                repeatRows=1,
            )
            dimension_table.setStyle(_table_style(font_name))
            story.extend([dimension_table, Spacer(1, 7)])

        limitations = str(analysis.get("limitations") or "").strip()
        if limitations:
            story.extend(
                [
                    Paragraph("分析边界", section),
                    Paragraph(escape(limitations), body),
                ]
            )

    story.append(Paragraph("五、题目映射与准确数据", section))
    question_map = {question.question_id: question for question in survey.questions}
    questions = analysis.get("questions") or summary.get("question_stats") or []
    if not questions:
        questions = [_fallback_question_stats(question, summary) for question in survey.questions]

    for question_stats in questions:
        question_id = str(question_stats.get("question_id") or "")
        question = question_map.get(question_id)
        title_text = (
            f"{question_id}｜{question_stats.get('research_tag') or (question.research_tag if question else '研究字段')}"
        )
        story.append(Paragraph(escape(title_text), subsection))
        if question:
            story.append(Paragraph(f"互动题目：{escape(question.public_text)}", body))
            if question.source_text:
                story.append(Paragraph(f"原始题目：{escape(question.source_text)}", body))
        elif question_stats.get("question"):
            story.append(Paragraph(f"题目：{escape(str(question_stats.get('question')))}", body))

        meta_parts = [
            f"题型：{question_stats.get('question_type') or (question.question_type if question else '-')}",
            f"覆盖：{question_stats.get('answered_count', 0)} 份答卷",
            f"答题率：{question_stats.get('answer_rate', 0)}%",
        ]
        dimension_keys = question_stats.get("dimension_keys") or []
        if dimension_keys:
            meta_parts.append(f"维度：{'、'.join(dimension_keys)}")
        research_refs = question_stats.get("research_refs") or []
        if research_refs:
            meta_parts.append(f"研究参考：{'、'.join(research_refs)}")
        story.append(Paragraph(escape("；".join(meta_parts)), small))

        option_rows = [["选项", "人数", "比例"]]
        for option in question_stats.get("options", []):
            option_rows.append(
                [
                    option.get("option", ""),
                    option.get("count", 0),
                    f"{option.get('percentage', 0)}%",
                ]
            )
        option_table = Table(
            _paragraph_rows(option_rows, small),
            colWidths=[119 * mm, 20 * mm, 30 * mm],
            repeatRows=1,
        )
        option_table.setStyle(_table_style(font_name))
        story.extend([option_table, Spacer(1, 5)])

    document.build(story)
    return buffer.getvalue()


def _paragraph_rows(rows: list[list[object]], style: ParagraphStyle) -> list[list[Paragraph]]:
    """把表格文本统一转为可自动换行的段落。"""

    return [
        [Paragraph(_paragraph_text(value), style) for value in row]
        for row in rows
    ]


def _fallback_question_stats(question: object, summary: dict) -> dict:
    """兼容没有最终分析时的实时统计。"""

    counts = summary.get("option_counts", {}).get(question.question_id, {})
    question_stats = next(
        (
            item
            for item in summary.get("question_stats", [])
            if item.get("question_id") == question.question_id
        ),
        {},
    )
    return question_stats or {
        "question_id": question.question_id,
        "question": question.public_text,
        "research_tag": question.research_tag,
        "question_type": question.question_type,
        "answered_count": 0,
        "answer_rate": 0,
        "options": [
            {"option": key, "count": value, "percentage": _find_percentage(question_stats, key)}
            for key, value in counts.items()
        ],
        "dimension_keys": [],
        "research_refs": [],
    }


def _table_style(font_name: str) -> TableStyle:
    """统一报告表格样式。"""

    return TableStyle(
        [
            ("FONTNAME", (0, 0), (-1, -1), font_name),
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#E8EEF7")),
            ("GRID", (0, 0), (-1, -1), 0.3, colors.HexColor("#A8B2C2")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
        ]
    )


def _find_percentage(question_stats: dict, option: str) -> str:
    """从后端准确统计中读取选项百分比。"""

    for item in question_stats.get("options", []):
        if item.get("option") == option:
            return str(item.get("percentage", 0))
    return "0"


def _paragraph_text(value: object) -> str:
    """保留表格单元格内的多行信息。"""

    return escape(str(value)).replace("\n", "<br/>")


def _format_lines(values: list[object]) -> str:
    return "\n".join(str(item) for item in values if str(item).strip())


def _join_values(value: object) -> str:
    if isinstance(value, list):
        return "、".join(str(item) for item in value if str(item).strip())
    if isinstance(value, tuple):
        return "、".join(str(item) for item in value if str(item).strip())
    return str(value).strip() if value is not None else ""


def _format_mapping(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    return "；".join(f"{key}:{item}" for key, item in value.items())


def _value_or_dash(value: object) -> object:
    return "-" if value is None or value == "" else value


def _register_chinese_font() -> str:
    """优先使用 Windows 常见中文字体。"""

    candidates = [
        ("Microsoft YaHei", r"C:\Windows\Fonts\msyh.ttc"),
        ("SimSun", r"C:\Windows\Fonts\simsun.ttc"),
        ("NotoSansCJK", "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"),
    ]
    for name, path in candidates:
        try:
            pdfmetrics.registerFont(TTFont(name, path))
            return name
        except (OSError, TTFError):
            continue
    return "Helvetica"
