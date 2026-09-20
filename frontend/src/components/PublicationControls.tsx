import { Archive, CheckCircle2, Play } from "lucide-react";
import { useState } from "react";
import { adminPostJson } from "../api/client";
import type { ResearchAnalysis, SurveyStatus, SurveySummary } from "../types";
import { canManageTenant } from "../permissions";

type PublicationControlsProps = {
  surveyId: number;
  token: string;
  role: string;
  status: SurveyStatus;
  onSaved: (item: SurveySummary, analysis?: ResearchAnalysis | null) => void;
};

export function PublicationControls({
  surveyId,
  token,
  role,
  status,
  onSaved,
}: PublicationControlsProps) {
  const canManage = canManageTenant(role);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");

  async function save(next = status) {
    if (!canManage || saving) return;
    setSaving(true);
    setMessage("");
    try {
      const data = await adminPostJson<{ item: SurveySummary; analysis?: ResearchAnalysis | null }>(
        `/api/surveys/${surveyId}/publication`,
        {
          status: next,
        },
        token,
      );
      onSaved(data.item, data.analysis);
      setMessage(next === "ended" ? "问卷已结束，答卷数量已锁定。" : "采集状态已更新。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "采集状态更新失败。");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      {canManage && status === "draft" && <button className="primary" onClick={() => void save("collecting")} disabled={saving}><Play size={16} /> {saving ? "发布中..." : "发布并开始收集"}</button>}
      {canManage && status === "collecting" && <button className="secondary" onClick={() => void save("ended")} disabled={saving}><CheckCircle2 size={16} /> {saving ? "结束中..." : "结束问卷"}</button>}
      {message && <span className="publication-action-message">{message}</span>}
    </>
  );
}

export function ArchiveSurveyAction({ surveyId, token, role, status, onSaved }: { surveyId: number; token: string; role: string; status: SurveyStatus; onSaved: (item: SurveySummary) => void }) {
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const [dialogOpen, setDialogOpen] = useState(false);
  if (role !== "admin" || status !== "ended") return null;

  async function archive() {
    if (saving) return;
    setSaving(true);
    setMessage("");
    try {
      const data = await adminPostJson<{ item: SurveySummary }>(
        `/api/surveys/${surveyId}/publication`,
        { status: "archived" },
        token,
      );
      onSaved(data.item);
      setDialogOpen(false);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "归档失败。");
    } finally {
      setSaving(false);
    }
  }

  return (
    <>
      <button className="secondary" onClick={() => setDialogOpen(true)} disabled={saving}><Archive size={16} /> 归档</button>
      {message && <span className="publication-action-message">{message}</span>}
      {dialogOpen && <div className="archive-dialog-overlay" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setDialogOpen(false); }}>
        <div className="archive-dialog" role="dialog" aria-modal="true" aria-labelledby="archive-dialog-title">
          <div className="archive-dialog-icon"><Archive size={22} /></div>
          <p className="eyebrow">ARCHIVE SURVEY</p>
          <h2 id="archive-dialog-title">确认归档这份问卷？</h2>
          <p>归档后将不能再收集问卷。</p>
          <div className="archive-dialog-actions">
            <button className="secondary" onClick={() => setDialogOpen(false)} disabled={saving}>取消</button>
            <button className="primary" onClick={() => void archive()} disabled={saving}><Archive size={16} /> {saving ? "归档中..." : "确认归档"}</button>
          </div>
        </div>
      </div>}
    </>
  );
}
