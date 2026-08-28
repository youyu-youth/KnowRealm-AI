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
      updated_at: "2026-08-27T08:00:00.000000Z",
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
          updated_at: "2026-08-27T09:00:00.000000Z",
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
