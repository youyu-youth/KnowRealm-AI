// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import type {
  LibraryItemListOut,
  LibraryItemOut,
  LibraryRecordOut,
} from "@/features/library/api/library";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.stubGlobal("scrollTo", vi.fn());

const COURSE_ID = "11111111-1111-4111-8111-111111111111";
const ITEM_ID = "33333333-3333-4333-8333-333333333333";
const ITEM_UNCLASSIFIED_ID = "55555555-5555-4555-8555-555555555555";
const RECORD_ID = "22222222-2222-4222-8222-222222222222";

function itemOut(overrides: Partial<LibraryItemOut>): LibraryItemOut {
  return {
    id: ITEM_ID,
    course_id: COURSE_ID,
    course_name: "高等数学",
    source_type: "AUDIO",
    title: "第3讲 傅里叶变换",
    origin_uri: null,
    local_path: "files/x/x.ogg",
    mime_type: "audio/ogg",
    file_size: 2048,
    content_hash: "hash",
    fetched_at: null,
    source_metadata: { kind: "RECORDING" },
    schema_version: 1,
    favorite: false,
    status: "ACTIVE",
    created_at: "2026-09-01T08:00:00.000000Z",
    updated_at: "2026-09-02T08:00:00.000000Z",
    availability: "RETRIEVABLE",
    ...overrides,
  };
}

const items: LibraryItemOut[] = [
  itemOut({}),
  itemOut({
    id: ITEM_UNCLASSIFIED_ID,
    course_id: null,
    course_name: null,
    source_type: "TEXT",
    title: "未归类速记",
    local_path: null,
    mime_type: "text/plain",
    file_size: 32,
  }),
];

const records: LibraryRecordOut[] = [
  {
    id: RECORD_ID,
    course_id: COURSE_ID,
    course_name: "高等数学",
    capture_type: "RECORDING",
    title: "傅里叶变换入门",
    status: "COMPLETED",
    duration_ms: 60000,
    linked_item_count: 1,
    library_item_ids: [ITEM_ID],
    created_at: "2026-09-01T08:00:00.000000Z",
    updated_at: "2026-09-03T08:00:00.000000Z",
  },
];

const itemRequests: string[] = [];
let favoritePatch: { id: string; body: unknown } | null = null;

function mockLibraryEndpoints(options?: {
  backfill?: { status: string; progress: number };
}) {
  itemRequests.length = 0;
  favoritePatch = null;
  server.use(
    http.get(`${TEST_SIDECAR_URL}/api/library/items`, ({ request }) => {
      itemRequests.push(request.url);
      const params = new URL(request.url).searchParams;
      let filtered = items;
      if (params.get("view") === "needsReview") {
        filtered = filtered.filter((item) => item.course_id === null);
      } else if (params.get("view") === "favorites") {
        filtered = filtered.filter((item) => item.favorite);
      }
      const list: LibraryItemListOut = {
        items: filtered,
        total: filtered.length,
        backfill: options?.backfill ?? null,
      };
      return HttpResponse.json(list);
    }),
    http.get(`${TEST_SIDECAR_URL}/api/library/records`, () =>
      HttpResponse.json(records),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/library/assets`, () =>
      HttpResponse.json([]),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/courses`, () => HttpResponse.json([])),
    http.get(`${TEST_SIDECAR_URL}/api/library/items/${ITEM_ID}`, () =>
      HttpResponse.json({
        ...items[0],
        derived_records: [
          {
            record_id: RECORD_ID,
            title: "傅里叶变换入门",
            status: "COMPLETED",
            capture_type: "RECORDING",
            role: "PRIMARY",
            sequence_no: 0,
          },
        ],
        segment_count: 12,
      }),
    ),
    http.get(`${TEST_SIDECAR_URL}/api/library/items/${ITEM_ID}/content`, () =>
      HttpResponse.json({
        content: "傅里叶变换把时域信号分解为频率分量。",
        truncated: false,
      }),
    ),
    http.patch(
      `${TEST_SIDECAR_URL}/api/library/items/${ITEM_ID}`,
      async ({ request }) => {
        favoritePatch = { id: ITEM_ID, body: await request.json() };
        return HttpResponse.json(itemOut({ favorite: true }));
      },
    ),
  );
}

function renderAt(path: string) {
  // jsdom resizeTo 不改 innerWidth：直接桩成宽屏，走常驻检查器路径（不开 Dialog）
  Object.defineProperty(window, "innerWidth", {
    value: 1440,
    configurable: true,
  });
  window.history.replaceState(null, "", path);
  return render(<App />);
}

afterEach(() => {
  cleanup();
  Object.defineProperty(window, "innerWidth", {
    value: 1024,
    configurable: true,
  });
  vi.clearAllMocks();
});

describe("LibraryPage 工作台", () => {
  it("默认可浏览：无关键词即列出资料条目（列表内搜索是可选导航）", async () => {
    mockLibraryEndpoints();
    renderAt("/library");
    expect(await screen.findByText("第3讲 傅里叶变换")).toBeVisible();
    expect(await screen.findByText("未归类速记")).toBeVisible();
    // 全部域默认混入学习记录
    expect(await screen.findByText("傅里叶变换入门")).toBeVisible();
  });

  it("URL 状态恢复：domain=records&view=favorites 直接进入对应视图", async () => {
    mockLibraryEndpoints();
    renderAt("/library?domain=records");
    const recordsTab = await screen.findByRole("tab", { name: "学习记录" });
    await waitFor(() => expect(recordsTab).toHaveAttribute("data-active"));
    expect(await screen.findByText("傅里叶变换入门")).toBeVisible();
    expect(screen.queryByText("第3讲 傅里叶变换")).not.toBeInTheDocument();
  });

  it("待整理视图只显示未归类条目", async () => {
    mockLibraryEndpoints();
    renderAt("/library?domain=sources&view=needsReview");
    expect(await screen.findByText("未归类速记")).toBeVisible();
    await waitFor(() =>
      expect(screen.queryByText("第3讲 傅里叶变换")).not.toBeInTheDocument(),
    );
    expect(itemRequests.some((url) => url.includes("view=needsReview"))).toBe(
      true,
    );
  });

  it("检查器动态展示：条目选中显示来源元数据/派生记录/预览，记录选中显示来源资料", async () => {
    mockLibraryEndpoints();
    renderAt("/library");
    fireEvent.click(await screen.findByText("第3讲 傅里叶变换"));
    expect(await screen.findByText("来源信息")).toBeVisible();
    expect(await screen.findByText("派生记录")).toBeVisible();
    // 全部域的记录行与检查器派生记录同名：断言检查器内存在即可
    expect(
      (await screen.findAllByText("傅里叶变换入门")).length,
    ).toBeGreaterThanOrEqual(2);
    expect(
      await screen.findByText("傅里叶变换把时域信号分解为频率分量。"),
    ).toBeVisible();
    expect(await screen.findByText("files/x/x.ogg")).toBeVisible();

    // 切到学习记录并选中：检查器显示来源资料回链
    fireEvent.click(screen.getByRole("tab", { name: "学习记录" }));
    // 检查器（aside）中的派生记录同名：取不在 aside 内的列表行
    const listRowText = (await screen.findAllByText("傅里叶变换入门")).find(
      (node) => node.closest("aside") === null,
    );
    expect(listRowText).toBeDefined();
    const recordRow = (listRowText as HTMLElement).closest("li") as HTMLElement;
    fireEvent.click(within(recordRow).getByRole("button"));
    const inspector = await screen.findByText("来源资料");
    expect(inspector).toBeVisible();
    expect(
      await within(inspector.closest("section") as HTMLElement).findByText(
        "第3讲 傅里叶变换",
      ),
    ).toBeVisible();
  });

  it("收藏切换发出 PATCH 并回写列表", async () => {
    mockLibraryEndpoints();
    renderAt("/library");
    // 左侧导航「收藏」智能视图同名：作用域限定在条目行内找收藏按钮
    const row = (await screen.findByText("第3讲 傅里叶变换")).closest(
      "li",
    ) as HTMLElement;
    fireEvent.click(within(row).getByRole("button", { name: "收藏" }));
    await waitFor(() =>
      expect(favoritePatch).toEqual({ id: ITEM_ID, body: { favorite: true } }),
    );
  });

  it("回填进行中显示进度横幅", async () => {
    mockLibraryEndpoints({
      backfill: { status: "RUNNING", progress: 0.42 },
    });
    renderAt("/library");
    expect(await screen.findByText("正在回填历史资料… 42%")).toBeVisible();
  });
});
