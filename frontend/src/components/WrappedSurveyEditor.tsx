import { Plus, Save, Trash2, X } from "lucide-react";
import { useEffect, useState } from "react";
import { adminPostJson } from "../api/client";
import type { SurveyStatus, WrappedQuestion, WrappedSurvey } from "../types";
import { canManageTenant } from "../permissions";

type WrappedSurveyEditorProps = {
  surveyId: number;
  survey: WrappedSurvey;
  token: string;
  role: string;
  status: SurveyStatus;
  onSaved: (survey: WrappedSurvey) => void;
};

export function WrappedSurveyEditor({ surveyId, survey, token, role, status, onSaved }: WrappedSurveyEditorProps) {
  const [draft, setDraft] = useState(survey);
  const [saving, setSaving] = useState(false);
  const [message, setMessage] = useState("");
  const canManage = canManageTenant(role);
  const canEdit = canManage && status === "draft";

  useEffect(() => setDraft(survey), [survey]);

  function updateQuestion(index: number, patch: Partial<WrappedQuestion>) {
    setDraft({ ...draft, questions: draft.questions.map((question, itemIndex) => itemIndex === index ? { ...question, ...patch } : question) });
  }

  function updateOption(questionIndex: number, optionIndex: number, value: string) {
    const question = draft.questions[questionIndex];
    if (!question) return;
    updateQuestion(questionIndex, { options: question.options.map((option, itemIndex) => itemIndex === optionIndex ? value : option) });
  }

  function addQuestion() {
    setDraft({
      ...draft,
      questions: [
        ...draft.questions,
        {
          question_id: `iq${draft.questions.length + 1}`,
          public_text: "",
          question_type: "single_choice",
          options: ["", ""],
          research_tag: "",
          source_text: "",
          required: true,
          research_refs: [],
          rationale: "",
        },
      ],
    });
  }

  async function save() {
    if (!canEdit || saving) return;
    setSaving(true);
    setMessage("");
    try {
      const data = await adminPostJson<{ survey: WrappedSurvey }>(`/api/surveys/${surveyId}/content`, { survey: draft }, token);
      onSaved(data.survey);
      setMessage("互动题面已保存，并已生成新的问卷版本。");
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "互动题面保存失败。");
    } finally {
      setSaving(false);
    }
  }

  return (
    <section className="wrapped-editor">
      <div className="page-title"><div><p className="eyebrow">EDIT WRAPPED SURVEY</p><h2>手动编辑 AI 包装题面</h2><p>可调整标题、导语、题干和选项；保存后会递增问卷版本，旧答卷仍保留原版本。</p></div><Save size={26} /></div>
      {message && <div className="notice">{message}</div>}
      <div className="panel editor-meta-fields">
        <label htmlFor="wrapped-title">问卷标题</label>
        <input id="wrapped-title" value={draft.survey_name} onChange={(event) => setDraft({ ...draft, survey_name: event.target.value })} disabled={!canEdit} />
        <label htmlFor="wrapped-tagline">副标题</label>
        <input id="wrapped-tagline" value={draft.tagline} onChange={(event) => setDraft({ ...draft, tagline: event.target.value })} disabled={!canEdit} />
        <label htmlFor="wrapped-intro">开场说明</label>
        <textarea id="wrapped-intro" value={draft.intro} onChange={(event) => setDraft({ ...draft, intro: event.target.value })} disabled={!canEdit} />
      </div>
      <div className="editor-list">{draft.questions.map((question, index) => <article className="question-editor-item panel" key={`${question.question_id}-${index}`}>
        <div className="editor-item-head"><span className="editor-index">{String(index + 1).padStart(2, "0")}</span><strong>{question.question_id}</strong><button className="icon-button subtle-danger" onClick={() => setDraft({ ...draft, questions: draft.questions.filter((_, itemIndex) => itemIndex !== index) })} disabled={!canEdit || draft.questions.length <= 1} title="删除题目" aria-label={`删除${question.question_id}`}><Trash2 size={16} /></button></div>
        <label htmlFor={`wrapped-question-${index}`}>互动题干</label>
        <textarea id={`wrapped-question-${index}`} className="question-text-input" value={question.public_text} onChange={(event) => updateQuestion(index, { public_text: event.target.value })} disabled={!canEdit} />
        <label htmlFor={`wrapped-tag-${index}`}>研究标签</label>
        <input id={`wrapped-tag-${index}`} value={question.research_tag} onChange={(event) => updateQuestion(index, { research_tag: event.target.value })} disabled={!canEdit} />
        <label className="required-toggle"><input type="checkbox" checked={question.required} onChange={(event) => updateQuestion(index, { required: event.target.checked })} disabled={!canEdit} /> 必答题</label>
        {question.question_type !== "text" && <div className="option-editor"><div className="option-editor-head"><label>选项</label><button className="text-action" onClick={() => updateQuestion(index, { options: [...question.options, ""] })} disabled={!canEdit}><Plus size={14} /> 添加选项</button></div>{question.options.map((option, optionIndex) => <div className="option-editor-row" key={`${question.question_id}-${optionIndex}`}><span>{String.fromCharCode(65 + optionIndex)}</span><input value={option} onChange={(event) => updateOption(index, optionIndex, event.target.value)} disabled={!canEdit} /><button className="icon-button" onClick={() => updateQuestion(index, { options: question.options.filter((_, itemIndex) => itemIndex !== optionIndex) })} disabled={!canEdit || question.options.length <= 1} title="删除选项" aria-label="删除选项"><X size={15} /></button></div>)}</div>}
      </article>)}</div>
      <div className="editor-actions"><button className="secondary" onClick={addQuestion} disabled={!canEdit}><Plus size={16} /> 新增题目</button>{canEdit && <button className="primary" onClick={() => void save()} disabled={saving}><Save size={16} /> {saving ? "保存中..." : "保存新版本"}</button>}</div>
      {!canManage ? <p className="field-hint">当前账号为只读查看者，只能预览题面。</p> : !canEdit && <p className="field-hint">问卷当前为“{statusLabel(status)}”，题目和选项已锁定。</p>}
    </section>
  );
}

function statusLabel(status: SurveyStatus) {
  const labels: Record<SurveyStatus, string> = {
    draft: "草稿",
    collecting: "收集中",
    ended: "已结束",
    archived: "已归档",
  };
  return labels[status] || status;
}
