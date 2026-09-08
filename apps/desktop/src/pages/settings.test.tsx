// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import type { components } from "@knowrealm/api-types";
import {
  act,
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
import i18n from "@/i18n";
import { LANGUAGE_STORAGE_KEY } from "@/i18n/language";
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

vi.mock("@/services/tauri/preferences", async (importOriginal) => {
  const actual =
    await importOriginal<typeof import("@/services/tauri/preferences")>();
  return {
    ...actual,
    rebindQuickNoteShortcut: vi.fn(actual.rebindQuickNoteShortcut),
  };
});

vi.stubGlobal("scrollTo", vi.fn());

type ProfileOut = components["schemas"]["ProfileOut"];

const AVATAR_URL = `${TEST_SIDECAR_URL}/api/profile/avatar`;
const PNG_BYTES = new Uint8Array([
  0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 1, 2, 3,
]);

function renderAt(path = "/") {
  window.history.replaceState(null, "", path);
  return render(<App />);
}

/** 设置页主区（排除侧边栏同名元素）。 */
function mainArea() {
  return within(screen.getByRole("main"));
}

/** 档案表单里隐藏的选图 input（display:none，无法走可访问查询）。 */
function avatarFileInput(): HTMLInputElement {
  const input = screen.getByRole("main").querySelector("input[type=file]");
  if (!(input instanceof HTMLInputElement)) {
    throw new Error("未找到选图 input");
  }
  return input;
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

  it("已建档时回显昵称、角色与自我介绍，保存提交最新值并给出反馈", async () => {
    const stored: ProfileOut = {
      nickname: "阿邹",
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
          nickname: "邹同学",
          primary_role: "STUDENT",
          about_me: "正在学 Rust",
        });
      }),
    );

    renderAt("/settings");

    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "程序员" })).toBeChecked(),
    );
    expect(screen.getByLabelText("昵称")).toHaveValue("阿邹");
    expect(screen.getByLabelText("自我介绍")).toHaveValue(
      "三年后端，正在补操作系统基础",
    );

    fireEvent.change(screen.getByLabelText("昵称"), {
      target: { value: "邹同学" },
    });
    fireEvent.click(screen.getByRole("radio", { name: "学生" }));
    fireEvent.change(screen.getByLabelText("自我介绍"), {
      target: { value: "正在学 Rust" },
    });
    fireEvent.click(screen.getByRole("button", { name: "保存档案" }));

    expect(await screen.findByText("档案已保存")).toBeInTheDocument();
    expect(bodies).toEqual([
      {
        nickname: "邹同学",
        primary_role: "STUDENT",
        about_me: "正在学 Rust",
      },
    ]);
  });

  it("昵称限制 20 字", async () => {
    renderAt("/settings");

    const nickname = await screen.findByLabelText("昵称");
    expect(nickname).toHaveAttribute("maxlength", "20");
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

  it("选择图片后上传头像并回显", async () => {
    const uploaded: Uint8Array[] = [];
    let hasAvatar = false;
    server.use(
      http.get(AVATAR_URL, () =>
        hasAvatar
          ? HttpResponse.arrayBuffer(PNG_BYTES, {
              headers: { "Content-Type": "image/png" },
            })
          : HttpResponse.json({ detail: "未设置头像" }, { status: 404 }),
      ),
      http.put(AVATAR_URL, async ({ request }) => {
        uploaded.push(new Uint8Array(await request.arrayBuffer()));
        hasAvatar = true;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderAt("/settings");

    await screen.findByRole("button", { name: "选择图片" });
    expect(mainArea().queryByAltText("头像")).not.toBeInTheDocument();
    await act(async () => {
      fireEvent.change(avatarFileInput(), {
        target: { files: [new File([PNG_BYTES], "avatar.png")] },
      });
    });

    expect(
      await screen.findByRole("button", { name: "删除头像" }),
    ).toBeEnabled();
    expect(mainArea().getByAltText("头像")).toBeInTheDocument();
    expect(uploaded).toEqual([PNG_BYTES]);
  });

  it("删除头像后回到占位图标", async () => {
    let hasAvatar = true;
    server.use(
      http.get(AVATAR_URL, () =>
        hasAvatar
          ? HttpResponse.arrayBuffer(PNG_BYTES, {
              headers: { "Content-Type": "image/png" },
            })
          : HttpResponse.json({ detail: "未设置头像" }, { status: 404 }),
      ),
      http.delete(AVATAR_URL, () => {
        hasAvatar = false;
        return new HttpResponse(null, { status: 204 });
      }),
    );

    renderAt("/settings");

    expect(
      await screen.findByRole("button", { name: "删除头像" }),
    ).toBeEnabled();
    expect(mainArea().getByAltText("头像")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "删除头像" }));

    await waitFor(() =>
      expect(mainArea().queryByAltText("头像")).not.toBeInTheDocument(),
    );
  });

  it("上传失败行内报错且可重试", async () => {
    server.use(
      http.put(AVATAR_URL, () =>
        HttpResponse.json(
          { detail: "头像仅支持 PNG/JPG/WebP 格式" },
          { status: 422 },
        ),
      ),
    );

    renderAt("/settings");

    await screen.findByRole("button", { name: "选择图片" });
    await act(async () => {
      fireEvent.change(avatarFileInput(), {
        target: { files: [new File([PNG_BYTES], "avatar.png")] },
      });
    });

    expect(
      await screen.findByRole("alert", undefined, { timeout: 8_000 }),
    ).toHaveTextContent("头像仅支持 PNG/JPG/WebP 格式");
    expect(screen.getByRole("button", { name: "选择图片" })).toBeEnabled();
  });
});

type PreferencesOut = components["schemas"]["PreferencesOut"];

const PREFERENCES_URL = `${TEST_SIDECAR_URL}/api/settings/preferences`;
const DEFAULT_PREFERENCES: PreferencesOut = {
  theme: "SYSTEM",
  font_scale: "M",
  language: "zh",
  timezone: null,
  close_behavior: "TRAY",
  quick_note_shortcut: "Ctrl+Alt+N",
  autostart: false,
  quiz_last_count: 5,
  last_route: null,
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
          quick_note_shortcut: "Ctrl+Alt+P",
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
    expect(screen.getByText("Ctrl+Alt+P")).toBeVisible();
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

describe("速记快捷键录制控件", () => {
  function pressRecordingKey(code: string, isComposing = false) {
    document.body.dispatchEvent(
      new KeyboardEvent("keydown", {
        bubbles: true,
        cancelable: true,
        code,
        isComposing,
      }),
    );
  }

  it("按下即录：修饰键先按主键收尾，立即提交改键并回显新值", async () => {
    const bodies: object[] = [];
    let current = { ...DEFAULT_PREFERENCES };
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
    fireEvent.click(await screen.findByRole("button", { name: "更改" }));

    expect(
      await screen.findByText("请按下新的组合键（Esc 取消）"),
    ).toBeVisible();

    act(() => {
      pressRecordingKey("ControlLeft");
      pressRecordingKey("AltLeft");
      pressRecordingKey("KeyP");
    });

    await waitFor(() => expect(screen.getByText("Ctrl+Alt+P")).toBeVisible());
    expect(bodies).toEqual([{ quick_note_shortcut: "Ctrl+Alt+P" }]);
    expect(
      screen.queryByText("请按下新的组合键（Esc 取消）"),
    ).not.toBeInTheDocument();
  }, 15_000);

  it("缺修饰键的组合行内报错且不改键", async () => {
    const bodies: object[] = [];
    server.use(
      http.get(PREFERENCES_URL, () => HttpResponse.json(DEFAULT_PREFERENCES)),
      http.put(PREFERENCES_URL, async ({ request }) => {
        bodies.push((await request.json()) as object);
        return HttpResponse.json(DEFAULT_PREFERENCES);
      }),
    );

    renderAt("/settings");
    fireEvent.click(await screen.findByRole("button", { name: "更改" }));

    act(() => pressRecordingKey("KeyP"));

    expect(
      await screen.findByRole("alert", undefined, { timeout: 8_000 }),
    ).toHaveTextContent("组合需包含至少一个修饰键");
    expect(bodies).toEqual([]);
    expect(screen.getByText("Ctrl+Alt+N")).toBeVisible();
  }, 15_000);

  it("中文输入法组合输入不进入录制结果", async () => {
    server.use(
      http.get(PREFERENCES_URL, () => HttpResponse.json(DEFAULT_PREFERENCES)),
      http.put(PREFERENCES_URL, async ({ request }) => {
        const body = (await request.json()) as {
          quick_note_shortcut?: string;
        };
        return HttpResponse.json({
          ...DEFAULT_PREFERENCES,
          quick_note_shortcut: body.quick_note_shortcut,
        });
      }),
    );
    renderAt("/settings");
    fireEvent.click(await screen.findByRole("button", { name: "更改" }));

    act(() => {
      pressRecordingKey("KeyX", true);
      pressRecordingKey("ControlLeft");
      pressRecordingKey("AltLeft");
      pressRecordingKey("KeyJ");
    });

    await waitFor(() => expect(screen.getByText("Ctrl+Alt+J")).toBeVisible());
  }, 15_000);

  it("Esc 取消录制，不提交任何改动", async () => {
    const bodies: object[] = [];
    server.use(
      http.get(PREFERENCES_URL, () => HttpResponse.json(DEFAULT_PREFERENCES)),
      http.put(PREFERENCES_URL, async ({ request }) => {
        bodies.push((await request.json()) as object);
        return HttpResponse.json(DEFAULT_PREFERENCES);
      }),
    );

    renderAt("/settings");
    fireEvent.click(await screen.findByRole("button", { name: "更改" }));

    act(() => pressRecordingKey("Escape"));

    await waitFor(() =>
      expect(
        screen.queryByText("请按下新的组合键（Esc 取消）"),
      ).not.toBeInTheDocument(),
    );
    expect(screen.getByText("Ctrl+Alt+N")).toBeVisible();
    expect(bodies).toEqual([]);
    expect(await screen.findByRole("button", { name: "更改" })).toBeEnabled();
  }, 15_000);

  it("系统级冲突提示并保持旧键", async () => {
    const { rebindQuickNoteShortcut } =
      await import("@/services/tauri/preferences");
    vi.mocked(rebindQuickNoteShortcut).mockResolvedValueOnce({
      ok: false,
      reason: "conflict",
    });
    server.use(
      http.get(PREFERENCES_URL, () => HttpResponse.json(DEFAULT_PREFERENCES)),
    );

    renderAt("/settings");
    fireEvent.click(await screen.findByRole("button", { name: "更改" }));

    act(() => {
      pressRecordingKey("ControlLeft");
      pressRecordingKey("AltLeft");
      pressRecordingKey("KeyP");
    });

    expect(
      await screen.findByRole("alert", undefined, { timeout: 8_000 }),
    ).toHaveTextContent("该组合已被其他应用占用");
    expect(screen.getByText("Ctrl+Alt+N")).toBeVisible();
  }, 15_000);

  it("改键持久化失败回滚并提示已保留原快捷键", async () => {
    server.use(
      http.get(PREFERENCES_URL, () => HttpResponse.json(DEFAULT_PREFERENCES)),
      http.put(PREFERENCES_URL, () =>
        HttpResponse.json({ detail: "偏好保存失败" }, { status: 500 }),
      ),
    );

    renderAt("/settings");
    fireEvent.click(await screen.findByRole("button", { name: "更改" }));

    act(() => {
      pressRecordingKey("ControlLeft");
      pressRecordingKey("AltLeft");
      pressRecordingKey("KeyP");
    });

    expect(
      await screen.findByRole("alert", undefined, { timeout: 8_000 }),
    ).toHaveTextContent("已保留原快捷键");
    expect(screen.getByText("Ctrl+Alt+N")).toBeVisible();
  }, 15_000);
});

const LLM_PROVIDER_URL = `${TEST_SIDECAR_URL}/api/settings/providers/llm`;
const ASR_PROVIDER_URL = `${TEST_SIDECAR_URL}/api/settings/providers/tencent-asr`;

describe("设置页供应商分区", () => {
  async function sectionOf(headingName: string) {
    const heading = await screen.findByRole("heading", { name: headingName });
    const section = heading.closest("section");
    expect(section).not.toBeNull();
    return section as HTMLElement;
  }

  it("AI 服务卡：DashScope 预设一键填充，保存后可测试连接", async () => {
    const bodies: object[] = [];
    server.use(
      http.get(LLM_PROVIDER_URL, () => HttpResponse.json({ provider: null })),
      http.put(LLM_PROVIDER_URL, async ({ request }) => {
        bodies.push((await request.json()) as object);
        return HttpResponse.json({
          provider: {
            base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
            model: "qwen-plus",
            has_api_key: true,
            api_key_hint: "••••5678",
          },
        });
      }),
      http.post(`${LLM_PROVIDER_URL}/tests`, () =>
        HttpResponse.json({ ok: true, model: "qwen-plus" }),
      ),
    );
    renderAt("/settings");

    const section = await sectionOf("AI 服务");
    // 未配置（无已保存密钥）时不显示测试按钮。
    expect(
      within(section).queryByRole("button", { name: "测试连接" }),
    ).toBeNull();

    fireEvent.click(
      within(section).getByRole("button", { name: "填入 DashScope 预设" }),
    );
    expect(within(section).getByLabelText("服务地址")).toHaveValue(
      "https://dashscope.aliyuncs.com/compatible-mode/v1",
    );
    expect(within(section).getByLabelText("模型")).toHaveValue("qwen-plus");

    fireEvent.change(within(section).getByLabelText("API 密钥"), {
      target: { value: "sk-abc" },
    });
    fireEvent.click(within(section).getByRole("button", { name: "保存配置" }));

    expect(await within(section).findByRole("status")).toHaveTextContent(
      "AI 服务配置已保存",
    );
    expect(bodies).toEqual([
      {
        base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: "qwen-plus",
        api_key: "sk-abc",
        clear_api_key: false,
      },
    ]);

    fireEvent.click(
      await within(section).findByRole("button", { name: "测试连接" }),
    );
    expect(
      await within(section).findByText("连接测试成功（qwen-plus）"),
    ).toBeVisible();
  }, 15_000);

  it("语音转写卡：保存腾讯密钥并测试连接，展示配置不等于同意文案", async () => {
    const bodies: object[] = [];
    server.use(
      http.get(ASR_PROVIDER_URL, () => HttpResponse.json({ provider: null })),
      http.put(ASR_PROVIDER_URL, async ({ request }) => {
        bodies.push((await request.json()) as object);
        return HttpResponse.json({
          provider: {
            region: "ap-shanghai",
            has_credentials: true,
            secret_id_hint: "••••1234",
          },
        });
      }),
      http.post(`${ASR_PROVIDER_URL}/tests`, () =>
        HttpResponse.json({ ok: true, region: "ap-shanghai" }),
      ),
    );
    renderAt("/settings");

    const section = await sectionOf("语音转写");
    fireEvent.change(within(section).getByLabelText("SecretId"), {
      target: { value: "AKIDexample1234" },
    });
    fireEvent.change(within(section).getByLabelText("SecretKey"), {
      target: { value: "tencent-secret" },
    });
    fireEvent.change(within(section).getByLabelText("地域（region）"), {
      target: { value: "ap-shanghai" },
    });
    fireEvent.click(within(section).getByRole("button", { name: "保存配置" }));

    expect(await within(section).findByRole("status")).toHaveTextContent(
      "语音转写配置已保存",
    );
    expect(bodies).toEqual([
      {
        region: "ap-shanghai",
        secret_id: "AKIDexample1234",
        secret_key: "tencent-secret",
        clear_secret_key: false,
      },
    ]);

    fireEvent.click(
      await within(section).findByRole("button", { name: "测试连接" }),
    );
    expect(
      await within(section).findByText("连接测试成功（ap-shanghai）"),
    ).toBeVisible();
    expect(screen.getByText(/保存密钥不等于同意外发/)).toBeVisible();
  }, 15_000);
});

describe("设置页界面语言", () => {
  it("切到 English 发出 language PUT，界面语言实例与 <html lang> 即时跟随", async () => {
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
    expect(screen.getByRole("radio", { name: "中文" })).toBeChecked();

    fireEvent.click(screen.getByRole("radio", { name: "English" }));

    await waitFor(() =>
      expect(screen.getByRole("radio", { name: "English" })).toBeChecked(),
    );
    expect(bodies).toEqual([{ language: "en" }]);
    await waitFor(() => expect(i18n.language).toBe("en"));
    expect(document.documentElement.lang).toBe("en-US");
    expect(window.localStorage.getItem(LANGUAGE_STORAGE_KEY)).toBe("en");
  });

  it("语言保存失败时行内报错，控件停留当前生效值", async () => {
    server.use(
      http.put(PREFERENCES_URL, () =>
        HttpResponse.json({ detail: "服务器内部错误" }, { status: 500 }),
      ),
    );

    renderAt("/settings");
    await screen.findByRole("heading", { name: "偏好" });

    fireEvent.click(screen.getByRole("radio", { name: "English" }));

    expect(await screen.findByText("服务器内部错误")).toBeVisible();
    expect(screen.getByRole("radio", { name: "中文" })).toBeChecked();
    expect(i18n.language).toBe("zh");
  }, 10_000);
});
