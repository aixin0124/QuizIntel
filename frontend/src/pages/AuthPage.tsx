import { KeyRound, Mail, ShieldCheck, User, UserPlus } from "lucide-react";
import { useState } from "react";
import { postJson } from "../api/client";

type AuthPageProps = {
  mode: "login" | "register";
  onAuthenticated: (data: { token: string; role?: string }) => void;
};

export function AuthPage({ mode, onAuthenticated }: AuthPageProps) {
  const [activeMode, setActiveMode] = useState(mode);
  const [username, setUsername] = useState(activeMode === "login" ? "aixin" : "");
  const [password, setPassword] = useState("");
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  function switchMode(next: "login" | "register") {
    setActiveMode(next);
    setMessage("");
    setUsername(next === "login" ? "aixin" : "");
  }

  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    try {
      const data = activeMode === "login"
        ? await postJson<{ token: string; role?: string }>("/api/auth/login", { username, password })
        : await postJson<{ token: string; role?: string }>("/api/auth/register", {
          username,
          password,
          email,
        });
      onAuthenticated(data);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "请求失败，请稍后重试。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="auth-page">
      <div className="auth-aside">
        <p className="eyebrow">FUN RESEARCH PLATFORM</p>
        <h1>让每一次调研，都有一个清晰的工作区。</h1>
        <p>个人问卷、可选协作、API Token 和平台治理统一在同一套账号体系里。</p>
        <div className="auth-aside-points">
          <span><ShieldCheck size={16} /> 每个账号拥有独立问卷空间</span>
          <span><UserPlus size={16} /> 可邀请成员协作管理问卷</span>
          <span><KeyRound size={16} /> 生成与解析用量透明可见</span>
        </div>
      </div>
      <form className="auth-panel" onSubmit={(event) => void submit(event)}>
        <div className="auth-logo"><img src="/brand-icon.png" alt="" /></div>
        <p className="eyebrow">{activeMode === "login" ? "WELCOME BACK" : "CREATE YOUR SPACE"}</p>
        <h2>{activeMode === "login" ? "登录趣测智研" : "创建个人账号"}</h2>
        <p className="auth-description">{activeMode === "login" ? "进入你的问卷工作区和 API 服务。" : "注册后会自动创建个人问卷空间和初始 Token 额度。"}</p>
        <div className="auth-tabs"><button type="button" className={activeMode === "login" ? "active" : ""} onClick={() => switchMode("login")}><User size={15} /> 登录</button><button type="button" className={activeMode === "register" ? "active" : ""} onClick={() => switchMode("register")}><UserPlus size={15} /> 注册</button></div>
        <label htmlFor="auth-username">账号</label><div className="input-with-icon"><User size={17} /><input id="auth-username" value={username} onChange={(event) => setUsername(event.target.value)} placeholder="请输入账号" autoFocus required /></div>
        {activeMode === "register" && <><label htmlFor="auth-email">联系邮箱（可选）</label><div className="input-with-icon"><Mail size={17} /><input id="auth-email" type="email" value={email} onChange={(event) => setEmail(event.target.value)} placeholder="name@company.com" /></div></>}
        <label htmlFor="auth-password">密码</label><div className="input-with-icon"><KeyRound size={17} /><input id="auth-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder={activeMode === "register" ? "至少 6 位" : "请输入密码"} minLength={activeMode === "register" ? 6 : undefined} required /></div>
        {message && <div className="form-error">{message}</div>}
        <button className="primary wide" type="submit" disabled={loading}>{loading ? "处理中..." : activeMode === "login" ? "进入控制台" : "创建并进入工作区"}</button>
        {activeMode === "login" && username === "aixin" && <p className="auth-hint">答辩演示账号：`aixin` / `123456`。</p>}
        {activeMode === "login" && <p className="auth-role-note">平台超级管理员请从独立的“平台管理”入口登录。</p>}
      </form>
    </section>
  );
}
