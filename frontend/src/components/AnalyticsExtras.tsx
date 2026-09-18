import { BarChart3, Info, TrendingUp } from "lucide-react";
import type { AnalyticsSummary } from "../types";

export function AnalyticsExtras({ summary }: { summary: AnalyticsSummary }) {
  const trend = summary.trend_stats || [];
  const completion = summary.completion_stats || [];
  const cross = summary.cross_analysis || [];
  const maxTrend = Math.max(...trend.map((item) => item.count), 1);

  return (
    <section className="analytics-extras">
      {summary.sample_warning && <div className="sample-warning"><Info size={17} /><span>{summary.sample_warning}</span></div>}
      <div className="analytics-extra-grid">
        <article className="panel analytics-extra-card">
          <div className="section-heading"><div><h3><TrendingUp size={18} /> 回收趋势</h3><p>按正式有效答卷的提交日期汇总。</p></div></div>
          {!trend.length ? <div className="empty">暂无正式回收数据。</div> : <div className="trend-list">{trend.map((item) => <div className="trend-row" key={item.date}><span>{item.date}</span><div className="trend-track"><i style={{ width: `${(item.count / maxTrend) * 100}%` }} /></div><strong>{item.count} 份 · 累计 {item.cumulative_count}</strong></div>)}</div>}
        </article>
        <article className="panel analytics-extra-card">
          <div className="section-heading"><div><h3><BarChart3 size={18} /> 完成率与跳出提示</h3><p>按题目统计回答覆盖，帮助定位题目流失。</p></div></div>
          {!completion.length ? <div className="empty">暂无题目完成数据。</div> : <div className="completion-list">{completion.slice(0, 8).map((item) => <div className="completion-row" key={item.question_id}><span>{item.question_id}</span><strong>{item.answer_rate}%</strong><small>跳出 {item.dropout_rate}%</small></div>)}</div>}
        </article>
      </div>
      <article className="panel cross-analysis">
        <div className="section-heading"><div><h3><BarChart3 size={18} /> 结果类型交叉分析</h3><p>比较不同结果类型下的选项差异，数字来自本地统计事实。</p></div></div>
        {!cross.length ? <div className="empty">暂无可交叉分析的数据。</div> : <div className="cross-list">{cross.slice(0, 6).map((item) => <div className="cross-item" key={item.question_id}><strong>{item.question_id} · {item.question}</strong>{Object.entries(item.by_result_type).map(([result, options]) => <div className="cross-result" key={result}><span>{result}</span><small>{Object.entries(options).filter(([, count]) => count > 0).map(([option, count]) => `${option} ${count}`).join(" · ") || "暂无回答"}</small></div>)}</div>)}</div>}
      </article>
      {summary.credibility_note && <div className="credibility-note"><Info size={16} /><span>{summary.credibility_note}</span></div>}
    </section>
  );
}
