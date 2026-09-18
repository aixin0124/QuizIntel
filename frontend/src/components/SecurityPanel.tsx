import { KeyRound, ShieldCheck, UserPlus, Users } from "lucide-react";
import { useEffect, useState } from "react";
import { adminFetchJson, adminPostJson } from "../api/client";
import type { AdminUser } from "../types";

export function SecurityPanel({ token, role }: { token: string; role: string }) {
  const [users, setUsers] = useState<AdminUser[]>([]);
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [newRole, setNewRole] = useState("viewer");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  async function loadUsers() {
    if (role !== "admin") return;
    try {
      const data = await adminFetchJson<{ items: AdminUser[] }>("/api/admin/users", token);
      setUsers(data.items);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "账号列表读取失败。");
    }
  }

  useEffect(() => { void loadUsers(); }, [role, token]);

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

  async function createUser(event: React.FormEvent) {
    event.preventDefault();
    setLoading(true);
    setMessage("");
    try {
      await adminPostJson("/api/admin/users", { username, password, role: newRole }, token);
      setUsername("");
      setPassword("");
      await loadUsers();
      setMessage("后台账号已创建。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "账号创建失败。");
    } finally {
      setLoading(false);
    }
  }

  return (
    <section className="security-panel">
      <div className="page-title"><div><p className="eyebrow">SECURITY & ACCESS</p><h2>后台账号与安全</h2><p>管理员账号使用哈希密码和过期会话；只读查看者只能查看数据。</p></div><ShieldCheck size={26} /></div>
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
        {role === "admin" ? <form className="panel security-form" onSubmit={(event) => void createUser(event)}>
          <div className="section-heading"><div><h3><UserPlus size={18} /> 新建后台账号</h3><p>可创建管理员或只读查看者。</p></div></div>
          <label htmlFor="new-username">账号名</label>
          <input id="new-username" value={username} onChange={(event) => setUsername(event.target.value)} required />
          <label htmlFor="new-user-password">初始密码</label>
          <input id="new-user-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} minLength={6} required />
          <label htmlFor="new-user-role">角色</label>
          <select id="new-user-role" value={newRole} onChange={(event) => setNewRole(event.target.value)}><option value="viewer">只读查看者</option><option value="admin">管理员</option></select>
          <button className="secondary" type="submit" disabled={loading}><UserPlus size={16} /> 创建账号</button>
        </form> : <div className="panel security-form"><h3><Users size={18} /> 当前角色</h3><p>只读查看者可以查看问卷、答卷和分析，但不能修改设置。</p></div>}
      </div>
      {role === "admin" && <section className="panel security-users"><div className="section-heading"><div><h3><Users size={18} /> 已有账号</h3><p>账号密码不会在列表中展示。</p></div></div><div className="security-user-list">{users.map((user) => <div className="security-user-row" key={user.id}><strong>{user.username}</strong><span>{user.role === "admin" ? "管理员" : "只读查看者"}</span><small>{user.is_active ? "启用中" : "已停用"}</small></div>)}</div></section>}
    </section>
  );
}
