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
type ConceptSourcesOut = components["schemas"]["ConceptSourcesOut"];

const COURSE_ID = "22222222-2222-4222-8222-222222222222";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}`;
const BRAIN_URL = `${DETAIL_URL}/brain`;
const CONCEPTS_URL = `${BRAIN_URL}/concepts`;
const SOURCES_URL = `${BRAIN_URL}/concepts/c1/sources`;
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

function snapshotOf(
  status: BrainSnapshotOut["status"],
  overrides: Partial<BrainSnapshotOut> = {},
): BrainSnapshotOut {
  return {
    course_id: COURSE_ID,
    status,
    concept_count: status === "EMPTY" ? 0 : 2,
    candidate_count: 0,
    stale: status === "STALE",
    active_job_id: null,
    last_built_at: status === "EMPTY" ? null : "2026-09-15T08:00:00.000000Z",
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
              {
                id: "c2",
                canonical_name: "虚拟内存",
                concept_type: "PRINCIPLE",
                importance: 3,
                occurrence_count: 2,
                record_count: 1,
              },
            ],
            edges: [
              {
                source_concept_id: "c1",
                target_concept_id: "c2",
                relation_type: "RELATED",
                evidence_count: 2,
                confidence: 0.9,
                stale: false,
              },
            ],
          },
    ...overrides,
  };
}

const conceptSources: ConceptSourcesOut = {
  concept_id: "c1",
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
      segment_id: "seg-65",
    },
    {
      anchor_id: "a2",
      source_type: "DOCUMENT_SEGMENT",
      record_id: "record-2",
      record_title: "课件.pdf",
      start_ms: null,
      end_ms: null,
      quote: null,
      relation_type: "MENTIONS",
      chat_session_id: null,
      page_no: 4,
      segment_id: "dseg-4",
    },
    {
      anchor_id: "a3",
      source_type: "CHAT_MESSAGE",
      record_id: null,
      record_title: null,
      start_ms: null,
      end_ms: null,
      quote: "进程调度和虚拟内存的关系是什么？",
      relation_type: "MENTIONS",
      chat_session_id: "session-1",
      page_no: null,
      segment_id: null,
    },
  ],
  knowledge_points: [
    {
      knowledge_point_id: "kp-1",
      knowledge_point_name: "进程调度策略",
      record_id: "record-1",
      record_title: "第 1 讲 进程",
      evidence_count: 2,
      relevance: 0.9,
    },
  ],
};

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.mock("@/charts/BaseChart", () => ({
  BaseChart: ({
    ariaLabel,
    onItemSelect,
  }: {
    ariaLabel: string;
    onItemSelect?: (params: { dataType: string; data: { id: string } }) => void;
  }) => (
    <div>
      <div role="img" aria-label={ariaLabel} />
      <button
        type="button"
        onClick={() => onItemSelect?.({ dataType: "node", data: { id: "c1" } })}
      >
        mock-select-node
      </button>
    </div>
  ),
}));

vi.stubGlobal("scrollTo", vi.fn());

beforeEach(() => {
  server.use(
    http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
    http.get(`${DETAIL_URL}/records`, () => HttpResponse.json([])),
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

describe("Course Brain 页面", () => {
  it("READY 态图谱与列表双视图可切换，选中概念后详情面板与来源跳转可达", async () => {
    server.use(
      http.get(BRAIN_URL, () => HttpResponse.json(snapshotOf("READY"))),
      http.get(CONCEPTS_URL, () => HttpResponse.json(confirmedConcepts)),
      http.get(SOURCES_URL, () => HttpResponse.json(conceptSources)),
    );
    renderAt(ROUTE_PATH);

    expect(
      await screen.findByRole("img", {
        name: "「操作系统」概念关系图谱",
      }),
    ).toBeInTheDocument();
    expect(screen.getByText("已就绪")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "列表" }));
    expect(await screen.findByText("虚拟内存")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /进程调度/ }));
    expect(
      await screen.findByRole("heading", { name: "进程调度" }),
    ).toBeInTheDocument();
    expect(
      screen.getByText("CPU 在多个进程间分配的策略。"),
    ).toBeInTheDocument();

    const quoteRow = (
      await screen.findByText("进程调度是操作系统的核心机制")
    ).closest("a");
    expect(quoteRow).toHaveAttribute(
      "href",
      `/records/record-1?tab=transcript&segmentId=seg-65&highlight=${encodeURIComponent(
        "进程调度是操作系统的核心机制",
      )}`,
    );

    const documentRow = screen.getByText("课件.pdf").closest("a");
    expect(documentRow).toHaveAttribute(
      "href",
      "/records/record-2?tab=transcript&segmentId=dseg-4",
    );
    expect(screen.getByText("第 4 页")).toBeInTheDocument();

    const chatRow = screen
      .getByText("进程调度和虚拟内存的关系是什么？")
      .closest("a");
    expect(chatRow).toHaveAttribute("href", "/chat/session-1");

    const kpRow = screen.getByText("进程调度策略").closest("a");
    expect(kpRow).toHaveAttribute(
      "href",
      "/records/record-1?tab=knowledge-points",
    );
  });

  it("图谱节点点击打开对应概念详情", async () => {
    server.use(
      http.get(BRAIN_URL, () => HttpResponse.json(snapshotOf("READY"))),
      http.get(CONCEPTS_URL, () => HttpResponse.json(confirmedConcepts)),
      http.get(SOURCES_URL, () => HttpResponse.json(conceptSources)),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(
      await screen.findByRole("button", { name: "mock-select-node" }),
    );

    expect(
      await screen.findByRole("heading", { name: "进程调度" }),
    ).toBeInTheDocument();
  });

  it("列表支持正式/候选筛选且候选请求带 status 参数", async () => {
    const candidate: BrainConceptOut = {
      ...confirmedConcepts[0],
      id: "c9",
      canonical_name: "死锁",
      status: "CANDIDATE",
    };
    let requestedStatus: string | null = null;
    server.use(
      http.get(BRAIN_URL, () => HttpResponse.json(snapshotOf("READY"))),
      http.get(CONCEPTS_URL, ({ request }) => {
        requestedStatus = new URL(request.url).searchParams.get("status");
        return requestedStatus === "CANDIDATE"
          ? HttpResponse.json([candidate])
          : HttpResponse.json(confirmedConcepts);
      }),
    );
    renderAt(ROUTE_PATH);

    await screen.findByRole("button", { name: "列表" });
    fireEvent.click(screen.getByRole("button", { name: "列表" }));
    expect(await screen.findByText("虚拟内存")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "待审核候选" }));

    expect(await screen.findByText("死锁")).toBeInTheDocument();
    expect(screen.queryByText("虚拟内存")).not.toBeInTheDocument();
    expect(requestedStatus).toBe("CANDIDATE");
  });

  it("EMPTY 态展示构建引导，触发后进入 BUILDING", async () => {
    let current = snapshotOf("EMPTY");
    server.use(
      http.get(BRAIN_URL, () => HttpResponse.json(current)),
      http.post(`${BRAIN_URL}/builds`, () => {
        current = snapshotOf("BUILDING");
        return HttpResponse.json({ job_id: "job-1", accepted: true });
      }),
    );
    renderAt(ROUTE_PATH);

    expect(
      await screen.findByRole("heading", { name: "让课程长出「大脑」" }),
    ).toBeInTheDocument();
    expect(screen.getByText("未构建")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "构建课程脑图" }));

    expect(await screen.findByText("构建中")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "构建中…" })).toBeDisabled();
  });

  it("FAILED 态提供重试构建，STALE 态提示重新构建", async () => {
    let current = snapshotOf("FAILED");
    server.use(
      http.get(BRAIN_URL, () => HttpResponse.json(current)),
      http.post(`${BRAIN_URL}/builds`, () => {
        current = snapshotOf("BUILDING");
        return HttpResponse.json({ job_id: "job-1", accepted: true });
      }),
    );
    renderAt(ROUTE_PATH);

    expect(await screen.findByText("构建失败")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重试构建" }));

    expect(await screen.findByText("构建中")).toBeInTheDocument();

    cleanup();
    server.use(
      http.get(BRAIN_URL, () => HttpResponse.json(snapshotOf("STALE"))),
    );
    window.history.replaceState(null, "", ROUTE_PATH);
    render(<App />);

    expect(await screen.findByText("待更新")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "重新构建" })).toBeEnabled();
  });

  it("概览概念分布卡吃真实 Concept Top 分布", async () => {
    server.use(
      http.get(BRAIN_URL, () => HttpResponse.json(snapshotOf("READY"))),
      http.get(CONCEPTS_URL, () => HttpResponse.json(confirmedConcepts)),
    );
    window.history.replaceState(null, "", `/spaces/${COURSE_ID}`);
    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "知识的轮廓" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByRole("img", {
        name: "「操作系统」核心概念出现次数分布",
      }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("6 次出现").length).toBeGreaterThan(0);
    const toggle = screen.getByRole("button", { name: "切换条形图 / 玫瑰图" });
    expect(toggle).toHaveAttribute("aria-pressed", "false");
    fireEvent.click(toggle);
    expect(toggle).toHaveAttribute("aria-pressed", "true");
  });
});
