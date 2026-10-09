import { useEffect, useRef } from "react";

import { echarts } from "@/charts/echarts";

type BaseChartProps = {
  option: echarts.EChartsCoreOption;
  /** 纯图形内容的可访问名称（图表本身不承载文字信息）。 */
  ariaLabel: string;
  className?: string;
  /** 图表元素点击回调（如关系图节点选中）；不传不监听。 */
  onItemSelect?: (params: echarts.ECElementEvent) => void;
};

export function BaseChart({
  option,
  ariaLabel,
  className,
  onItemSelect,
}: BaseChartProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const chartRef = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const element = containerRef.current;
    if (!element) return;
    const chart = echarts.init(element, undefined, { renderer: "svg" });
    chartRef.current = chart;
    const onResize = () => chart.resize();
    const observer = new ResizeObserver(onResize);
    observer.observe(element);
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      observer.disconnect();
      chart.dispose();
      chartRef.current = null;
    };
  }, []);

  useEffect(() => {
    // notMerge：数据集切换（如 7↔30 天）时丢弃旧序列，避免残留。
    chartRef.current?.setOption(option, { notMerge: true });
  }, [option]);

  useEffect(() => {
    const chart = chartRef.current;
    if (!chart || !onItemSelect) return;
    chart.on("click", onItemSelect);
    return () => {
      chart.off("click", onItemSelect);
    };
  }, [onItemSelect]);

  return (
    <div
      ref={containerRef}
      role="img"
      aria-label={ariaLabel}
      className={className}
    />
  );
}
