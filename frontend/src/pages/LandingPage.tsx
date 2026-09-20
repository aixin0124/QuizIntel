import { ArrowRight, BarChart3, CheckCircle2, ChevronRight, FileText, KeyRound, Layers3, Play, ShieldCheck, Sparkles, Users } from "lucide-react";

type LandingPageProps = {
  authenticated: boolean;
};

export function LandingPage({ authenticated }: LandingPageProps) {
  function go(path: string) {
    window.location.assign(path);
  }

  return (
    <div className="landing-page">
      <section className="landing-hero">
        <div className="landing-hero-copy">
          <p className="eyebrow">FUN RESEARCH PLATFORM</p>
          <h1>把问卷，变成真正能被理解的研究。</h1>
          <p className="landing-lead">
            趣测智研是一套面向个人研究者与协作小组的 AI 问卷平台：从题目导入、互动包装，到回收、分析和结果导出，都在一个清晰的工作区里完成。
          </p>
          <div className="landing-actions">
            <button className="primary landing-primary" onClick={() => go(authenticated ? "/console" : "/register")}>
              {authenticated ? "进入控制台" : "免费创建个人账号"} <ArrowRight size={17} />
            </button>
            <button className="landing-secondary-action" onClick={() => go("/login")}>
              <Play size={16} /> 查看演示流程
            </button>
          </div>
          <div className="landing-trust-row">
            <span><CheckCircle2 size={15} /> 个人空间隔离</span>
            <span><CheckCircle2 size={15} /> Token 用量可追踪</span>
            <span><CheckCircle2 size={15} /> 问卷数据可导出</span>
          </div>
        </div>
        <div className="landing-hero-visual" aria-label="趣测智研控制台预览">
          <div className="landing-visual-top">
            <div className="landing-visual-brand"><img src="/brand-icon.png" alt="" /><strong>趣测智研</strong></div>
            <span className="landing-live-dot"><i /> 工作区在线</span>
          </div>
          <div className="landing-visual-body">
            <div className="landing-visual-sidebar">
              <span className="visual-sidebar-active"><BarChart3 size={14} /> 数据总览</span>
              <span><Sparkles size={14} /> AI 问卷</span>
              <span><Users size={14} /> 协作成员</span>
              <span><KeyRound size={14} /> API 服务</span>
            </div>
            <div className="landing-visual-dashboard">
              <div className="visual-dashboard-heading"><span>本月研究概览</span><strong>2026 / 09</strong></div>
              <div className="visual-metric-row">
                <div><small>有效问卷</small><b>24</b><em>+18.4%</em></div>
                <div><small>回收答卷</small><b>3,860</b><em>+26.1%</em></div>
                <div><small>Token 余额</small><b>18.2k</b><em>可用</em></div>
              </div>
              <div className="visual-chart">
                <div className="visual-chart-head"><span>答卷回收趋势</span><small>近 30 天</small></div>
                <div className="visual-bars">{[35, 52, 43, 62, 54, 76, 68, 86, 72, 92, 81, 100].map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}</div>
              </div>
              <div className="visual-survey-list">
                <div><span className="visual-status green" /> <strong>新品用户体验调研</strong><small>收集中 · 1,284 份</small></div>
                <div><span className="visual-status blue" /> <strong>秋季消费偏好研究</strong><small>已归档 · AI 已分析</small></div>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="landing-service-band">
        <div><strong>产品能力</strong><span>把研究流程收拢成可协作的服务</span></div>
        <div><strong>可选协作</strong><span>个人独立管理，需要时再邀请成员访问指定问卷</span></div>
        <div><strong>开放 API</strong><span>按 Token 管理生成与解析用量</span></div>
        <div><strong>运营治理</strong><span>平台管理员统一审核与配置</span></div>
      </section>

      <section className="landing-section">
        <div className="landing-section-heading">
          <div><p className="eyebrow">ONE RESEARCH WORKSPACE</p><h2>从一个问题，到一份可用的研究结论</h2></div>
          <p>面向产品体验、品牌营销、校园调研和个人研究等场景，把复杂流程拆成清晰步骤。</p>
        </div>
        <div className="landing-feature-grid">
          <article><div className="landing-feature-icon"><FileText size={20} /></div><h3>快速导入问卷</h3><p>支持公开问卷链接和结构化文件，保留原始题目与研究字段。</p><button onClick={() => go("/login")}>了解问卷工作区 <ChevronRight size={15} /></button></article>
          <article><div className="landing-feature-icon green"><Sparkles size={20} /></div><h3>AI 互动包装</h3><p>围绕调研目标重新设计题面、主题维度和结果反馈，生成后仍可人工校准。</p><button onClick={() => go("/login")}>了解 AI 服务 <ChevronRight size={15} /></button></article>
          <article><div className="landing-feature-icon orange"><BarChart3 size={20} /></div><h3>数据回收与分析</h3><p>从分享链接、答卷明细到统计图表与研究分析，形成可追溯闭环。</p><button onClick={() => go("/login")}>查看分析能力 <ChevronRight size={15} /></button></article>
          <article><div className="landing-feature-icon purple"><ShieldCheck size={20} /></div><h3>平台级治理</h3><p>账号、成员权限、额度、用量和内容审核分层管理，为开放平台预留运营边界。</p><button onClick={() => go("/platform/login")}>查看平台架构 <ChevronRight size={15} /></button></article>
        </div>
      </section>

      <section className="landing-workflow">
        <div className="landing-section-heading">
          <div><p className="eyebrow">HOW IT WORKS</p><h2>三步，把研究推进到结果</h2></div>
        </div>
        <div className="landing-steps">
          <article><span>01</span><div><h3>创建个人空间</h3><p>注册账号后，所有问卷默认归你管理，同时获得可追踪的 Token 额度。</p></div></article>
          <article><span>02</span><div><h3>生成并发布问卷</h3><p>导入题目，调用 AI 生成互动包装，再发布专属分享链接。</p></div></article>
          <article><span>03</span><div><h3>按需邀请协作者</h3><p>需要共同维护时，邀请已注册成员，并按单份问卷设置仅查看或可编辑权限。</p></div></article>
        </div>
      </section>

      <section className="landing-cta">
        <div><p className="eyebrow">READY TO RESEARCH</p><h2>先建立一个属于你的研究空间。</h2><p>毕设阶段使用申请 Token 的方式，不接入真实支付，也保留未来平台化运营的扩展路径。</p></div>
        <button className="primary" onClick={() => go(authenticated ? "/console" : "/register")}>开始使用 <ArrowRight size={17} /></button>
      </section>
    </div>
  );
}
