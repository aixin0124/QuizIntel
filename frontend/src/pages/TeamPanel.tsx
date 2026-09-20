import { Bell, Check, Eye, Mail, Pencil, ShieldCheck, UserPlus, Users, X } from "lucide-react";
import { useEffect, useState } from "react";
import { adminFetchJson, adminPostJson } from "../api/client";
import type { SurveyPermission, SurveySummary, Team, TeamInvitation, TeamMember } from "../types";

export function TeamPanel({ token }: { token: string }) {
  const [teams, setTeams] = useState<Team[]>([]);
  const [selectedTeamId, setSelectedTeamId] = useState<number | null>(null);
  const [members, setMembers] = useState<TeamMember[]>([]);
  const [sentInvitations, setSentInvitations] = useState<TeamInvitation[]>([]);
  const [receivedInvitations, setReceivedInvitations] = useState<TeamInvitation[]>([]);
  const [surveys, setSurveys] = useState<SurveySummary[]>([]);
  const [permissions, setPermissions] = useState<SurveyPermission[]>([]);
  const [selectedSurveyId, setSelectedSurveyId] = useState<number | null>(null);
  const [inviteUsername, setInviteUsername] = useState("");
  const [invitePermission, setInvitePermission] = useState<"viewer" | "editor">("viewer");
  const [accessUserId, setAccessUserId] = useState<number | "">("");
  const [accessPermission, setAccessPermission] = useState<"viewer" | "editor" | "none">("viewer");
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);

  const selectedTeam = teams.find((team) => team.id === selectedTeamId) || null;
  const isManager = selectedTeam?.member_role === "manager";

  async function loadTeams() {
    try {
      const data = await adminFetchJson<{ items: Team[] }>("/api/tenant/teams", token);
      setTeams(data.items);
      const defaultTeam = data.items.find((team) => team.name === "我的问卷") || data.items[0];
      setSelectedTeamId((current) => current && data.items.some((team) => team.id === current) ? current : defaultTeam?.id || null);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "协作空间读取失败。");
    }
  }

  async function loadReceivedInvitations() {
    try {
      const data = await adminFetchJson<{ items: TeamInvitation[] }>("/api/invitations", token);
      setReceivedInvitations(data.items);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "邀请消息读取失败。");
    }
  }

  async function loadSurveys() {
    try {
      const data = await adminFetchJson<{ items: SurveySummary[] }>("/api/surveys", token);
      setSurveys(data.items);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "问卷列表读取失败。");
    }
  }

  async function loadSelectedTeam(teamId: number) {
    try {
      const data = await adminFetchJson<{ items: TeamMember[]; invitations: TeamInvitation[] }>(`/api/tenant/teams/${teamId}/members`, token);
      setMembers(data.items);
      setSentInvitations(data.invitations);
    } catch {
      setMembers([]);
      setSentInvitations([]);
    }
  }

  async function loadSurveyAccess(surveyId: number) {
    try {
      const data = await adminFetchJson<{ items: SurveyPermission[] }>(`/api/surveys/${surveyId}/access`, token);
      setPermissions(data.items);
      setAccessUserId("");
      setAccessPermission("viewer");
    } catch {
      setPermissions([]);
    }
  }

  useEffect(() => {
    void Promise.all([loadTeams(), loadReceivedInvitations(), loadSurveys()]);
  }, [token]);

  useEffect(() => {
    if (selectedTeamId) {
      void loadSelectedTeam(selectedTeamId);
    } else {
      setMembers([]);
      setSentInvitations([]);
    }
  }, [selectedTeamId, token]);

  useEffect(() => {
    const nextSurveyId = surveys[0]?.id || null;
    setSelectedSurveyId((current) => current && surveys.some((survey) => survey.id === current) ? current : nextSurveyId);
  }, [surveys]);

  useEffect(() => {
    if (selectedSurveyId && isManager) {
      void loadSurveyAccess(selectedSurveyId);
    } else {
      setPermissions([]);
    }
  }, [selectedSurveyId, isManager, token]);

  async function invite(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedTeamId) return;
    setLoading(true);
    setMessage("");
    try {
      await adminPostJson(`/api/tenant/teams/${selectedTeamId}/invitations`, {
        username: inviteUsername,
        permission: invitePermission,
      }, token);
      setInviteUsername("");
      setMessage("邀请已发送，等待对方确认。");
      await loadSelectedTeam(selectedTeamId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "邀请发送失败。");
    } finally {
      setLoading(false);
    }
  }

  async function respond(invitation: TeamInvitation, accepted: boolean) {
    setLoading(true);
    setMessage("");
    try {
      await adminPostJson(`/api/invitations/${invitation.id}/respond`, { accepted }, token);
      setMessage(accepted ? "已加入个人问卷空间。" : "已拒绝这条邀请。");
      await Promise.all([loadReceivedInvitations(), loadTeams()]);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "邀请处理失败。");
    } finally {
      setLoading(false);
    }
  }

  async function saveAccess(event: React.FormEvent) {
    event.preventDefault();
    if (!selectedSurveyId || !accessUserId) return;
    setLoading(true);
    setMessage("");
    try {
      await adminPostJson(`/api/surveys/${selectedSurveyId}/access`, {
        user_id: Number(accessUserId),
        permission: accessPermission === "none" ? null : accessPermission,
      }, token);
      setMessage(accessPermission === "none" ? "已收回该成员的问卷访问权限。" : "问卷访问权限已保存。");
      await loadSurveyAccess(selectedSurveyId);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "问卷权限保存失败。");
    } finally {
      setLoading(false);
    }
  }

  const pendingInvitations = receivedInvitations.filter((item) => item.status === "pending");

  return (
    <section className="team-page">
      <div className="page-title">
        <div><p className="eyebrow">PERSONAL WORKSPACE</p><h2>协作成员</h2><p>个人账号默认管理自己的全部问卷；只有需要协作时，才邀请成员并按问卷授权。</p></div>
        <Users size={25} />
      </div>
      {message && <div className="notice">{message}</div>}

      <section className="panel collaboration-intro">
        <div className="collaboration-intro-main">
          <div className="collaboration-intro-icon"><Users size={20} /></div>
          <div><strong>我的问卷空间</strong><p>所有新建问卷都会直接归你管理，不需要先创建协作空间。协作成员只能访问你明确授权的问卷。</p></div>
        </div>
        <span className="collaboration-badge">{selectedTeam ? "默认协作空间" : "等待加入协作"}</span>
      </section>

      <section className="panel invitation-inbox">
        <div className="section-heading"><div><p className="eyebrow">MESSAGE CENTER</p><h3><Bell size={18} /> 邀请消息</h3><p>其他用户邀请你协作时，会在这里接受或拒绝。</p></div><strong className="inbox-count">{pendingInvitations.length}</strong></div>
        {!receivedInvitations.length ? <div className="empty">暂无邀请消息。</div> : <div className="invitation-list">{receivedInvitations.map((invitation) => (
          <div className="invitation-row" key={invitation.id}>
            <div><strong>{invitation.team_name || "个人问卷空间"}</strong><span>{invitation.invited_by_name || invitation.invited_by_username || "其他用户"} 邀请你协作，权限为“{invitation.permission === "editor" ? "可编辑" : "仅查看"}”。</span><small>{invitation.created_at.replace("T", " ")}</small></div>
            {invitation.status === "pending" ? <div className="platform-row-actions"><button className="icon-button approve" onClick={() => void respond(invitation, true)} title="接受邀请" aria-label="接受邀请"><Check size={16} /></button><button className="icon-button reject" onClick={() => void respond(invitation, false)} title="拒绝邀请"><X size={16} /></button></div> : <em className={`request-status ${invitation.status}`}>{invitation.status === "accepted" ? "已接受" : "已拒绝"}</em>}
          </div>
        ))}</div>}
      </section>

      {selectedTeam && <section className="team-management-grid">
        <div className="panel team-members-panel">
          <div className="section-heading"><div><p className="eyebrow">COLLABORATORS</p><h3><Users size={18} /> 协作成员</h3><p>{isManager ? "邀请已注册账号，并选择默认的查看或编辑权限。" : "你是这个个人空间的协作成员。"}</p></div></div>
          {isManager && <form className="invite-form" onSubmit={(event) => void invite(event)}><label htmlFor="invite-username">账号或邮箱</label><div className="invite-row"><input id="invite-username" value={inviteUsername} onChange={(event) => setInviteUsername(event.target.value)} placeholder="输入已注册用户账号" required /><select value={invitePermission} onChange={(event) => setInvitePermission(event.target.value as "viewer" | "editor")}><option value="viewer">仅查看</option><option value="editor">可编辑</option></select><button className="primary" type="submit" disabled={loading}><UserPlus size={16} /> 邀请</button></div></form>}
          <div className="member-list">{!members.length ? <div className="empty">当前暂无已接受成员。</div> : members.map((member) => <div className="member-row" key={member.id}><div className="member-avatar"><Users size={16} /></div><div><strong>{member.display_name || member.username}</strong><small>{member.username}{member.email ? ` · ${member.email}` : ""}</small></div><em>{member.member_role === "manager" ? "空间所有者" : member.member_role === "editor" ? "可编辑" : "仅查看"}</em></div>)}</div>
          {isManager && sentInvitations.some((item) => item.status === "pending") && <div className="sent-invites"><h4><Mail size={16} /> 待确认邀请</h4>{sentInvitations.filter((item) => item.status === "pending").map((item) => <span key={item.id}>{item.invitee_name || item.invitee_username} · {item.permission === "editor" ? "可编辑" : "仅查看"}</span>)}</div>}
        </div>

        {isManager && <div className="panel survey-access-panel">
          <div className="section-heading"><div><p className="eyebrow">SURVEY ACCESS</p><h3><ShieldCheck size={18} /> 问卷访问权限</h3><p>为每一份问卷单独设置成员权限，避免协作范围过大。</p></div></div>
          {!surveys.length ? <div className="empty">还没有可授权的问卷。</div> : <>
            <label htmlFor="access-survey">选择问卷</label>
            <select id="access-survey" value={selectedSurveyId || ""} onChange={(event) => setSelectedSurveyId(Number(event.target.value))}>{surveys.map((survey) => <option key={survey.id} value={survey.id}>{survey.survey_name}</option>)}</select>
            <div className="permission-list">{permissions.map((item) => <div className="permission-row" key={item.user_id}><span>{item.display_name || item.username}</span><em>{item.permission === "editor" ? <><Pencil size={13} /> 可编辑</> : <><Eye size={13} /> 仅查看</>}</em></div>)}</div>
            <form className="access-form" onSubmit={(event) => void saveAccess(event)}><label htmlFor="access-user">选择协作成员</label><select id="access-user" value={accessUserId} onChange={(event) => setAccessUserId(event.target.value ? Number(event.target.value) : "")}><option value="">请选择成员</option>{members.filter((member) => member.member_role !== "manager").map((member) => <option key={member.id} value={member.id}>{member.display_name || member.username}</option>)}</select><div className="access-form-row"><select value={accessPermission} onChange={(event) => setAccessPermission(event.target.value as "viewer" | "editor" | "none")}><option value="viewer">仅查看</option><option value="editor">可编辑</option><option value="none">收回权限</option></select><button className="secondary" type="submit" disabled={loading || !accessUserId}><ShieldCheck size={16} /> 保存权限</button></div></form>
          </>}
        </div>}
      </section>}
    </section>
  );
}
