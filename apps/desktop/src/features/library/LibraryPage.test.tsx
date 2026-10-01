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

  it("添加资料入口：按钮打开三标签入库对话框", async () => {
    mockLibraryEndpoints();
    server.use(
      http.post(`${TEST_SIDECAR_URL}/api/library/ingest`, () =>
        HttpResponse.json({}, { status: 202 }),
      ),
    );
    renderAt("/library");
    fireEvent.click(await screen.findByRole("button", { name: "添加资料" }));
    expect(await screen.findByLabelText("网页地址")).toBeVisible();
    expect(screen.getByRole("tab", { name: /文件/ })).toBeEnabled();
    expect(screen.getByRole("tab", { name: /文本/ })).toBeEnabled();
  });

  it("失败条目检查器：显示失败原因与手动粘贴降级入口", async () => {
    mockLibraryEndpoints();
    const FAILED_ITEM_ID = "77777777-7777-4777-8777-777777777777";
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/library/items`, () =>
        HttpResponse.json({
          items: [
            itemOut({
              id: FAILED_ITEM_ID,
              source_type: "WEB",
              title: "登录墙文章",
              origin_uri: "https://example.com/paywall",
              local_path: null,
              mime_type: null,
              file_size: null,
              availability: "FAILED",
            }),
          ],
          total: 1,
          backfill: null,
        }),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/library/items/${FAILED_ITEM_ID}`, () =>
        HttpResponse.json({
          ...itemOut({
            id: FAILED_ITEM_ID,
            source_type: "WEB",
            title: "登录墙文章",
            origin_uri: "https://example.com/paywall",
            local_path: null,
            mime_type: null,
            file_size: null,
            availability: "FAILED",
          }),
          derived_records: [],
          segment_count: 0,
          failed_error_code: "WEB_FETCH_EXTRACT_FAILED",
        }),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/library/items/${FAILED_ITEM_ID}/content`,
        () => HttpResponse.json({ content: "", truncated: false }),
      ),
      http.post(`${TEST_SIDECAR_URL}/api/library/ingest`, () =>
        HttpResponse.json({}, { status: 202 }),
      ),
    );
    renderAt("/library");
    fireEvent.click(await screen.findByText("登录墙文章"));
    expect(
      await screen.findByText("正文提取失败，可改用手动粘贴"),
    ).toBeVisible();
    // WEB 失败提供降级手动粘贴（预填原 URL）与重新导入
    fireEvent.click(
      await screen.findByRole("button", { name: "手动粘贴正文" }),
    );
    expect(await screen.findByText(/将手动保存/)).toBeVisible();
    expect(await screen.findByLabelText("正文")).toBeVisible();
  });

  it("失败条目通用错误码显示任务文案而非 HTTP 500 文案", async () => {
    mockLibraryEndpoints();
    const FAILED_GENERIC_ID = "88888888-8888-4888-8888-888888888888";
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/library/items`, () =>
        HttpResponse.json({
          items: [
            itemOut({
              id: FAILED_GENERIC_ID,
              source_type: "WEB",
              title: "内部错误条目",
              origin_uri: "https://example.com/boom",
              availability: "FAILED",
            }),
          ],
          total: 1,
          backfill: null,
        }),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/library/items/${FAILED_GENERIC_ID}`,
        () =>
          HttpResponse.json({
            ...itemOut({
              id: FAILED_GENERIC_ID,
              source_type: "WEB",
              title: "内部错误条目",
              availability: "FAILED",
            }),
            derived_records: [],
            segment_count: 0,
            failed_error_code: "INTERNAL_ERROR",
          }),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/library/items/${FAILED_GENERIC_ID}/content`,
        () => HttpResponse.json({ content: "", truncated: false }),
      ),
    );
    renderAt("/library");
    fireEvent.click(await screen.findByText("内部错误条目"));
    expect(
      await screen.findByText(/处理失败，可重新导入或改用手动粘贴/),
    ).toBeVisible();
    // 不再泄露 HTTP 500 专用文案（含未插值的请求编号）
    expect(screen.queryByText(/服务器内部错误/)).not.toBeInTheDocument();
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

  it("AI 解读：对选中条目创建 LIBRARY_ITEM 会话并跳转对话页", async () => {
    mockLibraryEndpoints();
    const CHAT_SESSION_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc";
    let chatCreated: { url: string; body: unknown } | null = null;
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/chat-sessions`,
        async ({ request }) => {
          chatCreated = { url: request.url, body: await request.json() };
          return HttpResponse.json(
            {
              id: CHAT_SESSION_ID,
              mode: "ASK",
              scope: "LIBRARY_ITEM",
              title: null,
              record_id: null,
              course_id: COURSE_ID,
              library_item_id: ITEM_ID,
              record_deleted: false,
              course_deleted: false,
              library_item_deleted: false,
              created_at: "2026-09-19T08:00:00.000000Z",
              updated_at: "2026-09-19T08:00:00.000000Z",
            },
            { status: 201 },
          );
        },
      ),
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions`, () =>
        HttpResponse.json([]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/${CHAT_SESSION_ID}`, () =>
        HttpResponse.json({}),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/chat-sessions/${CHAT_SESSION_ID}/messages`,
        () => HttpResponse.json([]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/chat-sessions/record-options`, () =>
        HttpResponse.json([]),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/settings/providers/llm`, () =>
        HttpResponse.json({ provider: null }),
      ),
    );
    renderAt("/library");
    fireEvent.click(await screen.findByText("第3讲 傅里叶变换"));
    fireEvent.click(await screen.findByRole("button", { name: "AI 解读" }));
    await waitFor(() =>
      expect(chatCreated).toEqual({
        url: `${TEST_SIDECAR_URL}/api/chat-sessions`,
        body: { mode: "ASK", scope: "LIBRARY_ITEM", library_item_id: ITEM_ID },
      }),
    );
    await waitFor(() =>
      expect(window.location.pathname).toBe(`/chat/${CHAT_SESSION_ID}`),
    );
  });

  it("生命周期：检查器提供归档动作并发出归档请求", async () => {
    mockLibraryEndpoints();
    let archived = false;
    server.use(
      http.post(
        `${TEST_SIDECAR_URL}/api/library/items/${ITEM_ID}/archive`,
        () => {
          archived = true;
          return HttpResponse.json(itemOut({ status: "ARCHIVED" }));
        },
      ),
    );
    renderAt("/library");
    fireEvent.click(await screen.findByText("第3讲 傅里叶变换"));
    // 左侧导航「归档」视图同名：作用域限定在检查器 aside（DOM 序最后一个
    // complementary——前一个是应用壳的工作区导航）
    const inspector =
      screen.getAllByRole("complementary")[
        screen.getAllByRole("complementary").length - 1
      ];
    expect(inspector).toBeDefined();
    fireEvent.click(
      await within(inspector as HTMLElement).findByRole("button", {
        name: "归档",
      }),
    );
    await waitFor(() => expect(archived).toBe(true));
  });

  it("删除确认：展示派生记录且明示不级联，确认后发出软删请求", async () => {
    mockLibraryEndpoints();
    let deleted = false;
    server.use(
      http.delete(`${TEST_SIDECAR_URL}/api/library/items/${ITEM_ID}`, () => {
        deleted = true;
        return HttpResponse.json(
          itemOut({ deleted_at: "2026-09-19T09:00:00.000000Z" }),
        );
      }),
    );
    renderAt("/library");
    fireEvent.click(await screen.findByText("第3讲 傅里叶变换"));
    fireEvent.click(
      await screen.findByRole("button", { name: "删除", hidden: true }),
    );
    // 确认对话框展示派生记录与不级联提示（列表行同名：作用域限定在对话框内）
    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByText(/以下派生记录不会被删除/),
    ).toBeVisible();
    expect(await within(dialog).findByText("傅里叶变换入门")).toBeVisible();
    fireEvent.click(
      await within(dialog).findByRole("button", { name: "移入回收站" }),
    );
    await waitFor(() => expect(deleted).toBe(true));
  });

  it("回收站视图：请求 view=trash、显示提示横幅与恢复/彻底删除动作", async () => {
    mockLibraryEndpoints();
    const TRASH_ITEM_ID = "99999999-9999-4999-8999-999999999999";
    const trashItem = itemOut({
      id: TRASH_ITEM_ID,
      title: "已删条目",
      deleted_at: "2026-09-18T09:00:00.000000Z",
    });
    let restored = false;
    let purged = false;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/library/items`, ({ request }) => {
        itemRequests.push(request.url);
        const params = new URL(request.url).searchParams;
        const list: LibraryItemListOut = {
          items: params.get("view") === "trash" ? [trashItem] : [],
          total: params.get("view") === "trash" ? 1 : 0,
          backfill: null,
        };
        return HttpResponse.json(list);
      }),
      http.get(`${TEST_SIDECAR_URL}/api/library/items/${TRASH_ITEM_ID}`, () =>
        HttpResponse.json({
          ...trashItem,
          derived_records: [],
          segment_count: 0,
        }),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/library/items/${TRASH_ITEM_ID}/content`,
        () => HttpResponse.json({ content: "", truncated: false }),
      ),
      http.post(
        `${TEST_SIDECAR_URL}/api/library/items/${TRASH_ITEM_ID}/restore`,
        () => {
          restored = true;
          return HttpResponse.json(itemOut({}));
        },
      ),
      http.delete(
        `${TEST_SIDECAR_URL}/api/library/items/${TRASH_ITEM_ID}?permanent=true`,
        () => {
          purged = true;
          return new HttpResponse(null, { status: 204 });
        },
      ),
    );
    renderAt("/library?view=trash&domain=sources");
    expect(await screen.findByText("已删条目")).toBeVisible();
    expect(await screen.findByText(/回收站仅收录/)).toBeVisible();
    await waitFor(() =>
      expect(itemRequests.some((url) => url.includes("view=trash"))).toBe(true),
    );
    fireEvent.click(await screen.findByText("已删条目"));
    fireEvent.click(await screen.findByRole("button", { name: "恢复" }));
    await waitFor(() => expect(restored).toBe(true));
    // 回收站中的删除 = 物理删除（确认对话框二次确认）
    fireEvent.click(await screen.findByRole("button", { name: "彻底删除" }));
    const dialog = await screen.findByRole("dialog");
    fireEvent.click(
      await within(dialog).findByRole("button", { name: "彻底删除" }),
    );
    await waitFor(() => expect(purged).toBe(true));
  });

  it("彻底删除前置拦截：有未删派生记录时禁用确认并提供跳转删除路径", async () => {
    mockLibraryEndpoints();
    const BLOCKED_ITEM_ID = "88888888-8888-4888-8888-888888888888";
    const blockedRecordId = "88888888-8888-4888-8888-888888888801";
    let purged = false;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/library/items`, () =>
        HttpResponse.json({
          items: [
            itemOut({
              id: BLOCKED_ITEM_ID,
              title: "带记录的已删条目",
              deleted_at: "2026-09-18T09:00:00.000000Z",
            }),
          ],
          total: 1,
          backfill: null,
        }),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/library/items/${BLOCKED_ITEM_ID}`, () =>
        HttpResponse.json({
          ...itemOut({
            id: BLOCKED_ITEM_ID,
            title: "带记录的已删条目",
            deleted_at: "2026-09-18T09:00:00.000000Z",
          }),
          derived_records: [
            {
              record_id: blockedRecordId,
              title: "派生学习记录甲",
              status: "COMPLETED",
              capture_type: "DOCUMENT_IMPORT",
              role: "PRIMARY",
              sequence_no: 0,
            },
          ],
          segment_count: 3,
        }),
      ),
      http.get(
        `${TEST_SIDECAR_URL}/api/library/items/${BLOCKED_ITEM_ID}/content`,
        () => HttpResponse.json({ content: "", truncated: false }),
      ),
      http.delete(
        `${TEST_SIDECAR_URL}/api/library/items/${BLOCKED_ITEM_ID}?permanent=true`,
        () => {
          purged = true;
          return new HttpResponse(null, { status: 204 });
        },
      ),
    );
    renderAt("/library?view=trash&domain=sources");
    fireEvent.click(await screen.findByText("带记录的已删条目"));
    fireEvent.click(await screen.findByRole("button", { name: "彻底删除" }));

    // 前置拦截：提示可操作路径、确认禁用（不撞 409）、记录行可跳转删除。
    const dialog = await screen.findByRole("dialog");
    expect(
      await within(dialog).findByText(/彻底删除前需先删除以下派生学习记录/),
    ).toBeVisible();
    expect(
      within(dialog).getByRole("button", {
        name: "打开记录《派生学习记录甲》",
      }),
    ).toBeVisible();
    await waitFor(() =>
      expect(
        within(dialog).getByRole("button", { name: "彻底删除" }),
      ).toBeDisabled(),
    );
    expect(purged).toBe(false);

    // 跳转删除路径：点记录行关闭对话框并进入记录详情页。
    fireEvent.click(
      within(dialog).getByRole("button", {
        name: "打开记录《派生学习记录甲》",
      }),
    );
    await waitFor(() =>
      expect(window.location.pathname).toBe(`/records/${blockedRecordId}`),
    );
  });

  it("AI 整理：确定性结果展示与待审提案确认", async () => {
    mockLibraryEndpoints();
    const PROPOSAL_ID = "aaaaaaa1-0000-4000-8000-000000000001";
    let confirmed = false;
    server.use(
      http.post(`${TEST_SIDECAR_URL}/api/library/organize/scan`, () =>
        HttpResponse.json({
          duplicates: [
            {
              content_hash: "dup",
              items: [itemOut({ title: "重复A" }), itemOut({ title: "重复B" })],
            },
          ],
          failed_items: [],
          unclassified: [items[1]],
        }),
      ),
      http.get(`${TEST_SIDECAR_URL}/api/proposals`, ({ request }) => {
        const status = new URL(request.url).searchParams.get("status");
        const pending =
          status === "PENDING"
            ? [
                {
                  id: PROPOSAL_ID,
                  proposal_type: "ORGANIZE",
                  status: "PENDING",
                  session_id: null,
                  message_id: null,
                  target_type: "library_item",
                  target_id: ITEM_UNCLASSIFIED_ID,
                  payload: {
                    item_id: ITEM_UNCLASSIFIED_ID,
                    title: "规范化标题",
                  },
                  evidence_refs: null,
                  error_code: null,
                  created_at: "2026-09-19T08:00:00.000000Z",
                  decided_at: null,
                },
              ]
            : [];
        return HttpResponse.json(pending);
      }),
      http.post(
        `${TEST_SIDECAR_URL}/api/proposals/${PROPOSAL_ID}/confirm`,
        () => {
          confirmed = true;
          return HttpResponse.json({ status: "APPLIED" });
        },
      ),
    );
    renderAt("/library");
    fireEvent.click(await screen.findByRole("button", { name: "AI 整理" }));
    // 确定性检查结果先展示（零 LLM）
    expect(await screen.findByText(/内容重复/)).toBeVisible();
    expect(await screen.findByText("重复A / 重复B")).toBeVisible();
    // 待审提案逐项确认
    fireEvent.click(await screen.findByRole("button", { name: "应用" }));
    await waitFor(() => expect(confirmed).toBe(true));
  });
});
