// @vitest-environment jsdom

import { act, fireEvent, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";
import { renderWithQuery } from "@/test/test-utils";
import { CaptureFloatingToolbar } from "@/components/layout/CaptureFloatingToolbar";

afterEach(() => vi.restoreAllMocks());

function setup(recordingActive = false) {
  const onCapture = vi.fn();
  renderWithQuery(
    <CaptureFloatingToolbar
      onCapture={onCapture}
      recordingActive={recordingActive}
    />,
  );
  const trigger = screen.getByRole("button", { name: "快速捕获" });
  Object.defineProperties(trigger, {
    setPointerCapture: { value: vi.fn() },
    hasPointerCapture: { value: () => true },
    releasePointerCapture: { value: vi.fn() },
  });
  return {
    trigger,
    root: trigger.closest(".capture-floating-toolbar") as HTMLElement,
    onCapture,
  };
}

function pointer(target: HTMLElement, type: string, x: number, y: number) {
  const event = new MouseEvent(type, {
    bubbles: true,
    clientX: x,
    clientY: y,
    button: 0,
  });
  Object.defineProperty(event, "pointerId", { value: 1 });
  fireEvent(target, event);
}

describe("悬浮捕获工具栏", () => {
  it("默认收起，悬停展开，离开收起，四个按钮调用原入口", () => {
    const { trigger, root, onCapture } = setup();
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(screen.getByRole("group", { name: "快速捕获" })).toHaveAttribute(
      "inert",
    );
    fireEvent.mouseEnter(root);
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    fireEvent.mouseLeave(root);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    for (const [name, action] of [
      ["新建速记", "capture.note"],
      ["粘贴文本", "capture.paste"],
      ["导入资料", "capture.import"],
      ["开始录音", "capture.record"],
    ]) {
      fireEvent.mouseEnter(root);
      fireEvent.click(screen.getByRole("button", { name }));
      expect(onCapture).toHaveBeenLastCalledWith(action);
      expect(trigger).toHaveAttribute("aria-expanded", "false");
      expect(trigger).toHaveFocus();
    }
  });

  it("录音进行时阻止重复开始，其他操作仍可用", () => {
    const { trigger, onCapture } = setup(true);
    fireEvent.click(trigger);
    const record = screen.getByRole("button", { name: "开始录音" });
    expect(record).toHaveAttribute("aria-disabled", "true");
    fireEvent.click(record);
    expect(onCapture).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "新建速记" }));
    expect(onCapture).toHaveBeenCalledWith("capture.note");
  });

  it("拖动固定入口，释放不误展开，键盘仍可打开且可移动", () => {
    const { trigger, root } = setup();
    fireEvent.keyDown(trigger, { key: "ArrowRight" });
    for (let step = 0; step < 10; step++)
      fireEvent.keyDown(trigger, { key: "ArrowRight" });
    const initialX = Number.parseFloat(root.style.left);
    pointer(trigger, "pointerdown", initialX, 600);
    pointer(trigger, "pointermove", initialX - 100, 500);
    pointer(trigger, "pointerup", initialX - 100, 500);
    fireEvent.click(trigger, { detail: 1 });
    expect(root.style.left).toBe(`${initialX - 100}px`);
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    fireEvent.click(trigger, { detail: 0 });
    expect(trigger).toHaveAttribute("aria-expanded", "true");
    fireEvent.keyDown(trigger, { key: "ArrowLeft" });
    expect(root.style.left).toBe(`${initialX - 116}px`);
    fireEvent.keyDown(trigger, { key: "Escape" });
    expect(trigger).toHaveAttribute("aria-expanded", "false");
    expect(trigger).toHaveFocus();
  });

  it.each(["pointercancel", "blur", "Escape"])(
    "%s 取消拖动并恢复原位",
    (type) => {
      const { trigger, root } = setup();
      const original = root.style.left;
      pointer(trigger, "pointerdown", 900, 600);
      pointer(trigger, "pointermove", 600, 400);
      expect(root.style.left).not.toBe(original);
      if (type === "blur") fireEvent.blur(window);
      else if (type === "Escape") fireEvent.keyDown(trigger, { key: type });
      else pointer(trigger, type, 600, 400);
      expect(root.style.left).toBe(original);
      pointer(trigger, "pointermove", 300, 200);
      expect(root.style.left).toBe(original);
    },
  );

  it("限制拖动边界，靠上向下展开，窗口缩小时入口仍在工作面内", () => {
    const { trigger, root } = setup();
    pointer(trigger, "pointerdown", 900, 600);
    pointer(trigger, "pointermove", -1000, -1000);
    pointer(trigger, "pointerup", -1000, -1000);
    expect(root.style.left).toBe("16px");
    expect(root.style.top).toBe("16px");
    expect(screen.getByRole("group", { name: "快速捕获" })).toHaveAttribute(
      "data-side",
      "bottom",
    );
    pointer(trigger, "pointerdown", 16, 16);
    pointer(trigger, "pointermove", 3000, 3000);
    pointer(trigger, "pointerup", 3000, 3000);
    const surface = root.parentElement;
    expect(surface).not.toBeNull();
    if (!surface) return;
    vi.spyOn(surface, "getBoundingClientRect").mockReturnValue(
      new DOMRect(200, 60, 600, 500),
    );
    vi.spyOn(root, "getBoundingClientRect").mockReturnValue(
      new DOMRect(0, 0, 48, 48),
    );
    act(() => window.dispatchEvent(new Event("resize")));
    expect(root.style.left).toBe("736px");
    expect(root.style.top).toBe("496px");
  });
});
