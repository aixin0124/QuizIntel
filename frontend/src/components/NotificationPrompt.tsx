import { Bell, CheckCircle2, ExternalLink, X } from "lucide-react";
import { useEffect, useState } from "react";
import { adminFetchJson, adminPostJson } from "../api/client";
import type { UserNotification } from "../types";

export function NotificationPrompt({ token }: { token: string }) {
  const [items, setItems] = useState<UserNotification[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    void adminFetchJson<{ items: UserNotification[] }>("/api/notifications/unread", token)
      .then((data) => {
        if (!cancelled) setItems(data.items);
      })
      .catch(() => undefined)
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [token]);

  async function acknowledge(surveyId?: number | null) {
    try {
      await adminPostJson("/api/notifications/read-all", {}, token);
    } catch {
      return;
    }
    setItems([]);
    if (surveyId) window.location.assign(`/console?survey_id=${surveyId}`);
  }

  if (loading || !items.length) return null;
  const firstSurveyId = items.find((item) => item.survey_id)?.survey_id;
  return (
    <div className="modal-overlay notification-overlay" role="presentation">
      <div className="notification-dialog" role="dialog" aria-modal="true" aria-labelledby="notification-title">
        <div className="notification-dialog-head">
          <div className="notification-icon"><Bell size={20} /></div>
          <button className="icon-button" onClick={() => void acknowledge()} title="关闭" aria-label="关闭"><X size={17} /></button>
        </div>
        <p className="eyebrow">ACCOUNT NOTIFICATION</p>
        <h2 id="notification-title">有新的平台处理结果</h2>
        <div className="notification-list">
          {items.map((item) => <article key={item.id}><strong>{item.title}</strong><p>{item.content}</p><small>{item.created_at.replace("T", " ")}</small></article>)}
        </div>
        <div className="notification-actions">
          {firstSurveyId && <button className="secondary" onClick={() => void acknowledge(firstSurveyId)}><ExternalLink size={15} /> 去编辑问卷</button>}
          <button className="primary" onClick={() => void acknowledge()}><CheckCircle2 size={15} /> 我知道了</button>
        </div>
      </div>
    </div>
  );
}
