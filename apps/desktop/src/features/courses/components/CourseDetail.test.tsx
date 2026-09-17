// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  within,
  waitFor,
} from "@testing-library/react";
import { delay, http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_LAUNCH_TOKEN, TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

type CourseDetail = components["schemas"]["CourseDetailOut"];
type RecordOut = components["schemas"]["RecordOut"];
type CourseMastery = components["schemas"]["CourseMasteryOut"];
type ConceptMastery = components["schemas"]["ConceptMasteryOut"];
type ConceptMasteryDetail =
  components["schemas"]["ConceptMasteryDetailOut"];

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}`;
const RECORDS_URL = `${DETAIL_URL}/records`;
const MASTERY_URL = `${DETAIL_URL}/mastery`;
const ROUTE_PATH = `/spaces/${COURSE_ID}`;

const weakConcept: ConceptMastery = {
  concept_id: "concept-weak",
  canonical_name: "进程调度",
  description: "调度器如何选择就绪进程。",
  concept_type: "TERM",
  importance: 4,
  status: "WEAK",
  mastery_score: 0.33,
  confidence: "HIGH",
  evidence_count: 8,
  positive_evidence_count: 4,
  negative_evidence_count: 4,
  last_practiced_at: "2026-09-16T08:00:00.000000Z",
  last_verified_at: "2026-09-15T08:00:00.000000Z",
};

const learningConcept: ConceptMastery = {
  concept_id: "concept-learning",
  canonical_name: "内存分页",
  description: "分页机制与页表。",
  concept_type: "TERM",
  importance: 3,
  status: "LEARNING",
  mastery_score: 0.74,
  confidence: "MEDIUM",
  evidence_count: 6,
  positive_evidence_count: 5,
  negative_evidence_count: 1,
  last_practiced_at: "2026-09-16T09:00:00.000000Z",
  last_verified_at: "2026-09-16T09:00:00.000000Z",
};

const notEnoughConcept: ConceptMastery = {
  concept_id: "concept-empty",
  canonical_name: "虚拟内存",
  description: "地址空间与换页。",
  concept_type: "TERM",
  importance: 3,
  status: "NOT_ENOUGH_DATA",
  mastery_score: null,
  confidence: null,
  evidence_count: 1,
  positive_evidence_count: 1,
  negative_evidence_count: 0,
  last_practiced_at: "2026-09-14T08:00:00.000000Z",
  last_verified_at: null,
};

const masteryPayload: CourseMastery = {
  course_id: COURSE_ID,
  confirmed_concept_count: 3,
  verified_concept_count: 2,
  coverage: 2 / 3,
  status_counts: {
    not_enough_data: 1,
    weak: 1,
    learning: 1,
    stable: 0,
  },
  concepts: [weakConcept, learningConcept, notEnoughConcept],
};

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

const recordStatuses: RecordOut["status"][] = [
  "FAILED",
  "COMPLETED",
  "SUMMARY_READY",
  "SUMMARY_PROCESSING",
  "SUMMARY_PENDING",
  "CONTENT_PROCESSING",
  "DRAFT",
  "NOTE",
];

const records: RecordOut[] = recordStatuses.map((status, index) => ({
  id: `record-${index + 1}`,
  course_id: COURSE_ID,
  capture_type: index === 0 ? "AUDIO_IMPORT" : "QUICK_NOTE",
  title: index === 7 ? "   " : `学习记录 ${index + 1}`,
  status,
  duration_ms: index === 0 ? 65_000 : 0,
  summary_confirmed_at: null,
  created_at: `2026-08-${String(19 - index).padStart(2, "0")}T08:00:00.000000Z`,
  updated_at: `2026-08-${String(19 - index).padStart(2, "0")}T08:00:00.000000Z`,
}));

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

// 详情页现在常驻拉取课程学习记录（最近记录卡 / 相关资源 / 打开课程）；
// 各用例按需覆盖，默认给空列表避免未处理请求。
beforeEach(() => {
  server.use(http.get(RECORDS_URL, () => HttpResponse.json([])));
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

function renderAt(path: string) {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

async function selectOption(comboboxName: string, optionName: string) {
  const trigger = screen.getByRole("combobox", { name: comboboxName });
  fireEvent.click(trigger);
  const option = await screen.findByRole("option", { name: optionName });
  fireEvent.pointerDown(option);
  fireEvent.pointerUp(option);
  fireEvent.click(option);
  await waitFor(() => expect(trigger).toHaveTextContent(optionName));
}

describe("课程详情与编辑", () => {
  it("从列表进入详情并查看名称、场景、阶段、类型、说明与热词摘要", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json([schoolCourse]),
      ),
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
    );
    renderAt("/spaces");

    fireEvent.click(
      await screen.findByRole("button", { name: "打开课程 操作系统" }),
    );

    expect(
      await screen.findByRole("heading", { name: "操作系统" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("学业学习").length).toBeGreaterThan(0);
    expect(screen.getAllByText("本科").length).toBeGreaterThan(0);
    expect(screen.getAllByText("专业课").length).toBeGreaterThan(0);
    expect(screen.getByText("理解进程、内存与文件系统。")).toBeInTheDocument();
    expect(screen.getByText("暂无热词")).toBeInTheDocument();
    expect(screen.getByText("课程核心概览")).toBeInTheDocument();
  });

  it("tab 状态受 URL 校验：记录宿主可恢复、切换写回 URL、非法值回退概览", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)));
    renderAt(`${ROUTE_PATH}?tab=records`);

    expect(
      await screen.findByRole("heading", { name: "还没有学习记录" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "课程核心概览" }),
    ).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "概览" }));

    expect(
      await screen.findByRole("heading", { name: "课程核心概览" }),
    ).toBeInTheDocument();
    expect(window.location.search).toBe("?tab=overview");

    cleanup();
    window.history.replaceState(null, "", `${ROUTE_PATH}?tab=nonsense`);
    render(<App />);

    expect(
      await screen.findByRole("heading", { name: "课程核心概览" }),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("heading", { name: "还没有学习记录" }),
    ).not.toBeInTheDocument();
  });

  it("新增标签页（脑图/知识GPS/课程对话）可访问并写回 URL", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)));
    renderAt(`${ROUTE_PATH}?tab=map`);

    expect(
      await screen.findByRole("heading", { name: "课程脑图" }),
    ).toBeInTheDocument();

    fireEvent.click(screen.getByRole("tab", { name: "知识GPS" }));

    expect(
      await screen.findByRole("heading", { name: "知识GPS · 掌握状态" }),
    ).toBeInTheDocument();
    expect(window.location.search).toBe("?tab=gps");

    fireEvent.click(screen.getByRole("tab", { name: "课程对话" }));

    expect(
      await screen.findByRole("heading", { name: "课程对话" }),
    ).toBeInTheDocument();
    expect(window.location.search).toBe("?tab=chat");
    // 课程对话已接真（B2）：不再有「示意」标记，展示发起课程会话的 CTA。
    expect(screen.queryByText("示意")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", {
        name: "开启「操作系统」课程问答",
      }),
    ).toBeEnabled();
  });

  it("概览概念分布卡与课程脑图页在未构建时给出构建引导空态", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)));
    renderAt(ROUTE_PATH);

    expect(
      await screen.findByRole("heading", { name: "概念分布" }),
    ).toBeInTheDocument();
    expect(
      await screen.findByText(
        "积累转写、文档或对话后，一键抽取核心概念并整理成图谱；确认后可用于检索增强与问答。",
      ),
    ).toBeInTheDocument();

    cleanup();
    renderAt(`${ROUTE_PATH}?tab=map`);

    expect(
      await screen.findByRole("heading", { name: "让课程长出「大脑」" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "构建课程脑图" })).toBeEnabled();
  });

  it("概览掌握卡使用真实覆盖率与状态分布，不再出现章级示意数据", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(MASTERY_URL, () => HttpResponse.json(masteryPayload)),
    );
    renderAt(ROUTE_PATH);

    expect(await screen.findByText("67%")).toBeInTheDocument();
    expect(screen.getByText("已确认概念")).toBeInTheDocument();
    expect(screen.getByText("证据覆盖率")).toBeInTheDocument();
    expect(screen.getByText("待加强")).toBeInTheDocument();
    expect(screen.getByText("数据不足")).toBeInTheDocument();
    // 章级示意数据不再出现在概览入口。
    expect(screen.queryByText("基础概念")).not.toBeInTheDocument();
    expect(screen.queryByText("掌握度")).not.toBeInTheDocument();
  });

  it("知识GPS 展示真实 Concept 掌握列表并支持状态筛选写回 URL", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(MASTERY_URL, ({ request }) => {
        const status = new URL(request.url).searchParams.get("status");
        return HttpResponse.json(
          status
            ? {
                ...masteryPayload,
                concepts: masteryPayload.concepts.filter(
                  (concept) => concept.status === status,
                ),
              }
            : masteryPayload,
        );
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=gps`);

    const list = await screen.findByRole("list", { name: "概念掌握列表" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(3);
    expect(within(items[0]).getByText("进程调度")).toBeInTheDocument();
    expect(within(items[0]).getByText("待加强")).toBeInTheDocument();
    expect(within(items[0]).getByText("33%")).toBeInTheDocument();
    expect(within(items[0]).getByText("置信度 高")).toBeInTheDocument();
    expect(within(items[0]).getByText(/8 条证据/)).toBeInTheDocument();
    expect(within(items[1]).getByText("内存分页")).toBeInTheDocument();
    expect(within(items[1]).getByText("74%")).toBeInTheDocument();
    expect(within(items[1]).getByText("置信度 中")).toBeInTheDocument();
    expect(within(items[2]).getByText("虚拟内存")).toBeInTheDocument();
    expect(within(items[2]).getByText("数据不足")).toBeInTheDocument();
    // 无答对记录时展示「最近作答」，不把练习时间冒充为验证时间。
    expect(within(items[2]).getByText(/最近作答/)).toBeInTheDocument();
    expect(within(items[2]).queryByText(/最近验证/)).not.toBeInTheDocument();
    // 数据不足不显示伪造百分比。
    expect(within(items[2]).queryByText(/%/)).not.toBeInTheDocument();

    await selectOption("按掌握状态筛选", "待加强");

    await waitFor(() =>
      expect(window.location.search).toBe("?tab=gps&mastery=WEAK"),
    );
    await waitFor(() =>
      expect(
        within(screen.getByRole("list", { name: "概念掌握列表" })).getAllByRole(
          "listitem",
        ),
      ).toHaveLength(1),
    );
  });

  it("知识GPS 无已确认概念时给出构建课程脑图引导", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)));
    renderAt(`${ROUTE_PATH}?tab=gps`);

    expect(await screen.findByText("还没有已确认的概念")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "打开课程脑图" }));

    await waitFor(() => expect(window.location.search).toBe("?tab=map"));
  });

  it("知识GPS 掌握状态读取失败可原地重试且不伪装为空态", async () => {
    let calls = 0;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(MASTERY_URL, () => {
        calls += 1;
        return calls <= 3
          ? HttpResponse.json({ detail: "数据库暂时忙" }, { status: 500 })
          : HttpResponse.json(masteryPayload);
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=gps`);

    expect(
      await screen.findByText("掌握状态暂时无法读取", undefined, {
        timeout: 6_000,
      }),
    ).toBeInTheDocument();
    expect(screen.queryByText("还没有已确认的概念")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));

    expect(
      await screen.findByRole("list", { name: "概念掌握列表" }),
    ).toBeInTheDocument();
    expect(calls).toBeGreaterThanOrEqual(4);
  });

  it("点击概念行打开掌握详情，展示快照与参与计算的 Evidence 来源", async () => {
    const detailPayload: ConceptMasteryDetail = {
      snapshot: weakConcept,
      algorithm_version: "mastery_v1",
      evidences: [
        {
          evidence_id: "evidence-quiz-1",
          score: 1,
          result: "CORRECT",
          occurred_at: "2026-09-16T09:00:00.000000Z",
          source: {
            source_type: "QUIZ",
            record_id: "record-quiz-1",
            record_title: "进程与线程",
            quiz_id: "quiz-1",
          },
        },
        {
          evidence_id: "evidence-test-1",
          score: 0,
          result: "WRONG",
          occurred_at: "2026-09-15T10:00:00.000000Z",
          source: {
            source_type: "QUIZ_TEST",
            test_id: "test-1",
            sequence_no: 2,
          },
        },
        {
          evidence_id: "evidence-orphan-1",
          score: 0.5,
          result: null,
          occurred_at: "2026-09-14T10:00:00.000000Z",
          source: null,
        },
      ],
    };
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(MASTERY_URL, () => HttpResponse.json(masteryPayload)),
      http.get(
        `${DETAIL_URL}/mastery/concepts/${weakConcept.concept_id}`,
        () => HttpResponse.json(detailPayload),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=gps`);

    const list = await screen.findByRole("list", { name: "概念掌握列表" });
    fireEvent.click(within(list).getByText("进程调度"));

    const dialog = await screen.findByRole("dialog", { name: "进程调度" });
    expect(await within(dialog).findByText("待加强")).toBeInTheDocument();
    expect(within(dialog).getByText("33%")).toBeInTheDocument();
    expect(within(dialog).getByText("置信度 高")).toBeInTheDocument();
    expect(within(dialog).getByText("参与计算证据")).toBeInTheDocument();
    // 两类来源：普通 Quiz 带宿主记录标题，模拟测试带题号。
    expect(
      within(dialog).getByText("习题 · 进程与线程"),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("答对")).toBeInTheDocument();
    expect(
      within(dialog).getByText("模拟测试 · 第 2 题"),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("答错")).toBeInTheDocument();
    // 定位能力不足的 Evidence 只保留来源说明与时间，不生成假链接。
    expect(within(dialog).getByText("来源信息不足")).toBeInTheDocument();
    expect(
      within(dialog).getAllByRole("button", { name: "查看来源" }),
    ).toHaveLength(2);
  });

  it("Evidence 来源可跳回普通习题与模拟测试结果页", async () => {
    const detailPayload: ConceptMasteryDetail = {
      snapshot: weakConcept,
      algorithm_version: "mastery_v1",
      evidences: [
        {
          evidence_id: "evidence-quiz-1",
          score: 1,
          result: "CORRECT",
          occurred_at: "2026-09-16T09:00:00.000000Z",
          source: {
            source_type: "QUIZ",
            record_id: "record-quiz-1",
            record_title: "进程与线程",
            quiz_id: "quiz-1",
          },
        },
        {
          evidence_id: "evidence-test-1",
          score: 0,
          result: "WRONG",
          occurred_at: "2026-09-15T10:00:00.000000Z",
          source: {
            source_type: "QUIZ_TEST",
            test_id: "test-1",
            sequence_no: 2,
          },
        },
      ],
    };
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(MASTERY_URL, () => HttpResponse.json(masteryPayload)),
      http.get(
        `${DETAIL_URL}/mastery/concepts/${weakConcept.concept_id}`,
        () => HttpResponse.json(detailPayload),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=gps`);

    const list = await screen.findByRole("list", { name: "概念掌握列表" });
    fireEvent.click(within(list).getByText("进程调度"));

    const dialog = await screen.findByRole("dialog", { name: "进程调度" });
    const sources = await within(dialog).findAllByRole("button", {
      name: "查看来源",
    });
    // 第一条（时间倒序最晚）是普通 Quiz → 记录页习题区。
    fireEvent.click(sources[0]);

    await waitFor(() =>
      expect(window.location.pathname).toBe("/records/record-quiz-1"),
    );
    expect(window.location.search).toBe("?tab=quiz");

    // 第二条是模拟测试逐题 → 该场测试结果页。
    window.history.replaceState(null, "", `${ROUTE_PATH}?tab=gps`);
    render(<App />);
    const listAgain = await screen.findByRole("list", {
      name: "概念掌握列表",
    });
    fireEvent.click(within(listAgain).getByText("进程调度"));
    const dialogAgain = await screen.findByRole("dialog", {
      name: "进程调度",
    });
    const sourcesAgain = await within(dialogAgain).findAllByRole("button", {
      name: "查看来源",
    });
    fireEvent.click(sourcesAgain[1]);

    await waitFor(() =>
      expect(window.location.pathname).toBe(
        `/spaces/${COURSE_ID}/tests/test-1`,
      ),
    );
  });

  it("数据不足的概念详情给出空 Evidence 空态", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(MASTERY_URL, () => HttpResponse.json(masteryPayload)),
      http.get(
        `${DETAIL_URL}/mastery/concepts/${notEnoughConcept.concept_id}`,
        () =>
          HttpResponse.json({
            snapshot: notEnoughConcept,
            algorithm_version: "mastery_v1",
            evidences: [],
          } satisfies ConceptMasteryDetail),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=gps`);

    const list = await screen.findByRole("list", { name: "概念掌握列表" });
    fireEvent.click(within(list).getByText("虚拟内存"));

    const dialog = await screen.findByRole("dialog", { name: "虚拟内存" });
    expect(
      await within(dialog).findByText("数据不足"),
    ).toBeInTheDocument();
    expect(within(dialog).getByText("暂无参与计算的作答证据")).toBeInTheDocument();
    expect(
      within(dialog).queryByRole("button", { name: "查看来源" }),
    ).not.toBeInTheDocument();
  });

  it("关注为本地界面态切换且不发起请求", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)));
    renderAt(ROUTE_PATH);

    const follow = await screen.findByRole("button", { name: "关注" });
    expect(follow).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(follow);

    expect(screen.getByRole("button", { name: "已关注" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  it("打开课程进入最近一条学习记录", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(RECORDS_URL, () => HttpResponse.json(records)),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "打开课程" }));

    await waitFor(() =>
      expect(window.location.pathname).toBe(`/records/${records[0].id}`),
    );
  });

  it("没有学习记录时打开课程给出捕获引导", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)));
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "打开课程" }));

    expect(
      await screen.findByText(
        "暂无学习记录，可用顶部「速记 / 录音」创建第一条。",
      ),
    ).toBeInTheDocument();
  });

  it("学习记录加载中保持稳定状态", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(RECORDS_URL, async () => {
        await delay(200);
        return HttpResponse.json([]);
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=records`);

    expect(await screen.findByText("正在读取学习记录")).toHaveAttribute(
      "role",
      "status",
    );
    expect(screen.queryByText("还没有学习记录")).not.toBeInTheDocument();
  });

  it("学习记录加载失败可原地重试且不伪装为空态", async () => {
    let calls = 0;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(RECORDS_URL, () => {
        calls += 1;
        return calls <= 3
          ? HttpResponse.json({ detail: "数据库暂时忙" }, { status: 500 })
          : HttpResponse.json([]);
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=records`);

    expect(
      await screen.findByRole(
        "heading",
        { name: "学习记录暂时无法读取" },
        { timeout: 6_000 },
      ),
    ).toBeInTheDocument();
    expect(screen.queryByText("还没有学习记录")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));

    expect(
      await screen.findByRole("heading", { name: "还没有学习记录" }),
    ).toBeInTheDocument();
    expect(calls).toBeGreaterThanOrEqual(4);
  });

  it("真实列表呈现标题回退、采集类型、八态、创建时间和有效时长", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(RECORDS_URL, ({ request }) => {
        expect(request.headers.get("X-KnowRealm-Token")).toBe(
          TEST_LAUNCH_TOKEN,
        );
        return HttpResponse.json(records);
      }),
    );
    renderAt(`${ROUTE_PATH}?tab=records`);

    const list = await screen.findByRole("list", { name: "学习记录列表" });
    const items = within(list).getAllByRole("listitem");
    expect(items).toHaveLength(8);
    expect(within(items[0]).getByRole("link")).toHaveAttribute(
      "href",
      `/records/${records[0].id}`,
    );
    expect(within(items[0]).getByText("音频导入")).toBeInTheDocument();
    expect(within(items[0]).getByText("1 分 5 秒")).toBeInTheDocument();
    expect(within(items[0]).getByText(/2026/)).toBeInTheDocument();
    expect(within(items[7]).getByText("未命名学习记录")).toBeInTheDocument();
    expect(
      within(items[7]).queryByText(/秒|分钟|小时/),
    ).not.toBeInTheDocument();
    for (const label of [
      "仅保存",
      "草稿",
      "内容处理中",
      "等待生成总结",
      "总结生成中",
      "总结待确认",
      "已完成",
      "处理失败",
    ]) {
      expect(within(list).getByText(label)).toBeInTheDocument();
    }
  });

  it("概览最近学习记录展示真实记录并给出查看全部入口", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(RECORDS_URL, () => HttpResponse.json(records)),
    );
    renderAt(ROUTE_PATH);

    const recent = await screen.findByRole("heading", {
      name: "最近学习记录",
    });
    expect(recent).toBeInTheDocument();
    expect(await screen.findByText(`学习记录 1`)).toBeInTheDocument();

    const recentCard = recent.closest("section");
    expect(recentCard).not.toBeNull();
    fireEvent.click(
      within(recentCard as HTMLElement).getByRole("button", {
        name: /查看全部/,
      }),
    );
    await waitFor(() => expect(window.location.search).toBe("?tab=records"));
  });

  it("学习链标签页展示真实记录状态派生的流转与文字摘要", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(RECORDS_URL, () => HttpResponse.json(records)),
    );
    renderAt(`${ROUTE_PATH}?tab=chain`);

    expect(
      await screen.findByRole("heading", { name: "学习链流转" }),
    ).toBeInTheDocument();
    expect(screen.getByText("8 条 · 100%")).toBeInTheDocument();
    expect(screen.getByText("5 条 · 63%")).toBeInTheDocument();
    expect(screen.getByText("4 条 · 50%")).toBeInTheDocument();
    expect(screen.getByText("1 条 · 13%")).toBeInTheDocument();
    expect(screen.getByText("未开始处理")).toBeInTheDocument();
    expect(screen.getByText("待确认")).toBeInTheDocument();
    expect(
      screen.getByText("1 条失败；记录不保存失败阶段，未计入主链。"),
    ).toBeInTheDocument();
  });

  it("学习链标签页写回 URL，空课程给出捕获引导", async () => {
    server.use(http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)));
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("tab", { name: "学习链" }));

    expect(
      await screen.findByRole("heading", { name: "还没有学习记录" }),
    ).toBeInTheDocument();
    expect(window.location.search).toBe("?tab=chain");
    expect(
      screen.getByText(
        "用顶部「速记 / 录音」捕获第一条，学习链会随处理进度更新。",
      ),
    ).toBeInTheDocument();
  });

  it("不存在或已软删课程显示未找到状态并提供返回知识空间路径", async () => {
    server.use(
      http.get(DETAIL_URL, () =>
        HttpResponse.json({ detail: "课程不存在或已删除" }, { status: 404 }),
      ),
    );
    renderAt(ROUTE_PATH);

    expect(
      await screen.findByRole("heading", { name: "课程不存在或已删除" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "返回知识空间" })).toHaveAttribute(
      "href",
      "/spaces",
    );
  });

  it("编辑成功后详情缓存同步刷新并按契约提交 PATCH", async () => {
    let current = schoolCourse;
    let detailCalls = 0;
    let patchBody: unknown;
    let patchToken: string | null = null;
    server.use(
      http.get(DETAIL_URL, () => {
        detailCalls += 1;
        return HttpResponse.json(current);
      }),
      http.patch(DETAIL_URL, async ({ request }) => {
        patchBody = await request.json();
        patchToken = request.headers.get("X-KnowRealm-Token");
        current = {
          ...schoolCourse,
          name: "操作系统导论",
          updated_at: "2026-08-18T08:00:00.000000Z",
        };
        return HttpResponse.json(current);
      }),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "编辑课程" }));
    const nameField = await screen.findByRole("textbox", { name: "课程名称" });
    fireEvent.change(nameField, { target: { value: "操作系统导论" } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(
      await screen.findByRole("heading", { name: "操作系统导论" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "编辑课程" }),
    ).toBeInTheDocument();
    expect(detailCalls).toBeGreaterThanOrEqual(2);
    expect(patchToken).toBe(TEST_LAUNCH_TOKEN);
    expect(patchBody).toEqual({
      name: "操作系统导论",
      learning_context: "SCHOOL",
      education_stage: "UNDERGRADUATE",
      depth: null,
      course_type: "MAJOR",
      description: "理解进程、内存与文件系统。",
      hot_words: [],
    });
  });

  it("跨场景切换未选深度时保留输入、聚焦错误字段且不发请求；补选后成功保存", async () => {
    let patchCalls = 0;
    let patchBody: unknown = null;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.patch(DETAIL_URL, async ({ request }) => {
        patchCalls += 1;
        patchBody = await request.json();
        return HttpResponse.json({
          ...schoolCourse,
          learning_context: "CAREER",
          education_stage: null,
          depth: "BEGINNER",
          updated_at: "2026-08-18T08:00:00.000000Z",
        });
      }),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "编辑课程" }));
    fireEvent.click(screen.getByRole("radio", { name: /职业技能/ }));
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText("请选择学习深度")).toBeVisible();
    expect(screen.getByRole("combobox", { name: "学习深度" })).toHaveFocus();
    expect(screen.getByRole("textbox", { name: "课程名称" })).toHaveValue(
      "操作系统",
    );
    expect(patchCalls).toBe(0);

    await selectOption("学习深度", "入门");
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    await waitFor(() => expect(patchCalls).toBe(1));
    expect(patchBody).toMatchObject({
      learning_context: "CAREER",
      education_stage: null,
      depth: "BEGINNER",
    });
    expect(
      await screen.findByRole("heading", { name: "操作系统" }),
    ).toBeInTheDocument();
  });

  it("保存失败保留输入并显示可理解错误，重试后成功", async () => {
    let current = schoolCourse;
    let patchCalls = 0;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(current)),
      http.patch(DETAIL_URL, () => {
        patchCalls += 1;
        if (patchCalls === 1) {
          return HttpResponse.json(
            { detail: "本地服务暂时不可用" },
            { status: 500 },
          );
        }
        current = {
          ...schoolCourse,
          name: "操作系统导论",
          updated_at: "2026-08-18T08:00:00.000000Z",
        };
        return HttpResponse.json(current);
      }),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "编辑课程" }));
    fireEvent.change(await screen.findByRole("textbox", { name: "课程名称" }), {
      target: { value: "操作系统导论" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText("本地服务暂时不可用")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "课程名称" })).toHaveValue(
      "操作系统导论",
    );

    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(
      await screen.findByRole("heading", { name: "操作系统导论" }),
    ).toBeInTheDocument();
    expect(patchCalls).toBe(2);
  });

  it("API 边界 422 拒绝编辑时保留输入并显示服务端说明", async () => {
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.patch(DETAIL_URL, () =>
        HttpResponse.json(
          { detail: "学业场景必须选择教育阶段" },
          { status: 422 },
        ),
      ),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "编辑课程" }));
    const nameField = await screen.findByRole("textbox", { name: "课程名称" });
    fireEvent.change(nameField, { target: { value: "操作系统导论" } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText("学业场景必须选择教育阶段")).toBeVisible();
    expect(screen.getByRole("textbox", { name: "课程名称" })).toHaveValue(
      "操作系统导论",
    );
    expect(screen.getByRole("button", { name: "保存修改" })).toBeEnabled();
  });

  it("无效或超过 100 个热词时保留输入且不请求，合法热词按输入顺序随 PATCH 保存", async () => {
    let current = schoolCourse;
    let patchCalls = 0;
    let patchBody: unknown;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(current)),
      http.patch(DETAIL_URL, async ({ request }) => {
        patchCalls += 1;
        patchBody = await request.json();
        current = {
          ...schoolCourse,
          hot_words: ["进程", "文件系统", "内存"],
          updated_at: "2026-08-19T08:00:00.000000Z",
        };
        return HttpResponse.json(current);
      }),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "编辑课程" }));
    const hotWords = screen.getByRole("textbox", { name: "手动热词" });
    const tooMany = Array.from(
      { length: 101 },
      (_, index) => `热词${index}`,
    ).join("\n");
    fireEvent.change(hotWords, { target: { value: tooMany } });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText("最多保存 100 个热词")).toBeVisible();
    expect(hotWords).toHaveFocus();
    expect(hotWords).toHaveValue(tooMany);
    expect(patchCalls).toBe(0);

    fireEvent.change(hotWords, {
      target: { value: " 进程 \n\n 文件系统\n内存 " },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    expect(await screen.findByText("热词不能为空行")).toBeVisible();
    expect(hotWords).toHaveFocus();
    expect(patchCalls).toBe(0);

    fireEvent.change(hotWords, {
      target: { value: " 进程 \n 文件系统\n内存 " },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存修改" }));

    await waitFor(() => expect(patchCalls).toBe(1));
    expect(patchBody).toMatchObject({
      hot_words: ["进程", "文件系统", "内存"],
    });
    const infoPanel = screen.getByRole("complementary", {
      name: "课程信息",
    });
    expect(within(infoPanel).getByText("进程")).toBeInTheDocument();
    expect(within(infoPanel).getByText("文件系统")).toBeInTheDocument();
    expect(within(infoPanel).getByText("内存")).toBeInTheDocument();
  });

  it("取消删除不会发请求或改变课程状态", async () => {
    let deleteCalls = 0;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.delete(DETAIL_URL, () => {
        deleteCalls += 1;
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "删除课程" }));
    expect(screen.getByRole("heading", { name: "确认删除课程" })).toBeVisible();
    expect(screen.getByText(/当前没有恢复界面/)).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "取消" }));

    await waitFor(() =>
      expect(
        screen.queryByRole("heading", { name: "确认删除课程" }),
      ).not.toBeInTheDocument(),
    );
    expect(deleteCalls).toBe(0);
    expect(screen.getByRole("heading", { name: "操作系统" })).toBeVisible();
  });

  it("删除失败可原地重试，成功后失效缓存并返回知识空间", async () => {
    let deleteCalls = 0;
    let deleteToken: string | null = null;
    server.use(
      http.get(DETAIL_URL, () => HttpResponse.json(schoolCourse)),
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
      http.delete(DETAIL_URL, ({ request }) => {
        deleteCalls += 1;
        deleteToken = request.headers.get("X-KnowRealm-Token");
        if (deleteCalls === 1) {
          return HttpResponse.json(
            { detail: "数据库暂时忙，请重试" },
            { status: 500 },
          );
        }
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderAt(ROUTE_PATH);

    fireEvent.click(await screen.findByRole("button", { name: "删除课程" }));
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    expect(await screen.findByText("数据库暂时忙，请重试")).toBeVisible();
    expect(screen.getByRole("button", { name: "确认删除" })).toBeEnabled();
    fireEvent.click(screen.getByRole("button", { name: "确认删除" }));

    expect(await screen.findByText("还没有知识空间")).toBeVisible();
    expect(window.location.pathname).toBe("/spaces");
    expect(deleteCalls).toBe(2);
    expect(deleteToken).toBe(TEST_LAUNCH_TOKEN);
  });
});
