import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import { BarChart3 } from "lucide-react";

export function ChartCard({ title, subtitle, option, compact = false }: { title: string; subtitle: string; option: echarts.EChartsOption; compact?: boolean }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    chart.setOption(option);
    const resize = () => chart.resize();
    window.addEventListener("resize", resize);
    return () => {
      window.removeEventListener("resize", resize);
      chart.dispose();
    };
  }, [option]);
  return <div className={`chart-card ${compact ? "compact" : ""}`}><div className="chart-card-title"><div><h3>{title}</h3><p>{subtitle}</p></div><BarChart3 size={18} /></div><div className="chart-canvas" ref={ref} /></div>;
}
