// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
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
import { useLibraryItemAction } from "@/features/library/api/library";
import { SharedRefsTab } from "@/features/sharedRefs/components/SharedRefsTab";
import "@/i18n";

type CourseDetail = components["schemas"]["CourseDetailOut"];
type SharedRefOut = components["schemas"]["SharedRefOut"];
type LibraryItemOut = components["schemas"]["LibraryItemOut"];

const COURSE_ID = "22222222-2222-4222-8222-222222222222";
const ITEM_PAPER = "11111111-1111-4111-8111-111111111111";
const ITEM_WEB = "33333333-3333-4333-8333-333333333333";

const DETAIL_URL = `${TEST_SIDECAR_URL}/api/courses/${COURSE_ID}`;
const REFS_URL = `${DETAIL_URL}/shared-refs`;
const ITEMS_URL = `${TEST_SIDECAR_URL}/api/library/items`;
const ROUTE_PATH = `/spaces/${COURSE_ID}?tab=shared`;

const schoolCourse: CourseDetail = {
  id: COURSE_ID,
  name: "Agent 工程",
  learning_context: "INTEREST",
  education_stage: null,
  depth: "INTERMEDIATE",
  course_type: null,
  description: null,
  status: "ACTIVE",
  hot_words: [],
  created_at: "2026-08-17T00:00:00.000000Z",
  updated_at: "2026-08-18T00:00:00.000000Z",
};

function refOf(overrides: Partial<SharedRefOut> = {}): SharedRefOut {
  return {
    course_id: COURSE_ID,
    library_item_id: ITEM_PAPER,
    title: "梯度下降论文",
    source_type: "WEB",
    owner_course_id: "99999999-9999-4999-8999-999999999999",
    owner_course_name: "机器学习导论",
    available: true,
    created_at: "2026-09-28T08:00:00.000000Z",
    ...overrides,
  };
}

function itemOf(
  id: string,
  overrides: Partial<LibraryItemOut> = {},
): LibraryItemOut {
  return {
    id,
    course_id: null,
    source_type: "WEB",
    title: `资料-${id.slice(0, 8)}`,
    availability: "EMPTY",
    origin_uri: null,
    local_path: null,
    mime_type: null,
    file_size: null,
    content_hash: `hash-${id}`,
    fetched_at: null,
    source_metadata: {},
    schema_version: 1,
    favorite: false,
    status: "ACTIVE",
    created_at: "2026-09-01T00:00:00.000000Z",
    updated_at: "2026-09-01T00:00:00.000000Z",
    ...overrides,
  };
}

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
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

describe("共享资料 Tab（工单 05）", () => {
  it("渲染引用清单与只读提示，失效行展示来源已删除（tab 入 URL 路由可达）", async () => {
    server.use(
      http.get(REFS_URL, () =>
        HttpResponse.json([
          refOf(),
          refOf({
            library_item_id: ITEM_WEB,
            title: "注意力机制综述",
            available: false,
            owner_course_name: null,
            owner_course_id: null,
          }),
        ]),
      ),
    );

    renderAt(ROUTE_PATH);

    expect(
      await screen.findByRole("heading", { name: "引用的外部资料" }),
    ).toBeVisible();
    // 只读语义常驻提示（检索覆盖 + 资产只读；AlertTitle 渲染为 div 非 heading）。
    expect(screen.getByText("共享资料只读")).toBeVisible();
    expect(screen.getByText("梯度下降论文")).toBeVisible();
    expect(screen.getByText("归属：机器学习导论")).toBeVisible();
    expect(screen.getByText("注意力机制综述")).toBeVisible();
    expect(screen.getByText("来源已删除")).toBeVisible();
  });

  it("空清单展示空态引导", async () => {
    server.use(http.get(REFS_URL, () => HttpResponse.json([])));

    renderAt(ROUTE_PATH);

    expect(await screen.findByText("还没有引用外部资料")).toBeVisible();
  });

  it("添加引用：候选过滤本空间归属与已引用，选择确认后清单刷新", async () => {
    const added: unknown[] = [];
    server.use(
      http.get(REFS_URL, () =>
        HttpResponse.json(added.length > 0 ? [refOf()] : []),
      ),
      http.get(ITEMS_URL, () =>
        HttpResponse.json({
          items: [
            itemOf(ITEM_PAPER, { course_id: null }),
            // 本空间归属：不出现在候选中。
            itemOf("55555555-5555-4555-8555-555555555555", {
              course_id: COURSE_ID,
              title: "本课程的资料",
            }),
          ],
          total: 2,
          backfill: null,
        }),
      ),
      http.post(REFS_URL, async ({ request }) => {
        added.push(await request.json());
        return HttpResponse.json(refOf(), { status: 201 });
      }),
    );

    renderAt(ROUTE_PATH);
    fireEvent.click(await screen.findByRole("button", { name: "添加引用" }));

    const dialog = await screen.findByRole("dialog");
    await waitFor(() =>
      expect(screen.getByText("资料-11111111")).toBeVisible(),
    );
    // 本课程归属的条目被过滤。
    expect(screen.queryByText("资料-55555555")).not.toBeInTheDocument();

    // label 可访问名含来源类型与归属多段文本：点击标题文本（label 包裹整行，
    // 命中即选中该 radio）。
    fireEvent.click(screen.getByText("资料-11111111"));
    await waitFor(() =>
      expect(screen.getByRole("radio", { checked: true })).toBeInTheDocument(),
    );
    fireEvent.click(within(dialog).getByRole("button", { name: "引用" }));

    await waitFor(() => expect(added).toHaveLength(1));
    expect(added[0]).toEqual({ library_item_id: ITEM_PAPER });
    await waitFor(() => expect(screen.getByText("梯度下降论文")).toBeVisible());
  });

  it("移除引用：DELETE 成功后行消失", async () => {
    let removed = false;
    server.use(
      http.get(REFS_URL, () => HttpResponse.json(removed ? [] : [refOf()])),
      http.delete(`${REFS_URL}/${ITEM_PAPER}`, () => {
        removed = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderAt(ROUTE_PATH);
    fireEvent.click(
      await screen.findByRole("button", {
        name: "移除对《梯度下降论文》的引用",
      }),
    );

    await waitFor(() =>
      expect(screen.queryByText("梯度下降论文")).not.toBeInTheDocument(),
    );
  });

  it("首屏条目全属本空间时不误报无候选，搜索可命中列表之外的资料", async () => {
    // 单页 100 条全属本空间、库共 120 条（其余在其他空间）：
    // 无搜索时不得误报「暂无可引用」，须提示仅列出部分并引导搜索。
    const ownItems = Array.from({ length: 100 }, (_, index) =>
      itemOf(`66666666-6666-4666-8666-${String(index).padStart(12, "0")}`, {
        course_id: COURSE_ID,
        title: `本课程资料-${index}`,
      }),
    );
    server.use(
      http.get(REFS_URL, () => HttpResponse.json([])),
      http.get(ITEMS_URL, ({ request }) => {
        const q = new URL(request.url).searchParams.get("q");
        if (q) {
          return HttpResponse.json({
            items: [itemOf(ITEM_PAPER, { title: "梯度下降论文" })],
            total: 1,
            backfill: null,
          });
        }
        return HttpResponse.json({
          items: ownItems,
          total: 120,
          backfill: null,
        });
      }),
    );

    renderAt(ROUTE_PATH);
    fireEvent.click(await screen.findByRole("button", { name: "添加引用" }));

    // 截断场景：提示仅列出部分、引导搜索（而非「暂无可引用」）。
    expect(await screen.findByText(/仅列出最近更新的前 100 条/)).toBeVisible();
    expect(screen.queryByText(/暂无可引用的资料/)).not.toBeInTheDocument();

    // 搜索可命中首屏之外的资料（q 传后端）。
    fireEvent.change(await screen.findByPlaceholderText("搜索资料标题"), {
      target: { value: "梯度下降" },
    });
    fireEvent.click(await screen.findByText("梯度下降论文"));
    await waitFor(() =>
      expect(screen.getByRole("radio", { checked: true })).toBeInTheDocument(),
    );
  });

  it("资料软删后共享引用清单同步失效（available 派生位刷新）", async () => {
    let deleted = false;
    server.use(
      http.get(REFS_URL, () =>
        HttpResponse.json([refOf({ available: !deleted })]),
      ),
      // 软删契约：200 + 条目投影（204 仅物理删除路径，apiFetch 需 JSON 体）。
      http.delete(`${ITEMS_URL}/${ITEM_PAPER}`, () => {
        deleted = true;
        return HttpResponse.json(
          itemOf(ITEM_PAPER, { deleted_at: "2026-10-01T00:00:00.000000Z" }),
        );
      }),
    );

    // 同一 QueryClient 下渲染共享 Tab 与资料生命周期动作（资料库页同款
    // mutation）：软删成功后引用清单须失效重取（staleTime 60s 不会自愈）。
    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });
    function DeleteButton() {
      const action = useLibraryItemAction();
      return (
        <button
          type="button"
          onClick={() =>
            action.mutate({ action: "delete", itemId: ITEM_PAPER })
          }
        >
          软删资料
        </button>
      );
    }
    render(
      <QueryClientProvider client={queryClient}>
        <SharedRefsTab courseId={COURSE_ID} />
        <DeleteButton />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("梯度下降论文")).toBeVisible();
    expect(screen.queryByText("来源已删除")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "软删资料" }));

    await waitFor(() => expect(screen.getByText("来源已删除")).toBeVisible());
  });
});
