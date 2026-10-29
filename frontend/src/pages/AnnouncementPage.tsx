import { Bell, Check, Megaphone, Pencil, Plus, Send, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { adminFetchJson, adminPostJson, fetchJson } from "../api/client";
import type { Announcement } from "../types";

type AnnouncementPageProps = { token?: string; isPlatformAdmin?: boolean };

const guestAnnouncementReadStorageKey = "fun_research_read_announcements";

function getGuestAnnouncementReads(): Record<string, string> {
  try {
    const raw = localStorage.getItem(guestAnnouncementReadStorageKey);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (Array.isArray(parsed)) return Object.fromEntries(parsed.map((id) => [String(id), "legacy"]));
    if (parsed && typeof parsed === "object") return parsed as Record<string, string>;
  } catch {
    localStorage.removeItem(guestAnnouncementReadStorageKey);
  }
  return {};
}

function saveGuestAnnouncementReads(reads: Record<string, string>) {
  localStorage.setItem(guestAnnouncementReadStorageKey, JSON.stringify(reads));
}

function guestAnnouncementVersion(item: Announcement) {
  return item.updated_at || item.published_at || item.created_at;
}

export function AnnouncementPage({ token, isPlatformAdmin = false }: AnnouncementPageProps) {
  const [items, setItems] = useState<Announcement[]>([]);
  const [selected, setSelected] = useState<Announcement | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    try {
      const data = isPlatformAdmin && token
        ? await adminFetchJson<{ items: Announcement[] }>("/api/platform/announcements", token)
        : await fetchJson<{ items: Announcement[] }>("/api/announcements", token ? { headers: { "X-Admin-Token": token } } : undefined);
      setItems(data.items);
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "公告读取失败。");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void load(); }, [token, isPlatformAdmin]);

  async function markAllRead() {
    if (!token) {
      const reads = getGuestAnnouncementReads();
      items.forEach((item) => { reads[String(item.id)] = guestAnnouncementVersion(item); });
      saveGuestAnnouncementReads(reads);
      setItems((current) => current.map((item) => ({ ...item, is_read: true })));
      return;
    }
    try {
      await adminPostJson("/api/announcements/read-all", {}, token);
      setItems((current) => current.map((item) => ({ ...item, is_read: true })));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "公告已读状态更新失败。");
    }
  }

  const unreadCount = useMemo(() => items.filter((item) => item.status === "published" && !item.is_read).length, [items]);
  return (
    <section className="announcement-page">
      <div className="page-title">
        <div><p className="eyebrow">PLATFORM ANNOUNCEMENTS</p><h1>公告</h1><p>查看平台最新通知与服务动态。</p></div>
        <Megaphone size={26} />
      </div>
      {message && <div className="notice">{message}</div>}
      {isPlatformAdmin && token && <AnnouncementEditor token={token} selected={selected} onSaved={() => { setSelected(null); void load(); }} onCancel={() => setSelected(null)} />}
      <div className="announcement-toolbar">
        <span><Bell size={16} /> {unreadCount ? `${unreadCount} 条未读公告` : "已全部阅读"}</span>
        {unreadCount > 0 && <button className="secondary" onClick={() => void markAllRead()}><Check size={15} /> 全部标为已读</button>}
      </div>
      <div className="announcement-list">
        {loading ? <div className="empty">正在读取公告...</div> : !items.length ? <div className="empty">暂无公告。</div> : items.map((item) => (
          <article className={`announcement-item ${item.is_read ? "read" : "unread"}`} key={item.id}>
            <div className="announcement-item-head"><span>{item.status === "published" ? "已发布" : item.status === "draft" ? "草稿" : "已下线"}</span><small>{(item.published_at || item.updated_at).replace("T", " ")}</small></div>
            <h2>{item.title}</h2><p>{item.content}</p>
            {isPlatformAdmin && token ? <div className="announcement-item-actions"><button className="secondary" onClick={() => setSelected(item)}><Pencil size={15} /> 编辑</button>{item.status === "published" ? <button className="secondary" onClick={() => void updateStatus(token, item, "archived", load, setMessage)}><X size={15} /> 下线</button> : <button className="primary" onClick={() => void updateStatus(token, item, "published", load, setMessage)}><Send size={15} /> 发布</button>}</div> : null}
          </article>
        ))}
      </div>
    </section>
  );
}

function AnnouncementEditor({ token, selected, onSaved, onCancel }: { token: string; selected: Announcement | null; onSaved: () => void; onCancel: () => void }) {
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");
  const [status, setStatus] = useState<"draft" | "published">("draft");
  const [saving, setSaving] = useState(false);
  useEffect(() => { setTitle(selected?.title || ""); setContent(selected?.content || ""); setStatus(selected?.status === "published" ? "published" : "draft"); }, [selected]);
  async function save() {
    setSaving(true);
    try {
      if (selected) await adminPostJson(`/api/platform/announcements/${selected.id}`, { title, content, status }, token);
      else await adminPostJson("/api/platform/announcements", { title, content, status }, token);
      onSaved();
    } catch (error) {
      window.alert(error instanceof Error ? error.message : "公告保存失败。");
    } finally {
      setSaving(false);
    }
  }
  return <div className="announcement-editor"><div className="section-heading"><div><p className="eyebrow">ANNOUNCEMENT MANAGEMENT</p><h2>{selected ? "编辑公告" : "新建公告"}</h2></div><Plus size={19} /></div><label>公告标题<input value={title} onChange={(event) => setTitle(event.target.value)} maxLength={120} placeholder="例如：平台服务升级通知" /></label><label>公告内容<textarea value={content} onChange={(event) => setContent(event.target.value)} maxLength={5000} rows={5} placeholder="输入需要通知所有用户的内容" /></label><div className="announcement-editor-actions"><button className="primary" onClick={() => void save()} disabled={saving || !title.trim() || !content.trim()}>{saving ? "保存中..." : status === "published" ? "保存并发布" : "保存草稿"}</button>{selected && <button className="secondary" onClick={onCancel}>取消编辑</button>}</div></div>;
}

async function updateStatus(token: string, item: Announcement, status: "published" | "archived", load: () => Promise<void>, setMessage: (message: string) => void) {
  try {
    await adminPostJson(`/api/platform/announcements/${item.id}`, { title: item.title, content: item.content, status }, token);
    setMessage(status === "published" ? "公告已发布。" : "公告已下线。" );
    await load();
  } catch (error) {
    setMessage(error instanceof Error ? error.message : "公告状态更新失败。");
  }
}

export function AnnouncementHomePrompt({ token }: { token?: string }) {
  const [items, setItems] = useState<Announcement[]>([]);
  const [visible, setVisible] = useState(false);
  useEffect(() => {
    let cancelled = false;
    void fetchJson<{ items: Announcement[] }>("/api/announcements", token ? { headers: { "X-Admin-Token": token } } : undefined)
      .then((data) => {
        if (cancelled) return;
        const localRead = getGuestAnnouncementReads();
        const unread = data.items.filter((item) => !item.is_read && (token || localRead[String(item.id)] !== guestAnnouncementVersion(item)));
        setItems(unread);
        setVisible(unread.length > 0);
      })
      .catch(() => undefined);
    return () => { cancelled = true; };
  }, [token]);
  if (!visible || !items.length) return null;
  async function confirm() {
    if (token) await adminPostJson("/api/announcements/read-all", {}, token).catch(() => undefined);
    else {
      const reads = getGuestAnnouncementReads();
      items.forEach((item) => { reads[String(item.id)] = guestAnnouncementVersion(item); });
      saveGuestAnnouncementReads(reads);
    }
    setVisible(false);
  }
  return <div className="modal-overlay announcement-overlay" role="presentation"><div className="announcement-dialog" role="dialog" aria-modal="true" aria-labelledby="announcement-dialog-title"><div className="notification-icon"><Megaphone size={20} /></div><p className="eyebrow">NEW ANNOUNCEMENT</p><h2 id="announcement-dialog-title">平台有新的公告</h2><div className="announcement-dialog-list">{items.map((item) => <article key={item.id}><h3>{item.title}</h3><p>{item.content}</p><small>{(item.published_at || item.created_at).replace("T", " ")}</small></article>)}</div><button className="primary wide" onClick={() => void confirm()}><Check size={16} /> 我知道了</button></div></div>;
}
