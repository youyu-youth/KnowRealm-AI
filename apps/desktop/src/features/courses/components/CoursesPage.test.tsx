// @vitest-environment jsdom

import type { components } from "@knowrealm/api-types";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import type { ReactNode } from "react";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import { CoursesPage } from "@/features/courses/components/CoursesPage";
import type { SpacesSearch } from "@/features/courses/spacesSearch";
import { TEST_LAUNCH_TOKEN, TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { renderWithQuery } from "@/test/test-utils";

type Course = components["schemas"]["CourseOut"];

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

// 组件级测试没有 RouterProvider：仅把 Link 降级为普通锚点，其余 router 导出保持原样。
vi.mock("@tanstack/react-router", async (importOriginal) => {
  const actual = await importOriginal<Record<string, unknown>>();
  return {
    ...actual,
    Link: ({ to, children }: { to?: unknown; children?: ReactNode }) => (
      <a href={typeof to === "string" ? to : "#"}>{children}</a>
    ),
  };
});

const coursesUrl = `${TEST_SIDECAR_URL}/api/courses`;

function makeCourse(
  overrides: Partial<Course> & Pick<Course, "id" | "name">,
): Course {
  return {
    learning_context: "SCHOOL",
    education_stage: "UNDERGRADUATE",
    depth: null,
    course_type: "MAJOR",
    description: null,
    status: "ACTIVE",
    created_at: "2026-08-17T00:00:00.000000Z",
    updated_at: "2026-08-18T00:00:00.000000Z",
    ...overrides,
  };
}

async function selectLearningContext(name: string) {
  fireEvent.click(await screen.findByRole("radio", { name: new RegExp(name) }));
}

async function selectComboboxOption(comboboxName: string, optionName: string) {
  const trigger = screen.getByRole("combobox", { name: comboboxName });
  fireEvent.click(trigger);
  const option = await screen.findByRole("option", { name: optionName });
  fireEvent.pointerDown(option);
  fireEvent.pointerUp(option);
  fireEvent.click(option);
  await waitFor(() => expect(trigger).toHaveTextContent(optionName));
}

describe("知识空间页面", () => {
  function CourseDiscoveryHarness({
    initialSearch = {},
  }: {
    initialSearch?: SpacesSearch;
  }) {
    const [search, setSearch] = useState<SpacesSearch>(initialSearch);
    return (
      <CoursesPage
        search={search}
        onSearchChange={setSearch}
        onOpenCourse={vi.fn()}
        onEditCourse={vi.fn()}
      />
    );
  }

  it("保存失败后保留输入并提供可重试错误", async () => {
    server.use(
      http.post(coursesUrl, () =>
        HttpResponse.json({ detail: "本地服务暂时不可用" }, { status: 500 }),
      ),
    );
    renderWithQuery(<CourseDiscoveryHarness />);

    fireEvent.click(await screen.findByRole("button", { name: "新建课程" }));
    fireEvent.change(screen.getByRole("textbox", { name: "课程名称" }), {
      target: { value: "操作系统" },
    });
    await selectLearningContext("学业学习");
    await selectComboboxOption("教育阶段", "本科");
    const submit = screen.getByRole("button", { name: "创建课程" });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    expect(await screen.findByRole("alert")).toHaveTextContent(
      "本地服务暂时不可用",
    );
    expect(screen.getByRole("textbox", { name: "课程名称" })).toHaveValue(
      "操作系统",
    );
  });

  it("英文界面下带码错误显示英文译文（工单 04 端到端）", async () => {
    const { applyLanguage } = await import("@/i18n");
    await applyLanguage("en");
    server.use(
      http.post(coursesUrl, () =>
        HttpResponse.json(
          {
            detail: "学业场景必须选择教育阶段",
            code: "COURSE_EDUCATION_STAGE_REQUIRED",
          },
          { status: 422 },
        ),
      ),
    );
    renderWithQuery(<CourseDiscoveryHarness />);

    fireEvent.click(await screen.findByRole("button", { name: "New Course" }));
    fireEvent.change(screen.getByRole("textbox", { name: "Course name" }), {
      target: { value: "Operating Systems" },
    });
    await selectLearningContext("School");
    await selectComboboxOption("Education stage", "Undergraduate");
    fireEvent.click(screen.getByRole("button", { name: "Create course" }));

    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent(
      "A school context requires an education stage.",
    );
    expect(alert).not.toHaveTextContent("学业场景必须选择教育阶段");
  });

  it("携带启动令牌创建课程并立即刷新真实列表", async () => {
    const created = makeCourse({ id: "course-1", name: "操作系统" });
    let courses: Course[] = [];
    let receivedToken: string | null = null;
    let postCalls = 0;
    server.use(
      http.get(coursesUrl, () => HttpResponse.json(courses)),
      http.post(coursesUrl, ({ request }) => {
        postCalls += 1;
        receivedToken = request.headers.get("X-KnowRealm-Token");
        courses = [created];
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    renderWithQuery(<CourseDiscoveryHarness />);

    fireEvent.click(await screen.findByRole("button", { name: "新建课程" }));
    fireEvent.change(screen.getByRole("textbox", { name: "课程名称" }), {
      target: { value: "操作系统" },
    });
    await selectLearningContext("学业学习");
    await selectComboboxOption("教育阶段", "本科");
    const submit = screen.getByRole("button", { name: "创建课程" });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    expect(
      await screen.findByRole("button", { name: "打开课程 操作系统" }),
    ).toBeInTheDocument();
    expect(receivedToken).toBe(TEST_LAUNCH_TOKEN);
    expect(postCalls).toBe(1);
  });

  it("搜索、场景与状态筛选在客户端生效并一次清除", async () => {
    const courses = [
      makeCourse({ id: "c1", name: "操作系统" }),
      makeCourse({ id: "c2", name: "编译原理" }),
      makeCourse({
        id: "c3",
        name: "设计思维",
        learning_context: "INTEREST",
        education_stage: null,
        depth: "BEGINNER",
        course_type: null,
      }),
    ];
    let getCalls = 0;
    server.use(
      http.get(coursesUrl, () => {
        getCalls += 1;
        return HttpResponse.json(courses);
      }),
    );
    renderWithQuery(<CourseDiscoveryHarness />);

    expect(
      await screen.findByRole("button", { name: "打开课程 编译原理" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "打开课程 设计思维" }),
    ).toBeInTheDocument();

    fireEvent.change(screen.getByRole("searchbox", { name: "搜索课程" }), {
      target: { value: "操作" },
    });
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "打开课程 设计思维" }),
      ).not.toBeInTheDocument(),
    );

    fireEvent.click(screen.getByRole("tab", { name: "兴趣自学" }));
    await waitFor(() =>
      expect(
        screen.queryByRole("button", { name: "打开课程 操作系统" }),
      ).not.toBeInTheDocument(),
    );

    fireEvent.click(screen.getAllByRole("button", { name: "清除全部条件" })[0]);
    expect(
      await screen.findByRole("button", { name: "打开课程 编译原理" }),
    ).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "搜索课程" })).toHaveValue("");
    // 全部筛选都在客户端发生：一次加载，不因输入反复请求后端。
    expect(getCalls).toBe(1);
  });

  it("区分无匹配结果，并在查询失败后重试", async () => {
    let calls = 0;
    server.use(
      http.get(coursesUrl, () => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json({ detail: "数据库忙" }, { status: 500 });
        }
        return HttpResponse.json([
          makeCourse({
            id: "existing",
            name: "已有课程",
            learning_context: "INTEREST",
            education_stage: null,
            depth: "BEGINNER",
            course_type: null,
          }),
        ]);
      }),
    );
    renderWithQuery(<CourseDiscoveryHarness initialSearch={{ q: "不存在" }} />);

    expect(await screen.findByText("课程暂时无法读取")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));

    expect(await screen.findByText("没有匹配结果")).toBeInTheDocument();
    expect(screen.queryByText("还没有知识空间")).not.toBeInTheDocument();
    expect(calls).toBe(2);
  });

  it("空库即使带有筛选 URL 仍显示真实空态", async () => {
    renderWithQuery(<CourseDiscoveryHarness initialSearch={{ q: "不存在" }} />);

    expect(await screen.findByText("还没有知识空间")).toBeInTheDocument();
    expect(screen.queryByText("没有匹配结果")).not.toBeInTheDocument();
  });

  it("网格与列表视图可切换", async () => {
    server.use(
      http.get(coursesUrl, () =>
        HttpResponse.json([makeCourse({ id: "c1", name: "操作系统" })]),
      ),
    );
    renderWithQuery(<CourseDiscoveryHarness />);

    const openButton = await screen.findByRole("button", {
      name: "打开课程 操作系统",
    });
    expect(screen.getByRole("article")).toBeInTheDocument();
    expect(openButton).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "列表视图" }));

    expect(screen.getByRole("button", { name: "列表视图" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
    expect(screen.queryByRole("article")).not.toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "打开课程 操作系统" }),
    ).toBeInTheDocument();
  });

  it("卡片编辑按钮跳转编辑回调", async () => {
    const onEditCourse = vi.fn();
    server.use(
      http.get(coursesUrl, () =>
        HttpResponse.json([makeCourse({ id: "c1", name: "操作系统" })]),
      ),
    );
    function Harness() {
      const [search, setSearch] = useState<SpacesSearch>({});
      return (
        <CoursesPage
          search={search}
          onSearchChange={setSearch}
          onOpenCourse={vi.fn()}
          onEditCourse={onEditCourse}
        />
      );
    }
    renderWithQuery(<Harness />);

    fireEvent.click(await screen.findByRole("button", { name: "编辑" }));
    expect(onEditCourse).toHaveBeenCalledWith("c1");
  });

  it("轨道按场景分组，场景建课预选且关闭后不污染全局建课", async () => {
    server.use(
      http.get(coursesUrl, () =>
        HttpResponse.json([
          makeCourse({ id: "school", name: "操作系统" }),
          makeCourse({
            id: "career",
            name: "工程实践",
            learning_context: "CAREER",
            education_stage: null,
            depth: "ADVANCED",
          }),
        ]),
      ),
    );
    renderWithQuery(<CourseDiscoveryHarness />);
    expect(
      await screen.findByRole("region", { name: "职业技能" }),
    ).toHaveTextContent("工程实践");
    expect(screen.getByRole("region", { name: "学业学习" })).toHaveTextContent(
      "操作系统",
    );
    fireEvent.click(
      screen.getByRole("button", { name: "在职业技能中新建课程" }),
    );
    expect(
      await screen.findByRole("radio", { name: /职业技能/ }),
    ).toHaveAttribute("aria-checked", "true");
    fireEvent.click(screen.getByRole("button", { name: "取消" }));
    await waitFor(() =>
      expect(screen.queryByRole("dialog")).not.toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: "新建课程" }));
    expect(
      await screen.findByRole("radio", { name: /职业技能/ }),
    ).toHaveAttribute("aria-checked", "false");
  });

  it("卡片、列表与轨道切换保留筛选并保留洞察展示入口", async () => {
    server.use(
      http.get(coursesUrl, () =>
        HttpResponse.json([makeCourse({ id: "c1", name: "操作系统" })]),
      ),
    );
    renderWithQuery(
      <CourseDiscoveryHarness initialSearch={{ q: "操作", view: "grid" }} />,
    );
    await screen.findByRole("button", { name: "打开课程 操作系统" });
    fireEvent.click(screen.getByRole("button", { name: "列表视图" }));
    fireEvent.click(screen.getByRole("button", { name: "轨道" }));
    expect(screen.getByRole("searchbox", { name: "搜索课程" })).toHaveValue(
      "操作",
    );
    expect(screen.getByRole("region", { name: "学业学习" })).toHaveTextContent(
      "操作系统",
    );
    fireEvent.click(screen.getByRole("button", { name: "知识空间洞察" }));
    expect(await screen.findByText("最近活跃课程")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "前往收件箱" })).toHaveAttribute(
      "href",
      "/inbox",
    );
  });

  it("轨道翻页区分鼠标、键盘和减弱动效偏好", async () => {
    server.use(
      http.get(coursesUrl, () =>
        HttpResponse.json([
          makeCourse({ id: "c1", name: "操作系统" }),
          makeCourse({ id: "c2", name: "编译原理" }),
        ]),
      ),
    );
    renderWithQuery(<CourseDiscoveryHarness />);
    const rail = await screen.findByRole("region", {
      name: "浏览学业学习课程",
    });
    const scrollBy = vi.fn();
    Object.defineProperties(rail, {
      clientWidth: { value: 300 },
      scrollWidth: { value: 600 },
      scrollBy: { value: scrollBy },
    });
    fireEvent.scroll(rail);
    const next = screen.getByRole("button", { name: "下一组学业学习课程" });
    fireEvent.click(next, { detail: 1 });
    expect(scrollBy).toHaveBeenLastCalledWith({
      left: 300,
      behavior: "smooth",
    });
    fireEvent.click(next, { detail: 0 });
    expect(scrollBy).toHaveBeenLastCalledWith({
      left: 300,
      behavior: "instant",
    });
    const originalMatchMedia = window.matchMedia;
    const media = vi
      .spyOn(window, "matchMedia")
      .mockImplementation((query) => ({
        ...originalMatchMedia(query),
        matches: true,
      }));
    try {
      fireEvent.click(next, { detail: 1 });
      expect(scrollBy).toHaveBeenLastCalledWith({
        left: 300,
        behavior: "instant",
      });
    } finally {
      media.mockRestore();
    }
  });

  it("从卡片菜单删除课程后刷新列表", async () => {
    let courses = [makeCourse({ id: "c1", name: "操作系统" })];
    const deleted: string[] = [];
    server.use(
      http.get(coursesUrl, () => HttpResponse.json(courses)),
      http.delete(`${coursesUrl}/:courseId`, ({ params }) => {
        deleted.push(String(params.courseId));
        courses = [];
        return new HttpResponse(null, { status: 204 });
      }),
    );
    renderWithQuery(<CourseDiscoveryHarness />);

    fireEvent.click(
      await screen.findByRole("button", { name: "更多操作：操作系统" }),
    );
    fireEvent.click(await screen.findByRole("menuitem", { name: "删除课程" }));
    fireEvent.click(await screen.findByRole("button", { name: "确认删除" }));

    await waitFor(() => expect(deleted).toEqual(["c1"]));
    expect(await screen.findByText("还没有知识空间")).toBeInTheDocument();
  });
});

describe("建课按角色预选学习场景", () => {
  function CourseDiscoveryHarness() {
    return (
      <CoursesPage
        search={{}}
        onSearchChange={vi.fn()}
        onOpenCourse={vi.fn()}
        onEditCourse={vi.fn()}
      />
    );
  }

  function mockProfileRole(role: string | null) {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/profile`, () =>
        HttpResponse.json({
          nickname: null,
          primary_role: role,
          about_me: null,
        }),
      ),
    );
  }

  async function openSheet() {
    fireEvent.click(await screen.findByRole("button", { name: "新建课程" }));
    return screen.findByRole("radio", { name: /学业学习/ });
  }

  it("学生档案预选学业学习", async () => {
    mockProfileRole("STUDENT");
    renderWithQuery(<CourseDiscoveryHarness />);

    const radio = await openSheet();
    await waitFor(() => expect(radio).toHaveAttribute("aria-checked", "true"));
  });

  it("程序员与职场人档案预选职业技能", async () => {
    mockProfileRole("OFFICE_WORKER");
    renderWithQuery(<CourseDiscoveryHarness />);

    fireEvent.click(await screen.findByRole("button", { name: "新建课程" }));
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: /职业技能/ })).toHaveAttribute(
        "aria-checked",
        "true",
      ),
    );
  });

  it("无档案或其他角色不预选，未选场景不能提交", async () => {
    renderWithQuery(<CourseDiscoveryHarness />);

    fireEvent.click(await screen.findByRole("button", { name: "新建课程" }));
    const school = await screen.findByRole("radio", { name: /学业学习/ });
    await waitFor(() =>
      expect(school).toHaveAttribute("aria-checked", "false"),
    );
    fireEvent.change(screen.getByRole("textbox", { name: "课程名称" }), {
      target: { value: "操作系统" },
    });
    expect(screen.getByRole("button", { name: "创建课程" })).toBeDisabled();

    await selectLearningContext("兴趣自学");
    // 兴趣场景还需学习深度。
    expect(screen.getByRole("button", { name: "创建课程" })).toBeDisabled();
    await selectComboboxOption("学习深度", "入门");
    expect(screen.getByRole("button", { name: "创建课程" })).toBeEnabled();
  });

  it("其他角色同样不预选", async () => {
    mockProfileRole("OTHER");
    renderWithQuery(<CourseDiscoveryHarness />);

    const school = await openSheet();
    await waitFor(() =>
      expect(school).toHaveAttribute("aria-checked", "false"),
    );
  });
});
