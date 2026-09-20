// @vitest-environment jsdom

import "@testing-library/jest-dom/vitest";
import { fireEvent, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { LearnerMemorySection } from "./LearnerMemorySection";

const { getPreferences, savePreferences, deleteObserved, setOutbound } =
  vi.hoisted(() => ({
    getPreferences: vi.fn(),
    savePreferences: vi.fn(),
    deleteObserved: vi.fn(),
    setOutbound: vi.fn(),
  }));

vi.mock("@/features/settings/api/learnerMemory", () => ({
  learnerMemoryApi: {
    get: getPreferences,
    save: savePreferences,
    deleteObserved,
    setOutbound,
  },
}));

function preferenceData(overrides: Record<string, unknown> = {}) {
  return {
    explicit_items: ["先看例题"],
    observed_entries: { 解释风格: "偏好例子先行" },
    observed_confidence: 0.82,
    evidence_count: 12,
    last_observed_at: "2026-09-19T08:00:00.000000Z",
    updated_at: "2026-09-19T08:00:00.000000Z",
    memory_outbound: {
      enabled: true,
      consent_granted_at: "2026-09-18T08:00:00.000000Z",
      consent_current: true,
    },
    ...overrides,
  };
}

function renderSection() {
  return renderWithQuery(<LearnerMemorySection />);
}

beforeEach(() => {
  vi.clearAllMocks();
  getPreferences.mockResolvedValue(preferenceData());
});

describe("LearnerMemorySection", () => {
  it("展示显式偏好、观察偏好与外发开关", async () => {
    renderSection();
    expect(
      await screen.findByRole("heading", { name: "AI 记忆" }),
    ).toBeInTheDocument();
    expect(screen.getByText("先看例题")).toBeInTheDocument();
    expect(screen.getByText("解释风格：偏好例子先行")).toBeInTheDocument();
    expect(screen.getByText(/置信度 82%/)).toBeInTheDocument();
    expect(
      screen.getByRole("switch", { name: "在 AI 中使用长期记忆" }),
    ).toBeChecked();
  });

  it("添加显式偏好即改即存（PUT 全量列表）", async () => {
    savePreferences.mockResolvedValue(
      preferenceData({ explicit_items: ["先看例题", "多给反例"] }),
    );
    // 首次加载无新条目；保存触发失效重取后以服务端事实回显。
    getPreferences
      .mockResolvedValueOnce(preferenceData())
      .mockResolvedValue(preferenceData({ explicit_items: ["先看例题", "多给反例"] }));
    renderSection();
    await screen.findByText("先看例题");
    fireEvent.change(screen.getByPlaceholderText(/我喜欢先看例题/), {
      target: { value: "多给反例" },
    });
    fireEvent.click(screen.getByRole("button", { name: "添加" }));
    await waitFor(() => {
      expect(savePreferences).toHaveBeenCalledWith({
        items: ["先看例题", "多给反例"],
      });
    });
    expect(await screen.findByText("多给反例")).toBeInTheDocument();
  });

  it("删除观察偏好调用 DELETE 并从列表移除", async () => {
    deleteObserved.mockResolvedValue(undefined);
    // 首次加载含观察条目；删除触发失效重取后为空。
    getPreferences
      .mockResolvedValueOnce(preferenceData())
      .mockResolvedValue(preferenceData({ observed_entries: {} }));
    renderSection();
    await screen.findByText("解释风格：偏好例子先行");
    fireEvent.click(
      screen.getByRole("button", { name: "删除观察偏好「解释风格」" }),
    );
    await waitFor(() => {
      expect(deleteObserved).toHaveBeenCalledWith("解释风格");
    });
    await waitFor(() => {
      expect(screen.getByText("暂无观察偏好。")).toBeInTheDocument();
    });
  });

  it("关闭外发开关调用 setOutbound(false)", async () => {
    setOutbound.mockResolvedValue(
      preferenceData().memory_outbound && {
        enabled: false,
        consent_granted_at: null,
        consent_current: false,
      },
    );
    renderSection();
    const toggle = await screen.findByRole("switch", {
      name: "在 AI 中使用长期记忆",
    });
    fireEvent.click(toggle);
    await waitFor(() => {
      expect(setOutbound).toHaveBeenCalledWith(false);
    });
  });
});
