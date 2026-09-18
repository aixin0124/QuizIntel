import { Database, Play, Sparkles } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { adminFetchJson, adminPostJson, fetchJson, postJson } from "../api/client";
import type { PublicSurveyData, ResultPayload, SurveyStatus, SurveySummary, WrappedQuestion, WrappedSurvey } from "../types";

type UserPortalProps = {
  shareToken?: string | null;
  adminBrowse?: boolean;
  token?: string;
  renderResult: (result: ResultPayload) => ReactNode;
};

const browsableStatuses: SurveyStatus[] = ["collecting", "ended", "archived"];

export function UserPortal({ shareToken, adminBrowse = false, token, renderResult }: UserPortalProps) {
  const [surveys, setSurveys] = useState<SurveySummary[]>([]);
  const [selected, setSelected] = useState<{ id: number; survey: WrappedSurvey } | null>(null);
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [result, setResult] = useState<ResultPayload | null>(null);
  const [message, setMessage] = useState("");
  const [loading, setLoading] = useState(false);
  const [resultLoading, setResultLoading] = useState(false);
  const [submitted, setSubmitted] = useState(false);
  const [startedAt, setStartedAt] = useState(Date.now());
  const resultTimer = useRef<number | null>(null);
  const previewMode = Boolean(adminBrowse && token);

  useEffect(() => {
    void loadSurvey();
  }, [adminBrowse, shareToken, token]);

  useEffect(() => {
    return () => {
      if (resultTimer.current !== null) {
        window.clearTimeout(resultTimer.current);
      }
    };
  }, []);

  function clearResultTimer() {
    if (resultTimer.current !== null) {
      window.clearTimeout(resultTimer.current);
      resultTimer.current = null;
    }
  }

  async function loadSurvey() {
    try {
      if (adminBrowse && token) {
        await loadAdminSurveys(token);
        return;
      }
      if (shareToken) {
        await openSharedSurvey(shareToken);
        return;
      }
      setSubmitted(false);
      setMessage("请通过管理员分享出的专属链接访问问卷。");
    } catch (error) {
      setMessage(getErrorMessage(error));
    }
  }

  async function loadAdminSurveys(adminToken: string) {
    setLoading(true);
    setMessage("");
    try {
      const data = await adminFetchJson<{ items: SurveySummary[] }>("/api/surveys", adminToken);
      const published = data.items.filter((item) => browsableStatuses.includes(item.status));
      setSurveys(published);
      setSubmitted(false);
      if (published.length) {
        await openPreviewSurvey(published[0].id, adminToken);
      } else {
        setSelected(null);
        setMessage("暂无已发布的问卷，请先在管理后台完成发布。");
      }
    } catch (error) {
      setSelected(null);
      setMessage(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  async function openSharedSurvey(nextShareToken: string) {
    setLoading(true);
    setMessage("");
    try {
      const data = await fetchJson<PublicSurveyData>(
        `/api/public/share/${encodeURIComponent(nextShareToken)}`,
        {
          headers: {
            "X-Browser-Id": getBrowserSubmitId(),
            "X-Device-Fingerprint": buildBrowserFingerprint(),
          },
        },
      );
      if (data.submitted) {
        clearResultTimer();
        setSelected(null);
        setAnswers({});
        setResult(null);
        setResultLoading(false);
        setSubmitted(true);
        return;
      }
      if (!data.survey) throw new Error("分享问卷内容暂时不可用。");
      resetSurvey({ id: data.id, survey: data.survey });
    } catch (error) {
      setSelected(null);
      setMessage(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  async function openPreviewSurvey(id: number, adminToken: string) {
    setLoading(true);
    setMessage("");
    try {
      const data = await adminFetchJson<{ id: number; payload: WrappedSurvey }>(`/api/surveys/${id}`, adminToken);
      resetSurvey({ id, survey: data.payload });
    } catch (error) {
      setSelected(null);
      setMessage(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  function resetSurvey(data: { id: number; survey: WrappedSurvey }) {
    clearResultTimer();
    setSelected(data);
    setAnswers({});
    setResult(null);
    setResultLoading(false);
    setSubmitted(false);
    setStartedAt(Date.now());
  }

  async function submitAnswers() {
    if (!selected) return;
    if (!isSurveyComplete(selected.survey, answers)) {
      setMessage("请完成所有必答题后再提交。");
      return;
    }
    setLoading(true);
    setMessage("");
    setResultLoading(true);
    try {
      const payload = {
        survey_id: selected.id,
        share_token: shareToken,
        answers,
        source: previewMode ? "admin_preview" : "public_link",
        is_test: previewMode,
        duration_seconds: Math.max(1, Math.round((Date.now() - startedAt) / 1000)),
        browser_id: previewMode ? undefined : getBrowserSubmitId(),
        fingerprint: previewMode ? undefined : buildBrowserFingerprint(),
      };
      const data = previewMode && token
        ? await adminPostJson<{ result: ResultPayload }>("/api/responses", payload, token)
        : await postJson<{ result: ResultPayload }>("/api/responses", payload);
      setResult(data.result);
      setSubmitted(true);
      resultTimer.current = window.setTimeout(() => {
        resultTimer.current = null;
        setResultLoading(false);
        setMessage(previewMode ? "管理员浏览答卷已保存，已计入答卷明细和统计。" : "答卷已提交，感谢你的参与。");
      }, 1600);
    } catch (error) {
      setResultLoading(false);
      setMessage(getErrorMessage(error));
    } finally {
      setLoading(false);
    }
  }

  const completion = useMemo(() => {
    if (!selected) return 0;
    const required = selected.survey.questions.filter((question) => question.required);
    const answered = required.filter((question) => isAnswerPresent(answers[question.question_id])).length;
    return required.length ? Math.round((answered / required.length) * 100) : 100;
  }, [answers, selected]);
  const answerLocked = loading || resultLoading || submitted;

  return (
    <>
      <section className="hero compact-hero">
        <div>
          <p className="eyebrow">INTERACTIVE RESEARCH</p>
          <h1>用一分钟，完成一次有趣的市场调研。</h1>
          <p>{shareToken ? "这是一份通过专属分享链接打开的测评，按直觉作答即可。" : "选择一份测评，按直觉作答。你的答案将帮助品牌更好地理解真实需求。"}</p>
        </div>
        <div className="heroPanel user-hero-panel">
          <Sparkles size={23} />
          <strong>轻松作答，真实反馈</strong>
          <span>本页面不收集姓名、手机号等直接身份信息。</span>
        </div>
      </section>
      {message && <div className="notice">{message}</div>}
      <section className={`user-layout ${shareToken ? "shared-layout" : ""}`}>
        {!shareToken && <aside className="survey-list panel">
          <div className="section-heading">
            <div>
              <p className="eyebrow">SURVEYS</p>
              <h2>可参与的测评</h2>
            </div>
            <Database size={20} />
          </div>
          {!adminBrowse ? <Empty text="请通过管理员分享出的专属链接访问问卷。" /> : loading && !surveys.length ? <Empty text="正在读取已发布问卷..." /> : !surveys.length ? <Empty text="暂无已发布的测评，请由管理后台先生成一个。" /> : surveys.map((item) => <button key={item.id} className={`survey-item ${selected?.id === item.id ? "selected" : ""}`} onClick={() => token && void openPreviewSurvey(item.id, token)}>
            <span>{item.theme}</span>
            <strong>{item.survey_name}</strong>
            <small>{item.response_count} 人已完成</small>
          </button>)}
        </aside>}
        <section className="testSurface user-surface" aria-busy={resultLoading}>
          {resultLoading && <div className="result-loading-overlay result-loading" role="status" aria-live="polite"><div className="generation-icon"><Sparkles size={24} /></div><strong>正在解析问卷数据</strong><span>系统正在锁定你的答案并生成专属结果，请稍候。</span><div className="result-loading-dots" aria-hidden="true"><i /><i /><i /></div></div>}
          {!selected ? <div className="empty">{loading ? "正在读取问卷..." : submitted ? "【您已提交该问卷】" : shareToken ? "分享问卷暂时不可用。" : "请选择左侧测评开始体验。"}</div> : <>
            <p className="eyebrow">{selected.survey.theme}</p>
            <h2>{selected.survey.survey_name}</h2>
            <p className="lead">{selected.survey.tagline}</p>
            <p className="intro">{selected.survey.intro}</p>
            <div className="disclosure">{selected.survey.disclosure}</div>
            <div className="progress-label"><span>完成进度</span><b>{completion}%</b></div>
            <div className="progress"><span style={{ width: `${completion}%` }} /></div>
            {selected.survey.questions.map((question, index) => <QuestionInput key={question.question_id} index={index + 1} question={question} value={answers[question.question_id]} disabled={answerLocked} onChange={(value) => setAnswers({ ...answers, [question.question_id]: value })} />)}
            <button className="primary wide" onClick={() => void submitAnswers()} disabled={answerLocked || completion < 100}><Play size={18} /> {submitted ? "已提交" : loading ? "提交中..." : resultLoading ? "正在生成结果..." : "查看我的结果"}</button>
            {result && !resultLoading && renderResult(result)}
          </>}
        </section>
      </section>
    </>
  );
}

function QuestionInput({ index, question, value, disabled, onChange }: { index: number; question: WrappedQuestion; value: unknown; disabled: boolean; onChange: (value: unknown) => void }) {
  return <div className="question">
    <div className="question-meta"><span>{String(index).padStart(2, "0")}</span>{question.required && <em>必答</em>}</div>
    <h3>{question.public_text}</h3>
    {question.question_type === "multiple_choice" ? <div className="options">{question.options.map((option) => {
      const selected = Array.isArray(value) && value.includes(option);
      return <button className={selected ? "selected" : ""} key={option} disabled={disabled} onClick={() => {
        const current = Array.isArray(value) ? value : [];
        onChange(selected ? current.filter((item) => item !== option) : [...current, option]);
      }}>{option}</button>;
    })}</div> : question.question_type === "text" ? <input value={String(value || "")} onChange={(event) => onChange(event.target.value)} disabled={disabled} /> : <div className="options">{(question.options.length ? question.options : ["非常不像", "有点像", "很像"]).map((option) => <button className={value === option ? "selected" : ""} key={option} disabled={disabled} onClick={() => onChange(option)}>{option}</button>)}</div>}
  </div>;
}

function isAnswerPresent(value: unknown) {
  return Array.isArray(value) ? value.length > 0 : typeof value === "string" ? value.trim() !== "" : value !== undefined && value !== null;
}

function isSurveyComplete(survey: WrappedSurvey, answers: Record<string, unknown>) {
  return survey.questions.every((question) => !question.required || isAnswerPresent(answers[question.question_id]));
}

function getBrowserSubmitId() {
  const key = "fun_research_browser_id";
  const existing = localStorage.getItem(key);
  if (existing) return existing;
  const value = crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`;
  localStorage.setItem(key, value);
  return value;
}

function buildBrowserFingerprint() {
  return [navigator.userAgent, navigator.language, screen.width, screen.height, Intl.DateTimeFormat().resolvedOptions().timeZone].join("|");
}

function Empty({ text }: { text: string }) {
  return <div className="empty">{text}</div>;
}

function getErrorMessage(error: unknown) {
  return error instanceof Error ? error.message : "发生未知错误";
}
