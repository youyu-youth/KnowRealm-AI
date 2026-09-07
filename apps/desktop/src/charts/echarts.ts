// 图表按需注册中枢：新增图表类型只改这里，页面不直接 import "echarts"。
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { SVGRenderer } from "echarts/renderers";

echarts.use([LineChart, GridComponent, TooltipComponent, SVGRenderer]);

export { echarts };
