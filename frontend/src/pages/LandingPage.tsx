import { ArrowRight, BarChart3, CheckCircle2, FileText, KeyRound, Play, ShieldCheck, Sparkles, Users } from "lucide-react";
import { useEffect, useMemo, useRef, useState, type PointerEvent, type ReactNode } from "react";
import { SiteFooter } from "../components/SiteFooter";

type LandingPageProps = {
  authenticated: boolean;
};

const capabilityCards = [
  { title: "产品能力", description: "把问卷导入、互动包装、发布回收和数据分析组织成一条清晰的研究流程。", detail: "从一个研究问题开始，你可以在控制台中导入原始问卷，确认 AI 生成的互动题面，发布分享链接，结束后查看统计分析和导出报表。", icon: <Sparkles size={21} />, className: "" },
  { title: "个人管理", description: "问卷与答卷按照创建账号隔离，研究材料归属于自己的工作区。", detail: "每个账号拥有独立的个人问卷空间。问卷创建后默认由创建账号管理，管理员可以继续编辑题面、控制发布状态、查看答卷和处理回收站内容。", icon: <Users size={21} />, className: "purple" },
  { title: "开放 API", description: "按 Token 管理生成、解析和分析用量，让服务调用有记录可追踪。", detail: "API 服务页会展示 Token 余额、累计使用量、今日调用、最近调用记录和额度申请记录。生成互动包装、解析题目和数据分析会按内容量估算消耗。", icon: <KeyRound size={21} />, className: "orange" },
  { title: "运营治理", description: "平台管理员处理账号、额度、审核和平台配置，研究工作区保持专注。", detail: "平台管理入口与个人控制台分开，管理员可以审核额度申请、查看平台用量、进行内容审核和管理平台设置。", icon: <ShieldCheck size={21} />, className: "green" },
];

const demoQuestions = [
  { title: "如果你要开始一项调研，第一步通常会先确定什么？", hint: "这对应问卷导入前的研究目标整理。", options: ["先把研究目标说清楚", "先找一份可以参考的原始问卷", "先想好最后要展示的结果"] },
  { title: "你最希望 AI 优先帮你处理哪一部分？", hint: "这对应项目中的 AI 互动包装流程。", options: ["从原始题目提炼主题", "把题目改成更自然的互动表达", "根据答卷生成分析和研究结论"] },
  { title: "完成回收后，你最想先查看哪类信息？", hint: "这对应数据总览、分析页面和报表导出能力。", options: ["有效答卷数量和回收状态", "研究维度与选项比例", "可导出的 Excel 或 PDF 报表"] },
];

const demoResults = [
  { title: "研究目标先行型", summary: "你更重视从问题和研究目标出发，再决定题目如何包装。", next: "适合先在控制台导入问卷，检查研究字段，再调用 AI 生成互动草稿。", tags: ["目标明确", "适合研究导向", "先校准后发布"] },
  { title: "互动包装实践型", summary: "你关注题目是否自然、受访者是否愿意完成，以及结果是否容易理解。", next: "适合重点检查 AI 生成的题面、选项覆盖、结果类型和题目映射，再发布分享链接。", tags: ["体验优先", "适合互动包装", "保留人工判断"] },
  { title: "数据结论复核型", summary: "你更关心回收之后的证据、分布和可提交的研究材料。", next: "适合结束问卷后生成分析，查看人数、比例、维度和关键发现，并导出 Excel 或 PDF。", tags: ["数据驱动", "适合分析复核", "结果可导出"] },
];

export function LandingPage({ authenticated }: LandingPageProps) {
  const [demoIndex, setDemoIndex] = useState(0);
  const [answers, setAnswers] = useState<number[]>([]);
  const [demoFinished, setDemoFinished] = useState(false);
  const [revealReady, setRevealReady] = useState(true);
  const demoResult = useMemo(() => {
    if (!answers.length) return demoResults[0];
    const counts = answers.reduce((result, answer) => {
      result[answer] = (result[answer] || 0) + 1;
      return result;
    }, {} as Record<number, number>);
    const strongest = Object.entries(counts).sort((a, b) => b[1] - a[1])[0]?.[0] || "0";
    return demoResults[Number(strongest)];
  }, [answers]);

  useEffect(() => {
    if (!revealReady) return;
    const elements = Array.from(document.querySelectorAll<HTMLElement>(".landing-page [data-reveal]"));
    const observer = new IntersectionObserver((entries) => entries.forEach((entry) => {
      if (entry.isIntersecting) {
        entry.target.classList.add("is-revealed");
        observer.unobserve(entry.target);
      }
    }), { threshold: 0.12, rootMargin: "0px 0px -8%" });
    elements.forEach((element) => observer.observe(element));
    return () => observer.disconnect();
  }, [revealReady]);

  function go(path: string) {
    window.location.assign(path);
  }

  function scrollToDemo() {
    document.getElementById("try-demo")?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function chooseAnswer(answer: number) {
    const next = [...answers];
    next[demoIndex] = answer;
    setAnswers(next);
    if (demoIndex < demoQuestions.length - 1) {
      window.setTimeout(() => setDemoIndex((index) => index + 1), 220);
    } else {
      window.setTimeout(() => setDemoFinished(true), 220);
    }
  }

  function restartDemo() {
    setDemoIndex(0);
    setAnswers([]);
    setDemoFinished(false);
  }

  return (
    <div className={`landing-page ${revealReady ? "reveal-ready" : ""}`}>
      <section className="landing-hero" data-reveal>
        <div className="landing-hero-copy">
          <p className="eyebrow">FUN RESEARCH PLATFORM</p>
          <h1>把问卷，变成真正<span className="hero-accent-gradient">能被理解</span>的研究。</h1>
          <p className="landing-lead">趣测智研是一套面向个人研究者的 AI 问卷平台：从原始题目导入、互动包装，到答卷回收、数据分析和结果导出，都在一个清晰的研究工作区里完成。</p>
          <div className="landing-actions"><button className="primary landing-primary" onClick={() => go(authenticated ? "/console" : "/register")}>{authenticated ? "进入控制台" : "免费创建个人账号"} <ArrowRight size={17} /></button><button className="landing-secondary-action" onClick={scrollToDemo}><Play size={16} /> 查看演示流程</button></div>
          <div className="landing-trust-row"><span><CheckCircle2 size={15} /> 个人空间隔离</span><span><CheckCircle2 size={15} /> Token 用量可追踪</span><span><CheckCircle2 size={15} /> 问卷数据可导出</span></div>
        </div>
        <TiltPreview>
        <div className="landing-hero-visual" aria-label="趣测智研控制台预览">
          <div className="landing-visual-top"><div className="landing-visual-brand"><img src="/brand-icon.png" alt="" /><strong>趣测智研</strong></div><span className="landing-live-dot"><i /> 工作区在线</span></div>
          <div className="landing-visual-body"><div className="landing-visual-sidebar"><span className="visual-sidebar-active"><BarChart3 size={14} /> 数据总览</span><span><Sparkles size={14} /> AI 问卷</span><span><ShieldCheck size={14} /> 个人问卷</span><span><KeyRound size={14} /> API 服务</span></div><div className="landing-visual-dashboard"><div className="visual-dashboard-heading"><span>本月研究概览</span><strong>2026 / 09</strong></div><div className="visual-metric-row"><div><small>有效问卷</small><b>24</b><em>+18.4%</em></div><div><small>回收答卷</small><b>3,860</b><em>+26.1%</em></div><div><small>Token 余额</small><b>18.2k</b><em>可用</em></div></div><div className="visual-chart"><div className="visual-chart-head"><span>答卷回收趋势</span><small>近 30 天</small></div><div className="visual-bars">{[35, 52, 43, 62, 54, 76, 68, 86, 72, 92, 81, 100].map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}</div></div><div className="visual-survey-list"><div><span className="visual-status green" /><strong>新品用户体验调研</strong><small>收集中 · 1,284 份</small></div><div><span className="visual-status blue" /><strong>秋季消费偏好研究</strong><small>已归档 · AI 已分析</small></div></div></div></div>
        </div>
        </TiltPreview>
      </section>

      <section className="landing-service-band" data-reveal><div><strong>产品能力</strong><span>从导入到分析一站完成</span></div><div><strong>个人管理</strong><span>问卷数据按账号隔离</span></div><div><strong>开放 API</strong><span>Token 用量清晰可追踪</span></div><div><strong>运营治理</strong><span>平台管理员分层处理</span></div></section>

      <section className="landing-section landing-capability-section" id="product" data-reveal>
        <div className="landing-section-heading"><div><p className="eyebrow">PRODUCT CAPABILITIES</p><h2>从一个想法，到一份完整研究</h2></div><p>四个核心模块覆盖问卷研究的全流程，个人研究者也可以拥有接近专业团队的工作方式。</p></div>
        <div className="landing-feature-grid landing-capability-grid">{capabilityCards.map((feature) => <article data-reveal key={feature.title}><div className={`landing-feature-icon ${feature.className}`}>{feature.icon}</div><h3>{feature.title}</h3><p>{feature.description}</p><div className="landing-feature-detail">{feature.detail}</div></article>)}</div>
      </section>

      <section className="landing-demo-section" id="try-demo" data-reveal>
        <div className="landing-section-heading demo-section-heading"><div><p className="eyebrow">TRY AN AI-WRAPPED SURVEY · 30 SECONDS</p><h2>亲手做一份 AI 包装过的问卷</h2></div><p>不用注册，直接体验受访者看到的界面。这里用项目实际的“互动题面、结果反馈和研究说明”做一个轻量演示，不会创建真实问卷，也不会消耗 Token。</p></div>
        <div className="landing-demo-layout">
          <div className="demo-question-panel" data-reveal>
            {!demoFinished ? <><div className="demo-progress-label"><span>第 {demoIndex + 1} 题 / {demoQuestions.length}</span><b>{Math.round(((demoIndex + 1) / demoQuestions.length) * 100)}%</b></div><div className="demo-progress"><span style={{ width: `${((demoIndex + 1) / demoQuestions.length) * 100}%` }} /></div><div className="demo-question-kicker">互动研究体验</div><h3>{demoQuestions[demoIndex].title}</h3><p className="demo-question-hint">{demoQuestions[demoIndex].hint}</p><div className="demo-options">{demoQuestions[demoIndex].options.map((option, index) => <button key={option} className={answers[demoIndex] === index ? "selected" : ""} onClick={() => chooseAnswer(index)}><span>{String.fromCharCode(65 + index)}</span>{option}</button>)}</div><div className="demo-question-actions"><button onClick={() => setDemoIndex((index) => Math.max(0, index - 1))} disabled={demoIndex === 0}>上一题</button><span>选择后自动进入下一题</span></div></> : <DemoResult result={demoResult} onRestart={restartDemo} onStart={() => go(authenticated ? "/console" : "/register")} />}</div>
          <div className="demo-explainer" data-reveal><div className="demo-explainer-icon"><Sparkles size={23} /></div><h3>不只收集答案，而是理解答案背后的人。</h3><p>传统问卷让受访者疲劳，让研究者面对一堆干巴巴的选项。趣测智研用 AI 把题目变成更自然的互动表达，回收后再用统计和研究维度把数据变成可解释的洞察。</p><div className="demo-explainer-list"><div><span>🎯</span><div><strong>智能追问</strong><p>围绕研究目标组织题目，让每道题都能服务于后续分析。</p></div></div><div><span>⚡</span><div><strong>实时洞察</strong><p>回收过程中查看有效答卷、选项分布和答题完成情况。</p></div></div><div><span>🔒</span><div><strong>空间隔离</strong><p>每个账号拥有独立工作区，问卷和答卷按账号管理。</p></div></div></div></div>
        </div>
      </section>

      <section className="landing-workflow" data-reveal><div className="landing-section-heading"><div><p className="eyebrow">HOW IT WORKS</p><h2>三步，把研究推进到结果</h2></div><p>每一步都对应当前项目已经提供的页面和操作，不需要在多个工具之间来回切换。</p></div><div className="landing-steps"><article data-reveal><span>01</span><div><h3>创建个人空间</h3><p>注册账号后，所有问卷默认归你管理，同时获得可追踪的 Token 额度。你可以在控制台看到自己的问卷和状态。</p></div></article><article data-reveal><span>02</span><div><h3>生成并发布问卷</h3><p>导入题目，填写调研目标，调用 AI 生成互动包装，再检查题面、选项、研究标签和结果映射，确认后发布专属分享链接。</p></div></article><article data-reveal><span>03</span><div><h3>查看研究结果</h3><p>发布后回收答卷，结束问卷后生成数据分析，查看选项统计、研究维度、关键发现和分析边界，并导出 Excel 或 PDF 报表。</p></div></article></div></section>

      <section className="landing-faq-section" data-reveal><div className="landing-section-heading"><div><p className="eyebrow">FAQ</p><h2>你可能想问</h2></div><p>下面的说明按当前项目已有的账号、AI、分析和平台功能整理。</p></div><FaqItem question="个人研究者使用需要付费吗？" answer="当前项目不接入真实支付。注册后进入个人工作区，生成、解析和分析功能使用 Token 额度；额度不足时可以提交申请，由平台管理员审核发放。"/><FaqItem question="我的数据会被用于训练模型吗？" answer="项目当前的隐私边界是：AI 请求会将完成当前生成、解析或分析所需的研究内容发送给配置的模型服务。平台不会在页面中承诺将你的数据用于模型训练，建议不要提交与研究无关的敏感信息。"/><FaqItem question="AI 生成的问卷可以修改吗？" answer="可以。AI 生成结果先保存为草稿，研究者可以在互动问卷编辑器中调整题面、选项、研究标签和题目映射，确认后再发布。"/><FaqItem question="什么时候可以查看数据分析？" answer="问卷处于收集状态时先查看回收概况。结束问卷后样本数量锁定，管理员可以点击开始数据分析，系统再生成统计、维度和研究结论。"/><FaqItem question="API 有哪些可追踪信息？" answer="API 服务页会展示 Token 余额、累计已用、今日调用、调用次数、最近调用记录和额度申请记录。生成、解析和分析调用会记录用量，导出和查看不扣 Token。"/></section>

      <section className="landing-cta" data-reveal><div><p className="eyebrow">READY TO RESEARCH</p><h2>先建立一个属于你的研究空间。</h2><p>毕设阶段可以先用首页演示理解流程，再注册账号导入自己的问卷。平台保留 Token 申请、平台审核和研究结果导出的完整路径。</p></div><button className="primary" onClick={() => go(authenticated ? "/console" : "/register")}>开始使用 <ArrowRight size={17} /></button></section>
      <SiteFooter />
    </div>
  );
}

function TiltPreview({ children }: { children: ReactNode }) {
  const ref = useRef<HTMLDivElement>(null);
  function handleMove(event: PointerEvent<HTMLDivElement>) {
    const element = ref.current;
    if (!element || event.pointerType === "touch") return;
    const bounds = element.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width - 0.5;
    const y = (event.clientY - bounds.top) / bounds.height - 0.5;
    element.style.setProperty("--tilt-x", `${(-y * 7).toFixed(2)}deg`);
    element.style.setProperty("--tilt-y", `${(x * 9).toFixed(2)}deg`);
    element.style.setProperty("--tilt-scale", "1.015");
  }
  function reset() {
    const element = ref.current;
    if (!element) return;
    element.style.setProperty("--tilt-x", "0deg");
    element.style.setProperty("--tilt-y", "0deg");
    element.style.setProperty("--tilt-scale", "1");
  }
  return <div className="landing-tilt-wrap" ref={ref} onPointerMove={handleMove} onPointerLeave={reset}>{children}</div>;
}

function DemoResult({ result, onRestart, onStart }: { result: typeof demoResults[number]; onRestart: () => void; onStart: () => void }) {
  return <div className="demo-result"><div className="demo-result-mark">✦</div><p className="eyebrow">你的互动研究倾向</p><h3>{result.title}</h3><p>{result.summary}</p><div className="demo-result-tags">{result.tags.map((tag) => <span key={tag}>{tag}</span>)}</div><div className="demo-result-next"><strong>下一步建议</strong><p>{result.next}</p></div><div className="demo-result-actions"><button onClick={onRestart}>再体验一次</button><button className="primary" onClick={onStart}>开始真实研究 <ArrowRight size={15} /></button></div></div>;
}

function FaqItem({ question, answer }: { question: string; answer: string }) {
  const [open, setOpen] = useState(false);
  return <article className={`faq-item ${open ? "open" : ""}`}><button onClick={() => setOpen((value) => !value)}><span>{question}</span><b>{open ? "−" : "+"}</b></button>{open && <p>{answer}</p>}</article>;
}
