"""FastAPI 后端入口。"""

from __future__ import annotations

import json
import secrets
from typing import Any

from fastapi import FastAPI, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from .config import settings
from .services.analytics_service import (
    build_research_analysis,
    build_response,
    calculate_result_type,
    summarize_responses,
    validate_answers,
)
from .services.survey_service import (
    build_wrapped_survey,
    parse_wjx_url,
    parse_survey_text,
    wrapped_survey_from_dict,
)
from .storage.database import ResearchDatabase
from .utils.pdf_export import build_research_pdf
from .utils.excel_export import build_research_xlsx


app = FastAPI(title="趣测智研 API", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
database = ResearchDatabase(settings.database_path)
admin_tokens: set[str] = set()


class ParseRequest(BaseModel):
    """文本导入问卷请求。"""

    content: str
    file_name: str = "survey.json"


class WJXParseRequest(BaseModel):
    """问卷星链接导入请求。"""

    url: str


class WrapRequest(BaseModel):
    """生成互动包装请求。"""

    questions: list[dict[str, Any]]
    brand_goal: str
    theme_hint: str


class ResponseRequest(BaseModel):
    """提交答卷请求。"""

    survey_id: int
    answers: dict[str, Any]


class AdminLoginRequest(BaseModel):
    """后台登录请求。"""

    password: str


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {
        "status": "ok",
        "llm_configured": settings.has_llm,
        "llm_local": settings.is_local_llm,
        "llm_base_url": settings.llm_base_url,
        "llm_model": settings.llm_model,
        "llm_wire_api": settings.llm_wire_api,
        "llm_reasoning_effort": settings.llm_reasoning_effort,
    }


@app.post("/api/admin/login")
def admin_login(request: AdminLoginRequest) -> dict[str, Any]:
    if not secrets.compare_digest(request.password, settings.admin_password):
        raise HTTPException(status_code=401, detail="后台密码错误。")
    token = secrets.token_urlsafe(32)
    admin_tokens.add(token)
    return {"token": token}


def require_admin(token: str | None) -> None:
    """校验后台临时令牌。"""

    if not token or token not in admin_tokens:
        raise HTTPException(status_code=401, detail="请先登录管理后台。")


@app.post("/api/surveys/parse")
def parse_survey(
    request: ParseRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_admin_token)
    try:
        questions = parse_survey_text(request.content, request.file_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"问卷解析失败：{exc}") from exc
    return {"questions": [question.to_dict() for question in questions]}


@app.post("/api/surveys/parse-wjx")
def parse_wjx_survey(
    request: WJXParseRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """读取问卷星公开转发链接并返回可编辑题目。"""

    require_admin(x_admin_token)
    try:
        title, questions = parse_wjx_url(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"问卷星导入失败：{exc}") from exc
    return {
        "title": title,
        "source_url": request.url.strip(),
        "questions": [question.to_dict() for question in questions],
    }


@app.post("/api/surveys/upload")
async def upload_survey(
    file: UploadFile,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_admin_token)
    raw = await file.read()
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="上传文件不能超过 2 MB。")
    try:
        content = raw.decode("utf-8-sig")
        questions = parse_survey_text(content, file.filename or "survey.csv")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"问卷解析失败：{exc}") from exc
    return {"questions": [question.to_dict() for question in questions]}


@app.post("/api/surveys/wrap")
def wrap_survey(
    request: WrapRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_admin(x_admin_token)
    if not settings.has_llm:
        raise HTTPException(status_code=400, detail="未配置 LLM_API_KEY，不能生成 AI 包装。")
    if not request.brand_goal.strip() or not request.theme_hint.strip():
        raise HTTPException(status_code=422, detail="调研目标和互动主题不能为空。")
    if len(request.questions) > 100:
        raise HTTPException(status_code=413, detail="单次最多包装 100 道题。")
    try:
        questions = parse_survey_text(
            json.dumps(request.questions, ensure_ascii=False),
            "payload.json",
        )
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"问卷数据无效：{exc}") from exc
    if not questions:
        raise HTTPException(status_code=400, detail="没有可包装的问卷题目。")
    try:
        survey = build_wrapped_survey(questions, request.brand_goal, request.theme_hint)
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"大模型调用失败：{exc}") from exc
    survey_id = database.save_survey(survey)
    return {"id": survey_id, "survey": survey.to_dict()}


@app.get("/api/public/surveys")
def list_public_surveys() -> dict[str, Any]:
    """用户端只读取可参与的问卷摘要。"""

    return {"items": database.list_surveys(status="open")}


@app.get("/api/public/surveys/{survey_id}")
def get_public_survey(survey_id: int) -> dict[str, Any]:
    row = database.get_survey(survey_id)
    if not row:
        raise HTTPException(status_code=404, detail="问卷不存在。")
    if row["deleted_at"]:
        raise HTTPException(status_code=404, detail="问卷不存在。")
    if row["status"] != "open":
        raise HTTPException(status_code=410, detail="该问卷已结束，不再接受新的答卷。")
    payload = dict(row["payload"])
    payload.pop("brand_goal", None)
    for question in payload.get("questions", []):
        question.pop("research_tag", None)
        question.pop("source_text", None)
        question.pop("research_refs", None)
        question.pop("option_scores", None)
        question.pop("dimension_weights", None)
        question.pop("rationale", None)
    return {"id": row["id"], "survey": payload}


@app.get("/api/surveys")
def list_surveys(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    return {"items": database.list_surveys()}


@app.get("/api/surveys/trash")
def list_trash_surveys(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    """列出已移入回收站的问卷。"""

    require_admin(x_admin_token)
    return {"items": database.list_surveys(deleted=True)}


@app.get("/api/surveys/{survey_id}")
def get_survey(survey_id: int, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    row = database.get_survey(survey_id)
    if not row:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    return row


@app.delete("/api/surveys/{survey_id}")
def delete_survey(
    survey_id: int,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """将问卷移入回收站。"""

    require_admin(x_admin_token)
    row = database.get_survey(survey_id)
    if not row:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    if row["deleted_at"]:
        return {"item": row, "message": "问卷已在回收站。"}
    deleted = database.move_survey_to_trash(survey_id)
    return {"item": deleted, "message": "问卷已移入回收站。"}


@app.post("/api/surveys/{survey_id}/restore")
def restore_survey(
    survey_id: int,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """从回收站恢复问卷。"""

    require_admin(x_admin_token)
    row = database.get_survey(survey_id)
    if not row:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    restored = database.restore_survey(survey_id)
    return {"item": restored, "message": "问卷已恢复。"}


@app.delete("/api/surveys/{survey_id}/permanent")
def permanently_delete_survey(
    survey_id: int,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """永久删除回收站中的问卷和答卷。"""

    require_admin(x_admin_token)
    if not database.permanently_delete_survey(survey_id):
        raise HTTPException(status_code=404, detail="只能永久删除回收站中的问卷。")
    return {"message": "问卷已永久删除。"}


@app.post("/api/responses")
def submit_response(request: ResponseRequest) -> dict[str, Any]:
    row = database.get_survey(request.survey_id)
    if not row:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    if row["deleted_at"]:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    if row["status"] != "open":
        raise HTTPException(status_code=410, detail="该问卷已结束，不再接受新的答卷。")
    survey = wrapped_survey_from_dict(row["payload"])
    try:
        validate_answers(survey, request.answers)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = calculate_result_type(survey, request.answers)
    response = build_response(
        survey,
        request.answers,
        result["name"],
        result.get("dimension_scores", {}),
        result.get("analysis", {}),
    )
    response_id = database.save_response(response, request.survey_id)
    return {"id": response_id, "response": response.to_dict(), "result": result}


@app.get("/api/analytics/{survey_id}")
def get_analytics(survey_id: int, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    require_admin(x_admin_token)
    row = database.get_survey(survey_id)
    if not row:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    if row["deleted_at"]:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    survey = wrapped_survey_from_dict(row["payload"])
    responses = database.list_responses(survey_id)
    return {
        "status": row["status"],
        "ended_at": row["ended_at"],
        "summary": summarize_responses(survey, responses),
        "analysis": row["analysis"],
        "survey": survey.to_dict(),
    }


@app.post("/api/analytics/{survey_id}/finish")
def finish_analytics(
    survey_id: int,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """结束问卷，生成一次最终研究分析并锁定问卷状态。"""

    require_admin(x_admin_token)
    row = database.get_survey(survey_id)
    if not row:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    if row["deleted_at"]:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    if row["status"] == "ended" and row["analysis"]:
        return {
            "status": row["status"],
            "ended_at": row["ended_at"],
            "analysis": row["analysis"],
        }
    if not settings.has_llm:
        raise HTTPException(status_code=400, detail="未配置 LLM_API_KEY，不能生成 AI 数据分析。")
    survey = wrapped_survey_from_dict(row["payload"])
    responses = database.list_responses(survey_id)
    if not responses:
        raise HTTPException(status_code=422, detail="至少收集 1 份有效答卷后才能开始数据分析。")
    try:
        analysis = build_research_analysis(survey, responses)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 数据分析失败：{exc}") from exc
    finished = database.finish_survey(survey_id, analysis)
    return {
        "status": finished["status"] if finished else "ended",
        "ended_at": finished["ended_at"] if finished else None,
        "analysis": analysis,
    }


@app.get("/api/analytics/{survey_id}/pdf")
def export_pdf(survey_id: int, x_admin_token: str | None = Header(default=None)) -> Response:
    require_admin(x_admin_token)
    row = database.get_survey(survey_id)
    if not row:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    if row["deleted_at"]:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    survey = wrapped_survey_from_dict(row["payload"])
    summary = summarize_responses(survey, database.list_responses(survey_id))
    summary["analysis"] = row["analysis"]
    return Response(
        content=build_research_pdf(survey, summary),
        media_type="application/pdf",
        headers={"Content-Disposition": 'attachment; filename="fun_research_report.pdf"'},
    )


@app.get("/api/analytics/{survey_id}/excel")
def export_excel(survey_id: int, x_admin_token: str | None = Header(default=None)) -> Response:
    """导出题目映射和答卷明细 Excel。"""

    require_admin(x_admin_token)
    row = database.get_survey(survey_id)
    if not row:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    if row["deleted_at"]:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    survey = wrapped_survey_from_dict(row["payload"])
    content = build_research_xlsx(survey, database.list_response_rows(survey_id))
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="fun_research_data.xlsx"'},
    )
