// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import {
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import i18n from "@/i18n";
import { server } from "@/mocks/server";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import {
  exampleProfile,
  exampleEvidence,
} from "@/features/learning-profile/exampleProfile";
import { parseProfileSearch } from "@/features/learning-profile/profileSearch";

const courseId = "11111111-1111-4111-8111-111111111111";
const secondCourseId = "33333333-3333-4333-8333-333333333333";
const api = TEST_SIDECAR_URL;

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: async () => ({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));
vi.mock("@/charts/BaseChart", () => ({
  BaseChart: ({ ariaLabel }: { ariaLabel: string }) => (
    <div role="img" aria-label={ariaLabel} />
  ),
}));

beforeEach(() => {
  const data = { ...exampleProfile(i18n.t), course_id: courseId };
  server.use(
    http.get(`${api}/api/courses`, () =>
      HttpResponse.json([
        { id: courseId, name: "数据库原理", status: "ACTIVE" },
        { id: secondCourseId, name: "操作系统", status: "ACTIVE" },
      ]),
    ),
    http.get(`${api}/api/courses/:course/mastery`, ({ params }) =>
      HttpResponse.json(
        params.course === courseId
          ? data
          : {
              ...data,
              course_id: secondCourseId,
              concepts: [],
              confirmed_concept_count: 0,
              verified_concept_count: 0,
              coverage: 0,
              status_counts: {
                stable: 0,
                learning: 0,
                weak: 0,
                not_enough_data: 0,
              },
            },
      ),
    ),
    http.get(
      `${api}/api/courses/:course/mastery/concepts/:concept`,
      ({ params }) =>
        HttpResponse.json({
          snapshot: data.concepts.find(
            (concept) => concept.concept_id === params.concept,
          ),
          algorithm_version: "test",
          evidences: exampleEvidence().map((item, index) => ({
            ...item,
            source: index
              ? null
              : {
                  source_type: "QUIZ",
                  record_id: "record-1",
                  record_title: "真实题目来源",
                  quiz_id: "quiz-1",
                },
          })),
        }),
    ),
    http.get(`${api}/api/courses/:course/goals`, () => HttpResponse.json([])),
    http.get(`${api}/api/learner/preferences`, () =>
      HttpResponse.json({
        explicit_items: [],
        observed_entries: {},
        observed_confidence: null,
        evidence_count: 0,
        last_observed_at: null,
        updated_at: "2026-10-19T00:00:00Z",
        memory_outbound: {
          enabled: false,
          consent_granted_at: null,
          consent_current: false,
        },
      }),
    ),
  );
});

afterEach(() => window.history.replaceState(null, "", "/"));

function open(search = "") {
  window.history.replaceState(null, "", `/profile${search}`);
  return render(<App />);
}

describe("学习画像", () => {
  it("读取真实概念、有效证据并保留来源跳转与状态筛选", async () => {
    open();
    const workspace = await screen.findByRole("region", { name: "概念工作区" });
    expect(await within(workspace).findByText("真实题目来源")).toBeVisible();
    expect(
      within(workspace).getByRole("link", { name: "查看原题" }),
    ).toHaveAttribute("href", "/records/record-1?tab=quiz");
    expect(
      within(workspace).getByRole("link", { name: "在课程中查看" }),
    ).toHaveAttribute("href", `/spaces/${courseId}?tab=map`);
    fireEvent.click(screen.getByRole("button", { name: /稳定.*2/ }));
    await waitFor(() =>
      expect(new URLSearchParams(location.search).get("status")).toBe("STABLE"),
    );
    expect(
      await within(workspace).findByRole("heading", { name: "关系模型" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "清除状态筛选" }));
    await waitFor(() =>
      expect(new URLSearchParams(location.search).has("status")).toBe(false),
    );
  });

  it("示例只按明确入口展示，不读取虚构课程 API", async () => {
    let sampleRequests = 0;
    server.use(
      http.get(`${api}/api/courses/example/*`, () => {
        sampleRequests++;
        return HttpResponse.json({}, { status: 404 });
      }),
    );
    open("?course=example");
    expect(await screen.findByText(/界面示例：概念、证据与目标/)).toBeVisible();
    expect(
      await screen.findByRole("heading", { name: "事务隔离" }),
    ).toBeVisible();
    expect(sampleRequests).toBe(0);
    expect(
      screen.queryByRole("link", { name: "查看原题" }),
    ).not.toBeInTheDocument();
  });

  it("切换课程清除旧概念和状态，并展示真实空态", async () => {
    open("?course=" + secondCourseId + "&concept=example-0");
    expect(
      await screen.findByText(
        i18n.t("spaces.courseDetail.gps.emptyDescription"),
      ),
    ).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "事务隔离" }),
    ).not.toBeInTheDocument();
  });

  it("课程读取失败可重试，不以示例代替失败数据", async () => {
    let reads = 0;
    server.use(
      http.get(`${api}/api/courses`, () => {
        reads++;
        return HttpResponse.json({ detail: "unavailable" }, { status: 403 });
      }),
    );
    open();
    const panel = await screen.findByRole("tabpanel", { name: "概念与证据" });
    expect(
      await within(panel).findByText(
        "学习数据暂时不可用，请重试。",
        {},
        { timeout: 8000 },
      ),
    ).toBeVisible();
    expect(
      screen.queryByRole("heading", { name: "事务隔离" }),
    ).not.toBeInTheDocument();
    const before = reads;
    fireEvent.click(within(panel).getByRole("button", { name: "重新加载" }));
    await waitFor(() => expect(reads).toBeGreaterThan(before));
  }, 15000);

  it("日期选择写回 URL，超出真实统计范围不会伪造零时长", async () => {
    open("?date=2025-01-01");
    expect(
      await screen.findByText("该日期不在最近 30 天的统计范围内"),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "2025年1月2日" }));
    await waitFor(() =>
      expect(new URLSearchParams(location.search).get("date")).toBe(
        "2025-01-02",
      ),
    );
    fireEvent.click(screen.getByRole("button", { name: "下一个月" }));
    expect(screen.getByRole("button", { name: "2025年2月28日" })).toBeVisible();
    expect(new URLSearchParams(location.search).get("date")).toBe("2025-01-02");
    fireEvent.click(screen.getByRole("button", { name: "上一个月" }));
    expect(
      screen.getByRole("button", { name: "2025年1月2日" }).closest("td"),
    ).toHaveAttribute("aria-selected", "true");
  });

  it("切换页签后保留偏好输入草稿", async () => {
    open("?tab=memory");
    const input = await screen.findByPlaceholderText(/我喜欢先看例题/);
    fireEvent.change(input, { target: { value: "未保存的偏好" } });
    fireEvent.click(screen.getByRole("tab", { name: "概念与证据" }));
    fireEvent.click(screen.getByRole("tab", { name: "偏好与 AI 记忆" }));
    expect(screen.getByPlaceholderText(/我喜欢先看例题/)).toHaveValue(
      "未保存的偏好",
    );
  });

  it("统计范围内缺失的日期不会显示为零分钟，真实零值正常显示", async () => {
    server.use(
      http.get(`${api}/api/today/stats/trend`, () =>
        HttpResponse.json([
          { date: "2026-10-09", total_ms: 60000 },
          { date: "2026-10-11", total_ms: 0 },
        ]),
      ),
    );
    open("?date=2026-10-10");
    expect(await screen.findByText("该日期暂无学习时长统计")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "2026年10月11日" }));
    expect(await screen.findByText("0 分钟")).toBeVisible();
  });

  it("资料来源复用精确锚点和知识点跳转", async () => {
    server.use(
      http.get(
        `${api}/api/courses/:course/brain/concepts/:concept/sources`,
        () =>
          HttpResponse.json({
            concept_id: "example-0",
            anchors: [
              {
                anchor_id: "anchor-1",
                record_id: "record-1",
                record_title: "教材摘录",
                quote: "隔离级别",
                segment_id: "segment-1",
                source_type: "DOCUMENT_SEGMENT",
                relation_type: "PRIMARY",
              },
            ],
            knowledge_points: [
              {
                knowledge_point_id: "kp-1",
                knowledge_point_name: "隔离级别知识点",
                record_id: "record-2",
                record_title: "第二讲",
                relevance: 1,
                evidence_count: 1,
              },
            ],
          }),
      ),
    );
    open();
    fireEvent.click(await screen.findByRole("tab", { name: "相关资料" }));
    expect(await screen.findByText("隔离级别知识点")).toBeVisible();
    const links = screen.getAllByRole("link", { name: "打开资料" });
    expect(links[0]).toHaveAttribute(
      "href",
      expect.stringContaining("segmentId=segment-1"),
    );
    expect(links[1]).toHaveAttribute(
      "href",
      "/records/record-2?tab=knowledge-points",
    );
  });

  it("切换历程能展开全部概念，回到概念保留选择", async () => {
    open("?concept=example-1");
    const workspace = await screen.findByRole("region", { name: "概念工作区" });
    expect(
      await within(workspace).findByRole("heading", { name: "关系模型" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "阶段回顾 · 展开" }));
    expect(
      await screen.findByRole("heading", { name: "学习验证历程" }),
    ).toBeVisible();
    fireEvent.click(screen.getByRole("tab", { name: "概念与证据" }));
    expect(
      await within(workspace).findByRole("heading", { name: "关系模型" }),
    ).toBeVisible();
  });

  it("校验 URL 日期与状态，保留合法闰日", () => {
    expect(
      parseProfileSearch({ date: "2026-02-30", status: "fake", tab: "fake" }),
    ).toMatchObject({ date: undefined, status: undefined, tab: "concepts" });
    expect(
      parseProfileSearch({ date: "2024-02-29", status: "WEAK", tab: "memory" }),
    ).toMatchObject({ date: "2024-02-29", status: "WEAK", tab: "memory" });
  });
});
