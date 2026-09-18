// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

type CourseDetail = components["schemas"]["CourseDetailOut"];
type BrainSnapshotOut = components["schemas"]["BrainSnapshotOut"];
type BrainConceptOut = components["schemas"]["BrainConceptOut"];
type CourseMasteryOut = components["schemas"]["CourseMasteryOut"];
type ConceptMasteryOut = components["schemas"]["ConceptMasteryOut"];

const COURSE_ID = "33333333-3333-4333-8333-333333333331";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}`;
const BRAIN_URL = `${DETAIL_URL}/brain`;
const CONCEPTS_URL = `${BRAIN_URL}/concepts`;
const MASTERY_URL = `${DETAIL_URL}/mastery`;
const ROUTE_PATH = `/spaces/${COURSE_ID}?tab=map`;

const schoolCourse: CourseDetail = {
  id: COURSE_ID,
  name: "操作系统",
  learning_context: "SCHOOL",
  education_stage: "UNDERGRADUATE",
  depth: null,
  course_type: "MAJOR",
  description: "理解进程、内存与文件系统。",
  status: "ACTIVE",
  hot_words: [],
  created_at: "2026-08-17T00:00:00.000000Z",
  updated_at: "2026-08-18T00:00:00.000000Z",
};

const confirmedConcepts: BrainConceptOut[] = [
  {
    id: "c1",
    canonical_name: "进程调度",
    concept_type: "TERM",
    course_id: COURSE_ID,
    created_at: "2026-09-01T00:00:00.000000Z",
    updated_at: "2026-09-01T00:00:00.000000Z",
    description: "CPU 在多个进程间分配的策略。",
    importance: 5,
    occurrence_count: 6,
    record_count: 3,
    source: "AI_EXTRACTED",
    stale_archivable: false,
    status: "CONFIRMED",
    suggested_target_id: null,
    suggested_target_name: null,
  },
  {
    id: "c2",
    canonical_name: "虚拟内存",
    concept_type: "PRINCIPLE",
    course_id: COURSE_ID,
    created_at: "2026-09-01T00:00:00.000000Z",
    updated_at: "2026-09-01T00:00:00.000000Z",
    description: "",
    importance: 3,
    occurrence_count: 2,
    record_count: 1,
    source: "USER_CONFIRMED",
    stale_archivable: false,
    status: "CONFIRMED",
    suggested_target_id: null,
    suggested_target_name: null,
  },
];

function snapshotOf(status: BrainSnapshotOut["status"]): BrainSnapshotOut {
  return {
    course_id: COURSE_ID,
    status,
    concept_count: 2,
    candidate_count: 0,
    stale: false,
    active_job_id: null,
    last_built_at: "2026-09-15T08:00:00.000000Z",
    graph: {
      nodes: [
        {
          id: "c1",
          canonical_name: "进程调度",
          concept_type: "TERM",
          importance: 5,
          occurrence_count: 6,
          record_count: 3,
        },
        {
          id: "c2",
          canonical_name: "虚拟内存",
          concept_type: "PRINCIPLE",
          importance: 3,
          occurrence_count: 2,
          record_count: 1,
        },
      ],
      edges: [],
    },
  };
}

function conceptMastery(
  overrides: Partial<ConceptMasteryOut> & { concept_id: string },
): ConceptMasteryOut {
  return {
    canonical_name: "概念",
    description: "",
    concept_type: "TERM",
    importance: 3,
    status: "NOT_ENOUGH_DATA",
    mastery_score: null,
    confidence: null,
    evidence_count: 0,
    positive_evidence_count: 0,
    negative_evidence_count: 0,
    last_practiced_at: null,
    last_verified_at: null,
    ...overrides,
  };
}

const courseMastery: CourseMasteryOut = {
  course_id: COURSE_ID,
  confirmed_concept_count: 2,
  verified_concept_count: 1,
  coverage: 0.5,
  status_counts: { not_enough_data: 1, weak: 0, learning: 0, stable: 1 },
  concepts: [
    conceptMastery({
      concept_id: "c1",
      canonical_name: "进程调度",
      status: "STABLE",
      mastery_score: 0.92,
      confidence: "HIGH",
      evidence_count: 8,
      positive_evidence_count: 7,
      negative_evidence_count: 1,
      last_practiced_at: "2026-09-10T10:00:00.000000Z",
      last_verified_at: "2026-09-10T10:00:00.000000Z",
    }),
    conceptMastery({ concept_id: "c2", canonical_name: "虚拟内存" }),
  ],
};

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

// 捕获传入图谱的 option：tooltip/标签是 canvas 内容，经 formatter 合同断言。
let graphOption: Record<string, unknown> | null = null;
vi.mock("@/charts/BaseChart", () => ({
  BaseChart: ({
    ariaLabel,
    option,
  }: {
    ariaLabel: string;
    option: Record<string, unknown>;
  }) => {
    graphOption = option;
    return <div role="img" aria-label={ariaLabel} />;
  },
}));

vi.stubGlobal("scrollTo", vi.fn());

beforeEach(() => {
  graphOption = null;
  server.use(
    http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
    http.get(`${DETAIL_URL}/records`, () => HttpResponse.json([])),
    http.get(BRAIN_URL, () => HttpResponse.json(snapshotOf("READY"))),
    http.get(CONCEPTS_URL, () => HttpResponse.json(confirmedConcepts)),
    http.get(MASTERY_URL, () => HttpResponse.json(courseMastery)),
  );
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

function renderAt(path: string) {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

function tooltipTextFor(conceptId: string): string {
  const option = graphOption as {
    tooltip: {
      formatter: (params: { data: Record<string, unknown> }) => string;
    };
    series: {
      data: { id: string; masteryStatus?: string }[];
    }[];
  } | null;
  expect(option).not.toBeNull();
  const node = option!.series[0].data.find((item) => item.id === conceptId);
  expect(node).toBeDefined();
  return option!.tooltip.formatter({ data: node as Record<string, unknown> });
}

describe("Course Brain 非侵入式 Mastery 标记", () => {
  it("列表视图正式概念行显示掌握状态徽章，候选行不显示", async () => {
    server.use(
      http.get(CONCEPTS_URL, ({ request }) =>
        new URL(request.url).searchParams.get("status") === "CANDIDATE"
          ? HttpResponse.json([])
          : HttpResponse.json(confirmedConcepts),
      ),
    );
    renderAt(ROUTE_PATH);
    fireEvent.click(await screen.findByRole("button", { name: "列表" }));

    // mastery 与 concepts 两查询并发返回：先等徽章到齐，再做行结构断言。
    expect(await screen.findByText("稳定")).toBeInTheDocument();
    expect(screen.getByText("数据不足")).toBeInTheDocument();
    const confirmedRow = screen.getByText("进程调度").closest("button");
    expect(confirmedRow).toHaveTextContent("稳定");
    const noDataRow = screen.getByText("虚拟内存").closest("button");
    expect(noDataRow).toHaveTextContent("数据不足");

    fireEvent.click(screen.getByRole("button", { name: "待审核候选" }));
    expect(await screen.findByText("暂无概念")).toBeInTheDocument();
  });

  it("图谱节点 tooltip 与标签携带同一掌握状态", async () => {
    renderAt(ROUTE_PATH);
    await screen.findByRole("img", { name: "「操作系统」概念关系图谱" });

    const option = graphOption as {
      series: {
        data: { id: string; masteryStatus?: string }[];
        label: {
          formatter: (params: { data: unknown }) => string;
        };
      }[];
    } | null;
    expect(option).not.toBeNull();
    const statuses = Object.fromEntries(
      option!.series[0].data.map((node) => [node.id, node.masteryStatus]),
    );
    expect(statuses).toEqual({ c1: "STABLE", c2: "NOT_ENOUGH_DATA" });

    expect(tooltipTextFor("c1")).toContain("掌握状态：稳定");
    expect(tooltipTextFor("c2")).toContain("掌握状态：数据不足");

    const node = option!.series[0].data.find((item) => item.id === "c1")!;
    const label = option!.series[0].label.formatter({ data: node });
    expect(label).toContain("dot_STABLE");
    expect(label).toContain("进程调度");
  });

  it("概念详情面板提供掌握状态与详情入口，复用既有掌握详情弹窗", async () => {
    renderAt(ROUTE_PATH);
    fireEvent.click(await screen.findByRole("button", { name: "列表" }));
    fireEvent.click(await screen.findByRole("button", { name: /进程调度/ }));

    const detail = await screen.findByRole("heading", { name: "进程调度" });
    expect(detail).toBeInTheDocument();
    // 详情入口是详情面板独有的掌握状态证明（列表行徽章已在用例 1 覆盖）。
    fireEvent.click(screen.getByRole("button", { name: "掌握详情" }));

    expect(
      await screen.findByText("只展示参与当前算法版本的有效作答证据"),
    ).toBeInTheDocument();
  });

  it("掌握度查询失败时诚实降级：页面可用且不显示任何掌握标记", async () => {
    server.use(
      http.get(MASTERY_URL, () => HttpResponse.json({}, { status: 500 })),
    );
    renderAt(ROUTE_PATH);
    fireEvent.click(await screen.findByRole("button", { name: "列表" }));

    expect(await screen.findByText("虚拟内存")).toBeInTheDocument();
    expect(screen.queryByText("稳定")).not.toBeInTheDocument();
    expect(screen.queryByText("数据不足")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /进程调度/ }));
    expect(
      await screen.findByRole("heading", { name: "进程调度" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "掌握详情" }),
    ).not.toBeInTheDocument();
  });

  it("零已确认概念时图谱与列表正常渲染且无掌握标记", async () => {
    server.use(
      http.get(CONCEPTS_URL, () => HttpResponse.json([])),
      http.get(MASTERY_URL, () =>
        HttpResponse.json({
          course_id: COURSE_ID,
          confirmed_concept_count: 0,
          verified_concept_count: 0,
          coverage: 0,
          status_counts: {
            not_enough_data: 0,
            weak: 0,
            learning: 0,
            stable: 0,
          },
          concepts: [],
        }),
      ),
    );
    renderAt(ROUTE_PATH);
    fireEvent.click(await screen.findByRole("button", { name: "列表" }));

    expect(await screen.findByText("暂无概念")).toBeInTheDocument();
    expect(screen.queryByText("稳定")).not.toBeInTheDocument();
  });
});
