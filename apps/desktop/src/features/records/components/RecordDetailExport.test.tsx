// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  chooseMarkdownSavePath,
  openExportedFile,
  writeMarkdownFile,
} from "@/services/tauri/learningAssetExport";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { http, HttpResponse, delay } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_LAUNCH_TOKEN, TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

type RecordOut = components["schemas"]["RecordOut"];
type SummaryOut = components["schemas"]["SummaryOut"];
type KnowledgePointOut = components["schemas"]["KnowledgePointOut"];

const RECORD_ID = "22222222-2222-4222-8222-222222222222";
const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const DETAIL_URL = `${TEST_SIDECAR_URL}/api/records/${RECORD_ID}`;
const SUMMARY_URL = `${DETAIL_URL}/summary`;
const KNOWLEDGE_POINTS_URL = `${DETAIL_URL}/knowledge-points`;
const JOBS_URL = `${DETAIL_URL}/jobs`;
const TRANSCRIPT_URL = `${DETAIL_URL}/transcript`;
const LLM_PROVIDER_URL = `${TEST_SIDECAR_URL}/api/settings/providers/llm`;
const ROUTE_PATH = `/records/${RECORD_ID}`;

const record: RecordOut = {
  id: RECORD_ID,
  course_id: COURSE_ID,
  capture_type: "AUDIO_IMPORT",
  title: "操作系统第一讲",
  status: "COMPLETED",
  duration_ms: 65_000,
  summary_confirmed_at: "2026-08-25T08:30:00.000000Z",
  created_at: "2026-08-19T08:30:00.000000Z",
  updated_at: "2026-08-25T08:30:00.000000Z",
};

const confirmedSummary: SummaryOut = {
  id: "55555555-5555-4555-8555-555555555555",
  record_id: RECORD_ID,
  version_no: 1,
  transcript_source_version: 1,
  topic: "进程调度",
  abstract: "调度器按照既定策略选择下一个获得处理器的进程。",
  sections: [{ heading: "核心机制", points: ["就绪队列决定候选顺序。"] }],
  status: "CONFIRMED",
  model: "qwen-plus",
  prompt_version: "summary-v1",
  user_feedback: null,
  created_at: "2026-08-24T12:00:00.000000Z",
};

function summaryResponse(summary: SummaryOut | null) {
  return HttpResponse.json({
    action_required: "NONE",
    active_job_id: null,
    blocked_reason: null,
    summary,
  });
}

function knowledgePoint(
  overrides: Partial<KnowledgePointOut> = {},
): KnowledgePointOut {
  return {
    id: "44444444-4444-4444-8444-444444444444",
    record_id: RECORD_ID,
    batch_id: null,
    name: "进程调度",
    detail: "调度器从就绪队列中选择下一个运行的进程。",
    tags: ["操作系统"],
    importance: 5,
    generated_from_summary_id: null,
    generation_status: "ACTIVE",
    created_at: "2026-08-24T12:00:00.000000Z",
    updated_at: "2026-08-24T12:00:00.000000Z",
    ...overrides,
  };
}

function knowledgePointsResponse(items: KnowledgePointOut[]) {
  return HttpResponse.json({
    items,
    action_required: "NONE",
    active_job_id: null,
    blocked_reason: null,
    input_mode: null,
  });
}

const saveMock = vi.mocked(chooseMarkdownSavePath);
const writeTextFileMock = vi.mocked(writeMarkdownFile);
const openMock = vi.mocked(openExportedFile);

vi.mock("@/services/tauri/learningAssetExport", () => ({
  chooseMarkdownSavePath: vi.fn(),
  writeMarkdownFile: vi.fn(),
  openExportedFile: vi.fn(),
}));
vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.stubGlobal("scrollTo", vi.fn());

beforeEach(() => {
  saveMock.mockReset();
  writeTextFileMock.mockReset();
  openMock.mockReset();
  server.use(
    http.get(DETAIL_URL, ({ request }) => {
      expect(request.headers.get("X-KnowRealm-Token")).toBe(TEST_LAUNCH_TOKEN);
      return HttpResponse.json(record);
    }),
    http.get(SUMMARY_URL, () => summaryResponse(confirmedSummary)),
    http.get(LLM_PROVIDER_URL, () => HttpResponse.json({ provider: null })),
  );
});

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
});

function renderAt(path = ROUTE_PATH) {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

async function openExportMenu() {
  fireEvent.click(await screen.findByRole("button", { name: "导出 Markdown" }));
  return screen.findByRole("menuitem", { name: /导出当前 Tab/ });
}

const SAVED_PATH = "C:\\学习资料\\操作系统第一讲-总结.md";

describe("学习资产 Markdown 导出", () => {
  it("Summary 导出：最新读取后组装快照，经保存对话框写入并显示成功与打开动作", async () => {
    saveMock.mockResolvedValue(SAVED_PATH);
    writeTextFileMock.mockResolvedValue(undefined);
    renderAt();

    const item = await openExportMenu();
    fireEvent.click(item);

    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1));
    expect(saveMock).toHaveBeenCalledWith("操作系统第一讲-总结.md");
    await waitFor(() => expect(writeTextFileMock).toHaveBeenCalledTimes(1));
    expect(writeTextFileMock).toHaveBeenCalledWith(
      SAVED_PATH,
      [
        "# 操作系统第一讲",
        "",
        "## 总结",
        "",
        "**主题**：进程调度",
        "",
        "**摘要**：调度器按照既定策略选择下一个获得处理器的进程。",
        "",
        "### 核心机制",
        "",
        "- 就绪队列决定候选顺序。",
        "",
      ].join("\n"),
    );
    expect(
      await screen.findByText(`已保存：${SAVED_PATH}`),
    ).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "打开文件" }));
    await waitFor(() => expect(openMock).toHaveBeenCalledWith(SAVED_PATH));
  });

  it("每次触发都重新读取当前资产而非依赖缓存", async () => {
    let summaryGets = 0;
    server.use(
      http.get(SUMMARY_URL, () => {
        summaryGets += 1;
        return summaryResponse(confirmedSummary);
      }),
    );
    saveMock.mockResolvedValue(null);
    renderAt();

    const readsAfterMount = async () => {
      await waitFor(() => expect(summaryGets).toBeGreaterThan(0));
      return summaryGets;
    };
    const initial = await readsAfterMount();

    let item = await openExportMenu();
    fireEvent.click(item);
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1));
    const afterFirstExport = summaryGets;
    expect(afterFirstExport).toBeGreaterThan(initial);

    item = await openExportMenu();
    fireEvent.click(item);
    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(2));
    expect(summaryGets).toBeGreaterThan(afterFirstExport);
  });

  it("未确认总结时单项导出禁用并说明原因", async () => {
    server.use(
      http.get(SUMMARY_URL, () =>
        summaryResponse({ ...confirmedSummary, status: "GENERATED" }),
      ),
    );
    renderAt();

    const item = await openExportMenu();
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveTextContent("总结尚未确认，不能导出");
    fireEvent.click(item);
    await waitFor(() => expect(saveMock).not.toHaveBeenCalled());
  });

  it("还没有总结时单项导出禁用并说明原因", async () => {
    server.use(http.get(SUMMARY_URL, () => summaryResponse(null)));
    renderAt();

    const item = await openExportMenu();
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveTextContent("还没有总结");
  });

  it("当前 Tab 不支持导出时禁用并说明原因", async () => {
    server.use(
      http.get(JOBS_URL, () => HttpResponse.json({ jobs: [], progress: 1 })),
      http.get(TRANSCRIPT_URL, () =>
        HttpResponse.json({ status: "NOT_READY", transcript: null }),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=transcript`);

    const item = await openExportMenu();
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveTextContent("当前 Tab 暂不支持导出");
  });

  it("知识点导出仅包含 ACTIVE 项并沿用页面顺序，默认名以知识点结尾", async () => {
    server.use(
      http.get(KNOWLEDGE_POINTS_URL, () =>
        knowledgePointsResponse([
          knowledgePoint({
            id: "a",
            name: "候选不该出现",
            generation_status: "DRAFT",
            batch_id: "33333333-3333-4333-8333-333333333333",
          }),
          knowledgePoint({ id: "b", name: "进程调度", importance: 5 }),
          knowledgePoint({
            id: "c",
            name: "过时批次不该出现",
            generation_status: "SUPERSEDED",
          }),
          knowledgePoint({
            id: "d",
            name: "时间片",
            detail: "时间片轮转防止单一进程垄断处理器。",
            importance: 4,
            tags: [],
          }),
        ]),
      ),
    );
    saveMock.mockResolvedValue("D:\\资料\\操作系统第一讲-知识点.md");
    writeTextFileMock.mockResolvedValue(undefined);
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    const item = await openExportMenu();
    expect(item).not.toHaveAttribute("aria-disabled", "true");
    fireEvent.click(item);

    await waitFor(() => expect(writeTextFileMock).toHaveBeenCalledTimes(1));
    expect(saveMock).toHaveBeenCalledWith("操作系统第一讲-知识点.md");
    const [, markdown] = writeTextFileMock.mock.calls[0];
    expect(markdown).toBe(
      [
        "# 操作系统第一讲",
        "",
        "## 知识点",
        "",
        "### 进程调度",
        "",
        "调度器从就绪队列中选择下一个运行的进程。",
        "",
        "- 重要度：5/5",
        "- 标签：操作系统",
        "",
        "### 时间片",
        "",
        "时间片轮转防止单一进程垄断处理器。",
        "",
        "- 重要度：4/5",
        "",
      ].join("\n"),
    );
  });

  it("没有正式知识点时单项导出禁用并说明原因", async () => {
    server.use(
      http.get(KNOWLEDGE_POINTS_URL, () =>
        knowledgePointsResponse([
          knowledgePoint({ generation_status: "DRAFT" }),
        ]),
      ),
    );
    renderAt(`${ROUTE_PATH}?tab=knowledge-points`);

    const item = await openExportMenu();
    expect(item).toHaveAttribute("aria-disabled", "true");
    expect(item).toHaveTextContent("还没有正式知识点");
  });

  it("取消保存时不写文件、不报错、不显示成功", async () => {
    saveMock.mockResolvedValue(null);
    renderAt();

    const item = await openExportMenu();
    fireEvent.click(item);

    await waitFor(() => expect(saveMock).toHaveBeenCalledTimes(1));
    await waitFor(() =>
      expect(screen.queryByRole("status")).not.toBeInTheDocument(),
    );
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(writeTextFileMock).not.toHaveBeenCalled();
  });

  it("读取失败时显示页内错误且不进入保存流程", async () => {
    let summaryGets = 0;
    server.use(
      http.get(SUMMARY_URL, () => {
        summaryGets += 1;
        // 首次挂载读取成功让菜单可用，之后的每次读取都失败
        return summaryGets === 1
          ? summaryResponse(confirmedSummary)
          : HttpResponse.json({ detail: "数据库暂时繁忙" }, { status: 500 });
      }),
    );
    renderAt();

    const item = await openExportMenu();
    expect(item).not.toHaveAttribute("aria-disabled", "true");
    fireEvent.click(item);

    expect(
      await screen.findByRole("alert", {}, { timeout: 4_000 }),
    ).toHaveTextContent("读取学习资产失败，未导出文件");
    expect(saveMock).not.toHaveBeenCalled();
    expect(writeTextFileMock).not.toHaveBeenCalled();
  });

  it("写入失败时显示页内错误且不出现成功状态", async () => {
    saveMock.mockResolvedValue(SAVED_PATH);
    writeTextFileMock.mockRejectedValue(
      new Error("failed to write file: Access Denied"),
    );
    renderAt();

    const item = await openExportMenu();
    fireEvent.click(item);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "文件写入失败，未保存",
    );
    expect(screen.queryByText(/已保存/)).not.toBeInTheDocument();
  });

  it("保存对话框以异常结束时按写入失败提示，不停留在导出中", async () => {
    saveMock.mockRejectedValue(new Error("dialog plugin error"));
    renderAt();

    const item = await openExportMenu();
    fireEvent.click(item);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "文件写入失败，未保存",
    );
    expect(screen.queryByText("正在导出…")).not.toBeInTheDocument();
    expect(writeTextFileMock).not.toHaveBeenCalled();
  });

  it("打开文件失败单独提示，不推翻文件已保存的事实", async () => {
    saveMock.mockResolvedValue(SAVED_PATH);
    writeTextFileMock.mockResolvedValue(undefined);
    openMock.mockRejectedValue(new Error("no application"));
    renderAt();

    const item = await openExportMenu();
    fireEvent.click(item);

    fireEvent.click(await screen.findByRole("button", { name: "打开文件" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("无法打开文件");
    expect(screen.getByText(`已保存：${SAVED_PATH}`)).toBeInTheDocument();
  });

  it("导出进行中阻止重复触发", async () => {
    let summaryGets = 0;
    server.use(
      http.get(SUMMARY_URL, async () => {
        summaryGets += 1;
        // 挂载读取即时返回让菜单立即可用，导出触发的重新读取延迟进行
        if (summaryGets > 1) await delay(400);
        return summaryResponse(confirmedSummary);
      }),
    );
    saveMock.mockResolvedValue(SAVED_PATH);
    writeTextFileMock.mockResolvedValue(undefined);
    renderAt();

    const item = await openExportMenu();
    expect(item).not.toBeDisabled();
    fireEvent.click(item);

    expect(
      await screen.findByText("正在导出…", {}, { timeout: 3_000 }),
    ).toBeInTheDocument();
    const trigger = screen.getByRole("button", { name: "导出 Markdown" });
    expect(trigger).toBeDisabled();

    await waitFor(() => expect(writeTextFileMock).toHaveBeenCalledTimes(1));
    expect(saveMock).toHaveBeenCalledTimes(1);
  });
});
