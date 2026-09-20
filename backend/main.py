"""FastAPI 后端入口。"""

from __future__ import annotations

import json
import hashlib
import time
from typing import Any

import requests
from fastapi import FastAPI, Header, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from .config import settings
from .services.analytics_service import (
    build_collection_trend,
    build_research_analysis,
    build_response,
    calculate_result_type,
    summarize_responses,
    validate_answers,
)
from .services.survey_service import (
    build_wrapped_survey,
    parse_wjx_template_url,
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
database = ResearchDatabase(settings.database_url)


class ParseRequest(BaseModel):
    """文本导入问卷请求。"""

    content: str
    file_name: str = "survey.json"


class WJXParseRequest(BaseModel):
    """公开问卷链接导入请求。"""

    url: str


class WJXTemplateRequest(BaseModel):
    """公开模板导入请求。"""

    url: str


class WrapRequest(BaseModel):
    """生成互动包装请求。"""

    questions: list[dict[str, Any]]
    brand_goal: str
    theme_hint: str
    team_id: int | None = None


class PublishSurveyRequest(BaseModel):
    """发布控制请求。"""

    status: str


class RenameSurveyRequest(BaseModel):
    """修改已生成问卷标题请求。"""

    survey_name: str


class UpdateSurveyContentRequest(BaseModel):
    """保存管理员手动编辑后的互动问卷内容。"""

    survey: dict[str, Any]


class ResponseRequest(BaseModel):
    """提交答卷请求。"""

    survey_id: int
    answers: dict[str, Any]
    share_token: str | None = None
    source: str = "public_link"
    duration_seconds: int | None = None
    fingerprint: str | None = None
    browser_id: str | None = None
    access_code: str | None = None
    is_test: bool = False


class AdminLoginRequest(BaseModel):
    """后台登录请求。"""

    username: str = "aixin"
    password: str


class RegisterRequest(BaseModel):
    """个人账号注册请求。"""

    username: str
    password: str
    email: str = ""


class TeamRequest(BaseModel):
    """创建个人问卷组请求。"""

    name: str
    description: str = ""


class TeamInvitationRequest(BaseModel):
    """邀请已注册用户加入问卷组请求。"""

    username: str
    permission: str = "viewer"


class InvitationResponseRequest(BaseModel):
    """处理问卷组邀请请求。"""

    accepted: bool


class SurveyPermissionRequest(BaseModel):
    """调整问卷访问权限请求。"""

    user_id: int
    permission: str | None = None


class TokenRequestPayload(BaseModel):
    """申请 Token 额度请求。"""

    amount: int
    reason: str = ""


class TokenReviewRequest(BaseModel):
    """平台管理员审批 Token 请求。"""

    approved: bool


class ContentReviewRequest(BaseModel):
    """平台管理员审核问卷内容请求。"""

    approved: bool
    note: str = ""


class PlatformSettingRequest(BaseModel):
    """平台全局配置更新请求。"""

    value: str


class PlatformUserStatusRequest(BaseModel):
    """平台管理员启停账号请求。"""

    is_active: bool


class ChangePasswordRequest(BaseModel):
    """管理员修改密码请求。"""

    old_password: str
    new_password: str


class AdminUserRequest(BaseModel):
    """创建后台账号请求。"""

    username: str
    password: str
    role: str = "viewer"


class InvalidResponseRequest(BaseModel):
    """标记无效答卷请求。"""

    invalid: bool = True
    reason: str = ""


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
        "llm_fallback_configured": settings.has_llm_fallback,
        "llm_fallback_base_url": settings.llm_fallback_base_url,
        "llm_fallback_model": settings.llm_fallback_model,
        "database_engine": database.engine,
    }


@app.get("/api/headlines")
def get_headlines() -> Any:
    """代理读取头条接口，避免浏览器跨域限制。"""

    try:
        response = requests.get(
            "https://api.zxki.cn/api/jhrs?type=douyin",
            headers={"Accept": "application/json", "User-Agent": "FunResearch/1.0"},
            timeout=8,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=502, detail=f"头条接口暂时不可用：{exc}") from exc
    try:
        return JSONResponse(
            content=response.json(),
            headers={"Cache-Control": "no-store"},
        )
    except ValueError:
        return JSONResponse(
            content={"data": response.text},
            headers={"Cache-Control": "no-store"},
        )


@app.post("/api/admin/login")
def admin_login(request: AdminLoginRequest, raw_request: Request) -> dict[str, Any]:
    login = database.authenticate_admin(
        request.username,
        request.password,
        ip_hash=_hash_text(raw_request.client.host if raw_request.client else ""),
        user_agent=raw_request.headers.get("user-agent", ""),
        excluded_role="platform_admin",
    )
    if not login:
        if database.get_active_user_role(request.username) == "platform_admin":
            raise HTTPException(status_code=403, detail="平台管理员请使用 /platform/login。")
        raise HTTPException(status_code=401, detail="账号或密码错误，连续失败后会临时限制登录。")
    database.log_operation(
        admin_id=None,
        action="admin_login",
        detail={"username": request.username},
        ip_hash=_hash_text(raw_request.client.host if raw_request.client else ""),
    )
    return login


@app.post("/api/auth/login")
def auth_login(request: AdminLoginRequest, raw_request: Request) -> dict[str, Any]:
    """普通账号登录入口。平台管理员必须使用独立的平台登录入口。"""

    return admin_login(request, raw_request)


@app.post("/api/platform/auth/login")
def platform_auth_login(request: AdminLoginRequest, raw_request: Request) -> dict[str, Any]:
    """平台超级管理员独立登录入口。"""

    login = database.authenticate_admin(
        request.username,
        request.password,
        ip_hash=_hash_text(raw_request.client.host if raw_request.client else ""),
        user_agent=raw_request.headers.get("user-agent", ""),
        required_role="platform_admin",
    )
    if not login:
        if database.get_active_user_role(request.username) not in {None, "platform_admin"}:
            raise HTTPException(status_code=403, detail="普通账号请使用 /login。")
        raise HTTPException(status_code=401, detail="平台管理员账号或密码错误。")
    database.log_operation(
        admin_id=int(login["admin_id"]),
        action="platform_login",
        detail={"username": request.username},
        ip_hash=_hash_text(raw_request.client.host if raw_request.client else ""),
    )
    return login


@app.post("/api/auth/register")
def auth_register(request: RegisterRequest, raw_request: Request) -> dict[str, Any]:
    if len(request.password) < 6:
        raise HTTPException(status_code=422, detail="密码至少需要 6 位。")
    try:
        registered = database.register_tenant(
            username=request.username,
            password=request.password,
            email=request.email,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    login = database.authenticate_admin(
        request.username,
        request.password,
        ip_hash=_hash_text(raw_request.client.host if raw_request.client else ""),
        user_agent=raw_request.headers.get("user-agent", ""),
    )
    if not login:
        raise HTTPException(status_code=500, detail="注册完成，但自动登录失败，请重新登录。")
    database.log_operation(
        admin_id=int(registered["user"]["id"]),
        action="account_register",
        target_type="account",
        target_id=int(registered["user"]["id"]),
    )
    return {**login, "workspace": registered["workspace"], "team": registered["team"]}


@app.get("/api/auth/me")
def auth_me(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    session = require_admin(x_admin_token)
    return session


def require_admin(
    token: str | None,
    *,
    allow_viewer: bool = True,
    allow_platform: bool = False,
) -> dict[str, Any]:
    """校验后台临时令牌。"""

    session = database.get_admin_session(token)
    if not session:
        raise HTTPException(status_code=401, detail="请先登录管理后台。")
    if session["role"] == "platform_admin" and not allow_platform:
        raise HTTPException(status_code=403, detail="平台管理员请使用平台后台路由。")
    if not allow_viewer and session["role"] == "viewer":
        raise HTTPException(status_code=403, detail="当前账号只有只读权限。")
    return session


def require_platform_admin(token: str | None) -> dict[str, Any]:
    session = require_admin(token, allow_platform=True)
    if session["role"] != "platform_admin":
        raise HTTPException(status_code=403, detail="只有平台管理员可以访问平台运营中心。")
    return session


def ensure_survey_access(
    row: dict[str, Any] | None,
    session: dict[str, Any],
    *,
    write: bool = False,
) -> dict[str, Any]:
    if not row:
        raise HTTPException(status_code=404, detail="资源不存在。")
    if session["role"] == "platform_admin":
        return row
    permission = database.get_survey_permission(
        int(row["id"]),
        int(session["admin_id"]),
        session.get("tenant_id"),
    )
    if permission is None:
        raise HTTPException(status_code=404, detail="资源不存在。")
    if write and permission not in {"owner", "manager", "editor"}:
        raise HTTPException(status_code=403, detail="当前账号只有查看权限。")
    return row


def consume_session_tokens(session: dict[str, Any], amount: int) -> int:
    """扣除企业共享额度；平台管理员没有租户额度限制。"""

    if session["role"] == "platform_admin" or not session.get("tenant_id"):
        return 0
    if not database.consume_tokens(int(session["tenant_id"]), amount):
        raise HTTPException(
            status_code=402,
            detail=f"Token 额度不足，本次预计需要 {amount} Token，请先到 API 服务申请额度。",
        )
    return amount


def _record_token_call(
    session: dict[str, Any],
    prompt_version: str,
    token_amount: int,
    *,
    survey_id: int | None = None,
    status: str = "success",
    model_name: str = "platform-parser",
) -> None:
    database.record_generation(
        survey_id=survey_id,
        tenant_id=session.get("tenant_id"),
        created_by=int(session["admin_id"]),
        prompt_version=prompt_version,
        model_name=model_name,
        latency_ms=0,
        token_estimate=token_amount,
        cost_estimate=float(token_amount),
        quality_score=100.0 if status == "success" else 0.0,
        retry_count=0,
        status=status,
    )


@app.post("/api/admin/password")
def change_admin_password(
    request: ChangePasswordRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token, allow_viewer=False)
    if len(request.new_password) < 6:
        raise HTTPException(status_code=422, detail="新密码至少需要 6 位。")
    if not database.change_admin_password(
        int(session["admin_id"]),
        request.old_password,
        request.new_password,
    ):
        raise HTTPException(status_code=400, detail="原密码不正确。")
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="change_password",
        target_type="admin_user",
        target_id=int(session["admin_id"]),
    )
    return {"message": "密码已更新。"}


@app.get("/api/admin/users")
def list_admin_users(
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token, allow_viewer=False)
    tenant_id = None if session["role"] == "platform_admin" else session.get("tenant_id")
    return {"items": database.list_admin_users(tenant_id=tenant_id)}


@app.post("/api/admin/users")
def create_admin_user(
    request: AdminUserRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token, allow_viewer=False)
    if len(request.password) < 6:
        raise HTTPException(status_code=422, detail="账号密码至少需要 6 位。")
    try:
        user = database.create_admin_user(
            request.username,
            request.password,
            request.role,
            tenant_id=None if session["role"] == "platform_admin" else session.get("tenant_id"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="create_admin_user",
        target_type="admin_user",
        target_id=int(user["id"]),
        detail={"username": user["username"], "role": user["role"]},
    )
    return {"item": user}


@app.get("/api/tenant/teams")
def list_tenant_teams(
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token)
    return {
        "items": database.list_user_teams(
            int(session["admin_id"]),
            session.get("tenant_id"),
        )
    }


@app.post("/api/tenant/teams")
def create_tenant_team(
    request: TeamRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token, allow_viewer=False)
    if not session.get("tenant_id"):
        raise HTTPException(status_code=422, detail="平台账号不能创建个人问卷组。")
    try:
        item = database.create_team(
            int(session["tenant_id"]),
            request.name,
            request.description,
            int(session["admin_id"]),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="create_team",
        target_type="team",
        target_id=int(item["id"]),
    )
    return {"item": item}


@app.get("/api/tenant/teams/{team_id}/members")
def list_team_members(
    team_id: int,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token)
    if session["role"] == "viewer":
        raise HTTPException(status_code=403, detail="当前账号没有查看组成员的权限。")
    return {
        "items": database.list_team_members(team_id, int(session["admin_id"])),
        "invitations": database.list_team_invitations(team_id, int(session["admin_id"])),
    }


@app.post("/api/tenant/teams/{team_id}/invitations")
def create_team_invitation(
    team_id: int,
    request: TeamInvitationRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token, allow_viewer=False)
    try:
        item = database.create_team_invitation(
            team_id,
            int(session["admin_id"]),
            request.username,
            request.permission,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="invite_team_member",
        target_type="team",
        target_id=team_id,
        detail={"username": request.username, "permission": request.permission},
    )
    return {"item": item}


@app.get("/api/invitations")
def list_invitations(
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token)
    return {"items": database.list_user_invitations(int(session["admin_id"]))}


@app.post("/api/invitations/{invitation_id}/respond")
def respond_invitation(
    invitation_id: int,
    request: InvitationResponseRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token, allow_viewer=False)
    item = database.respond_team_invitation(
        invitation_id,
        int(session["admin_id"]),
        accepted=request.accepted,
    )
    if not item:
        raise HTTPException(status_code=404, detail="邀请不存在、已处理或不属于当前账号。")
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="respond_team_invitation",
        target_type="team_invitation",
        target_id=invitation_id,
        detail={"accepted": request.accepted},
    )
    return {"item": item}


@app.get("/api/surveys/{survey_id}/access")
def list_survey_access(
    survey_id: int,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token)
    row = ensure_survey_access(database.get_survey(survey_id), session)
    if session["role"] == "platform_admin":
        return {"items": []}
    if not database.can_manage_survey_access(
        survey_id,
        int(session["admin_id"]),
        session.get("tenant_id"),
    ):
        raise HTTPException(status_code=403, detail="只有问卷创建者或问卷组管理者可以管理访问权限。")
    return {
        "items": database.list_survey_permissions(
            int(row["id"]),
            int(session["admin_id"]),
            session.get("tenant_id"),
        )
    }


@app.post("/api/surveys/{survey_id}/access")
def update_survey_access(
    survey_id: int,
    request: SurveyPermissionRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token, allow_viewer=False)
    ensure_survey_access(database.get_survey(survey_id), session)
    try:
        item = database.set_survey_permission(
            survey_id,
            int(session["admin_id"]),
            request.user_id,
            request.permission,
            session.get("tenant_id"),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="update_survey_access",
        target_type="survey",
        target_id=survey_id,
        detail={"user_id": request.user_id, "permission": request.permission},
    )
    return {"item": item}


@app.get("/api/billing/overview")
def get_billing_overview(
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token)
    if not session.get("tenant_id"):
        return {
            "tenant_id": None,
            "tenant_name": "平台运营中心",
            "balance": 0,
            "used": 0,
            "today_used": 0,
            "api_calls": 0,
            "average_latency_ms": 0,
            "pending_requests": 0,
            "recent_usage": database.list_generation_records(),
        }
    return database.get_billing_overview(
        int(session["tenant_id"]),
        int(session["admin_id"]),
    )


@app.get("/api/billing/requests")
def list_billing_requests(
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token)
    if not session.get("tenant_id"):
        return {"items": []}
    return {
        "items": database.list_token_requests(
            int(session["tenant_id"]),
            requested_by=int(session["admin_id"]),
        )
    }


@app.post("/api/billing/requests")
def create_billing_request(
    request: TokenRequestPayload,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token, allow_viewer=False)
    if not session.get("tenant_id"):
        raise HTTPException(status_code=422, detail="平台管理员不需要申请企业 Token。")
    try:
        item = database.create_token_request(
            int(session["tenant_id"]),
            int(session["admin_id"]),
            request.amount,
            request.reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="request_tokens",
        target_type="token_request",
        target_id=int(item["id"]),
        detail={"amount": item["amount"]},
    )
    return {"item": item}


@app.get("/api/platform/overview")
def get_platform_overview(
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_platform_admin(x_admin_token)
    return {"overview": database.platform_overview()}


@app.get("/api/platform/tenants")
def list_platform_tenants(
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_platform_admin(x_admin_token)
    return {"items": database.list_platform_tenants()}


@app.get("/api/platform/users")
def list_platform_users(
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_platform_admin(x_admin_token)
    return {"items": database.list_platform_users()}


@app.post("/api/platform/users/{user_id}/status")
def update_platform_user_status(
    user_id: int,
    request: PlatformUserStatusRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_platform_admin(x_admin_token)
    if user_id == int(session["admin_id"]) and not request.is_active:
        raise HTTPException(status_code=422, detail="不能停用当前平台管理员账号。")
    item = database.update_user_status(user_id, request.is_active)
    if not item:
        raise HTTPException(status_code=404, detail="用户不存在。")
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="update_user_status",
        target_type="admin_user",
        target_id=user_id,
        detail={"is_active": request.is_active},
    )
    return {"item": item}


@app.get("/api/platform/reviews")
def list_platform_reviews(
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_platform_admin(x_admin_token)
    return {"items": database.list_platform_reviews()}


@app.post("/api/platform/reviews/{survey_id}")
def review_platform_survey(
    survey_id: int,
    request: ContentReviewRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_platform_admin(x_admin_token)
    item = database.review_survey(
        survey_id,
        int(session["admin_id"]),
        approved=request.approved,
        note=request.note,
    )
    if not item:
        raise HTTPException(status_code=404, detail="问卷不存在。")
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="review_survey",
        target_type="survey",
        target_id=survey_id,
        detail={"approved": request.approved, "note": request.note},
    )
    return {"item": item}


@app.get("/api/platform/token-requests")
def list_platform_token_requests(
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_platform_admin(x_admin_token)
    return {"items": database.list_token_requests()}


@app.post("/api/platform/token-requests/{request_id}")
def review_platform_token_request(
    request_id: int,
    request: TokenReviewRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_platform_admin(x_admin_token)
    item = database.review_token_request(
        request_id,
        int(session["admin_id"]),
        approved=request.approved,
    )
    if not item:
        raise HTTPException(status_code=404, detail="待审批的 Token 申请不存在。")
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="review_token_request",
        target_type="token_request",
        target_id=request_id,
        detail={"approved": request.approved},
    )
    return {"item": item}


@app.get("/api/platform/settings")
def list_platform_settings(
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    require_platform_admin(x_admin_token)
    return {"items": database.list_platform_settings()}


@app.post("/api/platform/settings/{key}")
def update_platform_setting(
    key: str,
    request: PlatformSettingRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_platform_admin(x_admin_token)
    if not key.replace("_", "").isalnum():
        raise HTTPException(status_code=422, detail="配置键名无效。")
    item = database.update_platform_setting(key, request.value)
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="update_platform_setting",
        target_type="platform_setting",
        detail={"key": key},
    )
    return {"item": item}


@app.post("/api/surveys/parse")
def parse_survey(
    request: ParseRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token, allow_viewer=False)
    try:
        questions = parse_survey_text(request.content, request.file_name)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"问卷解析失败：{exc}") from exc
    charged_tokens = consume_session_tokens(session, _estimate_parse_tokens(request.content))
    _record_token_call(session, "parse-survey-v1", charged_tokens)
    return {"questions": [question.to_dict() for question in questions]}


@app.post("/api/surveys/parse-wjx")
def parse_wjx_survey(
    request: WJXParseRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """读取问卷星或公开模板链接并返回可编辑题目。"""

    session = require_admin(x_admin_token, allow_viewer=False)
    try:
        title, source_url, questions = parse_wjx_template_url(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"公开问卷导入失败：{exc}") from exc
    charged_tokens = consume_session_tokens(session, max(600, len(questions) * 80))
    _record_token_call(session, "parse-wjx-v1", charged_tokens)
    return {
        "title": title,
        "source_url": source_url,
        "questions": [question.to_dict() for question in questions],
    }


@app.post("/api/surveys/import-template")
def import_wjx_template(
    request: WJXTemplateRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """从公开模板页抓取真实问卷并返回可编辑题目。"""

    session = require_admin(x_admin_token, allow_viewer=False)
    try:
        title, source_url, questions = parse_wjx_template_url(request.url)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"模板导入失败：{exc}") from exc
    charged_tokens = consume_session_tokens(session, max(600, len(questions) * 80))
    _record_token_call(session, "import-template-v1", charged_tokens)
    return {
        "title": title,
        "source_url": source_url,
        "questions": [question.to_dict() for question in questions],
    }


@app.post("/api/surveys/upload")
async def upload_survey(
    file: UploadFile,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token, allow_viewer=False)
    raw = await file.read()
    if len(raw) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="上传文件不能超过 2 MB。")
    try:
        content = raw.decode("utf-8-sig")
        questions = parse_survey_text(content, file.filename or "survey.csv")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"问卷解析失败：{exc}") from exc
    charged_tokens = consume_session_tokens(session, _estimate_parse_tokens(content))
    _record_token_call(session, "upload-survey-v1", charged_tokens)
    return {"questions": [question.to_dict() for question in questions]}


@app.post("/api/surveys/wrap")
def wrap_survey(
    request: WrapRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    session = require_admin(x_admin_token, allow_viewer=False)
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
    if request.team_id is not None:
        if not any(
            int(team["id"]) == request.team_id
            and team.get("member_role") in {"manager", "editor"}
            for team in database.list_user_teams(
                int(session["admin_id"]),
                session.get("tenant_id"),
            )
        ):
            raise HTTPException(status_code=404, detail="问卷组不存在或当前账号无权使用。")
    token_estimate = _estimate_tokens(request.brand_goal, request.theme_hint, request.questions)
    charged_tokens = consume_session_tokens(session, token_estimate)
    prompt_version = "wrap-v2-quality-control"
    started_at = time.perf_counter()
    retry_count = 0
    last_error: Exception | None = None
    survey = None
    for attempt in range(2):
        try:
            survey = build_wrapped_survey(questions, request.brand_goal, request.theme_hint)
            retry_count = attempt
            break
        except ValueError as exc:
            last_error = exc
            retry_count = attempt + 1
        except Exception as exc:
            last_error = exc
            retry_count = attempt
            break
    latency_ms = int((time.perf_counter() - started_at) * 1000)
    if survey is None:
        if session.get("tenant_id"):
            database.refund_tokens(int(session["tenant_id"]), charged_tokens)
        database.record_generation(
            survey_id=None,
            tenant_id=session.get("tenant_id"),
            created_by=int(session["admin_id"]),
            prompt_version=prompt_version,
            model_name=settings.llm_model,
            latency_ms=latency_ms,
            token_estimate=token_estimate,
            cost_estimate=float(charged_tokens),
            quality_score=0.0,
            retry_count=retry_count,
            status="failed",
            error_message=str(last_error or "生成失败"),
        )
        raise HTTPException(status_code=502, detail=f"大模型调用失败：{last_error}") from last_error
    quality_score = _score_generated_survey(survey)
    survey_id = database.save_survey(
        survey,
        status="draft",
        prompt_version=prompt_version,
        model_name=settings.llm_model,
        generation_latency_ms=latency_ms,
        quality_score=quality_score,
        tenant_id=session.get("tenant_id"),
        team_id=request.team_id,
        created_by=int(session["admin_id"]),
        moderation_status="pending",
    )
    database.record_generation(
        survey_id=survey_id,
        tenant_id=session.get("tenant_id"),
        created_by=int(session["admin_id"]),
        prompt_version=prompt_version,
        model_name=settings.llm_model,
        latency_ms=latency_ms,
        token_estimate=token_estimate,
        cost_estimate=float(charged_tokens),
        quality_score=quality_score,
        retry_count=retry_count,
        status="success",
    )
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="generate_draft_survey",
        target_type="survey",
        target_id=survey_id,
        detail={
            "prompt_version": prompt_version,
            "quality_score": quality_score,
            "token_estimate": token_estimate,
            "team_id": request.team_id,
        },
    )
    saved = database.get_survey(survey_id)
    return {
        "id": survey_id,
        "share_token": saved["share_token"] if saved else None,
        "survey": survey.to_dict(),
        "status": "draft",
        "generation": {
            "prompt_version": prompt_version,
            "model_name": settings.llm_model,
            "latency_ms": latency_ms,
            "quality_score": quality_score,
            "retry_count": retry_count,
            "token_estimate": token_estimate,
        },
    }


@app.get("/api/public/surveys")
def list_public_surveys() -> dict[str, Any]:
    """公开端不再暴露问卷列表，用户只能访问管理员分享出的链接。"""

    return {"items": []}


@app.get("/api/public/surveys/{survey_id}")
def get_public_survey(survey_id: int) -> dict[str, Any]:
    """兼容旧客户端，但不再允许通过编号直接读取公开问卷。"""

    raise HTTPException(status_code=404, detail="请使用管理员生成的问卷分享链接访问。")


@app.get("/api/public/share/{share_token}")
def get_shared_survey(
    share_token: str,
    raw_request: Request,
    x_browser_id: str | None = Header(default=None),
    x_device_fingerprint: str | None = Header(default=None),
) -> dict[str, Any]:
    """通过分享链接读取单份问卷，用户端不会拿到问卷列表。"""

    row = database.get_survey_by_share_token(share_token)
    return _public_survey_response(
        row,
        raw_request=raw_request,
        browser_id=x_browser_id,
        fingerprint=x_device_fingerprint,
    )


def _public_survey_response(
    row: dict[str, Any] | None,
    *,
    raw_request: Request | None = None,
    browser_id: str | None = None,
    fingerprint: str | None = None,
) -> dict[str, Any]:
    """输出答题端可见字段，剥离调研映射和评分细节。"""

    if not row:
        raise HTTPException(status_code=404, detail="问卷不存在。")
    if row["deleted_at"]:
        raise HTTPException(status_code=404, detail="问卷不存在。")
    ip_hash = _hash_text(raw_request.client.host if raw_request and raw_request.client else "")
    if database.has_duplicate_response(
        row["id"],
        fingerprint_hash=_hash_text(fingerprint or ""),
        browser_id_hash=_hash_text(browser_id or ""),
        ip_hash=ip_hash,
    ):
        return {
            "id": row["id"],
            "share_token": row.get("share_token"),
            "submitted": True,
        }
    if row["status"] != "collecting":
        raise HTTPException(status_code=410, detail="该问卷已结束，不再接受新的答卷。")
    _ensure_collection_limit(row)
    payload = dict(row["payload"])
    payload.pop("brand_goal", None)
    for question in payload.get("questions", []):
        question.pop("research_tag", None)
        question.pop("source_text", None)
        question.pop("research_refs", None)
        question.pop("option_scores", None)
        question.pop("dimension_weights", None)
        question.pop("rationale", None)
    return {
        "id": row["id"],
        "share_token": row.get("share_token"),
        "submitted": False,
        "survey": payload,
    }


@app.get("/api/surveys")
def list_surveys(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    session = require_admin(x_admin_token)
    return {
        "items": database.list_surveys(
            tenant_id=session.get("tenant_id"),
            user_id=int(session["admin_id"]),
        )
    }


@app.get("/api/surveys/trash")
def list_trash_surveys(x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    """列出已移入回收站的问卷。"""

    session = require_admin(x_admin_token)
    return {
        "items": database.list_surveys(
            deleted=True,
            tenant_id=session.get("tenant_id"),
            user_id=int(session["admin_id"]),
        )
    }


@app.get("/api/surveys/{survey_id}")
def get_survey(survey_id: int, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    session = require_admin(x_admin_token)
    return ensure_survey_access(database.get_survey(survey_id), session)


@app.post("/api/surveys/{survey_id}/publication")
def update_publication(
    survey_id: int,
    request: PublishSurveyRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """更新问卷生命周期和采集控制，发布前允许管理员先预览草稿。"""

    session = require_admin(x_admin_token, allow_viewer=False)
    row = ensure_survey_access(database.get_survey(survey_id), session, write=True)
    if row["deleted_at"]:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    try:
        _validate_status_transition(str(row["status"]), request.status)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if request.status == "collecting":
        if row.get("moderation_status") == "rejected":
            raise HTTPException(status_code=409, detail="问卷内容已被平台退回，请修改后重新提交审核。")
        review_required = database.get_platform_setting("content_review_required", default="false").lower() == "true"
        if review_required and row.get("moderation_status") != "approved":
            raise HTTPException(status_code=409, detail="平台已开启内容审核，问卷通过审核后才能发布。")
    generated_analysis: dict[str, Any] | None = None
    if request.status == "archived":
        if not row.get("analysis"):
            raise HTTPException(status_code=422, detail="请先完成数据分析，再归档问卷。")
        updated = database.archive_survey(survey_id, analysis=row["analysis"])
    else:
        updated = database.update_survey_publication(survey_id, status=request.status)
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="update_survey_publication",
        target_type="survey",
        target_id=survey_id,
        detail={
            **request.model_dump(),
            "analysis_generated": generated_analysis is not None,
        },
    )
    return {"item": updated, "analysis": generated_analysis}


@app.post("/api/surveys/{survey_id}/content")
def update_survey_content(
    survey_id: int,
    request: UpdateSurveyContentRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """保存发布前的互动题面编辑，发布后不允许直接改变题目语义。"""

    session = require_admin(x_admin_token, allow_viewer=False)
    row = ensure_survey_access(database.get_survey(survey_id), session, write=True)
    if row["deleted_at"]:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    if row["status"] not in {"draft"}:
        raise HTTPException(status_code=409, detail="问卷只有草稿状态才能编辑题面。")
    try:
        survey = wrapped_survey_from_dict(request.survey)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=f"问卷内容无效：{exc}") from exc
    if not survey.questions:
        raise HTTPException(status_code=422, detail="至少保留 1 道互动题。")
    updated = database.update_survey_content(survey_id, survey)
    if not updated:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="update_survey_content",
        target_type="survey",
        target_id=survey_id,
        detail={"version": updated.get("version")},
    )
    return {"item": updated, "survey": updated["payload"]}


@app.post("/api/surveys/{survey_id}/title")
def rename_survey(
    survey_id: int,
    request: RenameSurveyRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """允许管理员修改 AI 生成后的问卷标题。"""

    session = require_admin(x_admin_token, allow_viewer=False)
    row = ensure_survey_access(database.get_survey(survey_id), session, write=True)
    if row["deleted_at"]:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    survey_name = " ".join(request.survey_name.split()).strip()
    if not survey_name:
        raise HTTPException(status_code=422, detail="问卷标题不能为空。")
    if len(survey_name) > 60:
        raise HTTPException(status_code=422, detail="问卷标题不能超过 60 个字符。")
    updated = database.update_survey_title(survey_id, survey_name)
    if not updated:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="rename_survey",
        target_type="survey",
        target_id=survey_id,
        detail={"survey_name": survey_name},
    )
    return {"survey": updated["payload"], "item": updated}


@app.delete("/api/surveys/{survey_id}")
def delete_survey(
    survey_id: int,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """将问卷移入回收站。"""

    session = require_admin(x_admin_token, allow_viewer=False)
    row = ensure_survey_access(database.get_survey(survey_id), session, write=True)
    if row["deleted_at"]:
        return {"item": row, "message": "问卷已在回收站。"}
    deleted = database.move_survey_to_trash(survey_id)
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="move_survey_to_trash",
        target_type="survey",
        target_id=survey_id,
    )
    return {"item": deleted, "message": "问卷已移入回收站。"}


@app.post("/api/surveys/{survey_id}/restore")
def restore_survey(
    survey_id: int,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """从回收站恢复问卷。"""

    session = require_admin(x_admin_token, allow_viewer=False)
    ensure_survey_access(database.get_survey(survey_id), session, write=True)
    restored = database.restore_survey(survey_id)
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="restore_survey",
        target_type="survey",
        target_id=survey_id,
    )
    return {"item": restored, "message": "问卷已恢复。"}


@app.delete("/api/surveys/{survey_id}/permanent")
def permanently_delete_survey(
    survey_id: int,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """永久删除回收站中的问卷和答卷。"""

    session = require_admin(x_admin_token, allow_viewer=False)
    row = ensure_survey_access(database.get_survey(survey_id), session, write=True)
    if not row["deleted_at"]:
        raise HTTPException(status_code=404, detail="只能永久删除回收站中的问卷。")
    if not database.permanently_delete_survey(survey_id):
        raise HTTPException(status_code=404, detail="只能永久删除回收站中的问卷。")
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="permanently_delete_survey",
        target_type="survey",
        target_id=survey_id,
    )
    return {"message": "问卷已永久删除。"}


@app.post("/api/responses")
def submit_response(request: ResponseRequest, raw_request: Request) -> dict[str, Any]:
    row = database.get_survey(request.survey_id)
    if not row:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    if row["deleted_at"]:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    source = request.source if request.source in {"public_link", "admin_preview", "test"} else "public_link"
    if source == "public_link":
        if not request.share_token or request.share_token != row.get("share_token"):
            raise HTTPException(status_code=403, detail="请通过管理员分享链接提交问卷。")
        if row["status"] != "collecting":
            raise HTTPException(status_code=410, detail="该问卷已结束，不再接受新的答卷。")
        _ensure_collection_limit(row)
        fingerprint_hash = _hash_text(request.fingerprint or "")
        browser_id_hash = _hash_text(request.browser_id or "")
        ip_hash = _hash_text(raw_request.client.host if raw_request.client else "")
        if database.has_duplicate_response(
            request.survey_id,
            fingerprint_hash=fingerprint_hash,
            browser_id_hash=browser_id_hash,
            ip_hash=ip_hash,
            access_code=request.access_code,
        ):
            raise HTTPException(status_code=409, detail="该设备或访问码已经提交过这份问卷。")
    else:
        session = require_admin(
            raw_request.headers.get("x-admin-token"),
            allow_viewer=False,
        )
        ensure_survey_access(row, session)
        fingerprint_hash = _hash_text(request.fingerprint or "")
        browser_id_hash = _hash_text(request.browser_id or "")
        ip_hash = _hash_text(raw_request.client.host if raw_request.client else "")
    if source != "public_link" and row["status"] not in {"draft", "collecting"}:
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
    response_id = database.save_response(
        response,
        request.survey_id,
        survey_version=int(row.get("version") or 1),
        source=source,
        duration_seconds=request.duration_seconds,
        fingerprint_hash=fingerprint_hash,
        browser_id_hash=browser_id_hash,
        ip_hash=ip_hash,
        access_code=request.access_code,
        is_test=source == "test",
    )
    return {"id": response_id, "response": response.to_dict(), "result": result}


@app.get("/api/analytics/{survey_id}")
def get_analytics(survey_id: int, x_admin_token: str | None = Header(default=None)) -> dict[str, Any]:
    session = require_admin(x_admin_token)
    row = ensure_survey_access(database.get_survey(survey_id), session)
    if row["deleted_at"]:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    survey = wrapped_survey_from_dict(row["payload"])
    responses = database.list_responses(survey_id)
    response_rows = database.list_response_rows(survey_id, include_invalid=True, include_test=True)
    summary = summarize_responses(survey, responses)
    summary["trend_stats"] = build_collection_trend(
        [
            item
            for item in response_rows
            if not item["is_invalid"] and not item["is_test"]
        ]
    )
    return {
        "status": row["status"],
        "target_sample_count": row.get("target_sample_count"),
        "ended_at": row["ended_at"],
        "summary": summary,
        "analysis": row["analysis"],
        "survey": survey.to_dict(),
        "responses": database.list_response_rows(survey_id, include_invalid=True, include_test=True),
        "generations": database.list_generation_records(survey_id),
    }


def _generate_final_analysis(row: dict[str, Any]) -> dict[str, Any]:
    """基于当前问卷和有效答卷生成最终研究分析。"""

    if not settings.has_llm:
        raise HTTPException(status_code=400, detail="未配置 LLM_API_KEY，不能生成 AI 数据分析。")
    survey = wrapped_survey_from_dict(row["payload"])
    responses = database.list_responses(int(row["id"]))
    if not responses:
        raise HTTPException(status_code=422, detail="至少收集 1 份有效答卷后才能归档并生成数据分析。")
    try:
        return build_research_analysis(survey, responses)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"AI 数据分析失败：{exc}") from exc


@app.post("/api/analytics/{survey_id}/finish")
def finish_analytics(
    survey_id: int,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """为已结束且答卷不再变化的问卷生成最终研究分析。"""

    session = require_admin(x_admin_token, allow_viewer=False)
    row = ensure_survey_access(database.get_survey(survey_id), session, write=True)
    if row["deleted_at"]:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    if row["status"] in {"ended", "archived"} and row["analysis"]:
        return {
            "status": row["status"],
            "ended_at": row["ended_at"],
            "analysis": row["analysis"],
        }
    if row["status"] != "ended":
        raise HTTPException(status_code=409, detail="请先结束问卷，再开始数据分析。")
    analysis_tokens = max(1800, int(row.get("response_count") or 0) * 40)
    charged_tokens = consume_session_tokens(session, analysis_tokens)
    try:
        analysis = _generate_final_analysis(row)
    except Exception:
        if session.get("tenant_id"):
            database.refund_tokens(int(session["tenant_id"]), charged_tokens)
        raise
    finished = database.finish_survey(survey_id, analysis)
    _record_token_call(
        session,
        "analysis-v1",
        charged_tokens,
        survey_id=survey_id,
        model_name=settings.llm_model,
    )
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="finish_survey",
        target_type="survey",
        target_id=survey_id,
    )
    return {
        "status": finished["status"] if finished else "ended",
        "ended_at": finished["ended_at"] if finished else None,
        "analysis": analysis,
    }


@app.post("/api/responses/{response_id}/invalid")
def mark_response_invalid(
    response_id: int,
    request: InvalidResponseRequest,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """管理员标记或恢复无效答卷。"""

    session = require_admin(x_admin_token, allow_viewer=False)
    existing = database.get_response_row(response_id)
    if not existing:
        raise HTTPException(status_code=404, detail="答卷不存在。")
    ensure_survey_access(database.get_survey(int(existing["survey_id"])), session, write=True)
    row = database.mark_response_invalid(
        response_id,
        invalid=request.invalid,
        reason=request.reason,
    )
    if not row:
        raise HTTPException(status_code=404, detail="答卷不存在。")
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="mark_response_invalid" if request.invalid else "restore_response",
        target_type="response",
        target_id=response_id,
        detail={"reason": request.reason},
    )
    return {"item": row}


@app.delete("/api/responses/{response_id}")
def delete_response(
    response_id: int,
    x_admin_token: str | None = Header(default=None),
) -> dict[str, Any]:
    """管理员删除测试或无效答卷。"""

    session = require_admin(x_admin_token, allow_viewer=False)
    existing = database.get_response_row(response_id)
    if not existing:
        raise HTTPException(status_code=404, detail="答卷不存在。")
    ensure_survey_access(database.get_survey(int(existing["survey_id"])), session, write=True)
    if not database.delete_response(response_id):
        raise HTTPException(status_code=404, detail="答卷不存在。")
    database.log_operation(
        admin_id=int(session["admin_id"]),
        action="delete_response",
        target_type="response",
        target_id=response_id,
    )
    return {"message": "答卷已删除。"}


@app.get("/api/analytics/{survey_id}/pdf")
def export_pdf(survey_id: int, x_admin_token: str | None = Header(default=None)) -> Response:
    session = require_admin(x_admin_token)
    row = ensure_survey_access(database.get_survey(survey_id), session)
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
    """导出完整研究分析和答卷明细 Excel。"""

    session = require_admin(x_admin_token)
    row = ensure_survey_access(database.get_survey(survey_id), session)
    if row["deleted_at"]:
        raise HTTPException(status_code=404, detail="包装方案不存在。")
    survey = wrapped_survey_from_dict(row["payload"])
    responses = database.list_responses(survey_id)
    summary = summarize_responses(survey, responses)
    content = build_research_xlsx(
        survey,
        database.list_response_rows(survey_id),
        summary,
        row["analysis"],
    )
    return Response(
        content=content,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="fun_research_data.xlsx"'},
    )


def _ensure_collection_limit(row: dict[str, Any]) -> None:
    """检查问卷是否达到目标样本数。"""

    target = row.get("target_sample_count")
    if target is not None:
        try:
            target_count = int(target)
        except (TypeError, ValueError):
            target_count = 0
        if target_count > 0:
            responses = database.list_response_rows(int(row["id"]))
            if len(responses) >= target_count:
                raise HTTPException(status_code=410, detail="问卷已达到目标样本数。")


def _validate_status_transition(current: str, target: str) -> None:
    """限制生命周期只能沿可解释的路径变化。"""

    allowed: dict[str, set[str]] = {
        "draft": {"draft", "collecting"},
        "collecting": {"collecting", "ended"},
        "ended": {"ended", "archived"},
        "archived": {"archived"},
    }
    if target not in allowed.get(current, {current}):
        raise ValueError(f"问卷不能从“{current}”直接变更为“{target}”。")

def _hash_text(value: str) -> str | None:
    text = value.strip()
    if not text:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _estimate_tokens(brand_goal: str, theme_hint: str, questions: list[dict[str, Any]]) -> int:
    """用字符数粗估 token，用于毕业答辩展示成本记录。"""

    payload = json.dumps(
        {"brand_goal": brand_goal, "theme_hint": theme_hint, "questions": questions},
        ensure_ascii=False,
    )
    return max(1, len(payload) // 2)


def _estimate_parse_tokens(content: str) -> int:
    """估算解析请求消耗的 Token，便于在控制台提前展示额度影响。"""

    return max(200, min(5000, len(content.strip()) // 4))


def _score_generated_survey(survey: Any) -> float:
    """按题量、维度覆盖和选项评分完整度给 AI 生成结果打分。"""

    question_score = min(len(survey.questions) / 12, 1.0) * 40
    dimension_score = min(len(survey.dimensions or []) / 4, 1.0) * 25
    mapped_options = 0
    total_options = 0
    for question in survey.questions:
        total_options += len(question.options)
        mapped_options += sum(1 for option in question.options if question.option_scores.get(option))
    mapping_score = (mapped_options / total_options * 25) if total_options else 10
    result_score = min(len(survey.result_types) / 4, 1.0) * 10
    return round(question_score + dimension_score + mapping_score + result_score, 1)
