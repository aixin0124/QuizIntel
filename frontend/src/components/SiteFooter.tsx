import { Mail } from "lucide-react";

export function SiteFooter() {
  function go(path: string) {
    window.location.assign(path);
  }

  return (
    <footer className="site-footer">
      <div className="site-footer-inner">
        <div className="site-footer-brand">
          <strong>© 2026 趣测智研 FUN RESEARCH</strong>
          <span>把问卷变成真正能被研究的数据</span>
        </div>
        <nav className="site-footer-nav" aria-label="页脚导航">
          <button onClick={() => go("/docs")}>文档</button>
          <button onClick={() => go("/changelog")}>更新日志</button>
          <button onClick={() => go("/privacy")}>隐私政策</button>
          <button onClick={() => go("/contact")}><Mail size={14} /> 联系我们</button>
        </nav>
      </div>
    </footer>
  );
}
