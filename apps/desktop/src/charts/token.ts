// 图表配色统一读语义 token 的计算值，亮暗主题（.dark 类）随之生效。
// 主题切换只发生在设置页，返回页面即重挂载并重读 token，故无需监听类翻转；
// 取不到值（如 jsdom 无样式表）时交由 echarts 默认色兜底，不阻塞渲染。
export function cssVar(name: string): string | undefined {
  const value = getComputedStyle(document.documentElement)
    .getPropertyValue(name)
    .trim();
  return value === "" ? undefined : value;
}

export function hexWithAlpha(color: string | undefined, alpha: string) {
  if (!color) return undefined;
  return /^#[0-9a-f]{6}$/i.test(color) ? `${color}${alpha}` : color;
}

export type ChartPalette = {
  foreground?: string;
  primary?: string;
  mutedForeground?: string;
  border?: string;
  card?: string;
  learning?: string;
};

export function chartPalette(): ChartPalette {
  return {
    foreground: cssVar("--ink"),
    primary: cssVar("--ink-strong"),
    mutedForeground: cssVar("--muted-foreground"),
    border: cssVar("--border"),
    card: cssVar("--paper"),
    learning: cssVar("--learning"),
  };
}

// 深色 tooltip（参考稿形态）：ink 底反白，暗色主题下经 token 自动反转。
export function darkTooltipStyle() {
  return {
    backgroundColor: cssVar("--ink-strong"),
    borderWidth: 0,
    textStyle: { color: cssVar("--paper") },
  };
}
