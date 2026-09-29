import { KeyRound, ShieldCheck, Users } from "lucide-react";
import { useState } from "react";
import { adminPostJson } from "../api/client";
import { roleLabel } from "../permissions";

export function SecurityPanel({ token, role }: { token: string; role: string }) {
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function changePassword(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    try {
      await adminPostJson("/api/admin/password", { old_password: oldPassword, new_password: newPassword }, token);
      setOldPassword("");
      setNewPassword("");
      setMessage("密码已更新。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "密码修改失败。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="security-panel">
      <div className="page-title"><div><p className="eyebrow">ACCOUNT & SECURITY</p><h2>账号与安全</h2><p>个人账号拥有自己问卷的完整管理权限，问卷数据只在当前个人工作区内管理。</p></div><ShieldCheck size={26} /></div>
      {message && <div className="notice">{message}</div>}
      <div className="security-grid">
        <form className="panel security-form" onSubmit={(event) => void changePassword(event)}>
          <div className="section-heading"><div><h3><KeyRound size={18} /> 修改我的密码</h3><p>新密码至少需要 6 位。</p></div></div>
          <label htmlFor="old-password">原密码</label>
          <input id="old-password" type="password" value={oldPassword} onChange={(event) => setOldPassword(event.target.value)} required />
          <label htmlFor="new-password">新密码</label>
          <input id="new-password" type="password" value={newPassword} onChange={(event) => setNewPassword(event.target.value)} minLength={6} required />
          <button className="primary" type="submit" disabled={loading}><KeyRound size={16} /> 保存新密码</button>
        </form>
        <div className="panel security-form">
          <div className="section-heading"><div><h3><Users size={18} /> 当前账号权限</h3><p>权限随资源归属变化，不再创建全局问卷管理员账号。</p></div></div>
          <div className="security-role-card"><strong>{roleLabel(role)}</strong><span>可以完整管理当前个人工作区内创建的问卷、答卷、分析和导出数据。</span></div>
          <p className="security-access-note"><ShieldCheck size={16} /> 当前账号的问卷默认归本人管理。</p>
        </div>
      </div>
    </section>
  );
}
