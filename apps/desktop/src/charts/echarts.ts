// 图表按需注册中枢：新增图表类型只改这里，页面不直接 import "echarts"。
import * as echarts from "echarts/core";
import {
  GraphChart,
  BarChart,
  LineChart,
  PieChart,
  RadarChart,
  SankeyChart,
  HeatmapChart,
} from "echarts/charts";
import {
  GridComponent,
  RadarComponent,
  TooltipComponent,
  CalendarComponent,
  VisualMapPiecewiseComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";

echarts.use([
  GraphChart,
  BarChart,
  LineChart,
  PieChart,
  RadarChart,
  SankeyChart,
  HeatmapChart,
  GridComponent,
  RadarComponent,
  TooltipComponent,
  CalendarComponent,
  VisualMapPiecewiseComponent,
  SVGRenderer,
]);

export { echarts };
