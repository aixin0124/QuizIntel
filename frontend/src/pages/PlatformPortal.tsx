import { Activity, BarChart3, Check, CheckCircle2, Database, Gauge, Settings2, ShieldCheck, Users, X } from "lucide-react";
import { useEffect, useState } from "react";
import { adminFetchJson, adminPostJson } from "../api/client";
import type { PlatformOverview, PlatformUser, TokenRequest } from "../types";

type ReviewItem = {
  id: number;
  survey_name: string;
  theme: string;
  status: string;
  moderation_status: string;
  moderation_note?: string | null;
  created_at: string;
  workspace_name?: string | null;
  created_by_name?: string | null;
};

export function PlatformPortal({ token }: { token: string }) {
  const [active, setActive] = useState<"overview" | "users" | "requests" | "reviews" | "settings">("overview");
  const [overview, setOverview] = useState<PlatformOverview | null>(null);
  const [users, setUsers] = useState<PlatformUser[]>([]);
  const [requests, setRequests] = useState<TokenRequest[]>([]);
  const [reviews, setReviews] = useState<ReviewItem[]>([]);
  const [settings, setSettings] = useState<Array<{ setting_key: string; setting_value: string; updated_at: string }>>([]);
  const [message, setMessage] = useState("");

  async function load() {
    try {
      const [overviewData, userData, requestData, reviewData, settingData] = await Promise.all([
        adminFetchJson<{ overview: PlatformOverview }>("/api/platform/overview", token),
        adminFetchJson<{ items: PlatformUser[] }>("/api/platform/users", token),
        adminFetchJson<{ items: TokenRequest[] }>("/api/platform/token-requests", token),
        adminFetchJson<{ items: ReviewItem[] }>("/api/platform/reviews", token),
        adminFetchJson<{ items: Array<{ setting_key: string; setting_value: string; updated_at: string }> }>("/api/platform/settings", token),
      ]);
      setOverview(overviewData.overview);
      setUsers(userData.items);
      setRequests(requestData.items);
      setReviews(reviewData.items);
      setSettings(settingData.items);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "平台数据读取失败。");
    }
  }

  useEffect(() => { void load(); }, [token]);

  async function reviewToken(id: number, approved: boolean) {
    try {
      await adminPostJson(`/api/platform/token-requests/${id}`, { approved }, token);
      setMessage(approved ? "Token 已发放到个人工作区。" : "Token 申请已驳回。");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Token 审批失败。");
    }
  }

  async function reviewSurvey(id: number, approved: boolean) {
    try {
      await adminPostJson(`/api/platform/reviews/${id}`, { approved, note: approved ? "平台审核通过。" : "请补充内容说明后重新提交。" }, token);
      setMessage(approved ? "问卷内容已审核通过。" : "问卷内容已退回。");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "内容审核失败。");
    }
  }

  async function toggleUser(user: PlatformUser) {
    try {
      await adminPostJson(`/api/platform/users/${user.id}/status`, { is_active: !user.is_active }, token);
      setMessage(user.is_active ? "账号已冻结。" : "账号已恢复。");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "账号状态更新失败。");
    }
  }

  return (
    <section className="platform-page">
      <div className="platform-head"><div><p className="eyebrow">PLATFORM SUPER ADMIN</p><h1>平台超级管理员后台</h1><p>管理全部个人账号、问卷资源、Token 消耗和平台内容审核。</p></div><div className="platform-head-badge"><ShieldCheck size={17} /> 全局视角</div></div>
      {message && <div className="notice">{message}</div>}
      <div className="platform-shell">
        <aside className="platform-sidebar">
          <button className={active === "overview" ? "active" : ""} onClick={() => setActive("overview")}><Gauge size={17} /> 资源与用量</button>
          <button className={active === "users" ? "active" : ""} onClick={() => setActive("users")}><Users size={17} /> 用户管理</button>
          <button className={active === "requests" ? "active" : ""} onClick={() => setActive("requests")}><Database size={17} /> Token 审批 <b>{requests.filter((item) => item.status === "pending").length}</b></button>
          <button className={active === "reviews" ? "active" : ""} onClick={() => setActive("reviews")}><ShieldCheck size={17} /> 内容审核 <b>{reviews.filter((item) => item.moderation_status === "pending").length}</b></button>
          <button className={active === "settings" ? "active" : ""} onClick={() => setActive("settings")}><Settings2 size={17} /> 平台配置</button>
        </aside>
        <div className="platform-content">
          {active === "overview" && <PlatformOverviewView overview={overview} users={users} />}
          {active === "users" && <PlatformUsersView users={users} onToggle={toggleUser} />}
          {active === "requests" && <TokenRequestsView requests={requests} onReview={reviewToken} />}
          {active === "reviews" && <ReviewView reviews={reviews} onReview={reviewSurvey} />}
          {active === "settings" && <SettingsView settings={settings} token={token} onSaved={load} />}
        </div>
      </div>
    </section>
  );
}

function PlatformOverviewView({ overview, users }: { overview: PlatformOverview | null; users: PlatformUser[] }) {
  const items = [
    ["今日 Token", (overview?.token_used_today || 0).toLocaleString(), <Activity size={18} />],
    ["累计 Token", (overview?.token_used || 0).toLocaleString(), <Gauge size={18} />],
    ["API 调用", (overview?.api_call_count || 0).toLocaleString(), <BarChart3 size={18} />],
    ["活跃账号", (overview?.user_count || 0).toLocaleString(), <Users size={18} />],
  ];
  return <section><div className="page-title"><div><p className="eyebrow">GLOBAL RESOURCE MONITOR</p><h2>全局资源与用量</h2><p>平台只统计消耗和调用情况，额度发放由 Token 审批处理。</p></div><Gauge size={25} /></div><div className="platform-metric-grid">{items.map(([label, value, icon]) => <article key={String(label)}><span>{icon}</span><small>{label}</small><strong>{value}</strong></article>)}</div><div className="platform-summary-strip"><span>个人账号 <b>{overview?.account_count || 0}</b></span><span>问卷总量 <b>{overview?.survey_count || 0}</b></span><span>有效答卷 <b>{overview?.response_count || 0}</b></span><span>待审核 <b>{(overview?.pending_reviews || 0) + (overview?.pending_token_requests || 0)}</b></span></div><div className="platform-alert-row"><div><ShieldCheck size={17} /><span>待审核内容</span><b>{overview?.pending_reviews || 0}</b></div><div><Database size={17} /><span>待发放 Token</span><b>{overview?.pending_token_requests || 0}</b></div></div><div className="platform-mini-table"><div className="section-heading"><div><h3>账号消耗排行</h3><p>按累计已用 Token 排序，平台管理员可以快速查看每个人的调用成本。</p></div></div>{users.filter((user) => user.role !== "platform_admin").slice().sort((a, b) => b.token_used - a.token_used).slice(0, 5).map((user) => <div className="platform-mini-row" key={user.id}><strong>{user.display_name || user.username}</strong><span>{user.survey_count} 份问卷 · {user.response_count} 份答卷</span><b>{user.token_used.toLocaleString()} Token</b></div>)}</div></section>;
}

function PlatformUsersView({ users, onToggle }: { users: PlatformUser[]; onToggle: (user: PlatformUser) => void }) {
  return <section><div className="page-title"><div><p className="eyebrow">USER DIRECTORY</p><h2>全部用户与消耗</h2><p>查看每个账号的问卷、答卷、API 调用次数和累计 Token 使用量，并处理账号状态。</p></div><Users size={25} /></div><div className="platform-user-list">{!users.length ? <div className="empty">暂无用户。</div> : users.map((user) => <article key={user.id}><div><span>{user.workspace_name || user.tenant_name || "平台账号"}</span><h3>{user.display_name || user.username}</h3><small>{user.username}{user.email ? ` · ${user.email}` : ""}</small></div><div className="platform-user-role"><b>{platformRoleLabel(user.role)}</b><em className={user.is_active ? "active" : "inactive"}>{user.is_active ? "正常" : "已冻结"}</em></div><div className="platform-user-usage"><span><b>{user.survey_count}</b>问卷</span><span><b>{user.response_count}</b>答卷</span><span><b>{user.api_call_count}</b>次调用</span><span><b>{user.token_used.toLocaleString()}</b>累计 Token</span></div><button className={user.is_active ? "secondary" : "primary"} onClick={() => onToggle(user)} disabled={user.role === "platform_admin"}>{user.is_active ? "冻结账号" : "恢复账号"}</button></article>)}</div></section>;
}

function TokenRequestsView({ requests, onReview }: { requests: TokenRequest[]; onReview: (id: number, approved: boolean) => void }) {
  return <section><div className="page-title"><div><p className="eyebrow">TOKEN REVIEW</p><h2>Token 额度审批</h2><p>审批通过后，额度会发放到申请人的个人工作区。</p></div><Database size={25} /></div><div className="platform-request-list">{!requests.length ? <div className="empty">暂无额度申请。</div> : requests.map((item) => <article key={item.id}><div><span>{item.tenant_name || "个人工作区"} · {item.requested_by_name || "未知用户"}</span><h3>{item.amount.toLocaleString()} Token</h3><p>{item.reason || "未填写用途说明"}</p></div><em className={`request-status ${item.status}`}>{requestStatusLabel(item.status)}</em>{item.status === "pending" && <div className="platform-row-actions"><button className="icon-button approve" onClick={() => onReview(item.id, true)} title="批准申请" aria-label="批准申请"><Check size={16} /></button><button className="icon-button reject" onClick={() => onReview(item.id, false)} title="驳回申请" aria-label="驳回申请"><X size={16} /></button></div>}</article>)}</div></section>;
}

function ReviewView({ reviews, onReview }: { reviews: ReviewItem[]; onReview: (id: number, approved: boolean) => void }) {
  return <section><div className="page-title"><div><p className="eyebrow">CONTENT MODERATION</p><h2>内容审核</h2><p>平台管理员负责处理所有账号提交的问卷内容，保留审核状态和说明。</p></div><ShieldCheck size={25} /></div><div className="platform-review-list">{!reviews.length ? <div className="empty">暂无问卷记录。</div> : reviews.map((item) => <article key={item.id}><div className="review-main"><span>{item.workspace_name || "个人工作区"} · {item.created_by_name || "未知用户"}</span><h3>{item.survey_name}</h3><p>{item.theme}</p></div><em className={`review-status ${item.moderation_status}`}>{moderationStatusLabel(item.moderation_status)}</em><div className="platform-row-actions">{item.moderation_status !== "approved" && <button className="icon-button approve" onClick={() => onReview(item.id, true)} title="审核通过" aria-label="审核通过"><Check size={16} /></button>}{item.moderation_status !== "rejected" && <button className="icon-button reject" onClick={() => onReview(item.id, false)} title="退回问卷" aria-label="退回问卷"><X size={16} /></button>}</div></article>)}</div></section>;
}

function SettingsView({ settings, token, onSaved }: { settings: Array<{ setting_key: string; setting_value: string; updated_at: string }>; token: string; onSaved: () => void }) {
  const [values, setValues] = useState<Record<string, string>>({});
  const [saving, setSaving] = useState("");
  useEffect(() => setValues(Object.fromEntries(settings.map((item) => [item.setting_key, item.setting_value]))), [settings]);
  async function save(key: string) {
    setSaving(key);
    try {
      await adminPostJson(`/api/platform/settings/${key}`, { value: values[key] || "" }, token);
      onSaved();
    } finally {
      setSaving("");
    }
  }
  return <section><div className="page-title"><div><p className="eyebrow">PLATFORM CONFIGURATION</p><h2>平台全局配置</h2><p>调整注册初始额度、解析和分析的默认 Token 估算。</p></div><Settings2 size={25} /></div><div className="settings-list">{settings.map((item) => <div className="setting-row" key={item.setting_key}><div><strong>{settingLabel(item.setting_key)}</strong><small>{item.setting_key}</small></div><input value={values[item.setting_key] || ""} onChange={(event) => setValues({ ...values, [item.setting_key]: event.target.value })} /><button className="secondary" onClick={() => void save(item.setting_key)} disabled={saving === item.setting_key}>{saving === item.setting_key ? "保存中..." : "保存"}</button></div>)}</div></section>;
}

function requestStatusLabel(status: string) {
  return ({ pending: "待审核", approved: "已发放", rejected: "已驳回" } as Record<string, string>)[status] || status;
}

function moderationStatusLabel(status: string) {
  return ({ pending: "待审核", approved: "已通过", rejected: "已退回" } as Record<string, string>)[status] || status;
}

function settingLabel(key: string) {
  return ({
    default_registration_tokens: "新账号初始 Token",
    parse_request_tokens: "解析请求默认 Token",
    analysis_request_tokens: "分析请求默认 Token",
    content_review_required: "是否必须内容审核",
  } as Record<string, string>)[key] || key;
}

function platformRoleLabel(role: string) {
  return ({
    platform_admin: "平台超级管理员",
    owner: "个人账号所有者",
    tenant_owner: "个人账号所有者",
    survey_admin: "个人账号所有者",
    member: "组内成员",
    viewer: "兼容只读账号",
    admin: "个人账号所有者",
  } as Record<string, string>)[role] || role;
}
