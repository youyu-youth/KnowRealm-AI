// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

type CourseDetail = components["schemas"]["CourseDetailOut"];
type BrainSnapshotOut = components["schemas"]["BrainSnapshotOut"];
type BrainConceptOut = components["schemas"]["BrainConceptOut"];
type BrainRelationOut = components["schemas"]["BrainRelationOut"];

const COURSE_ID = "33333333-3333-4333-8333-333333333333";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}`;
const BRAIN_URL = `${DETAIL_URL}/brain`;
const CONCEPTS_URL = `${BRAIN_URL}/concepts`;
const RELATIONS_URL = `${BRAIN_URL}/relations`;
const SOURCES_URL = `${BRAIN_URL}/concepts/c9/sources`;
const APPLY_REVIEW_URL = `${BRAIN_URL}/apply-review`;
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
];

const candidateConcepts: BrainConceptOut[] = [
  {
    id: "c9",
    canonical_name: "进程调读",
    concept_type: "TERM",
    course_id: COURSE_ID,
    created_at: "2026-09-15T00:00:00.000000Z",
    updated_at: "2026-09-15T00:00:00.000000Z",
    description: "候选：CPU 在多个进程间分配的策略。",
    importance: 4,
    occurrence_count: 2,
    record_count: 1,
    source: "AI_EXTRACTED",
    stale_archivable: false,
    status: "CANDIDATE",
    suggested_target_id: "c1",
    suggested_target_name: "进程调度",
  },
  {
    id: "c10",
    canonical_name: "死锁",
    concept_type: "TERM",
    course_id: COURSE_ID,
    created_at: "2026-09-15T00:00:00.000000Z",
    updated_at: "2026-09-15T00:00:00.000000Z",
    description: "一组进程互相等待对方持有的资源。",
    importance: 3,
    occurrence_count: 1,
    record_count: 1,
    source: "AI_EXTRACTED",
    stale_archivable: false,
    status: "CANDIDATE",
    suggested_target_id: null,
    suggested_target_name: null,
  },
];

const candidateRelations: BrainRelationOut[] = [
  {
    id: "r1",
    course_id: COURSE_ID,
    source_concept_id: "c1",
    source_name: "进程调度",
    target_concept_id: "c10",
    target_name: "死锁",
    relation_type: "PREREQUISITE",
    confidence: 0.86,
    evidence_count: 0,
    status: "CANDIDATE",
    stale: false,
    created_at: "2026-09-15T00:00:00.000000Z",
    updated_at: "2026-09-15T00:00:00.000000Z",
  },
];

const staleRelations: BrainRelationOut[] = [
  {
    ...candidateRelations[0],
    id: "r2",
    status: "CONFIRMED",
    stale: true,
  },
];

let snapshot: BrainSnapshotOut;
let capturedDecisions: unknown[];

function snapshotOf(
  status: BrainSnapshotOut["status"],
  overrides: Partial<BrainSnapshotOut> = {},
): BrainSnapshotOut {
  return {
    course_id: COURSE_ID,
    status,
    concept_count: 1,
    candidate_count: status === "REVIEW" ? 2 : 0,
    stale: false,
    active_job_id: null,
    last_built_at: "2026-09-15T08:00:00.000000Z",
    graph:
      status === "EMPTY"
        ? { nodes: [], edges: [] }
        : {
            nodes: [
              {
                id: "c1",
                canonical_name: "进程调度",
                concept_type: "TERM",
                importance: 5,
                occurrence_count: 6,
                record_count: 3,
              },
            ],
            edges: [],
          },
    ...overrides,
  };
}

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.mock("@/charts/BaseChart", () => ({
  BaseChart: ({ ariaLabel }: { ariaLabel: string }) => (
    <div role="img" aria-label={ariaLabel} />
  ),
}));

vi.stubGlobal("scrollTo", vi.fn());

function useConceptHandlers() {
  server.use(
    http.get(CONCEPTS_URL, ({ request }) => {
      const status = new URL(request.url).searchParams.get("status");
      return HttpResponse.json(
        status === "CANDIDATE" ? candidateConcepts : confirmedConcepts,
      );
    }),
    http.get(SOURCES_URL, () =>
      HttpResponse.json({
        concept_id: "c9",
        anchors: [
          {
            anchor_id: "a1",
            source_type: "AUDIO_SEGMENT",
            record_id: "record-1",
            record_title: "第 1 讲 进程",
            start_ms: 65_000,
            end_ms: 71_000,
            quote: "进程调度是操作系统的核心机制",
            relation_type: "MENTIONS",
            chat_session_id: null,
            page_no: null,
          },
        ],
        knowledge_points: [],
      }),
    ),
  );
}

async function openReviewDrawer() {
  fireEvent.click(await screen.findByRole("button", { name: "审核候选 (2)" }));
  await screen.findByRole("heading", { name: "概念审核" });
  // 候选名可能同时出现在页面 Relation 审核区，用抽屉独有的批量工具栏文本等待列表就绪。
  await screen.findByText("已选 0 项");
}

/** 候选行容器：以勾选框 aria-label 定位（候选名在页面 Relation 审核区可能重名）。 */
function candidateRow(name: string): HTMLElement {
  const checkbox = screen.getByRole("checkbox", { name: `选择候选 ${name}` });
  const row = checkbox.closest("li");
  if (!(row instanceof HTMLElement)) throw new Error(`候选行未找到：${name}`);
  return row;
}

beforeEach(() => {
  snapshot = snapshotOf("REVIEW");
  capturedDecisions = [];
  server.use(
    http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
    http.get(`${DETAIL_URL}/records`, () => HttpResponse.json([])),
    http.get(BRAIN_URL, () => HttpResponse.json(snapshot)),
    http.get(RELATIONS_URL, ({ request }) => {
      const status = new URL(request.url).searchParams.get("status");
      return HttpResponse.json(
        status === "CONFIRMED" ? staleRelations : candidateRelations,
      );
    }),
    http.post(APPLY_REVIEW_URL, async ({ request }) => {
      const body = (await request.json()) as { decisions: unknown[] };
      capturedDecisions.push(...body.decisions);
      snapshot = snapshotOf("READY");
      return HttpResponse.json(snapshot);
    }),
  );
  useConceptHandlers();
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

function renderAt(path: string) {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

describe("Course Brain 审核工作台", () => {
  it("候选审核全链路：打开抽屉单条确认，apply-review 携带 confirm 决策，快照联动到 READY", async () => {
    renderAt(ROUTE_PATH);

    await screen.findByRole("button", { name: "审核候选 (2)" });
    await openReviewDrawer();

    // 单条确认（行内按钮；与批量「确认所选」区分）。
    fireEvent.click(
      within(candidateRow("进程调读")).getByRole("button", {
        name: "确认",
      }),
    );

    await waitFor(() =>
      expect(capturedDecisions).toEqual([
        { decision_type: "confirm", concept_id: "c9" },
      ]),
    );
    // 审核成功 → 快照失效重拉 → READY 状态标签与 Toast 反馈。
    expect(await screen.findByText("已就绪")).toBeInTheDocument();
    expect(await screen.findByText("已处理 1 项审核决策")).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: "审核候选 (2)" }),
    ).not.toBeInTheDocument();
  });

  it("重命名后确认：决策携带 new_name", async () => {
    renderAt(ROUTE_PATH);
    await openReviewDrawer();

    fireEvent.click(
      await screen.findByRole("button", { name: "死锁 的更多操作" }),
    );
    fireEvent.click(
      await screen.findByRole("menuitem", { name: "重命名后确认" }),
    );
    const input = await screen.findByLabelText("新名称");
    fireEvent.change(input, { target: { value: "进程间通信" } });
    fireEvent.click(screen.getByRole("button", { name: "重命名并确认" }));

    await waitFor(() =>
      expect(capturedDecisions).toEqual([
        {
          decision_type: "confirm",
          concept_id: "c10",
          new_name: "进程间通信",
        },
      ]),
    );
  });

  it("合并到已有概念：默认预填合并建议目标", async () => {
    renderAt(ROUTE_PATH);
    await openReviewDrawer();

    fireEvent.click(
      await screen.findByRole("button", { name: "进程调读 的更多操作" }),
    );
    fireEvent.click(
      await screen.findByRole("menuitem", { name: "合并到已有概念" }),
    );
    // 展开区展示来源预览与合并建议。
    expect(await screen.findByText("疑似重复")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "合并" }));

    await waitFor(() =>
      expect(capturedDecisions).toEqual([
        {
          decision_type: "merge",
          concept_id: "c9",
          target_concept_id: "c1",
        },
      ]),
    );
  });

  it("批量勾选后一次提交多条决策", async () => {
    renderAt(ROUTE_PATH);
    await openReviewDrawer();

    fireEvent.click(
      await screen.findByRole("checkbox", { name: "选择候选 死锁" }),
    );
    fireEvent.click(
      screen.getByRole("checkbox", { name: "选择候选 进程调读" }),
    );
    fireEvent.click(screen.getByRole("button", { name: "确认所选 (2)" }));

    await waitFor(() =>
      expect(capturedDecisions).toEqual([
        { decision_type: "confirm", concept_id: "c10" },
        { decision_type: "confirm", concept_id: "c9" },
      ]),
    );
  });

  it("候选关系逐条确认；已确认视图展示过期徽章", async () => {
    renderAt(ROUTE_PATH);

    expect(await screen.findByText("进程调度")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认关系" }));

    await waitFor(() =>
      expect(capturedDecisions).toEqual([
        { decision_type: "confirm_relation", relation_id: "r1" },
      ]),
    );

    fireEvent.click(screen.getByRole("button", { name: "已确认" }));
    expect(await screen.findByText("证据已失效")).toBeInTheDocument();
    expect(screen.getByText("置信度 0.86")).toBeInTheDocument();
  });

  it("手动创建概念：表单提交 POST /concepts；409 撞名内联错误反馈", async () => {
    let createCalls = 0;
    server.use(
      http.post(CONCEPTS_URL, async () => {
        createCalls += 1;
        if (createCalls === 1) {
          return HttpResponse.json(
            {
              detail: "已存在同名概念",
              code: "COURSE_BRAIN_CONCEPT_EXISTS",
            },
            { status: 409 },
          );
        }
        return HttpResponse.json(confirmedConcepts[0]);
      }),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "手动创建" }));
    await screen.findByRole("heading", { name: "手动创建概念" });
    fireEvent.change(screen.getByLabelText("概念名称"), {
      target: { value: "虚拟内存" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建" }));

    // 第一次撞名 409：内联 Alert 展示翻译后的错误码文案。
    expect(await screen.findByText("已存在同名概念")).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText("概念名称"), {
      target: { value: "页表" },
    });
    fireEvent.click(screen.getByRole("button", { name: "创建" }));

    await waitFor(() => expect(createCalls).toBe(2));
    expect(
      await screen.findByText("已创建概念「进程调度」"),
    ).toBeInTheDocument();
  });

  it("概念归档：详情面板二次确认后 POST archive 并关闭面板", async () => {
    snapshot = snapshotOf("READY");
    let archived = false;
    server.use(
      http.post(`${BRAIN_URL}/concepts/c1/archive`, () => {
        archived = true;
        return HttpResponse.json({
          ...confirmedConcepts[0],
          status: "ARCHIVED",
        });
      }),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "列表" }));
    // 列表行是按钮（可访问名含统计后缀）；页面 Relation 区的重名 span 不可点。
    fireEvent.click(await screen.findByRole("button", { name: /进程调度/ }));
    fireEvent.click(await screen.findByRole("button", { name: "归档概念" }));
    expect(
      await screen.findByText(/将退出正式图谱与检索增强/),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "确认归档" }));

    await waitFor(() => expect(archived).toBe(true));
    expect(await screen.findByText("已归档「进程调度」")).toBeInTheDocument();
    // 归档成功后详情面板关闭（回到占位文案）。
    expect(
      await screen.findByText("选择概念查看详情与来源"),
    ).toBeInTheDocument();
  });

  it("apply-review 失败时内联展示错误且快照不变", async () => {
    server.use(
      http.post(APPLY_REVIEW_URL, () =>
        HttpResponse.json(
          {
            detail: "概念当前状态不允许该操作",
            code: "COURSE_BRAIN_CONCEPT_STATE_INVALID",
          },
          { status: 409 },
        ),
      ),
    );
    renderAt(ROUTE_PATH);
    await openReviewDrawer();

    fireEvent.click(
      within(candidateRow("死锁")).getByRole("button", { name: "确认" }),
    );

    expect(
      await screen.findByText("概念当前状态不允许该操作"),
    ).toBeInTheDocument();
    // 快照未失效成功路径：状态栏仍是待审核（状态标签唯一，候选筛选 chip 属关系审核区）。
    expect(
      await screen.findByText("有概念候选待审核，确认后进入正式图谱。"),
    ).toBeInTheDocument();
  });
});
