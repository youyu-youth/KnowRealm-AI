// 图表按需注册中枢：新增图表类型只改这里，页面不直接 import "echarts"。
import * as echarts from "echarts/core";
import {
  GraphChart,
  LineChart,
  PieChart,
  RadarChart,
  SankeyChart,
  TreeChart,
} from "echarts/charts";
import {
  GridComponent,
  RadarComponent,
  TooltipComponent,
} from "echarts/components";
import { SVGRenderer } from "echarts/renderers";

echarts.use([
  GraphChart,
  LineChart,
  PieChart,
  RadarChart,
  SankeyChart,
  TreeChart,
  GridComponent,
  RadarComponent,
  TooltipComponent,
  SVGRenderer,
]);

export { echarts };
