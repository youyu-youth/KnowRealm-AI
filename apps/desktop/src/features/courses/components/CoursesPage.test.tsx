// @vitest-environment jsdom

import type { components } from "@knowrealm/api-types";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { useState } from "react";
import { describe, expect, it, vi } from "vitest";
import type { CourseListQuery } from "@/features/courses/api/types";
import { CoursesPage } from "@/features/courses/components/CoursesPage";
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

async function selectLearningContext(optionName: string) {
  const trigger = screen.getByRole("combobox", { name: "学习场景" });
  fireEvent.click(trigger);
  const option = await screen.findByRole("option", { name: optionName });
  fireEvent.pointerDown(option);
  fireEvent.pointerUp(option);
  fireEvent.click(option);
  await waitFor(() => expect(trigger).toHaveTextContent(optionName));
}

describe("首门课程持久化入口", () => {
  function CourseDiscoveryHarness({
    initialFilters = {},
  }: {
    initialFilters?: CourseListQuery;
  }) {
    const [filters, setFilters] = useState(initialFilters);
    return (
      <CoursesPage
        filters={filters}
        onFiltersChange={setFilters}
        onOpenCourse={vi.fn()}
      />
    );
  }

  async function selectEducationStage() {
    const trigger = screen.getByRole("combobox", { name: "教育阶段" });
    fireEvent.click(trigger);
    const option = await screen.findByRole("option", { name: "本科" });
    fireEvent.pointerDown(option);
    fireEvent.pointerUp(option);
    fireEvent.click(option);
    await waitFor(() => expect(trigger).toHaveTextContent("本科"));
  }

  async function selectFilterOption(comboboxName: string, optionName: string) {
    const trigger = screen.getByRole("combobox", { name: comboboxName });
    fireEvent.click(trigger);
    const option = await screen.findByRole("option", { name: optionName });
    fireEvent.pointerDown(option);
    fireEvent.pointerUp(option);
    fireEvent.click(option);
    await waitFor(() => expect(trigger).toHaveTextContent(optionName));
  }

  it("保存失败后保留输入并提供可重试错误", async () => {
    server.use(
      http.post(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json({ detail: "本地服务暂时不可用" }, { status: 500 }),
      ),
    );
    renderWithQuery(<CourseDiscoveryHarness />);

    fireEvent.click(
      await screen.findByRole("button", { name: "新建知识空间" }),
    );
    fireEvent.change(screen.getByRole("textbox", { name: "课程名称" }), {
      target: { value: "操作系统" },
    });
    await selectLearningContext("学业学习");
    await selectEducationStage();
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

  it("携带启动令牌创建课程并立即刷新真实列表", async () => {
    const created: Course = {
      id: "11111111-1111-4111-8111-111111111111",
      name: "操作系统",
      learning_context: "SCHOOL",
      education_stage: "UNDERGRADUATE",
      depth: null,
      course_type: "MAJOR",
      description: null,
      status: "ACTIVE",
      created_at: "2026-08-17T00:00:00.000000Z",
      updated_at: "2026-08-17T00:00:00.000000Z",
    };
    let courses: Course[] = [];
    let receivedToken: string | null = null;
    let postCalls = 0;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, () =>
        HttpResponse.json(courses),
      ),
      http.post(`${TEST_SIDECAR_URL}/api/courses`, ({ request }) => {
        postCalls += 1;
        receivedToken = request.headers.get("X-KnowRealm-Token");
        courses = [created];
        return HttpResponse.json(created, { status: 201 });
      }),
    );
    renderWithQuery(<CourseDiscoveryHarness />);

    fireEvent.click(
      await screen.findByRole("button", { name: "新建知识空间" }),
    );
    fireEvent.change(screen.getByRole("textbox", { name: "课程名称" }), {
      target: { value: "操作系统" },
    });
    await selectLearningContext("学业学习");
    await selectEducationStage();
    const submit = screen.getByRole("button", { name: "创建课程" });
    expect(submit).toBeEnabled();
    fireEvent.click(submit);

    expect(await screen.findByText("操作系统")).toBeInTheDocument();
    expect(receivedToken).toBe(TEST_LAUNCH_TOKEN);
    expect(postCalls).toBe(1);
  });

  it("通过可访问控件组合搜索筛选并一次清除", async () => {
    const operationSystems: Course[] = [
      {
        id: "11111111-1111-4111-8111-111111111111",
        name: "操作系统",
        learning_context: "SCHOOL",
        education_stage: "UNDERGRADUATE",
        depth: null,
        course_type: "MAJOR",
        description: null,
        status: "ACTIVE",
        created_at: "2026-08-17T00:00:00.000000Z",
        updated_at: "2026-08-18T00:00:00.000000Z",
      },
    ];
    const allCourses = [
      ...operationSystems,
      { ...operationSystems[0], id: "second", name: "编译原理" },
    ];
    const requests: URL[] = [];
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, ({ request }) => {
        const url = new URL(request.url);
        requests.push(url);
        return HttpResponse.json(url.search ? operationSystems : allCourses);
      }),
    );
    renderWithQuery(<CourseDiscoveryHarness />);

    expect(await screen.findByText("编译原理")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索课程" }), {
      target: { value: "  操作  " },
    });
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));

    await selectFilterOption("教育阶段筛选", "本科");
    await selectFilterOption("课程类型筛选", "专业课");

    await waitFor(() =>
      expect(
        requests[requests.length - 1]?.searchParams.get("course_type"),
      ).toBe("MAJOR"),
    );
    const latestRequest = requests[requests.length - 1];
    expect(latestRequest?.searchParams.get("q")).toBe("操作");
    expect(latestRequest?.searchParams.get("education_stage")).toBe(
      "UNDERGRADUATE",
    );
    expect(screen.queryByText("编译原理")).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "清除全部条件" }));

    expect(await screen.findByText("编译原理")).toBeInTheDocument();
    expect(screen.getByRole("searchbox", { name: "搜索课程" })).toHaveValue("");
  });

  it("区分无匹配结果，并在查询失败后重试", async () => {
    let calls = 0;
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, ({ request }) => {
        calls += 1;
        if (calls === 1) {
          return HttpResponse.json({ detail: "数据库忙" }, { status: 500 });
        }
        return HttpResponse.json(
          new URL(request.url).search
            ? []
            : [
                {
                  id: "existing",
                  name: "已有课程",
                  learning_context: "INTEREST",
                  education_stage: null,
                  depth: "BEGINNER",
                  course_type: null,
                  description: null,
                  status: "ACTIVE",
                  created_at: "2026-08-17T00:00:00.000000Z",
                  updated_at: "2026-08-18T00:00:00.000000Z",
                },
              ],
        );
      }),
    );
    renderWithQuery(
      <CourseDiscoveryHarness initialFilters={{ q: "不存在" }} />,
    );

    expect(await screen.findByText("课程暂时无法读取")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "重新读取" }));

    expect(await screen.findByText("没有匹配结果")).toBeInTheDocument();
    expect(screen.queryByText("还没有知识空间")).not.toBeInTheDocument();
    expect(calls).toBe(3);
  });

  it("空库即使带有筛选 URL 仍显示真实空态", async () => {
    renderWithQuery(
      <CourseDiscoveryHarness initialFilters={{ q: "不存在" }} />,
    );

    expect(await screen.findByText("还没有知识空间")).toBeInTheDocument();
    expect(screen.queryByText("没有匹配结果")).not.toBeInTheDocument();
  });

  it("真实空态探测失败后仍可通过新搜索恢复", async () => {
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/courses`, ({ request }) => {
        const query = new URL(request.url).searchParams.get("q");
        if (!query) {
          return HttpResponse.json({ detail: "数据库忙" }, { status: 500 });
        }
        return HttpResponse.json(
          query === "操作"
            ? [
                {
                  id: "recovered",
                  name: "操作系统",
                  learning_context: "SCHOOL",
                  education_stage: "UNDERGRADUATE",
                  depth: null,
                  course_type: "MAJOR",
                  description: null,
                  status: "ACTIVE",
                  created_at: "2026-08-17T00:00:00.000000Z",
                  updated_at: "2026-08-18T00:00:00.000000Z",
                },
              ]
            : [],
        );
      }),
    );
    renderWithQuery(
      <CourseDiscoveryHarness initialFilters={{ q: "不存在" }} />,
    );

    expect(await screen.findByText("课程暂时无法读取")).toBeInTheDocument();
    fireEvent.change(screen.getByRole("searchbox", { name: "搜索课程" }), {
      target: { value: "操作" },
    });
    fireEvent.click(screen.getByRole("button", { name: "搜索" }));

    expect(await screen.findByText("操作系统")).toBeInTheDocument();
    expect(screen.queryByText("课程暂时无法读取")).not.toBeInTheDocument();
  });
});

describe("建课按角色预选学习场景", () => {
  function CourseDiscoveryHarness() {
    return (
      <CoursesPage
        filters={{}}
        onFiltersChange={vi.fn()}
        onOpenCourse={vi.fn()}
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

  async function openDialog() {
    fireEvent.click(
      await screen.findByRole("button", { name: "新建知识空间" }),
    );
    return screen.findByRole("combobox", { name: "学习场景" });
  }

  it("学生档案预选学业学习", async () => {
    mockProfileRole("STUDENT");
    renderWithQuery(<CourseDiscoveryHarness />);

    const trigger = await openDialog();
    await waitFor(() => expect(trigger).toHaveTextContent("学业学习"));
  });

  it("程序员与职场人档案预选职业技能", async () => {
    mockProfileRole("OFFICE_WORKER");
    renderWithQuery(<CourseDiscoveryHarness />);

    const trigger = await openDialog();
    await waitFor(() => expect(trigger).toHaveTextContent("职业技能"));
  });

  it("无档案或其他角色不预选，未选场景不能提交", async () => {
    renderWithQuery(<CourseDiscoveryHarness />);

    const trigger = await openDialog();
    await waitFor(() => expect(trigger).toHaveTextContent("选择学习场景"));
    fireEvent.change(screen.getByRole("textbox", { name: "课程名称" }), {
      target: { value: "操作系统" },
    });
    expect(screen.getByRole("button", { name: "创建课程" })).toBeDisabled();

    await selectLearningContext("兴趣自学");
    // 兴趣场景还需学习深度。
    expect(screen.getByRole("button", { name: "创建课程" })).toBeDisabled();
    const depth = screen.getByRole("combobox", { name: "学习深度" });
    fireEvent.click(depth);
    fireEvent.click(await screen.findByRole("option", { name: "入门" }));
    await waitFor(() => expect(depth).toHaveTextContent("入门"));
    expect(screen.getByRole("button", { name: "创建课程" })).toBeEnabled();
  });

  it("其他角色同样不预选", async () => {
    mockProfileRole("OTHER");
    renderWithQuery(<CourseDiscoveryHarness />);

    const trigger = await openDialog();
    await waitFor(() => expect(trigger).toHaveTextContent("选择学习场景"));
  });
});
