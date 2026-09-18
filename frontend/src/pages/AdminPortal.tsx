import type { ReactNode } from "react";

export function AdminPortalLayout({ children, role }: { children: ReactNode; role: string }) {
  return <>
    <section className="admin-head">
      <div><p className="eyebrow">ADMINISTRATION</p><h1>研究数据工作台</h1><p>管理互动问卷，追踪研究字段，导出可提交的调研报告。</p></div>
      <div className="admin-status"><span className="status-dot" /> 本地数据库已连接 · {role === "viewer" ? "只读查看者" : "管理员"}</div>
    </section>
    <div className="admin-shell">{children}</div>
  </>;
}
