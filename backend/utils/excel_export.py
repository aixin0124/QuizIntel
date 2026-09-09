"""生成不依赖第三方 Java 运行时的 XLSX 调研明细报表。"""

from __future__ import annotations

from io import BytesIO
from zipfile import ZIP_DEFLATED, ZipFile
from xml.sax.saxutils import escape

from ..models import WrappedSurvey


def build_research_xlsx(
    survey: WrappedSurvey, response_rows: list[dict]
) -> bytes:
    """生成 Excel 可直接打开的工作簿，包含题目映射和答卷明细两个工作表。"""

    mapping_rows = [["题目编号", "原始题目", "互动题目", "题型", "研究标签"]]
    for question in survey.questions:
        mapping_rows.append(
            [
                question.question_id,
                question.source_text,
                question.public_text,
                question.question_type,
                question.research_tag or "-",
            ]
        )

    answer_rows = [["答卷编号", "提交时间", "结果类型"]]
    answer_rows[0].extend(question.research_tag or question.question_id for question in survey.questions)
    for row in response_rows:
        values = [row["id"], row["created_at"], row["result_type"]]
        values.extend(
            _display_value(row["answers"].get(question.question_id))
            for question in survey.questions
        )
        answer_rows.append(values)

    buffer = BytesIO()
    with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
        files = {
            "[Content_Types].xml": _content_types(),
            "_rels/.rels": _root_relationships(),
            "xl/workbook.xml": _workbook(),
            "xl/_rels/workbook.xml.rels": _workbook_relationships(),
            "xl/styles.xml": _styles(),
            "xl/worksheets/sheet1.xml": _worksheet(mapping_rows),
            "xl/worksheets/sheet2.xml": _worksheet(answer_rows),
        }
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()


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
        "<sheetData>" + "".join(row_xml) + "</sheetData></worksheet>"
    )


def _column_name(number: int) -> str:
    name = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name


def _content_types() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        '<Override PartName="/xl/worksheets/sheet2.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
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


def _workbook() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        '<sheets><sheet name="题目映射" sheetId="1" r:id="rId1"/><sheet name="答卷明细" sheetId="2" r:id="rId2"/></sheets>'
        "</workbook>"
    )


def _workbook_relationships() -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet2.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>'
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
