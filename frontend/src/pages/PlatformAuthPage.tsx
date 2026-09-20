import { ArrowLeft, KeyRound, ShieldCheck, Users } from "lucide-react";
import { useState } from "react";
import { postJson } from "../api/client";

export function PlatformAuthPage({ onAuthenticated }: { onAuthenticated: (data: { token: string; role?: string }) => void }) {
  const [username, setUsername] = useState("platform");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    try {
      const data = await postJson<{ token: string; role?: string }>("/api/platform/auth/login", { username, password });
      onAuthenticated(data);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "平台登录失败，请稍后重试。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="auth-page platform-auth-page">
      <div className="auth-aside">
        <p className="eyebrow">PLATFORM ADMINISTRATION</p>
        <h1>平台超级管理员后台</h1>
        <p>这里管理所有个人账号、问卷资源、Token 用量和平台内容审核。</p>
        <div className="auth-aside-points">
          <span><Users size={16} /> 查看全部账号和资源用量</span>
          <span><ShieldCheck size={16} /> 冻结或恢复异常账号</span>
          <span><KeyRound size={16} /> 处理额度申请和平台配置</span>
        </div>
      </div>
      <form className="auth-panel" onSubmit={(event) => void submit(event)}>
        <div className="auth-logo platform-auth-logo"><ShieldCheck size={25} /></div>
        <p className="eyebrow">SECURE ENTRY</p>
        <h2>登录平台后台</h2>
        <p className="auth-description">这是平台超级管理员专用入口，普通账号不能从这里登录。</p>
        <label htmlFor="platform-username">平台账号</label>
        <div className="input-with-icon"><ShieldCheck size={17} /><input id="platform-username" value={username} onChange={(event) => setUsername(event.target.value)} autoFocus required /></div>
        <label htmlFor="platform-password">登录密码</label>
        <div className="input-with-icon"><KeyRound size={17} /><input id="platform-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="请输入平台密码" required /></div>
        {message && <div className="form-error">{message}</div>}
        <button className="primary wide" type="submit" disabled={loading || !username.trim() || !password}>{loading ? "验证中..." : "进入平台后台"}</button>
        <button className="auth-back-link" type="button" onClick={() => window.location.assign("/login")}><ArrowLeft size={15} /> 返回普通用户登录</button>
        <p className="auth-hint">答辩演示账号：`platform` / `10124`。</p>
      </form>
    </section>
  );
}
