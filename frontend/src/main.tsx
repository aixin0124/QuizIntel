import React, { useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import * as echarts from "echarts";
import { BarChart3, BookOpen, CheckCircle2, Database, ExternalLink, FileDown, FileSpreadsheet, FileText, KeyRound, LayoutDashboard, Link2, LoaderCircle, LockKeyhole, LogOut, Play, Plus, RotateCcw, Save, ShieldCheck, Sparkles, Trash2, Users, X } from "lucide-react";
import "./styles.css";

type SurveyQuestion = { question_id: string; text: string; question_type: string; options: string[]; research_tag: string; required: boolean };
type WrappedQuestion = { question_id: string; public_text: string; question_type: string; options: string[]; research_tag: string; source_text: string; required: boolean; research_refs?: string[]; rationale?: string };
type DimensionBreakdown = { key: string; name: string; score: number; signal: string; description: string };
type ResultAnalysis = { summary: string; personality_reference?: string; dimension_breakdown: DimensionBreakdown[]; evidence: Array<{ question: string; answer: string; reason: string; rationale?: string }>; strengths: string[]; watchouts: string[]; advice: string };
type ResultPayload = { name: string; description: string; strengths?: string[]; watchouts?: string[]; advice?: string; dimension_scores?: Record<string, number>; analysis?: ResultAnalysis };
type WrappedSurvey = { survey_name: string; theme: string; tagline: string; intro: string; disclosure: string; result_types: Array<{ name: string; description: string }>; questions: WrappedQuestion[]; brand_goal: string; source: string; dimensions?: Array<{ key: string; name: string; description: string; high_pole: string; low_pole: string }>; analysis_method?: string };
type SurveySummary = { id: number; survey_name: string; theme: string; source: string; created_at: string; response_count: number; status: "open" | "ended"; ended_at?: string | null; deleted_at?: string | null };
type AnalyticsSummary = { response_count: number; result_counts: Record<string, number>; option_counts: Record<string, Record<string, number>>; research_tags: string[]; dimension_stats?: DimensionStat[]; question_stats?: QuestionStat[] };
type DimensionStat = { key: string; name: string; description: string; high_pole?: string; low_pole?: string; score?: number | null; index?: number | null; positive_count?: number | null; neutral_count?: number | null; negative_count?: number | null; coverage_count: number; mapped_question_ids: string[]; mapped_research_tags: string[]; conclusion?: string };
type QuestionStat = { question_id: string; question: string; research_tag: string; answered_count: number; answer_rate: number; options: Array<{ option: string; count: number; percentage: number }>; dimension_keys: string[] };
type ResearchAnalysis = { generated_at: string; research_goal: string; theme: string; response_count: number; result_counts: Record<string, number>; research_tags: string[]; dimensions: DimensionStat[]; questions: QuestionStat[]; key_findings: string[]; research_conclusion: string; long_summary: string; limitations: string; analysis_method: string };
type GenerationStep = { title: string; detail: string };
type SurveyTemplate = { id: string; title: string; category: string; sourceUrl: string; summary: string; goal: string; themeHint: string };
type ImportSurveyResponse = { title: string; source_url?: string; questions: SurveyQuestion[] };

const recommendedSurveyTemplates: SurveyTemplate[] = [
  { id: "travel", title: "旅游调查问卷", category: "消费与旅游", sourceUrl: "https://www.wenjuan.com/lib_detail_full/6125dcc62bc3caa35810da45/", summary: "围绕旅游频率、出游原因、目的地偏好和消费安排。", goal: "了解用户旅游偏好、出游动机、消费支出和服务期待，为旅游产品与体验优化提供依据", themeHint: "旅行决策风格测评" },
  { id: "summer-job", title: "关于大学生暑假工的调查问卷", category: "校园与就业", sourceUrl: "https://www.wenjuan.com/lib_detail_full/62fc480159d4f61dba0278d3/", summary: "关注大学生暑期兼职意愿、渠道、收入期待和风险认知。", goal: "了解大学生暑假工参与意愿、求职渠道、收入期待和权益保障需求", themeHint: "暑期求职风格测评" },
  { id: "bilibili", title: "B站用户体验及满意度的网络在线调查", category: "产品体验", sourceUrl: "https://www.wenjuan.com/lib_detail_full/638f038bd40fd403008ebe19/", summary: "覆盖内容平台使用习惯、功能体验和满意度反馈。", goal: "评估视频社区用户体验、功能满意度和内容消费偏好，为平台体验优化提供依据", themeHint: "内容社区使用风格测评" },
  { id: "video-member", title: "视频网站付费会员模式调查问卷", category: "会员消费", sourceUrl: "https://www.wenjuan.com/lib_detail_full/62d64c8b59d4f67a26d58919/", summary: "用于研究付费会员认知、购买动机和续费意愿。", goal: "洞察用户对视频网站付费会员模式的认知、价格接受度和续费意愿", themeHint: "会员消费决策测评" },
  { id: "teen-vision", title: "青少年视力健康调查问卷", category: "健康研究", sourceUrl: "https://www.wenjuan.com/lib_detail_full/619317a12bc3ca9028f6ec7e/", summary: "关注用眼习惯、电子设备使用和视力健康行为。", goal: "了解青少年视力健康状况、用眼习惯和护眼意识，为健康干预提供依据", themeHint: "用眼健康习惯测评" },
  { id: "college-consume", title: "大学生在校消费调查", category: "校园消费", sourceUrl: "https://www.wenjuan.com/lib_detail_full/5c52dd693fcf57039143f1b9/", summary: "研究大学生日常消费结构、预算管理和消费观。", goal: "分析大学生在校消费结构、消费动机和预算管理方式，为校园服务和产品定位提供依据", themeHint: "校园消费风格测评" },
  { id: "hospice", title: "临终关怀调查问卷", category: "社会与医疗", sourceUrl: "https://www.wenjuan.com/lib_detail_full/63368f4ad40fd480221a8f78/", summary: "了解公众对临终关怀的认知、态度和服务期待。", goal: "了解公众对临终关怀的认知程度、接受态度和服务需求，为医疗人文服务研究提供依据", themeHint: "医疗关怀态度测评" },
  { id: "word-aphasia", title: "文字失语现象调查研究", category: "文化研究", sourceUrl: "https://www.wenjuan.com/lib_detail_full/6257bf712bc3ca95a027651d/", summary: "关注表达能力、网络语言使用和文字沟通体验。", goal: "研究用户对文字失语现象的感知、成因判断和沟通行为变化", themeHint: "表达习惯测评" },
  { id: "teacher-eval", title: "师德师风评价表（学生评教师）", category: "教育评价", sourceUrl: "https://www.wenjuan.com/lib_detail_full/639c466659d4f6cafaad02d5/", summary: "适合教学态度、课堂互动和教师行为评价。", goal: "收集学生对教师师德师风、教学态度和课堂体验的评价，为教学管理提供依据", themeHint: "课堂体验测评" },
  { id: "fan-culture", title: "饭圈文化对青少年心理影响调查及反思", category: "青年文化", sourceUrl: "https://www.wenjuan.com/lib_detail_full/6119fe412bc3cada1cc21b36/", summary: "研究粉丝文化参与、心理影响和价值判断。", goal: "了解饭圈文化对青少年心理状态、社交行为和价值判断的影响", themeHint: "粉丝文化参与测评" },
  { id: "black-myth", title: "对《黑神话：悟空》的看法调研", category: "游戏文化", sourceUrl: "https://www.wenjuan.com/lib_detail_full/66c6985bc3fb54fc2e9aeb3e/", summary: "适合游戏认知、文化传播和玩家期待研究。", goal: "了解用户对《黑神话：悟空》的认知、游玩兴趣和文化传播感受", themeHint: "游戏文化态度测评" },
  { id: "maotai-icecream", title: "大众关于茅台冰激淋的认知调查问卷", category: "品牌营销", sourceUrl: "https://www.wenjuan.com/lib_detail_full/62ea0a79d40fd4ec53916bfa/", summary: "聚焦联名产品认知、购买意愿和品牌感知。", goal: "评估大众对茅台冰激淋的认知、购买意愿和品牌联想，为新品营销提供依据", themeHint: "品牌新品接受度测评" },
  { id: "hpv", title: "对HPV疫苗认知及接种意愿影响因素调查问卷", category: "健康医疗", sourceUrl: "https://www.wenjuan.com/lib_detail_full/6413d5d3d40fd43e0f729209/", summary: "研究疫苗认知、接种意愿和影响因素。", goal: "了解用户对 HPV 疫苗的认知程度、接种意愿和主要影响因素", themeHint: "健康决策风格测评" },
  { id: "paris-olympic-focus", title: "大众对巴黎奥运会的关注程度调查", category: "体育传播", sourceUrl: "https://www.wenjuan.com/lib_detail_full/66825edbc3fb54c0a13736d7/", summary: "关注奥运会知晓度、观看行为和兴趣项目。", goal: "了解大众对巴黎奥运会的关注程度、观看习惯和体育内容兴趣", themeHint: "体育赛事关注测评" },
  { id: "olympic-opening", title: "2024年巴黎奥运会开幕式调研问卷", category: "体育传播", sourceUrl: "https://www.wenjuan.com/lib_detail_full/66b1ed3e97b33e9e96d9e27c/", summary: "用于开幕式观看体验、评价和传播反馈。", goal: "收集用户对巴黎奥运会开幕式的观看体验、内容评价和传播感受", themeHint: "开幕式体验测评" },
  { id: "olympic-project", title: "2024巴黎奥运会最关注的项目调查", category: "体育兴趣", sourceUrl: "https://www.wenjuan.com/lib_detail_full/66b1ed31c3fb54aeb7b18fc3/", summary: "研究体育项目关注偏好和观看选择。", goal: "了解用户最关注的奥运项目、关注原因和观看偏好，为体育内容运营提供依据", themeHint: "体育项目偏好测评" },
  { id: "part-time", title: "大学生兼职倾向调查", category: "校园就业", sourceUrl: "https://www.wenjuan.com/lib_detail_full/5ce4eea1a320fc274f4d865d/", summary: "分析兼职动机、时间安排、薪资期待和岗位偏好。", goal: "了解大学生兼职意愿、岗位偏好、时间投入和薪资期待，为就业服务提供依据", themeHint: "兼职选择风格测评" },
  { id: "phone-dependence", title: "大学生手机依赖程度情况调查", category: "数字生活", sourceUrl: "https://www.wenjuan.com/lib_detail_full/6464a7cfd40fd4ea26c7cb46/", summary: "关注手机使用时长、依赖表现和自我管理。", goal: "评估大学生手机依赖程度、使用场景和自我管理需求", themeHint: "手机依赖画像测评" },
  { id: "phone-use", title: "大学生手机使用情况调查", category: "数字生活", sourceUrl: "https://www.wenjuan.com/lib_detail_full/5eb64659a320fc35c69a9e05/", summary: "覆盖手机用途、使用频率和应用偏好。", goal: "了解大学生手机使用习惯、主要用途和应用偏好，为数字产品研究提供依据", themeHint: "手机使用风格测评" },
  { id: "back-school", title: "学生开学心理问卷调查表", category: "心理与教育", sourceUrl: "https://www.wenjuan.com/lib_detail_full/63ed93c459d4f6789d748bd0/", summary: "面向开学适应、情绪状态和学习准备。", goal: "了解学生开学阶段的心理状态、适应压力和支持需求，为教育关怀提供依据", themeHint: "开学适应状态测评" },
  { id: "lying-flat", title: "关于摆烂现象的问卷调查", category: "青年心态", sourceUrl: "https://www.wenjuan.com/lib_detail_full/630a314359d4f6987ba7eece/", summary: "研究摆烂心态、压力来源和行为表现。", goal: "分析用户对摆烂现象的认知、压力来源和行为态度，为青年心态研究提供依据", themeHint: "压力应对风格测评" },
];

const generationSteps: GenerationStep[] = [
  { title: "提炼主题", detail: "抽取调研目标、用户语境和可包装的互动主题。" },
  { title: "设计题目", detail: "把研究字段转成更自然的场景问题，并检查选项覆盖。" },
  { title: "问卷分析", detail: "建立结果类型、评分映射和后续数据分析维度。" },
];

const fallbackHeadlines = [
  "AI 正在同步热点灵感，稍后会继续尝试读取今日头条。",
  "生成期间可以停留在本页，完成后会自动进入新问卷。",
  "系统正在校验题目映射，避免分析维度和原始问卷脱节。",
];

const maxHeadlinesPerGeneration = 30;
const seenHeadlinesStorageKey = "fun_research_seen_headlines";
const headlineApiUrl = "https://api.zxki.cn/api/jhrs?type=douyin";

function App() {
  const [mode, setMode] = useState<"user" | "admin">("user");
  const [adminToken, setAdminToken] = useState(() => sessionStorage.getItem("admin_token") || "");
  function logout() { sessionStorage.removeItem("admin_token"); setAdminToken(""); setMode("user"); }
  return <main>
    <header className="topbar"><button className="brand" onClick={() => setMode("user")} aria-label="返回用户端">趣测智研 <span>FUN RESEARCH</span></button><nav className="main-nav"><button className={mode === "user" ? "active" : ""} onClick={() => setMode("user")}><Users size={16} /> 用户端</button><button className={mode === "admin" ? "active" : ""} onClick={() => setMode("admin")}><LayoutDashboard size={16} /> 管理后台</button>{adminToken && <button className="icon-button" onClick={logout} title="退出管理后台" aria-label="退出管理后台"><LogOut size={17} /></button>}</nav></header>
    {mode === "user" ? <UserPortal /> : adminToken ? <AdminPortal token={adminToken} /> : <AdminLogin onLogin={setAdminToken} />}
  </main>;
}

function UserPortal() {
  const [surveys, setSurveys] = useState<SurveySummary[]>([]); const [selected, setSelected] = useState<{ id: number; survey: WrappedSurvey } | null>(null); const [answers, setAnswers] = useState<Record<string, unknown>>({}); const [result, setResult] = useState<ResultPayload | null>(null); const [message, setMessage] = useState(""); const [loading, setLoading] = useState(false);
  useEffect(() => { void loadPublicSurveys(); }, []);
  async function loadPublicSurveys() { try { const data = await fetchJson<{ items: SurveySummary[] }>("/api/public/surveys"); setSurveys(data.items); if (data.items.length) await openSurvey(data.items[0].id); } catch (error) { setMessage(getErrorMessage(error)); } }
  async function openSurvey(id: number) { setLoading(true); setMessage(""); try { const data = await fetchJson<{ id: number; survey: WrappedSurvey }>(`/api/public/surveys/${id}`); setSelected(data); setAnswers({}); setResult(null); } catch (error) { setMessage(getErrorMessage(error)); } finally { setLoading(false); } }
  async function submitAnswers() { if (!selected) return; if (!isSurveyComplete(selected.survey, answers)) { setMessage("请完成所有必答题后再提交。"); return; } setLoading(true); setMessage(""); try { const data = await postJson<{ result: ResultPayload }>("/api/responses", { survey_id: selected.id, answers }); setResult(data.result); setMessage("答卷已提交，感谢你的参与。"); } catch (error) { setMessage(getErrorMessage(error)); } finally { setLoading(false); } }
  const completion = useMemo(() => { if (!selected) return 0; const required = selected.survey.questions.filter((question) => question.required); const answered = required.filter((question) => isAnswerPresent(answers[question.question_id])).length; return required.length ? Math.round((answered / required.length) * 100) : 100; }, [answers, selected]);
  return <><section className="hero compact-hero"><div><p className="eyebrow">INTERACTIVE RESEARCH</p><h1>用一分钟，完成一次有趣的市场调研。</h1><p>选择一份测评，按直觉作答。你的答案将帮助品牌更好地理解真实需求。</p></div><div className="heroPanel user-hero-panel"><Sparkles size={23} /><strong>轻松作答，真实反馈</strong><span>本页面不收集姓名、手机号等直接身份信息。</span></div></section>{message && <div className="notice">{message}</div>}<section className="user-layout"><aside className="survey-list panel"><div className="section-heading"><div><p className="eyebrow">SURVEYS</p><h2>可参与的测评</h2></div><Database size={20} /></div>{!surveys.length ? <Empty text="暂无已发布的测评，请由管理后台先生成一个。" /> : surveys.map((item) => <button key={item.id} className={`survey-item ${selected?.id === item.id ? "selected" : ""}`} onClick={() => void openSurvey(item.id)}><span>{item.theme}</span><strong>{item.survey_name}</strong><small>{item.response_count} 人已完成</small></button>)}</aside><section className="testSurface user-surface">{!selected ? <Empty text="请选择左侧测评开始体验。" /> : <><p className="eyebrow">{selected.survey.theme}</p><h2>{selected.survey.survey_name}</h2><p className="lead">{selected.survey.tagline}</p><p className="intro">{selected.survey.intro}</p><div className="disclosure">{selected.survey.disclosure}</div><div className="progress-label"><span>完成进度</span><b>{completion}%</b></div><div className="progress"><span style={{ width: `${completion}%` }} /></div>{selected.survey.questions.map((question, index) => <QuestionInput key={question.question_id} index={index + 1} question={question} value={answers[question.question_id]} onChange={(value) => setAnswers({ ...answers, [question.question_id]: value })} />)}<button className="primary wide" onClick={() => void submitAnswers()} disabled={loading || completion < 100}><Play size={18} /> {loading ? "提交中..." : "查看我的结果"}</button>{result && <ResultPanel result={result} />}</>}</section></section></>;
}

function ResultPanel({ result }: { result: ResultPayload }) {
  const analysis = result.analysis;
  const strengths = analysis?.strengths?.length ? analysis.strengths : result.strengths || [];
  const watchouts = analysis?.watchouts?.length ? analysis.watchouts : result.watchouts || [];
  const advice = analysis?.advice || result.advice || "把这份结果当作自我观察的起点，结合具体场景判断是否符合你最近的状态。";
  const dimensions = analysis?.dimension_breakdown || [];
  const personalityReference = analysis?.personality_reference || buildPersonalityReference(result, dimensions);
  const summary = buildPersonalitySummary(analysis?.summary || result.description, result, dimensions, personalityReference);
  const highlightDimensions = dimensions.slice().sort((a, b) => Math.abs(b.score) - Math.abs(a.score)).slice(0, 3);
  const matchIndex = getResultMatchIndex(dimensions);
  return <div className="result result-report"><div className="result-hero"><div><p className="result-kicker">YOUR RESULT</p><h3>你是{result.name}</h3><p>{getHeroSummary(summary)}</p>{highlightDimensions.length > 0 && <div className="result-tags">{highlightDimensions.map((item) => <span key={item.key}>{item.name} · {item.signal}</span>)}</div>}</div><div className="result-score"><span>匹配指数</span><b>{matchIndex}</b><em>/ 100</em></div></div>{dimensions.length > 0 && <section className="result-section"><div className="result-section-title"><strong>维度画像</strong><span>根据你的选择换算出的倾向强弱</span></div><div className="result-dimension-overview"><ResultRadarChart dimensions={dimensions} /><div className="dimension-grid">{dimensions.map((item) => { const percent = dimensionPercent(item.score); return <article className="dimension-card" key={item.key}><div className="dimension-card-head"><span>{item.name}</span><b>{item.signal}</b></div><div className="dimension-scale"><span style={{ width: `${percent}%` }} /></div><div className="dimension-card-foot"><small>{item.description}</small><em>{percent}%</em></div></article>; })}</div></div></section>}<section className="personality-section"><div className="personality-reference"><span>人格参考</span><strong>你是{personalityReference}</strong></div><div className="personality-analysis"><span>人格解析</span><p>{summary}</p></div></section><section className="result-insights"><InsightCard title="你的突出特质" items={strengths} fallback="你的选择呈现出比较清晰的个人偏好。" /><InsightCard title="可以留意" items={watchouts} fallback="当结果落在中间区间时，可以结合真实场景继续观察。" /><div className="insight-card advice-card"><strong>带走一条建议</strong><p>{advice}</p></div></section></div>;
}

function InsightCard({ title, items, fallback }: { title: string; items: string[]; fallback: string }) {
  return <div className="insight-card"><strong>{title}</strong><ul>{(items.length ? items : [fallback]).map((item) => <li key={item}>{item}</li>)}</ul></div>;
}

function ResultRadarChart({ dimensions }: { dimensions: DimensionBreakdown[] }) {
  const ref = useRef<HTMLDivElement>(null);
  const option = useMemo<echarts.EChartsOption>(() => {
    const values = dimensions.map((item) => dimensionPercent(item.score));
    return {
      color: ["#2467e8"],
      tooltip: { trigger: "item" },
      radar: {
        radius: "68%",
        center: ["50%", "52%"],
        shape: "polygon",
        splitNumber: 4,
        indicator: dimensions.map((item) => ({ name: item.name, max: 100 })),
        axisName: { color: "#526277", fontSize: 12 },
        splitArea: { areaStyle: { color: ["#f7faff", "#ffffff"] } },
        axisLine: { lineStyle: { color: "#d8e2ee" } },
        splitLine: { lineStyle: { color: "#d8e2ee" } },
      },
      series: [{
        type: "radar",
        areaStyle: { color: "rgba(36, 103, 232, 0.18)" },
        lineStyle: { width: 2 },
        symbolSize: 5,
        data: [{ value: values, name: "维度强度" }],
      }],
    };
  }, [dimensions]);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.setOption(option);
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => { window.removeEventListener("resize", resize); chart.dispose(); };
  }, [option]);

  return <div className="result-radar" aria-label="多维人格雷达图" ref={ref} />;
}

function buildPersonalityReference(result: ResultPayload, dimensions: DimensionBreakdown[]) {
  const strongest = dimensions.slice().sort((a, b) => Math.abs(b.score) - Math.abs(a.score));
  const adjectives = strongest.slice(0, 2).map(dimensionAdjective).filter(Boolean);
  const typeName = result.name.endsWith("型") ? `${result.name.slice(0, -1)}者` : "自我观察者";
  return `${(adjectives.length ? adjectives : ["清醒"]).join("")}的${typeName}`;
}

function dimensionAdjective(item: DimensionBreakdown) {
  const text = `${item.name}${item.signal}`;
  if (/理性|规划|现实|边界|谨慎|稳定/.test(text)) return item.score >= 0 ? "清醒" : "松弛";
  if (/投入|主动|表达|热情|行动/.test(text)) return item.score >= 0 ? "真诚" : "克制";
  if (/沟通|冲突|修复|包容/.test(text)) return item.score >= 0 ? "温和" : "直接";
  if (item.score >= 0.35) return "笃定";
  if (item.score <= -0.35) return "审慎";
  return "弹性";
}

function buildPersonalitySummary(summary: string, result: ResultPayload, dimensions: DimensionBreakdown[], reference: string) {
  const text = summary.trim();
  if (text.length >= 120) return trimPersonalityText(text);
  const leading = dimensions.slice().sort((a, b) => Math.abs(b.score) - Math.abs(a.score)).slice(0, 3).map((item) => `${item.name}偏向${item.signal}`).join("、") || "多个维度保留弹性";
  const base = `你的结果显示，你更像${reference}。${text || result.description}从维度画像看，${leading}，说明你不是只凭一时情绪做判断的人。你会先观察环境、关系节奏和现实条件，确认值得投入后才慢慢靠近。外在可能显得慢热，内心却一直在整理细节、评估风险和匹配度；一旦确认方向，你会用稳定行动表达认真。需要留意的是，过度分析会让真实感受被推迟表达，适度说出期待，会让关系或选择更有温度。`;
  return trimPersonalityText(base);
}

function trimPersonalityText(value: string) {
  const text = value.replace(/\s+/g, " ").trim();
  if (text.length <= 230) return text;
  return `${text.slice(0, 227).replace(/[，；、\s]+$/, "")}。`;
}

function getHeroSummary(summary: string) {
  if (summary.length <= 88) return summary;
  return `${summary.slice(0, 85).replace(/[，；、\s]+$/, "")}。`;
}

function dimensionPercent(score: number) {
  return Math.max(0, Math.min(100, Math.round((score + 1) * 50)));
}

function getResultMatchIndex(dimensions: DimensionBreakdown[]) {
  if (!dimensions.length) return 88;
  const averageStrength = dimensions.reduce((sum, item) => sum + Math.abs(item.score), 0) / dimensions.length;
  return Math.max(59, Math.min(98, Math.round(72 + averageStrength * 26)));
}

function AdminLogin({ onLogin }: { onLogin: (token: string) => void }) {
  const [password, setPassword] = useState(""); const [message, setMessage] = useState(""); const [loading, setLoading] = useState(false);
  async function login(event: React.FormEvent) { event.preventDefault(); setLoading(true); setMessage(""); try { const data = await postJson<{ token: string }>("/api/admin/login", { password }); sessionStorage.setItem("admin_token", data.token); onLogin(data.token); } catch (error) { setMessage(getErrorMessage(error)); } finally { setLoading(false); } }
  return <section className="login-wrap"><form className="login-panel" onSubmit={login}><div className="login-icon"><ShieldCheck size={25} /></div><p className="eyebrow">RESEARCH CONSOLE</p><h1>管理后台</h1><p>登录后管理问卷包装、查看题目映射和分析答卷数据。</p><label htmlFor="admin-password">后台密码</label><div className="password-input"><KeyRound size={17} /><input id="admin-password" type="password" value={password} onChange={(event) => setPassword(event.target.value)} placeholder="请输入后台密码" autoFocus /></div>{message && <div className="form-error">{message}</div>}<button className="primary wide" type="submit" disabled={loading || !password}>{loading ? "登录中..." : "进入管理后台"}</button></form></section>;
}

function AdminPortal({ token }: { token: string }) {
  const [active, setActive] = useState<"overview" | "create" | "mapping" | "analysis" | "trash">("overview"); const [surveys, setSurveys] = useState<SurveySummary[]>([]); const [trashItems, setTrashItems] = useState<SurveySummary[]>([]); const [selectedId, setSelectedId] = useState<number | null>(null); const [survey, setSurvey] = useState<WrappedSurvey | null>(null); const [summary, setSummary] = useState<AnalyticsSummary | null>(null); const [analysis, setAnalysis] = useState<ResearchAnalysis | null>(null); const [surveyStatus, setSurveyStatus] = useState<"open" | "ended">("open"); const [message, setMessage] = useState(""); const [loading, setLoading] = useState(false); const [finishing, setFinishing] = useState(false); const [trashLoading, setTrashLoading] = useState(false);
  async function loadSurveys() { try { const data = await adminFetchJson<{ items: SurveySummary[] }>("/api/surveys", token); setSurveys(data.items); if (data.items.length && !selectedId) await selectSurvey(data.items[0].id); } catch (error) { setMessage(getErrorMessage(error)); } }
  async function loadTrash() { setTrashLoading(true); setMessage(""); try { const data = await adminFetchJson<{ items: SurveySummary[] }>("/api/surveys/trash", token); setTrashItems(data.items); } catch (error) { setMessage(getErrorMessage(error)); } finally { setTrashLoading(false); } }
  async function selectSurvey(id: number) { setLoading(true); setMessage(""); try { const [surveyData, analyticsData] = await Promise.all([adminFetchJson<{ payload: WrappedSurvey; status: "open" | "ended" }>(`/api/surveys/${id}`, token), adminFetchJson<{ summary: AnalyticsSummary; analysis: ResearchAnalysis | null; status: "open" | "ended" }>(`/api/analytics/${id}`, token)]); setSelectedId(id); setSurvey(surveyData.payload); setSummary(analyticsData.summary); setAnalysis(analyticsData.analysis); setSurveyStatus(analyticsData.status); } catch (error) { setMessage(getErrorMessage(error)); } finally { setLoading(false); } }
  async function moveToTrash(item: SurveySummary) { if (!window.confirm(`确定将“${item.survey_name}”移入回收站吗？`)) return; try { await adminDeleteJson(`/api/surveys/${item.id}`, token); const next = surveys.filter((surveyItem) => surveyItem.id !== item.id); setSurveys(next); setTrashItems((items) => [{ ...item, deleted_at: new Date().toISOString() }, ...items]); if (selectedId === item.id) { setSelectedId(null); setSurvey(null); setSummary(null); setAnalysis(null); setActive("overview"); if (next.length) await selectSurvey(next[0].id); } setMessage("问卷已移入回收站。"); } catch (error) { setMessage(getErrorMessage(error)); } }
  async function restoreFromTrash(item: SurveySummary) { try { await adminPostJson(`/api/surveys/${item.id}/restore`, {}, token); setTrashItems((items) => items.filter((trashItem) => trashItem.id !== item.id)); setSurveys((items) => [{ ...item, deleted_at: null }, ...items]); setMessage("问卷已恢复到已保存问卷。"); } catch (error) { setMessage(getErrorMessage(error)); } }
  async function permanentlyDelete(item: SurveySummary) { if (!window.confirm(`“${item.survey_name}”及其答卷数据将永久删除，确定继续吗？`)) return; try { await adminDeleteJson(`/api/surveys/${item.id}/permanent`, token); setTrashItems((items) => items.filter((trashItem) => trashItem.id !== item.id)); setMessage("问卷已永久删除。"); } catch (error) { setMessage(getErrorMessage(error)); } }
  async function finishSurvey() { if (!selectedId || !summary?.response_count) { setMessage("至少收集 1 份有效答卷后才能开始数据分析。"); return; } setFinishing(true); setMessage(""); try { const data = await adminPostJson<{ status: "ended"; ended_at: string; analysis: ResearchAnalysis }>(`/api/analytics/${selectedId}/finish`, {}, token); setSurveyStatus(data.status); setAnalysis(data.analysis); setSurveys((items) => items.map((item) => item.id === selectedId ? { ...item, status: data.status, ended_at: data.ended_at } : item)); setActive("analysis"); setMessage("问卷已结束，AI 数据分析已生成。"); } catch (error) { setMessage(getErrorMessage(error)); } finally { setFinishing(false); } }
  async function renameSurvey(surveyName: string) { if (!selectedId) return; try { const data = await adminPostJson<{ survey: WrappedSurvey }>(`/api/surveys/${selectedId}/title`, { survey_name: surveyName }, token); setSurvey(data.survey); setSurveys((items) => items.map((item) => item.id === selectedId ? { ...item, survey_name: data.survey.survey_name } : item)); setMessage("问卷标题已更新。"); } catch (error) { setMessage(getErrorMessage(error)); throw error; } }
  useEffect(() => { void loadSurveys(); void loadTrash(); }, []);
  function onCreated(id: number, createdSurvey: WrappedSurvey) { setSurveys((items) => [{ id, survey_name: createdSurvey.survey_name, theme: createdSurvey.theme, source: createdSurvey.source, created_at: new Date().toISOString(), response_count: 0, status: "open" }, ...items]); setSelectedId(id); setSurvey(createdSurvey); setSummary({ response_count: 0, result_counts: {}, option_counts: {}, research_tags: createdSurvey.questions.map((question) => question.research_tag).filter(Boolean) }); setAnalysis(null); setSurveyStatus("open"); setActive("mapping"); }
  return <><section className="admin-head"><div><p className="eyebrow">ADMINISTRATION</p><h1>研究数据工作台</h1><p>管理互动问卷，追踪研究字段，导出可提交的调研报告。</p></div><div className="admin-status"><span className="status-dot" /> 本地数据库已连接</div></section>{message && <div className="notice">{message}</div>}<div className="admin-shell"><aside className="admin-sidebar"><button className={active === "overview" ? "active" : ""} onClick={() => setActive("overview")}><LayoutDashboard size={17} /> 数据总览</button><button className={active === "create" ? "active" : ""} onClick={() => setActive("create")}><Plus size={17} /> 创建包装</button><button className={active === "mapping" ? "active" : ""} onClick={() => setActive("mapping")} disabled={!survey}><Database size={17} /> 题目映射</button><button className={active === "analysis" ? "active" : ""} onClick={() => setActive("analysis")} disabled={!survey}><FileText size={17} /> 问卷数据分析</button><button className={active === "trash" ? "active" : ""} onClick={() => { setActive("trash"); void loadTrash(); }}><Trash2 size={17} /> 回收站 <span className="trash-count">{trashItems.length}</span></button><div className="sidebar-divider" /><p>已保存问卷</p>{!surveys.length ? <span className="sidebar-empty">暂无已保存问卷</span> : surveys.map((item) => <button className={`sidebar-survey ${selectedId === item.id ? "selected" : ""}`} key={item.id} onClick={(event) => { const target = event.target as HTMLElement; if (target.closest("[data-delete-survey]")) { event.stopPropagation(); void moveToTrash(item); return; } void selectSurvey(item.id); }}><span>{item.theme}<em className={`survey-status ${item.status}`}>{item.status === "ended" ? "已结束" : "开放中"}</em></span><strong>{item.survey_name}</strong><span data-delete-survey className="sidebar-delete-action" title="移入回收站" aria-label={`将${item.survey_name}移入回收站`}><Trash2 size={15} /></span></button>)}</aside><section className="admin-content">{active === "create" ? <CreateWorkspace token={token} onCreated={onCreated} /> : active === "mapping" && survey ? <MappingView survey={survey} /> : active === "analysis" && survey ? <AnalysisView survey={survey} summary={summary} analysis={analysis} status={surveyStatus} token={token} selectedId={selectedId} /> : active === "trash" ? <TrashView items={trashItems} loading={trashLoading} onRestore={restoreFromTrash} onPermanentDelete={permanentlyDelete} /> : <Dashboard survey={survey} summary={summary} surveyCount={surveys.length} loading={loading} token={token} selectedId={selectedId} status={surveyStatus} finishing={finishing} onFinish={finishSurvey} onRename={renameSurvey} />}</section></div></>;
}

function TrashView({ items, loading, onRestore, onPermanentDelete }: { items: SurveySummary[]; loading: boolean; onRestore: (item: SurveySummary) => void; onPermanentDelete: (item: SurveySummary) => void }) {
  return <section><div className="page-title"><div><p className="eyebrow">TRASH / RECOVERY</p><h2>回收站</h2><p>已删除的问卷暂时保留在这里，恢复后可继续管理；永久删除会同时清理答卷和分析结果。</p></div><Trash2 size={26} /></div><div className="trash-note"><strong>数据保留说明</strong><p>移入回收站不会影响历史答卷、AI 分析和导出数据。永久删除后无法恢复，请谨慎操作。</p></div>{loading ? <Empty text="正在读取回收站..." /> : !items.length ? <div className="trash-empty panel"><Trash2 size={26} /><strong>回收站为空</strong><span>从已保存问卷旁边的删除按钮移入的问卷会出现在这里。</span></div> : <div className="trash-list">{items.map((item) => <article className="trash-item" key={item.id}><div className="trash-item-main"><span className="trash-item-theme">{item.theme}<em className={`survey-status ${item.status}`}>{item.status === "ended" ? "已结束" : "开放中"}</em></span><strong>{item.survey_name}</strong><small>原有答卷 {item.response_count} 份 · 删除于 {formatDate(item.deleted_at)}</small></div><div className="trash-item-actions"><button className="secondary" onClick={() => onRestore(item)}><RotateCcw size={16} /> 恢复</button><button className="danger-action" onClick={() => onPermanentDelete(item)}><Trash2 size={16} /> 永久删除</button></div></article>)}</div>}</section>;
}

function formatDate(value?: string | null) {
  if (!value) return "未知时间";
  return value.replace("T", " ");
}

function CreateWorkspace({ token, onCreated }: { token: string; onCreated: (id: number, survey: WrappedSurvey) => void }) {
  const [wjxUrl, setWjxUrl] = useState(""); const [questions, setQuestions] = useState<SurveyQuestion[]>([]); const [brandGoal, setBrandGoal] = useState(""); const [themeHint, setThemeHint] = useState("你的隐藏行动风格"); const [message, setMessage] = useState(""); const [loading, setLoading] = useState(false); const [generating, setGenerating] = useState(false); const [templateDialogOpen, setTemplateDialogOpen] = useState(false); const [selectedTemplate, setSelectedTemplate] = useState<SurveyTemplate>(recommendedSurveyTemplates[0]);
  async function parseWjx() { const importUrl = normalizeImportUrl(wjxUrl); setLoading(true); setMessage(""); try { const data = await adminPostJson<ImportSurveyResponse>("/api/surveys/parse-wjx", { url: importUrl }, token); setQuestions(data.questions); setBrandGoal(buildDefaultBrandGoal(data.title)); setWjxUrl(data.source_url || importUrl); setMessage(`已导入“${data.title}”，识别 ${data.questions.length} 道题，并已将问卷标题写入调研目标。`); } catch (error) { setMessage(getErrorMessage(error)); } finally { setLoading(false); } }
  async function importTemplate(template: SurveyTemplate) { setLoading(true); setMessage(""); try { const data = await adminPostJson<ImportSurveyResponse>("/api/surveys/import-template", { url: template.sourceUrl }, token); setQuestions(data.questions); setBrandGoal(`${template.goal}。来源问卷：${data.title}`); setThemeHint(template.themeHint); setWjxUrl(data.source_url || template.sourceUrl); setTemplateDialogOpen(false); setMessage(`已从推荐模板“${template.title}”抓取真实问卷“${data.title}”，识别 ${data.questions.length} 道题。`); } catch (error) { setMessage(getErrorMessage(error)); } finally { setLoading(false); } }
  async function wrapSurvey() { setLoading(true); setGenerating(true); setMessage(""); try { const data = await adminPostJson<{ id: number; survey: WrappedSurvey }>("/api/surveys/wrap", { questions, brand_goal: brandGoal, theme_hint: themeHint }, token); onCreated(data.id, data.survey); } catch (error) { setMessage(getErrorMessage(error)); } finally { setGenerating(false); setLoading(false); } }
  return <section><GenerationOverlay visible={generating} /><TemplatePickerModal visible={templateDialogOpen} selected={selectedTemplate} loading={loading} onClose={() => setTemplateDialogOpen(false)} onSelect={setSelectedTemplate} onImport={importTemplate} /><div className="page-title"><div><p className="eyebrow">CREATE A STUDY</p><h2>创建互动包装</h2><p>从真实问卷模板开始，让 AI 围绕主题重新设计互动题和分析维度。</p></div><Sparkles size={26} /></div>{message && <div className="notice">{message}</div>}<div className="workspace two"><div className="panel import-panel"><div className="section-heading"><div><h2><BookOpen size={19} /> 导入问卷</h2><p>推荐先从公开模板库选择一份真实问卷。</p></div><span className="step-number">01</span></div><button className="template-trigger" onClick={() => setTemplateDialogOpen(true)} disabled={loading}><BookOpen size={18} /><span><strong>选择推荐问卷模板</strong><small>内置 {recommendedSurveyTemplates.length} 份公开模板入口，点击后浮窗预览并导入真实题目。</small></span></button><label htmlFor="wjx-url">公开问卷或模板链接</label><div className="url-input-row"><input id="wjx-url" type="url" value={wjxUrl} onChange={(event) => setWjxUrl(event.target.value)} placeholder="v.wjx.cn/vm/xxxxx.aspx 或 wenjuan.com/lib_detail_full/..." /><button className="primary import-action" onClick={() => void parseWjx()} disabled={loading || !wjxUrl.trim()}><Link2 size={16} /> 解析链接</button></div><p className="field-hint">支持问卷星公开填写链接和问卷网公开模板详情页；无法解析需要登录、校验或仅小程序可访问的链接。</p></div><div className="panel"><div className="section-heading"><h2><Sparkles size={19} /> AI 包装设定</h2><span className="step-number">02</span></div><label>调研目标</label><textarea className="short" value={brandGoal} onChange={(event) => setBrandGoal(event.target.value)} placeholder="选择模板或导入公开链接后自动填入，也可以手动补充" /><p className="field-hint">导入问卷后会自动填入来源标题，也可以继续补充调研目标。</p><label>测评主题</label><input value={themeHint} onChange={(event) => setThemeHint(event.target.value)} placeholder="例如：年轻人的口红消费风格、周末旅行决策风格" /><button className="primary" onClick={() => void wrapSurvey()} disabled={!questions.length || !brandGoal.trim() || !themeHint.trim() || loading}>生成互动包装</button></div></div><QuestionEditor questions={questions} onChange={setQuestions} /></section>;
}

function buildDefaultBrandGoal(surveyTitle = "") {
  return surveyTitle.trim() || "导入问卷";
}

function normalizeImportUrl(value: string) {
  const trimmed = value.trim();
  if (!trimmed || /^[a-z][a-z\d+.-]*:\/\//i.test(trimmed)) return trimmed;
  if (/^(?:[\w-]+\.)?(?:wjx\.cn|wenjuan\.com)(?:[/?#]|$)/i.test(trimmed)) {
    return `https://${trimmed}`;
  }
  return trimmed;
}

function TemplatePickerModal({ visible, selected, loading, onClose, onSelect, onImport }: { visible: boolean; selected: SurveyTemplate; loading: boolean; onClose: () => void; onSelect: (template: SurveyTemplate) => void; onImport: (template: SurveyTemplate) => void }) {
  if (!visible) return null;
  return <div className="template-overlay" role="dialog" aria-modal="true" aria-labelledby="template-dialog-title" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
    <div className="template-window">
      <div className="template-window-head"><div><p className="eyebrow">RECOMMENDED TEMPLATES</p><h2 id="template-dialog-title">选择一份真实问卷模板</h2><p>模板来自公开问卷模板页，导入时会实时抓取页面中的真实问卷题目。</p></div><button className="icon-button" onClick={onClose} title="关闭模板窗口" aria-label="关闭模板窗口"><X size={18} /></button></div>
      <div className="template-picker-layout">
        <div className="template-grid">{recommendedSurveyTemplates.map((template) => <button key={template.id} className={`template-card ${selected.id === template.id ? "selected" : ""}`} onClick={() => onSelect(template)}><span className="template-card-top"><em>{template.category}</em><BookOpen size={16} /></span><strong>{template.title}</strong><small>{template.summary}</small></button>)}</div>
        <aside className="template-preview"><span className="template-preview-label">当前选择</span><h3>{selected.title}</h3><span className="template-category">{selected.category}</span><p>{selected.summary}</p><div className="template-source"><span>真实来源</span><a href={selected.sourceUrl} target="_blank" rel="noreferrer">{selected.sourceUrl}<ExternalLink size={13} /></a></div><button className="primary wide" onClick={() => onImport(selected)} disabled={loading}><BookOpen size={17} /> {loading ? "正在抓取真实问卷..." : "导入这份模板"}</button></aside>
      </div>
    </div>
  </div>;
}

function GenerationOverlay({ visible }: { visible: boolean }) {
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [activeStep, setActiveStep] = useState(0);
  const [headlines, setHeadlines] = useState(fallbackHeadlines);
  const [headlineIndex, setHeadlineIndex] = useState(0);
  const headlinesRef = useRef(fallbackHeadlines);
  const seenHeadlinesRef = useRef<Set<string> | null>(null);

  useEffect(() => {
    if (!visible) return;
    setElapsedSeconds(0);
    setActiveStep(0);
    headlinesRef.current = fallbackHeadlines;
    setHeadlines(fallbackHeadlines);
    setHeadlineIndex(0);
    const startedAt = Date.now();
    const timer = window.setInterval(() => {
      const elapsed = Math.floor((Date.now() - startedAt) / 1000);
      setElapsedSeconds(elapsed);
      setActiveStep(Math.min(generationSteps.length - 1, elapsed < 5 ? 0 : elapsed < 12 ? 1 : 2));
    }, 1000);

    const controller = new AbortController();
    void loadHeadlines(controller.signal).then((items) => {
      if (!items.length) return;
      const seenHeadlines = seenHeadlinesRef.current ??= loadSeenHeadlines();
      const selectedHeadlines = selectHeadlineBatch(items, seenHeadlines);
      if (!selectedHeadlines.length) return;
      saveSeenHeadlines(seenHeadlines);
      headlinesRef.current = selectedHeadlines;
      setHeadlines(selectedHeadlines);
      setHeadlineIndex(0);
    }).catch(() => {
      headlinesRef.current = fallbackHeadlines;
      setHeadlines(fallbackHeadlines);
      setHeadlineIndex(0);
    });

    return () => {
      window.clearInterval(timer);
      controller.abort();
    };
  }, [visible]);

  useEffect(() => {
    if (!visible) return;
    const ticker = window.setInterval(() => {
      const items = headlinesRef.current;
      if (items.length > 1) setHeadlineIndex((index) => (index + 1) % items.length);
    }, 5000);
    return () => window.clearInterval(ticker);
  }, [visible]);

  if (!visible) return null;
  return <div className="generation-overlay" role="status" aria-live="polite"><div className="generation-window">
    <div className="generation-window-top"><div className="generation-icon"><LoaderCircle size={28} /></div><span className="generation-live"><i /> LIVE</span></div>
    <p className="eyebrow">AI GENERATION</p>
    <h2>正在生成你的互动测评</h2>
    <p className="generation-description">正在理解研究目标、设计主题维度、编排场景题，并校验评分映射。</p>
    <div className="generation-steps">
      {generationSteps.map((step, index) => <div className={`generation-step ${index < activeStep ? "done" : index === activeStep ? "active" : ""}`} key={step.title}>
        <span className="generation-step-marker">{index < activeStep ? "✓" : String(index + 1).padStart(2, "0")}</span>
        <div><strong>{step.title}</strong><small>{index === activeStep ? step.detail : index < activeStep ? "已完成，结果已交给下一阶段。" : "等待前置阶段完成。"}</small></div>
        {index === activeStep && <LoaderCircle className="generation-step-loader" size={16} />}
      </div>)}
    </div>
    <div className="generation-news"><span className="generation-news-label"><Sparkles size={13} /> 当今头条</span><span className="generation-news-text" key={headlines[headlineIndex]}>{headlines[headlineIndex]}</span></div>
    <div className="generation-elapsed"><span>已加载</span><strong>{formatElapsed(elapsedSeconds)}</strong></div>
  </div></div>;
}

function formatElapsed(seconds: number) {
  const minutes = Math.floor(seconds / 60).toString().padStart(2, "0");
  const remainder = (seconds % 60).toString().padStart(2, "0");
  return `${minutes}:${remainder}`;
}

async function loadHeadlines(signal: AbortSignal): Promise<string[]> {
  const cacheBust = Date.now().toString();
  try {
    const proxyResponse = await fetch(`/api/headlines?request_id=${cacheBust}`, {
      signal,
      cache: "no-store",
      headers: { Accept: "application/json", "Cache-Control": "no-cache" },
    });
    if (proxyResponse.ok) return normalizeHeadlines(await proxyResponse.json() as unknown);
  } catch {
    // 代理不可用时继续尝试浏览器直连。
  }
  const directUrl = `${headlineApiUrl}&request_id=${cacheBust}`;
  const response = await fetch(directUrl, {
    signal,
    cache: "no-store",
    headers: { Accept: "application/json", "Cache-Control": "no-cache" },
  });
  if (!response.ok) throw new Error(`头条接口请求失败（HTTP ${response.status}）`);
  const contentType = response.headers.get("content-type") || "";
  const rawPayload = contentType.includes("json") ? await response.json() as unknown : await response.text();
  const payload = typeof rawPayload === "string" ? parseHeadlineJson(rawPayload) : rawPayload;
  return normalizeHeadlines(payload);
}

function normalizeHeadlines(payload: unknown): string[] {
  const titles: string[] = [];
  const visit = (value: unknown) => {
    if (Array.isArray(value)) {
      value.forEach(visit);
      return;
    }
    if (!value || typeof value !== "object") return;
    const record = value as Record<string, unknown>;
    if (typeof record.title === "string") {
      const title = record.title.replace(/\s+/g, " ").trim();
      if (title.length >= 6 && title.length <= 160) titles.push(title);
    }
    Object.entries(record).forEach(([key, item]) => {
      if (key !== "title" && (Array.isArray(item) || Boolean(item && typeof item === "object"))) {
        visit(item);
      }
    });
  };
  visit(payload);
  return Array.from(new Set(titles));
}

function parseHeadlineJson(payload: string): unknown {
  try {
    return JSON.parse(payload);
  } catch {
    return null;
  }
}

function loadSeenHeadlines(): Set<string> {
  try {
    const stored = sessionStorage.getItem(seenHeadlinesStorageKey);
    const parsed = stored ? JSON.parse(stored) : [];
    return Array.isArray(parsed)
      ? new Set(parsed.filter((item): item is string => typeof item === "string"))
      : new Set<string>();
  } catch {
    return new Set<string>();
  }
}

function saveSeenHeadlines(seen: Set<string>) {
  try {
    sessionStorage.setItem(seenHeadlinesStorageKey, JSON.stringify(Array.from(seen)));
  } catch {
    // 浏览器禁止会话存储时，仍保留当前页面内的去重记录。
  }
}

function selectHeadlineBatch(items: string[], seen: Set<string>): string[] {
  const uniqueItems = Array.from(new Set(items));
  if (!uniqueItems.length) return [];
  let freshItems = uniqueItems.filter((item) => !seen.has(item));
  if (!freshItems.length) {
    seen.clear();
    freshItems = uniqueItems;
  }
  const batchSize = Math.min(maxHeadlinesPerGeneration, uniqueItems.length);
  const selected = shuffle(freshItems).slice(0, batchSize);
  selected.forEach((item) => seen.add(item));
  if (selected.length < batchSize) {
    const remaining = shuffle(uniqueItems.filter((item) => !selected.includes(item)));
    selected.push(...remaining.slice(0, batchSize - selected.length));
  }
  return selected;
}

function shuffle<T>(items: T[]): T[] {
  const result = items.slice();
  for (let index = result.length - 1; index > 0; index -= 1) {
    const randomIndex = Math.floor(Math.random() * (index + 1));
    [result[index], result[randomIndex]] = [result[randomIndex], result[index]];
  }
  return result;
}

function Dashboard({ survey, summary, surveyCount, loading, token, selectedId, status, finishing, onFinish, onRename }: { survey: WrappedSurvey | null; summary: AnalyticsSummary | null; surveyCount: number; loading: boolean; token: string; selectedId: number | null; status: "open" | "ended"; finishing: boolean; onFinish: () => void; onRename: (surveyName: string) => Promise<void> }) {
  if (!survey || !summary) return <Empty text={loading ? "正在读取数据..." : surveyCount ? "请选择一份问卷查看分析。" : "暂无问卷，请先创建互动包装。"} />;
  return <section><div className="page-title"><div><p className="eyebrow">OVERVIEW / {survey.theme}</p><SurveyTitleEditor title={survey.survey_name} onSave={onRename} /><p>{survey.tagline}</p></div><span className={`source-badge ${status}`}><span className="status-dot" /> {status === "ended" ? "问卷已结束" : "问卷开放中"}</span></div><div className="survey-control"><div><strong>{status === "ended" ? "数据分析已锁定" : "问卷正在收集答卷"}</strong><p>{status === "ended" ? "问卷已结束，已生成最终分析；后续答卷不会再写入。" : `当前已收集 ${summary.response_count} 份有效答卷，确认样本足够后即可结束问卷并生成 AI 数据分析。`}</p></div>{status === "open" ? <button className="primary" onClick={onFinish} disabled={finishing || summary.response_count < 1}><LockKeyhole size={17} /> {finishing ? "正在分析..." : "问卷份数足够，开始数据分析"}</button> : <span className="ended-mark"><CheckCircle2 size={17} /> 可查看问卷数据分析</span>}</div><div className="metrics"><Metric label="有效答卷" value={summary.response_count} icon={<Users size={18} />} /><Metric label="研究字段" value={summary.research_tags.length} icon={<Database size={18} />} /><Metric label="包装题目" value={survey.questions.length} icon={<Sparkles size={18} />} /><Metric label="结果类型" value={Object.keys(summary.result_counts).length} icon={<BarChart3 size={18} />} /></div><div className="dashboard-grid"><ChartCard title="结果类型分布" subtitle="了解不同趣味结果的占比" option={resultChartOption(summary.result_counts)} /><ChartCard title="答卷完成概况" subtitle="当前包装方案的有效回收量" option={completionChartOption(summary.response_count)} /></div><div className="chart-section"><div className="section-heading"><div><h3>研究选项分布</h3><p>数据按原始题目 ID 与研究标签聚合</p></div><BarChart3 size={20} /></div>{survey.questions.map((question) => <ChartCard key={question.question_id} compact title={question.research_tag || question.source_text} subtitle={`${question.question_id} · ${question.question_type}`} option={barChartOption(question, summary.option_counts[question.question_id] || {})} />)}</div><div className="export-row"><button onClick={() => selectedId && void downloadReport(`/api/analytics/${selectedId}/excel`, token, "fun_research_data.xlsx")}><FileSpreadsheet size={17} /> 导出 Excel 明细</button><button onClick={() => selectedId && void downloadReport(`/api/analytics/${selectedId}/pdf`, token, "fun_research_report.pdf")}><FileDown size={17} /> 导出 PDF 报表</button></div></section>;
}

function SurveyTitleEditor({ title, onSave }: { title: string; onSave: (surveyName: string) => Promise<void> }) {
  const [draft, setDraft] = useState(title);
  const [saving, setSaving] = useState(false);
  useEffect(() => { setDraft(title); }, [title]);
  async function saveTitle(event: React.FormEvent) {
    event.preventDefault();
    const nextTitle = draft.trim();
    if (!nextTitle || nextTitle === title || saving) return;
    setSaving(true);
    try {
      await onSave(nextTitle);
    } finally {
      setSaving(false);
    }
  }
  return <form className="title-editor" onSubmit={(event) => void saveTitle(event)}><label htmlFor="survey-title-input">问卷标题</label><div className="title-editor-row"><input id="survey-title-input" value={draft} onChange={(event) => setDraft(event.target.value)} maxLength={60} /><button className="primary" type="submit" disabled={saving || !draft.trim() || draft.trim() === title} title="保存标题"><Save size={16} /> {saving ? "保存中..." : "保存"}</button></div></form>;
}

function AnalysisView({ survey, summary, analysis, status, token, selectedId }: { survey: WrappedSurvey; summary: AnalyticsSummary | null; analysis: ResearchAnalysis | null; status: "open" | "ended"; token: string; selectedId: number | null }) {
  if (status !== "ended" || !analysis) return <section className="analysis-locked panel"><LockKeyhole size={28} /><p className="eyebrow">ANALYSIS LOCKED</p><h2>问卷还在进行，暂不开放分析数据功能</h2><p>请先在“数据总览”中确认问卷份数足够并点击结束问卷，系统才会调用 AI 生成最终研究分析。</p></section>;
  const dimensions = analysis.dimensions || [];
  const questions = analysis.questions || summary?.question_stats || [];
  return <section><div className="page-title"><div><p className="eyebrow">RESEARCH ANALYSIS / {survey.theme}</p><h2>问卷数据分析</h2><p>以“{analysis.research_goal || survey.brand_goal || survey.theme}”为主要调研目标，结合题目映射综合解读。</p></div><span className="source-badge ended"><span className="status-dot" /> 已结束 · AI 已生成</span></div><div className="analysis-summary"><div className="analysis-summary-title"><div><span>调研目标</span><strong>{analysis.research_goal || survey.brand_goal || survey.theme}</strong></div><span className="analysis-time">生成于 {analysis.generated_at}</span></div><p className="analysis-conclusion">{analysis.research_conclusion}</p><div className="analysis-long-summary"><strong>总结小结</strong><p>{analysis.long_summary}</p></div></div><div className="analysis-findings"><div className="section-heading"><div><h3>关键发现</h3><p>AI 根据准确统计事实提炼的研究启示</p></div><Sparkles size={20} /></div><div className="finding-grid">{analysis.key_findings.map((finding, index) => <article key={`${index}-${finding}`}><span>{String(index + 1).padStart(2, "0")}</span><p>{finding}</p></article>)}</div></div><div className="analysis-section"><div className="section-heading"><div><h3>按映射维度拆分分析</h3><p>维度指数、覆盖答卷和 AI 解释均绑定当前样本</p></div><BarChart3 size={20} /></div><div className="analysis-dimension-list">{dimensions.map((dimension) => <article className="analysis-dimension" key={dimension.key}><div className="analysis-dimension-head"><div><strong>{dimension.name}</strong><span>{dimension.mapped_research_tags.length ? `映射：${dimension.mapped_research_tags.join("、")}` : "主题维度"}</span></div>{dimension.index !== null && dimension.index !== undefined && <b>{dimension.index}</b>}</div>{dimension.index !== null && dimension.index !== undefined && <div className="dimension-scale"><span style={{ width: `${dimension.index}%` }} /></div>}<p>{dimension.conclusion}</p><small>覆盖 {dimension.coverage_count} 份答卷 · 关联 {dimension.mapped_question_ids.length} 道题</small></article>)}</div></div><div className="analysis-section"><div className="section-heading"><div><h3>题目映射与准确数据</h3><p>人数和比例由系统按选项原值统计，AI 不改写数字</p></div><Database size={20} /></div><div className="analysis-data-list">{questions.map((question) => <article className="analysis-question" key={question.question_id}><div className="analysis-question-head"><div><strong>{question.research_tag || question.question}</strong><span>{question.question_id} · 覆盖 {question.answered_count} 份答卷（{question.answer_rate}%）</span></div><span>{question.dimension_keys.length ? `维度：${question.dimension_keys.join("、")}` : "研究字段"}</span></div><p>{question.question}</p><div className="option-stat-list">{question.options.map((option) => <div className="option-stat" key={option.option}><span>{option.option}</span><div className="option-stat-track"><i style={{ width: `${option.percentage}%` }} /></div><b>{option.count} 人 · {option.percentage}%</b></div>)}</div></article>)}</div></div><div className="analysis-limitations"><strong>分析边界</strong><p>{analysis.limitations}</p></div><div className="export-row"><button onClick={() => selectedId && void downloadReport(`/api/analytics/${selectedId}/excel`, token, "fun_research_data.xlsx")}><FileSpreadsheet size={17} /> 导出 Excel 明细</button><button onClick={() => selectedId && void downloadReport(`/api/analytics/${selectedId}/pdf`, token, "fun_research_report.pdf")}><FileDown size={17} /> 导出 PDF 报表</button></div></section>;
}

function MappingView({ survey }: { survey: WrappedSurvey }) { return <section><div className="page-title"><div><p className="eyebrow">TRACEABLE MAPPING</p><h2>研究参考与互动题映射</h2><p>互动题以主题维度为主重新设计，只有相关研究内容才建立映射，不再强行一题对应一题。</p></div><ShieldCheck size={26} /></div>{survey.analysis_method && <div className="method-note"><strong>分析方法</strong><p>{survey.analysis_method}</p></div>}<div className="mapping-list">{survey.questions.map((question, index) => <article className="mapping-row" key={question.question_id}><div className="mapping-index">{String(index + 1).padStart(2, "0")}</div><div><span className="mapping-label">研究参考 · {question.research_tag || "主题原创题"}</span><h3>{question.source_text || "本题由互动主题独立设计"}</h3><small>{question.research_refs?.length ? `关联 ${question.research_refs.join("、")}` : "无直接原题映射"}</small></div><div className="mapping-arrow">→</div><div><span className="mapping-label accent">用户体验题面</span><h3>{question.public_text}</h3><small>{question.options.length ? `${question.options.length} 个选项` : "文本回答"}{question.rationale ? ` · ${question.rationale}` : ""}</small></div></article>)}</div></section>; }
function QuestionEditor({ questions, onChange }: { questions: SurveyQuestion[]; onChange: (questions: SurveyQuestion[]) => void }) {
  function updateQuestion(index: number, patch: Partial<SurveyQuestion>) {
    onChange(questions.map((question, questionIndex) => questionIndex === index ? { ...question, ...patch } : question));
  }
  function updateOption(questionIndex: number, optionIndex: number, value: string) {
    const question = questions[questionIndex];
    if (!question) return;
    updateQuestion(questionIndex, { options: question.options.map((option, index) => index === optionIndex ? value : option) });
  }
  function addQuestion() {
    onChange([...questions, { question_id: `q${questions.length + 1}`, text: "", question_type: "single_choice", options: ["", ""], research_tag: "", required: true }]);
  }
  function removeQuestion(index: number) {
    onChange(questions.filter((_, questionIndex) => questionIndex !== index));
  }
  function addOption(questionIndex: number) {
    const question = questions[questionIndex];
    if (!question) return;
    updateQuestion(questionIndex, { options: [...question.options, ""] });
  }
  function removeOption(questionIndex: number, optionIndex: number) {
    const question = questions[questionIndex];
    if (!question) return;
    updateQuestion(questionIndex, { options: question.options.filter((_, index) => index !== optionIndex) });
  }
  return <section className="question-editor panel"><div className="section-heading"><div><h2><Database size={19} /> 已解析题目</h2><p>解析后可直接填写和调整，修改内容会用于生成互动包装。</p></div><button className="secondary compact-action" onClick={addQuestion}><Plus size={16} /> 新增题目</button></div>{!questions.length ? <div className="editor-empty"><p>尚未解析问卷。</p><span>选择推荐模板或粘贴问卷星公开链接后，题目会出现在这里。</span></div> : <div className="editor-list">{questions.map((question, index) => <article className="question-editor-item" key={`${question.question_id}-${index}`}><div className="editor-item-head"><span className="editor-index">{String(index + 1).padStart(2, "0")}</span><strong>第 {index + 1} 题</strong><button className="icon-button subtle-danger" onClick={() => removeQuestion(index)} title="删除题目" aria-label={`删除第 ${index + 1} 题`}><Trash2 size={16} /></button></div><div className="editor-fields"><div><label htmlFor={`question-id-${index}`}>题目编号</label><input id={`question-id-${index}`} value={question.question_id} onChange={(event) => updateQuestion(index, { question_id: event.target.value })} placeholder="例如 q1" /></div><div><label htmlFor={`question-type-${index}`}>题型</label><select id={`question-type-${index}`} value={question.question_type} onChange={(event) => updateQuestion(index, { question_type: event.target.value, options: event.target.value === "text" ? [] : question.options.length ? question.options : ["", ""] })}><option value="single_choice">单选题</option><option value="multiple_choice">多选题</option><option value="text">填空题</option><option value="scale">评分题</option></select></div><label className="required-toggle"><input type="checkbox" checked={question.required} onChange={(event) => updateQuestion(index, { required: event.target.checked })} /> 必答题</label></div><label htmlFor={`question-text-${index}`}>题目内容</label><textarea id={`question-text-${index}`} className="question-text-input" value={question.text} onChange={(event) => updateQuestion(index, { text: event.target.value })} placeholder="填写题目内容" /><div className="editor-fields"><div><label htmlFor={`research-tag-${index}`}>研究标签</label><input id={`research-tag-${index}`} value={question.research_tag} onChange={(event) => updateQuestion(index, { research_tag: event.target.value })} placeholder="例如：价格接受区间" /></div></div>{question.question_type !== "text" && <div className="option-editor"><div className="option-editor-head"><label>选项</label><button className="text-action" onClick={() => addOption(index)}><Plus size={14} /> 添加选项</button></div>{question.options.map((option, optionIndex) => <div className="option-editor-row" key={`${index}-${optionIndex}`}><span>{String.fromCharCode(65 + optionIndex)}</span><input value={option} onChange={(event) => updateOption(index, optionIndex, event.target.value)} placeholder={`填写选项 ${optionIndex + 1}`} /><button className="icon-button" onClick={() => removeOption(index, optionIndex)} title="删除选项" aria-label={`删除第 ${optionIndex + 1} 个选项`} disabled={question.options.length <= 1}><X size={15} /></button></div>)}</div>}</article>)}</div>}</section>;
}
function QuestionInput({ index, question, value, onChange }: { index: number; question: WrappedQuestion; value: unknown; onChange: (value: unknown) => void }) { return <div className="question"><div className="question-meta"><span>{String(index).padStart(2, "0")}</span>{question.required && <em>必答</em>}</div><h3>{question.public_text}</h3>{question.question_type === "multiple_choice" ? <div className="options">{question.options.map((option) => { const selected = Array.isArray(value) && value.includes(option); return <button className={selected ? "selected" : ""} key={option} onClick={() => { const current = Array.isArray(value) ? value : []; onChange(selected ? current.filter((item) => item !== option) : [...current, option]); }}>{option}</button>; })}</div> : question.question_type === "text" ? <input value={String(value || "")} onChange={(event) => onChange(event.target.value)} /> : <div className="options">{(question.options.length ? question.options : ["非常不像", "有点像", "很像"]).map((option) => <button className={value === option ? "selected" : ""} key={option} onClick={() => onChange(option)}>{option}</button>)}</div>}</div>; }
function Metric({ label, value, icon }: { label: string; value: number; icon: React.ReactNode }) { return <div className="metric"><span className="metric-icon">{icon}</span><span>{label}</span><strong>{value}</strong></div>; }
function ChartCard({ title, subtitle, option, compact = false }: { title: string; subtitle: string; option: echarts.EChartsOption; compact?: boolean }) { const ref = useRef<HTMLDivElement>(null); useEffect(() => { if (!ref.current) return; const chart = echarts.init(ref.current); chart.setOption(option); const resize = () => chart.resize(); window.addEventListener("resize", resize); return () => { window.removeEventListener("resize", resize); chart.dispose(); }; }, [option]); return <div className={`chart-card ${compact ? "compact" : ""}`}><div className="chart-card-title"><div><h3>{title}</h3><p>{subtitle}</p></div><BarChart3 size={18} /></div><div className="chart-canvas" ref={ref} /></div>; }
function resultChartOption(counts: Record<string, number>): echarts.EChartsOption { return { color: ["#2467e8", "#32a287", "#f29d49", "#db5873", "#7b61c9"], tooltip: { trigger: "item" }, legend: { bottom: 0, type: "scroll" }, series: [{ type: "pie", radius: ["42%", "68%"], center: ["50%", "44%"], label: { formatter: "{b}\n{d}%" }, data: Object.entries(counts).map(([name, value]) => ({ name, value })) }] }; }
function completionChartOption(count: number): echarts.EChartsOption { return { series: [{ type: "gauge", startAngle: 90, endAngle: -270, radius: "78%", pointer: { show: false }, progress: { show: true, width: 15, itemStyle: { color: "#2467e8" } }, axisLine: { lineStyle: { width: 15, color: [[1, "#e4e9f1"]] } }, axisTick: { show: false }, splitLine: { show: false }, axisLabel: { show: false }, detail: { valueAnimation: true, formatter: `${count}\n有效答卷`, fontSize: 20, lineHeight: 30, color: "#18212b" }, data: [{ value: count, name: "" }] }] }; }
function barChartOption(question: WrappedQuestion, counts: Record<string, number>): echarts.EChartsOption { const labels = question.options.length ? question.options : Object.keys(counts); return { color: ["#2467e8"], grid: { left: 20, right: 28, top: 12, bottom: 10, containLabel: true }, tooltip: { trigger: "axis", axisPointer: { type: "shadow" } }, xAxis: { type: "value", minInterval: 1 }, yAxis: { type: "category", data: labels, axisLabel: { width: 150, overflow: "truncate" } }, series: [{ type: "bar", data: labels.map((label) => counts[label] || 0), barMaxWidth: 18, itemStyle: { borderRadius: [0, 4, 4, 0] }, label: { show: true, position: "right" } }] }; }
function isAnswerPresent(value: unknown) { return Array.isArray(value) ? value.length > 0 : typeof value === "string" ? value.trim() !== "" : value !== undefined && value !== null; }
function isSurveyComplete(survey: WrappedSurvey, answers: Record<string, unknown>) { return survey.questions.every((question) => !question.required || isAnswerPresent(answers[question.question_id])); }
function Empty({ text }: { text: string }) { return <div className="empty">{text}</div>; }
async function postJson<T>(url: string, body: unknown): Promise<T> { const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) }); if (!response.ok) throw new Error(await readError(response)); return response.json(); }
async function adminPostJson<T>(url: string, body: unknown, token: string): Promise<T> { const response = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json", "X-Admin-Token": token }, body: JSON.stringify(body) }); if (!response.ok) throw new Error(await readError(response)); return response.json(); }
async function adminDeleteJson<T = { message?: string }>(url: string, token: string): Promise<T> { const response = await fetch(url, { method: "DELETE", headers: { "X-Admin-Token": token } }); if (!response.ok) throw new Error(await readError(response)); return response.json(); }
async function fetchJson<T>(url: string): Promise<T> { const response = await fetch(url); if (!response.ok) throw new Error(await readError(response)); return response.json(); }
async function adminFetchJson<T>(url: string, token: string): Promise<T> { const response = await fetch(url, { headers: { "X-Admin-Token": token } }); if (!response.ok) throw new Error(await readError(response)); return response.json(); }
async function readError(response: Response) { try { const data = (await response.json()) as { detail?: string }; return data.detail || "请求失败"; } catch { return `请求失败（HTTP ${response.status}）`; } }
async function downloadReport(url: string, token: string, fileName: string) { const response = await fetch(url, { headers: { "X-Admin-Token": token } }); if (!response.ok) throw new Error(await readError(response)); const blob = await response.blob(); const link = document.createElement("a"); link.href = URL.createObjectURL(blob); link.download = fileName; link.click(); URL.revokeObjectURL(link.href); }
function getErrorMessage(error: unknown) { return error instanceof Error ? error.message : "发生未知错误"; }
createRoot(document.getElementById("root")!).render(<App />);
