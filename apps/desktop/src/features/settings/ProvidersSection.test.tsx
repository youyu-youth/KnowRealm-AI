// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { ProvidersSection } from "./ProvidersSection";

const { getLlmProvider, getTencentAsrProvider, getLlmUsage } = vi.hoisted(
  () => ({
    getLlmProvider: vi.fn(),
    getTencentAsrProvider: vi.fn(),
    getLlmUsage: vi.fn(),
  }),
);

vi.mock("@/features/settings/api/settings", () => ({
  settingsApi: { getLlmProvider, getTencentAsrProvider, getLlmUsage },
}));

const EMPTY_USAGE = {
  items: [],
  daily: Array.from({ length: 30 }, (_, index) => ({
    date: `2026-08-${String(1 + index).padStart(2, "0")}`,
    total_tokens: 0,
    call_count: 0,
  })),
};

describe("ProvidersSection 健康检查徽章", () => {
  beforeEach(() => {
    getLlmProvider.mockReset();
    getTencentAsrProvider.mockReset();
    getLlmUsage.mockReset();
    getLlmUsage.mockResolvedValue(EMPTY_USAGE);
  });

  it("缺 key 时两张卡标红并给出补救提示", async () => {
    getLlmProvider.mockResolvedValue({
      provider: {
        base_url: "",
        model: "",
        has_api_key: false,
        api_key_hint: null,
      },
    });
    getTencentAsrProvider.mockResolvedValue({
      provider: { region: "", has_credentials: false, secret_id_hint: null },
    });

    renderWithQuery(<ProvidersSection />);

    await waitFor(() =>
      expect(screen.getAllByText("未配置密钥")).toHaveLength(2),
    );
    expect(
      screen.getByText(
        "未配置 API 密钥，总结、知识点、习题、复习资料与 AI 问答暂不可用；在下方填写并保存后即可恢复。",
      ),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        "未配置腾讯云密钥，录音与音频导入的转写暂不可用；在下方填写并保存后即可恢复。",
      ),
    ).toBeInTheDocument();
  });

  it("已配置时显示绿徽章且无补救提示", async () => {
    getLlmProvider.mockResolvedValue({
      provider: {
        base_url: "https://dashscope.aliyuncs.com/compatible-mode/v1",
        model: "qwen-plus",
        has_api_key: true,
        api_key_hint: "••••1234",
      },
    });
    getTencentAsrProvider.mockResolvedValue({
      provider: {
        region: "ap-shanghai",
        has_credentials: true,
        secret_id_hint: "••••1234",
      },
    });

    renderWithQuery(<ProvidersSection />);

    await waitFor(() => expect(screen.getAllByText("已配置")).toHaveLength(2));
    expect(screen.queryByText("未配置密钥")).not.toBeInTheDocument();
    expect(
      screen.queryByText(/暂不可用；在下方填写并保存后即可恢复。/),
    ).not.toBeInTheDocument();
  });
});
