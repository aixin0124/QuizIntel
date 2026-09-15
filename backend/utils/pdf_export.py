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
    """生成包含准确统计和 AI 研究总结的 PDF。"""

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
    if analysis:
        story.extend(
            [
                Paragraph("一、调研结论", section),
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
                Paragraph(f"• {escape(str(item))}", body)
                for item in findings
            )

        dimensions = analysis.get("dimensions") or []
        if dimensions:
            story.append(Paragraph("二、按映射维度拆分分析", section))
            dimension_rows = [["分析维度", "准确指数", "覆盖答卷", "维度结论"]]
            for dimension in dimensions:
                index = dimension.get("index")
                index_text = f"{index}" if index is not None else "按选项分布"
                dimension_rows.append(
                    [
                        Paragraph(escape(str(dimension.get("name") or "")), small),
                        Paragraph(escape(index_text), small),
                        Paragraph(
                            escape(
                                f"{dimension.get('coverage_count', 0)} / "
                                f"{summary.get('response_count', 0)}"
                            ),
                            small,
                        ),
                        Paragraph(
                            escape(str(dimension.get("conclusion") or "")),
                            small,
                        ),
                    ]
                )
            dimension_table = Table(
                dimension_rows,
                colWidths=[31 * mm, 22 * mm, 25 * mm, 91 * mm],
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

    story.append(Paragraph("三、题目映射与准确数据", section))
    rows = [["题目", "研究标签", "选项分布"]]
    for question in survey.questions:
        counts = summary.get("option_counts", {}).get(question.question_id, {})
        question_stats = next(
            (
                item
                for item in summary.get("question_stats", [])
                if item.get("question_id") == question.question_id
            ),
            {},
        )
        distribution = "；".join(
            f"{key}:{value}人（{_find_percentage(question_stats, key)}%）"
            for key, value in counts.items()
        ) or "暂无"
        rows.append(
            [
                Paragraph(escape(question.public_text), body),
                Paragraph(escape(question.research_tag or "-"), body),
                Paragraph(escape(distribution), body),
            ]
        )
    table = Table(rows, colWidths=[86 * mm, 28 * mm, 55 * mm])
    table.setStyle(
        _table_style(font_name)
    )
    story.extend(
        [
            table,
            Spacer(1, 8),
            Paragraph(
                "结果类型分布："
                + escape(
                    "；".join(
                        f"{name}：{count}"
                        for name, count in summary.get("result_counts", {}).items()
                    )
                    or "暂无"
                ),
                body,
            ),
        ]
    )
    document.build(story)
    return buffer.getvalue()


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
