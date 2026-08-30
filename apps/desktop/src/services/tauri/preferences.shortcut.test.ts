import { beforeEach, describe, expect, it, vi } from "vitest";

type ShortcutEventHandler = (event: { state: "Pressed" | "Released" }) => void;

const runtime = vi.hoisted(() => ({
  registered: new Map<string, ShortcutEventHandler>(),
  registerShouldFail: null as string | null,
  unregisterShouldFail: null as string | null,
  registerGates: new Map<string, () => void>(),
}));

vi.mock("@tauri-apps/api/core", () => ({ isTauri: vi.fn(() => true) }));

vi.mock("@tauri-apps/plugin-global-shortcut", () => ({
  register: vi.fn(async (shortcut: string, handler: ShortcutEventHandler) => {
    if (runtime.registerShouldFail === shortcut)
      throw new Error("hotkey already registered by another app");
    if (runtime.registerGates.has(shortcut)) {
      await new Promise<void>((resolve) => {
        runtime.registerGates.set(shortcut, resolve);
      });
    }
    runtime.registered.set(shortcut, handler);
  }),
  unregister: vi.fn(async (shortcut: string) => {
    if (runtime.unregisterShouldFail === shortcut)
      throw new Error("unregister failed");
    runtime.registered.delete(shortcut);
  }),
  isRegistered: vi.fn(async (shortcut: string) =>
    runtime.registered.has(shortcut),
  ),
}));

// 让 register(shortcut) 挂起，直到 releaseRegister 手动放行（竞态编排）。
function holdRegister(shortcut: string) {
  runtime.registerGates.set(shortcut, () => undefined);
}

function releaseRegister(shortcut: string) {
  runtime.registerGates.get(shortcut)?.();
  runtime.registerGates.delete(shortcut);
}

function trigger(shortcut: string, state: "Pressed" | "Released" = "Pressed") {
  runtime.registered.get(shortcut)?.({ state });
}

async function importWrapper() {
  return import("./preferences");
}

async function mountDefault(
  shortcut = "Ctrl+Alt+N",
): Promise<{ onTriggered: ReturnType<typeof vi.fn> }> {
  const onTriggered = vi.fn();
  const { mountQuickNoteShortcut } = await importWrapper();
  await mountQuickNoteShortcut(shortcut, onTriggered);
  return { onTriggered };
}

beforeEach(async () => {
  vi.resetModules();
  runtime.registered.clear();
  runtime.registerShouldFail = null;
  runtime.unregisterShouldFail = null;
  runtime.registerGates.clear();
  vi.clearAllMocks();
  const { isTauri } = await import("@tauri-apps/api/core");
  vi.mocked(isTauri).mockReturnValue(true);
});

describe("速记快捷键启动挂载", () => {
  it("按偏好注册，回调只在按下时打开速记", async () => {
    const { onTriggered } = await mountDefault("Ctrl+Alt+N");
    const { register } = await import("@tauri-apps/plugin-global-shortcut");
    expect(register).toHaveBeenCalledWith("Ctrl+Alt+N", expect.any(Function));

    trigger("Ctrl+Alt+N", "Pressed");
    expect(onTriggered).toHaveBeenCalledOnce();

    trigger("Ctrl+Alt+N", "Released");
    expect(onTriggered).toHaveBeenCalledOnce();
  });

  it("注册冲突返回 false，不产生可用回调", async () => {
    runtime.registerShouldFail = "Ctrl+Alt+N";
    const { mountQuickNoteShortcut } = await importWrapper();
    const onTriggered = vi.fn();

    await expect(
      mountQuickNoteShortcut("Ctrl+Alt+N", onTriggered),
    ).resolves.toBe(false);

    trigger("Ctrl+Alt+N");
    expect(onTriggered).not.toHaveBeenCalled();
  });

  it("偏好未载入（null）不注册", async () => {
    const { mountQuickNoteShortcut } = await importWrapper();
    const { register } = await import("@tauri-apps/plugin-global-shortcut");

    await expect(mountQuickNoteShortcut(null, vi.fn())).resolves.toBe(false);
    expect(register).not.toHaveBeenCalled();
  });

  it("同一键重复挂载（StrictMode 重挂/改键后偏好刷新）只注册一次", async () => {
    const { mountQuickNoteShortcut } = await importWrapper();
    await mountQuickNoteShortcut("Ctrl+Alt+N", vi.fn());
    await expect(mountQuickNoteShortcut("Ctrl+Alt+N", vi.fn())).resolves.toBe(
      true,
    );
    const { register } = await import("@tauri-apps/plugin-global-shortcut");
    expect(register).toHaveBeenCalledOnce();
  });

  it("改键流程已注册的键经 isRegistered 去重，不重复注册", async () => {
    // 模拟改键完成、偏好缓存刷新触发重挂：OS 已注册而模块状态为空
    runtime.registered.set("Ctrl+Alt+P", vi.fn());
    const { mountQuickNoteShortcut } = await importWrapper();
    const { register } = await import("@tauri-apps/plugin-global-shortcut");

    await expect(mountQuickNoteShortcut("Ctrl+Alt+P", vi.fn())).resolves.toBe(
      true,
    );
    expect(register).not.toHaveBeenCalled();
  });

  it("挂载在途期间改键完成，落定后撤销在途键", async () => {
    holdRegister("Ctrl+Alt+N");
    const { mountQuickNoteShortcut, rebindQuickNoteShortcut } =
      await importWrapper();
    const mountPromise = mountQuickNoteShortcut("Ctrl+Alt+N", vi.fn());
    const persist = vi.fn(async () => undefined);
    await expect(
      rebindQuickNoteShortcut("Ctrl+Alt+P", persist),
    ).resolves.toEqual({ ok: true });

    releaseRegister("Ctrl+Alt+N");
    await expect(mountPromise).resolves.toBe(true);

    expect(runtime.registered.has("Ctrl+Alt+N")).toBe(false);
    expect(runtime.registered.has("Ctrl+Alt+P")).toBe(true);
  });

  it("非桌面环境不注册", async () => {
    const { isTauri } = await import("@tauri-apps/api/core");
    vi.mocked(isTauri).mockReturnValue(false);
    const { mountQuickNoteShortcut } = await importWrapper();
    const { register } = await import("@tauri-apps/plugin-global-shortcut");

    await expect(mountQuickNoteShortcut("Ctrl+Alt+N", vi.fn())).resolves.toBe(
      false,
    );
    expect(register).not.toHaveBeenCalled();
  });
});

describe("速记快捷键改键时序", () => {
  it("成功：试注册新键 → 注销旧键 → 持久化，旧键失效新键生效", async () => {
    const { onTriggered } = await mountDefault("Ctrl+Alt+N");
    const { register, unregister } =
      await import("@tauri-apps/plugin-global-shortcut");
    const mockedRegister = vi.mocked(register);
    const mockedUnregister = vi.mocked(unregister);
    const persist = vi.fn(async () => undefined);
    const { rebindQuickNoteShortcut } = await importWrapper();

    await expect(
      rebindQuickNoteShortcut("Ctrl+Alt+P", persist),
    ).resolves.toEqual({ ok: true });

    expect(mockedRegister).toHaveBeenCalledWith(
      "Ctrl+Alt+P",
      expect.any(Function),
    );
    expect(
      mockedRegister.mock.invocationCallOrder[
        mockedRegister.mock.invocationCallOrder.length - 1
      ],
    ).toBeLessThan(mockedUnregister.mock.invocationCallOrder[0]);
    expect(mockedUnregister.mock.invocationCallOrder[0]).toBeLessThan(
      persist.mock.invocationCallOrder[0],
    );

    trigger("Ctrl+Alt+P", "Pressed");
    expect(onTriggered).toHaveBeenCalledOnce();
    trigger("Ctrl+Alt+N", "Pressed");
    expect(onTriggered).toHaveBeenCalledOnce();
  });

  it("改键在旧键读取时机上覆盖在途挂载：挂载先落定、改键后放行，旧键仍被注销", async () => {
    holdRegister("Ctrl+Alt+N");
    holdRegister("Ctrl+Alt+P");
    const { mountQuickNoteShortcut, rebindQuickNoteShortcut } =
      await importWrapper();
    const mountPromise = mountQuickNoteShortcut("Ctrl+Alt+N", vi.fn());
    const persist = vi.fn(async () => undefined);
    const rebindPromise = rebindQuickNoteShortcut("Ctrl+Alt+P", persist);

    releaseRegister("Ctrl+Alt+N");
    releaseRegister("Ctrl+Alt+P");

    await expect(rebindPromise).resolves.toEqual({ ok: true });
    await expect(mountPromise).resolves.toBe(true);
    expect(runtime.registered.has("Ctrl+Alt+N")).toBe(false);
    expect(runtime.registered.has("Ctrl+Alt+P")).toBe(true);
  });

  it("改回同键为无操作：不动注册也不持久化", async () => {
    await mountDefault("Ctrl+Alt+N");
    const { register, unregister } =
      await import("@tauri-apps/plugin-global-shortcut");
    const persist = vi.fn(async () => undefined);
    const { rebindQuickNoteShortcut } = await importWrapper();

    await expect(
      rebindQuickNoteShortcut("Ctrl+Alt+N", persist),
    ).resolves.toEqual({ ok: true });

    expect(register).toHaveBeenCalledOnce();
    expect(unregister).not.toHaveBeenCalled();
    expect(persist).not.toHaveBeenCalled();
  });

  it("新键被系统占用：不注销旧键、不持久化，旧键保持可用", async () => {
    const { onTriggered } = await mountDefault("Ctrl+Alt+N");
    runtime.registerShouldFail = "Ctrl+Alt+P";
    const { unregister } = await import("@tauri-apps/plugin-global-shortcut");
    const persist = vi.fn(async () => undefined);
    const { rebindQuickNoteShortcut } = await importWrapper();

    await expect(
      rebindQuickNoteShortcut("Ctrl+Alt+P", persist),
    ).resolves.toEqual({
      ok: false,
      reason: "conflict",
    });

    expect(unregister).not.toHaveBeenCalled();
    expect(persist).not.toHaveBeenCalled();
    trigger("Ctrl+Alt+N", "Pressed");
    expect(onTriggered).toHaveBeenCalledOnce();
  });

  it("PUT 失败回滚：注销新键并恢复旧键", async () => {
    const { onTriggered } = await mountDefault("Ctrl+Alt+N");
    const persist = vi.fn(async () => {
      throw new Error("put failed");
    });
    const { rebindQuickNoteShortcut } = await importWrapper();

    await expect(
      rebindQuickNoteShortcut("Ctrl+Alt+P", persist),
    ).resolves.toEqual({
      ok: false,
      reason: "persist-failed",
    });

    trigger("Ctrl+Alt+P", "Pressed");
    expect(onTriggered).not.toHaveBeenCalled();
    trigger("Ctrl+Alt+N", "Pressed");
    expect(onTriggered).toHaveBeenCalledOnce();
  });

  it("注销旧键失败：回滚新键，旧键保持生效", async () => {
    const { onTriggered } = await mountDefault("Ctrl+Alt+N");
    runtime.unregisterShouldFail = "Ctrl+Alt+N";
    const persist = vi.fn(async () => undefined);
    const { rebindQuickNoteShortcut } = await importWrapper();

    await expect(
      rebindQuickNoteShortcut("Ctrl+Alt+P", persist),
    ).resolves.toEqual({
      ok: false,
      reason: "failed",
    });

    expect(persist).not.toHaveBeenCalled();
    trigger("Ctrl+Alt+P", "Pressed");
    expect(onTriggered).not.toHaveBeenCalled();
    trigger("Ctrl+Alt+N", "Pressed");
    expect(onTriggered).toHaveBeenCalledOnce();
  });

  it("非桌面环境无 OS 注册可动，等价于只持久化", async () => {
    const { isTauri } = await import("@tauri-apps/api/core");
    vi.mocked(isTauri).mockReturnValue(false);
    const persist = vi.fn(async () => undefined);
    const { register, unregister } =
      await import("@tauri-apps/plugin-global-shortcut");
    const { rebindQuickNoteShortcut } = await importWrapper();

    await expect(
      rebindQuickNoteShortcut("Ctrl+Alt+P", persist),
    ).resolves.toEqual({ ok: true });

    expect(register).not.toHaveBeenCalled();
    expect(unregister).not.toHaveBeenCalled();
    expect(persist).toHaveBeenCalledOnce();
  });
});
