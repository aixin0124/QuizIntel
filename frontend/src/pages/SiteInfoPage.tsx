import { ArrowLeft, ArrowRight, BookOpen, Clock3, ExternalLink, FileText, Github, Mail, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { fetchJson } from "../api/client";
import { SiteFooter } from "../components/SiteFooter";

type SiteInfoKind = "docs" | "changelog" | "privacy" | "contact";

type SiteInfoPageProps = {
  kind: SiteInfoKind;
};

const changelogItems = [
  { hash: "b897dc2", date: "2026-09-29", title: "移除协作成员功能", detail: "下线前端协作成员菜单、团队面板、成员邀请、问卷授权及对应的后端权限接口，平台边界回到个人研究工作区。" },
  { hash: "b95d34e", date: "2026-09-29", title: "移除 SQLite 相关说明", detail: "清理项目文档中已经不再适用的 SQLite 说明，保持当前数据库和部署文档与实际实现一致。" },
  { hash: "8a88e12", date: "2026-09-29", title: "完成样式调整", detail: "统一公开首页、登录页和工作区的视觉语言，补充首页交互、演示区域和响应式布局。" },
  { hash: "fa41e4f", date: "2026-09-20", title: "V3.0 开放平台化改造完成", detail: "加入个人账号体系、API Token、平台管理员、额度申请、内容治理和研究工作区隔离。" },
  { hash: "154fbf4", date: "2026-09-20", title: "新增人格解析图片导出", detail: "结果页面支持将人格解析内容导出为图片，方便保存和提交研究材料。" },
  { hash: "ead917e", date: "2026-09-18", title: "V2.0 研究工作流升级", detail: "新增管理员账号体系、问卷发布与采集控制、问卷生命周期、数据分析、AI 生成质量控制和后台安全能力。" },
];
type ChangelogItem = (typeof changelogItems)[number] & { url?: string | null; author?: string };

export function SiteInfoPage({ kind }: SiteInfoPageProps) {
  const content = {
    docs: {
      eyebrow: "DOCUMENTATION",
      title: "趣测智研使用说明书",
      description: "从创建账号到导出研究结果，按项目当前提供的能力了解每一步如何使用。",
      icon: BookOpen,
    },
    changelog: {
      eyebrow: "CHANGELOG",
      title: "项目更新日志",
      description: "这里展示当前 Git 仓库中已经发生的主要版本和功能变更。",
      icon: Clock3,
    },
    privacy: {
      eyebrow: "PRIVACY POLICY",
      title: "趣测智研隐私政策",
      description: "说明平台如何处理账号、问卷、答卷和 API 使用相关信息。",
      icon: ShieldCheck,
    },
    contact: {
      eyebrow: "CONTACT",
      title: "联系我们",
      description: "如果你在使用问卷工作区、AI 包装、数据分析或平台服务时遇到问题，可以通过邮箱联系。",
      icon: Mail,
    },
  }[kind];
  const Icon = content.icon;

  return (
    <div className="site-info-page">
      <section className="site-info-hero">
        <button className="site-info-back" onClick={() => window.location.assign("/")}><ArrowLeft size={15} /> 返回首页</button>
        <div className="site-info-heading"><div className="site-info-icon"><Icon size={24} /></div><div><p className="eyebrow">{content.eyebrow}</p><h1>{content.title}</h1><p>{content.description}</p></div></div>
      </section>
      <div className="site-info-content">
        {kind === "docs" && <DocsContent />}
        {kind === "changelog" && <ChangelogContent />}
        {kind === "privacy" && <PrivacyContent />}
        {kind === "contact" && <ContactContent />}
      </div>
      <SiteFooter />
    </div>
  );
}

function DocsContent() {
  return <div className="info-docs">
    <article className="info-intro-band"><strong>一句话理解</strong><p>趣测智研把“原始问卷导入、AI 互动包装、分享回收、统计分析和报表导出”放进同一份个人研究工作区，AI 生成内容可以继续人工修改，数据分析以真实答卷统计为依据。</p></article>
    <div className="info-doc-grid">
      <DocBlock number="01" title="创建个人空间" detail="注册账号后，系统会创建个人问卷空间。新建问卷默认由创建账号管理，账号之间的数据相互隔离。登录后可以进入控制台、用户端和 API 服务页面。" />
      <DocBlock number="02" title="导入原始问卷" detail="在控制台中选择公开问卷链接或结构化题目内容，系统会尽量保留原始题目、选项和研究字段。导入完成后，可以在互动问卷编辑器中继续检查和修改。" />
      <DocBlock number="03" title="生成 AI 互动包装" detail="填写调研目标后，系统会围绕研究内容提炼主题、设计互动题面、配置结果类型和分析维度。生成结果会先保存为草稿，研究者确认后才能发布。" />
      <DocBlock number="04" title="发布并回收答卷" detail="发布后生成专属分享链接和二维码。答卷者打开链接即可填写，不需要进入管理员控制台。管理员可以在数据总览中查看有效答卷数量和回收状态。" />
      <DocBlock number="05" title="结束问卷并分析" detail="问卷处于收集状态时不会开放正式数据分析。结束问卷后样本数量锁定，再点击开始数据分析，系统会根据选项原值生成统计、维度拆分、关键发现和研究结论。" />
      <DocBlock number="06" title="查看与导出结果" detail="分析页面提供题目映射、选项人数和比例、维度指数、分析边界及 AI 解释。数据可以导出为 Excel 明细和 PDF 报表，结果页也支持导出人格解析图片。" />
    </div>
    <section className="info-section"><h2>Token 和 API 服务</h2><p>生成互动包装、解析问卷题目和数据分析会根据内容量消耗 Token。API 服务页会展示余额、累计用量、今日调用、调用历史和额度申请记录。当前项目不接入真实支付，额度不足时可以向平台管理员提交申请，导出和查看本身不扣 Token。</p></section>
    <section className="info-section"><h2>平台管理员</h2><p>平台管理员使用独立的“平台管理”入口登录，负责账号、Token 额度申请、平台用量、内容审核和平台配置。普通研究者的问卷内容仍然在个人工作区中管理。</p></section>
  </div>;
}

function DocBlock({ number, title, detail }: { number: string; title: string; detail: string }) {
  return <article className="info-doc-block"><span>{number}</span><div><h2>{title}</h2><p>{detail}</p></div></article>;
}

function ChangelogContent() {
  const [items, setItems] = useState<ChangelogItem[]>(changelogItems);
  const [repository, setRepository] = useState("aixin0124/QuizIntel");
  const [live, setLive] = useState(false);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let cancelled = false;
    void fetchJson<{ repository: string; items: ChangelogItem[] }>("/api/changelog")
      .then((data) => {
        if (cancelled || !data.items.length) return;
        setItems(data.items);
        setRepository(data.repository);
        setLive(true);
      })
      .catch(() => undefined)
      .finally(() => { if (!cancelled) setLoading(false); });
    return () => { cancelled = true; };
  }, []);
  return <div className="changelog-list">
    <div className="changelog-note"><FileText size={17} /><span>{loading ? "正在读取 GitHub 更新日志..." : live ? <>以下内容实时同步自 <a className="changelog-repository-link" href={`https://github.com/${repository}`} target="_blank" rel="noreferrer"><Github size={14} />{repository}<ExternalLink size={12} /></a>。</> : "GitHub 暂时不可用，当前显示本地保留的项目更新记录。"}</span></div>
    {items.map((item) => <article className="changelog-item" key={item.hash}><div className="changelog-date">{item.date}<code>{item.hash}</code></div><div><h2>{item.title}</h2><p>{item.detail || "该提交未附加详细说明。"}</p>{"url" in item && item.url && <a className="changelog-commit-link" href={item.url} target="_blank" rel="noreferrer">在 GitHub 查看 <ExternalLink size={13} /></a>}</div></article>)}
  </div>;
}

function PrivacyContent() {
  return <div className="policy-content">
    <p className="policy-updated">生效日期：2026 年 9 月 29 日</p>
    <PolicySection title="一、我们处理哪些信息" text="当你注册或登录时，平台会处理账号名、密码的加密凭据、可选联系邮箱和登录状态。使用问卷工作区时，平台会处理你主动导入或创建的问卷题目、研究目标、互动题面、答卷内容、分析结果和导出记录。使用 API 服务时，平台会记录 Token 余额、调用类型、调用时间、调用状态和估算用量。" />
    <PolicySection title="二、这些信息用于什么" text="上述信息仅用于提供账号登录、问卷创建与管理、AI 互动包装、答卷回收、统计分析、结果导出、Token 用量展示和平台治理。问卷与答卷数据不会因为公开分享链接而自动公开到其他问卷或其他账号。" />
    <PolicySection title="三、AI 服务和数据边界" text="当你使用 AI 生成、解析或分析功能时，相关研究内容会被发送给项目配置的模型服务以完成当前请求。平台会保留生成结果和调用记录，以便你在工作区中继续编辑、复核和查看用量。请不要在问卷中提交与研究无关的身份证件、支付密码或其他高敏感信息。" />
    <PolicySection title="四、数据保存与导出" text="账号、问卷和答卷会按照当前项目的数据库和问卷生命周期进行保存。你可以在工作区查看、结束、归档和导出已有数据。删除或归档等操作可能影响后续编辑和分析，请在操作前确认。" />
    <PolicySection title="五、第三方服务" text="项目可能使用模型服务、二维码生成服务或浏览器端导出能力完成对应功能。第三方服务只接收完成当前功能所需的数据，具体处理还应以相应服务的隐私规则为准。" />
    <PolicySection title="六、联系我们" text="如果你希望了解账号数据、问卷数据或隐私政策相关问题，请发送邮件至 19501724018@163.com。我们会根据问题核对必要的信息，不会要求你在邮件中发送密码或完整 Token。" />
  </div>;
}

function PolicySection({ title, text }: { title: string; text: string }) {
  return <section className="policy-section"><h2>{title}</h2><p>{text}</p></section>;
}

function ContactContent() {
  return <div className="contact-content">
    <div className="contact-card"><div className="contact-card-icon"><Mail size={22} /></div><p className="eyebrow">EMAIL SUPPORT</p><h2>19501724018@163.com</h2><p>欢迎反馈页面使用问题、问卷导入问题、AI 包装结果、答卷分析、Token 申请和平台管理相关事项。</p><a href="mailto:19501724018@163.com">发送邮件 <ArrowRight size={15} /></a></div>
    <div className="contact-topics"><h2>建议在邮件中说明</h2><p>为了更快定位问题，可以写明你所在的页面、操作步骤、出现的提示，以及是否涉及某一份问卷。请不要发送密码、完整 Token 或受访者的敏感个人信息。</p><div><span>页面或功能名称</span><span>复现步骤</span><span>问题截图</span></div></div>
  </div>;
}
