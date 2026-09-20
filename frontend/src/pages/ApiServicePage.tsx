import { Activity, ArrowDownToLine, Clock3, Coins, FileKey2, Gauge, KeyRound, Plus, RefreshCw, Send, Sparkles } from "lucide-react";
import { useEffect, useState } from "react";
import { adminFetchJson, adminPostJson } from "../api/client";
import type { BillingOverview, TokenRequest } from "../types";

export function ApiServicePage({ token }: { token: string }) {
  const [overview, setOverview] = useState<BillingOverview | null>(null);
  const [requests, setRequests] = useState<TokenRequest[]>([]);
  const [amount, setAmount] = useState("10000");
  const [reason, setReason] = useState("用于生成互动问卷和后续数据分析。");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function load() {
    setLoading(true);
    try {
      const [billing, requestData] = await Promise.all([
        adminFetchJson<BillingOverview>("/api/billing/overview", token),
        adminFetchJson<{ items: TokenRequest[] }>("/api/billing/requests", token),
      ]);
      setOverview(billing);
      setRequests(requestData.items);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "API 服务读取失败。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [token]);

  async function requestTokens(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    try {
      await adminPostJson("/api/billing/requests", { amount: Number(amount), reason }, token);
      setMessage("Token 申请已提交，等待平台管理员审核。");
      await load();
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Token 申请失败。");
    } finally {
      setLoading(false);
    }
  }

  const balance = overview?.balance || 0;
  const used = overview?.used || 0;
  const total = Math.max(balance + used, 1);
  const usedPercent = Math.min(100, Math.round((used / total) * 100));

  return (
    <section className="api-service-page">
      <div className="page-title api-page-title"><div><p className="eyebrow">API SERVICE / TOKEN CENTER</p><h2>API 服务</h2><p>生成问卷、解析题目和数据分析都会消耗 Token。额度不足时，可以向平台管理员提交申请。</p></div><div className="api-title-icon"><KeyRound size={25} /></div></div>
      {message && <div className="notice">{message}</div>}
      <div className="api-metric-grid">
        <article><span className="api-metric-icon"><Coins size={18} /></span><small>Token 余额</small><strong>{balance.toLocaleString()}</strong><em>当前可用额度</em></article>
        <article><span className="api-metric-icon green"><Gauge size={18} /></span><small>累计已用</small><strong>{used.toLocaleString()}</strong><em>当前账号累计消耗</em></article>
        <article><span className="api-metric-icon orange"><Activity size={18} /></span><small>今日调用</small><strong>{(overview?.today_used || 0).toLocaleString()}</strong><em>{overview?.api_calls || 0} 次 API 调用</em></article>
        <article><span className="api-metric-icon purple"><Clock3 size={18} /></span><small>待审批额度</small><strong>{overview?.pending_requests || 0}</strong><em>平台管理员处理</em></article>
      </div>
      <div className="api-main-grid">
        <section className="panel api-balance-panel">
          <div className="section-heading"><div><p className="eyebrow">USAGE OVERVIEW</p><h3>个人 Token 使用情况</h3><p>每份问卷的生成、解析和分析调用都会记录在这里。</p></div><button className="icon-button" onClick={() => void load()} title="刷新用量" aria-label="刷新用量"><RefreshCw size={16} /></button></div>
          <div className="api-balance-number"><strong>{balance.toLocaleString()}</strong><span>Token remaining</span></div>
          <div className="api-usage-track"><span style={{ width: `${usedPercent}%` }} /></div>
          <div className="api-usage-foot"><span>已使用 {used.toLocaleString()}</span><b>{usedPercent}%</b><span>可用 {balance.toLocaleString()}</span></div>
          <div className="api-cost-list">
            <div><span><Sparkles size={15} /> 生成互动包装</span><strong>按请求估算</strong></div>
            <div><span><FileKey2 size={15} /> 解析问卷题目</span><strong>按内容长度估算</strong></div>
            <div><span><ArrowDownToLine size={15} /> 导出与查看</span><strong>不扣 Token</strong></div>
          </div>
        </section>
        <form className="panel api-request-panel" onSubmit={(event) => void requestTokens(event)}>
          <div className="section-heading"><div><p className="eyebrow">REQUEST QUOTA</p><h3>申请额度</h3></div><Send size={21} /></div>
          <p className="api-form-description">当前版本不接入真实支付。提交需要的额度和用途，平台管理员同意后会发放到你的个人账号。</p>
          <label htmlFor="token-amount">申请数量</label><div className="token-input"><Coins size={17} /><input id="token-amount" type="number" min="100" step="100" value={amount} onChange={(event) => setAmount(event.target.value)} /></div>
          <label htmlFor="token-reason">申请说明</label><textarea id="token-reason" className="short" value={reason} onChange={(event) => setReason(event.target.value)} maxLength={500} />
          <button className="primary" type="submit" disabled={loading || Number(amount) < 100}><Plus size={16} /> {loading ? "提交中..." : "提交额度申请"}</button>
        </form>
      </div>
      <section className="panel api-usage-panel"><div className="section-heading"><div><p className="eyebrow">CALL HISTORY</p><h3>最近 API 调用</h3><p>可以看到每份问卷对应的调用类型和 Token 消耗。</p></div><FileKey2 size={21} /></div><div className="api-history-list">{!overview?.recent_usage.length ? <div className="empty">暂无调用记录。</div> : overview.recent_usage.map((item) => <div className="api-history-row" key={item.id}><span className="api-history-status"><i /> {item.status === "success" ? "成功" : item.status}</span><strong>{item.survey_name || (item.survey_id ? `问卷 #${item.survey_id}` : "平台服务")}</strong><span>{item.prompt_version} · {item.model_name}</span><b>{item.token_estimate.toLocaleString()} Token</b><small>{item.created_at.replace("T", " ")}</small></div>)}</div></section>
      <section className="panel token-request-history"><div className="section-heading"><div><p className="eyebrow">REQUESTS</p><h3>额度申请记录</h3></div><span className="muted">{requests.length} 条</span></div><div className="token-request-list">{!requests.length ? <div className="empty">还没有申请记录。</div> : requests.map((item) => <div className="token-request-row" key={item.id}><div><strong>{item.amount.toLocaleString()} Token</strong><span>{item.reason || "未填写申请说明"}</span></div><em className={`request-status ${item.status}`}>{requestStatusLabel(item.status)}</em><small>{item.created_at.replace("T", " ")}</small></div>)}</div></section>
    </section>
  );
}

function requestStatusLabel(status: string) {
  return ({ pending: "待审核", approved: "已发放", rejected: "已驳回" } as Record<string, string>)[status] || status;
}
