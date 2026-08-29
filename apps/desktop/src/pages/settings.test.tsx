// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, describe, expect, it, vi } from "vitest";
import App from "@/App";
import { TEST_SIDECAR_URL } from "@/mocks/handlers";
import { server } from "@/mocks/server";
import { setRecordingKeepAwake } from "@/services/tauri/recording";

vi.mock("@/services/tauri/sidecar", () => ({
  getSidecarConfig: vi.fn().mockResolvedValue({
    baseUrl: "http://127.0.0.1:43127",
    token: "test-launch-token",
  }),
}));

vi.mock("@/services/tauri/recording", () => ({
  setRecordingKeepAwake: vi.fn().mockResolvedValue(undefined),
  hideWindowTemporarily: vi.fn().mockResolvedValue(undefined),
}));

vi.stubGlobal("scrollTo", vi.fn());

type ProfileOut = components["schemas"]["ProfileOut"];

function renderAt(path = "/") {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

afterEach(() => {
  cleanup();
  window.history.replaceState(null, "", "/");
  vi.mocked(setRecordingKeepAwake).mockReset().mockResolvedValue(undefined);
});

describe("设置页档案区块", () => {
  it("未建档时表单为空，未选角色不能保存", async () => {
    renderAt("/settings");

    expect(await screen.findByRole("heading", { name: "档案" })).toBeVisible();
    for (const role of ["学生", "程序员", "职场人", "其他"]) {
      expect(screen.getByRole("radio", { name: role })).not.toBeChecked();
    }
    const save = screen.getByRole("button", { name: "保存档案" });
    expect(save).toBeDisabled();

    fireEvent.change(screen.getByLabelText("自我介绍"), {
      target: { value: "先填介绍" },
    });
    expect(save).toBeDisabled();

    fireEvent.click(screen.getByRole("radio", { name: "学生" }));
    await waitFor(() => expect(save).toBeEnabled());
  });

  it("已建档时回显角色与自我介绍，保存提交最新值并给出反馈", async () => {
    const stored: ProfileOut = {
      primary_role: "DEVELOPER",
      about_me: "三年后端，正在补操作系统基础",
    };
    const bodies: object[] = [];
    server.use(
      http.get(`${TEST_SIDECAR_URL}/api/profile`, () =>
        HttpResponse.json(stored),
      ),
      http.put(`${TEST_SIDECAR_URL}/api/profile`, async ({ request }) => {
        bodies.push((await request.json()) as object);
        return HttpResponse.json({
          primary_role: "STUDENT",
          about_me: "正在学 Rust",
        });
      }),
    );

    renderAt("/settings");

    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "程序员" })).toBeChecked(),
    );
    expect(screen.getByLabelText("自我介绍")).toHaveValue(
      "三年后端，正在补操作系统基础",
    );

    fireEvent.click(screen.getByRole("radio", { name: "学生" }));
    fireEvent.change(screen.getByLabelText("自我介绍"), {
      target: { value: "正在学 Rust" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存档案" }));

    expect(await screen.findByRole("status")).toHaveTextContent("档案已保存");
    expect(bodies).toEqual([
      { primary_role: "STUDENT", about_me: "正在学 Rust" },
    ]);
  });

  it("自我介绍限制 200 字并显示字数计数", async () => {
    renderAt("/settings");

    const aboutMe = await screen.findByLabelText("自我介绍");
    expect(aboutMe).toHaveAttribute("maxlength", "200");
    fireEvent.change(aboutMe, { target: { value: "长".repeat(200) } });
    expect(screen.getByText("200/200")).toBeVisible();
  });

  it("保存失败保留表单内容并显示错误", async () => {
    server.use(
      http.put(`${TEST_SIDECAR_URL}/api/profile`, () =>
        HttpResponse.json({ detail: "档案保存失败" }, { status: 500 }),
      ),
    );

    renderAt("/settings");

    fireEvent.click(await screen.findByRole("radio", { name: "其他" }));
    const aboutMe = screen.getByLabelText("自我介绍");
    fireEvent.change(aboutMe, { target: { value: "不会成功的介绍" } });
    fireEvent.click(screen.getByRole("button", { name: "保存档案" }));

    expect(
      await screen.findByRole("alert", undefined, { timeout: 8_000 }),
    ).toHaveTextContent("档案保存失败");
    expect(aboutMe).toHaveValue("不会成功的介绍");
    expect(screen.getByRole("radio", { name: "其他" })).toBeChecked();
  });
});

type PreferencesOut = components["schemas"]["PreferencesOut"];

const PREFERENCES_URL = `${TEST_SIDECAR_URL}/api/settings/preferences`;
const DEFAULT_PREFERENCES: PreferencesOut = {
  theme: "SYSTEM",
  font_scale: "M",
  timezone: null,
  close_behavior: "TRAY",
  autostart: false,
  quiz_last_count: 5,
};

describe("设置页偏好分区", () => {
  afterEach(() => {
    document.documentElement.classList.remove("dark", "light");
    document.documentElement.style.removeProperty("font-size");
  });

  it("渲染外观、桌面行为与通用小节并回显已存偏好", async () => {
    server.use(
      http.get(PREFERENCES_URL, () =>
        HttpResponse.json({
          theme: "DARK",
          font_scale: "L",
          timezone: "Asia/Shanghai",
          close_behavior: "EXIT",
          autostart: true,
          quiz_last_count: 10,
        }),
      ),
    );

    renderAt("/settings");

    expect(await screen.findByRole("heading", { name: "偏好" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "外观" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "桌面行为" })).toBeVisible();
    expect(screen.getByRole("heading", { name: "通用" })).toBeVisible();
    expect(screen.getByRole("radio", { name: "深色" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "大" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "直接退出" })).toBeChecked();
    expect(screen.getByRole("checkbox", { name: "开机自启" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "10" })).toBeChecked();
    expect(screen.getByRole("combobox")).toHaveTextContent("Asia/Shanghai");
  });

  it("控件即改即存：每次只提交被改字段", async () => {
    let current = { ...DEFAULT_PREFERENCES };
    const bodies: object[] = [];
    server.use(
      http.get(PREFERENCES_URL, () => HttpResponse.json(current)),
      http.put(PREFERENCES_URL, async ({ request }) => {
        const body = (await request.json()) as object;
        bodies.push(body);
        current = { ...current, ...body };
        return HttpResponse.json(current);
      }),
    );

    renderAt("/settings");
    await screen.findByRole("heading", { name: "偏好" });

    fireEvent.click(screen.getByRole("radio", { name: "浅色" }));
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "浅色" })).toBeChecked(),
    );
    fireEvent.click(screen.getByRole("radio", { name: "小" }));
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "小" })).toBeChecked(),
    );
    fireEvent.click(screen.getByRole("radio", { name: "3" }));
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "3" })).toBeChecked(),
    );

    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.change(screen.getByLabelText("搜索时区"), {
      target: { value: "Tokyo" },
    });
    fireEvent.click(screen.getByRole("option", { name: "Asia/Tokyo" }));
    await waitFor(() =>
      expect(screen.getByRole("combobox")).toHaveTextContent("Asia/Tokyo"),
    );
    fireEvent.click(screen.getByRole("combobox"));
    fireEvent.click(screen.getByRole("option", { name: "跟随系统" }));
    await waitFor(() =>
      expect(screen.getByRole("combobox")).toHaveTextContent("跟随系统"),
    );

    expect(bodies).toEqual([
      { theme: "LIGHT" },
      { font_scale: "S" },
      { quiz_last_count: 3 },
      { timezone: "Asia/Tokyo" },
      { timezone: null },
    ]);
  }, 15_000);

  it("保存失败行内报错并回显服务端事实", async () => {
    server.use(
      http.get(PREFERENCES_URL, () =>
        HttpResponse.json({ ...DEFAULT_PREFERENCES, theme: "DARK" }),
      ),
      http.put(PREFERENCES_URL, () =>
        HttpResponse.json({ detail: "偏好保存失败" }, { status: 500 }),
      ),
    );

    renderAt("/settings");

    fireEvent.click(await screen.findByRole("radio", { name: "浅色" }));

    expect(
      await screen.findByRole("alert", undefined, { timeout: 8_000 }),
    ).toHaveTextContent("偏好保存失败");
    expect(screen.getByRole("radio", { name: "深色" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "浅色" })).not.toBeChecked();
  });

  it("桌面行为控件即改即存：关窗行为与自启开关只提交被改字段", async () => {
    let current = { ...DEFAULT_PREFERENCES };
    const bodies: object[] = [];
    server.use(
      http.get(PREFERENCES_URL, () => HttpResponse.json(current)),
      http.put(PREFERENCES_URL, async ({ request }) => {
        const body = (await request.json()) as object;
        bodies.push(body);
        current = { ...current, ...body };
        return HttpResponse.json(current);
      }),
    );

    renderAt("/settings");
    await screen.findByRole("heading", { name: "偏好" });

    fireEvent.click(screen.getByRole("radio", { name: "直接退出" }));
    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "直接退出" })).toBeChecked(),
    );
    fireEvent.click(screen.getByRole("checkbox", { name: "开机自启" }));
    await waitFor(() =>
      expect(screen.getByRole("checkbox", { name: "开机自启" })).toBeChecked(),
    );

    expect(bodies).toEqual([{ close_behavior: "EXIT" }, { autostart: true }]);
  }, 15_000);

  it("自启保存失败行内报错并回显服务端事实", async () => {
    server.use(
      http.get(PREFERENCES_URL, () => HttpResponse.json(DEFAULT_PREFERENCES)),
      http.put(PREFERENCES_URL, () =>
        HttpResponse.json({ detail: "偏好保存失败" }, { status: 500 }),
      ),
    );

    renderAt("/settings");

    fireEvent.click(await screen.findByRole("checkbox", { name: "开机自启" }));

    expect(
      await screen.findByRole("alert", undefined, { timeout: 8_000 }),
    ).toHaveTextContent("偏好保存失败");
    expect(
      screen.getByRole("checkbox", { name: "开机自启" }),
    ).not.toBeChecked();
  });

  it("主题与字号偏好应用到根元素并即时切换", async () => {
    server.use(
      http.get(PREFERENCES_URL, () =>
        HttpResponse.json({
          ...DEFAULT_PREFERENCES,
          theme: "DARK",
          font_scale: "L",
        }),
      ),
    );

    renderAt("/settings");

    await screen.findByRole("heading", { name: "偏好" });
    await waitFor(() => expect(document.documentElement).toHaveClass("dark"));
    expect(document.documentElement.style.fontSize).toBe("18px");

    let current: PreferencesOut = {
      ...DEFAULT_PREFERENCES,
      theme: "DARK",
      font_scale: "L",
    };
    server.use(
      http.put(PREFERENCES_URL, async ({ request }) => {
        current = { ...current, ...((await request.json()) as object) };
        return HttpResponse.json(current);
      }),
    );
    fireEvent.click(screen.getByRole("radio", { name: "浅色" }));
    await waitFor(() => expect(document.documentElement).toHaveClass("light"));
    expect(document.documentElement).not.toHaveClass("dark");

    fireEvent.click(screen.getByRole("radio", { name: "跟随系统" }));
    await waitFor(() =>
      expect(document.documentElement).not.toHaveClass("light"),
    );
    expect(document.documentElement).not.toHaveClass("dark");

    // 系统深色时 SYSTEM 同样落到 .dark
    const systemDarkQuery = window.matchMedia("(prefers-color-scheme: dark)");
    Object.defineProperty(systemDarkQuery, "matches", { value: true });
    const matchMediaSpy = vi
      .spyOn(window, "matchMedia")
      .mockReturnValue(systemDarkQuery);
    try {
      fireEvent.click(screen.getByRole("radio", { name: "深色" }));
      await waitFor(() => expect(document.documentElement).toHaveClass("dark"));
      fireEvent.click(screen.getByRole("radio", { name: "跟随系统" }));
      await waitFor(() => expect(document.documentElement).toHaveClass("dark"));
      expect(document.documentElement).not.toHaveClass("light");
    } finally {
      matchMediaSpy.mockRestore();
    }
  }, 15_000);
});
