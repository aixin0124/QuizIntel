import type { ReactNode } from "react";
import { useEffect, useState } from "react";
import { adminFetchJson } from "../api/client";
import { roleLabel } from "../permissions";

export function AdminPortalLayout({ children, role, token }: { children: ReactNode; role: string; token: string }) {
  useEffect(() => {
    void adminFetchJson("/api/auth/me", token).catch(() => undefined);
  }, [token]);
  return <>
    <section className="admin-head">
      <div><p className="eyebrow">ADMINISTRATION</p><h1>研究数据工作台</h1><p>管理互动问卷，追踪研究字段，导出可提交的调研报告。</p></div>
      <div className="admin-head-status"><div className="admin-status"><span className="status-dot" /> 个人工作区 · {roleLabel(role)}</div></div>
    </section>
    <div className="admin-shell">{children}</div>
  </>;
}
