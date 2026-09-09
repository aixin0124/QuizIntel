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
    """生成当前包装方案和答卷概况的 PDF。"""

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
    story = [
        Paragraph(f"{escape(survey.survey_name)}｜调研报告", title),
        Paragraph(f"包装主题：{escape(survey.theme)}", body),
        Paragraph(f"有效答卷数：{summary.get('response_count', 0)}", body),
        Spacer(1, 8),
    ]
    rows = [["题目", "研究标签", "选项分布"]]
    for question in survey.questions:
        counts = summary.get("option_counts", {}).get(question.question_id, {})
        distribution = "；".join(f"{key}:{value}" for key, value in counts.items()) or "暂无"
        rows.append(
            [
                Paragraph(escape(question.public_text), body),
                Paragraph(escape(question.research_tag or "-"), body),
                Paragraph(escape(distribution), body),
            ]
        )
    table = Table(rows, colWidths=[86 * mm, 28 * mm, 55 * mm])
    table.setStyle(
        TableStyle(
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
