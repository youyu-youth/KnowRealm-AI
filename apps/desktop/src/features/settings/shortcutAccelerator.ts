// useRecordHotkeys 录制产物 → Tauri accelerator。
// hook 会先把 code 规范化：修饰键进别名表（ControlLeft→ctrl、MetaLeft→meta 等），
// 其余小写并剥掉首个 key/digit/numpad 子串（KeyP→p、Digit1→1、Numpad1→1）。
// 主键白名单与后端 is_valid_shortcut 一致；不在表内的组合键（小键盘运算符、媒体键等）视为不支持。

const MODIFIER_CODES: Record<string, string> = {
  ctrl: "Ctrl",
  alt: "Alt",
  shift: "Shift",
  meta: "Super",
};

const KEY_CODES: Record<string, string> = {
  ...Object.fromEntries(
    Array.from({ length: 26 }, (_, index) => [
      String.fromCharCode(97 + index),
      String.fromCharCode(65 + index),
    ]),
  ),
  ...Object.fromEntries(
    Array.from({ length: 10 }, (_, digit) => [String(digit), String(digit)]),
  ),
  ...Object.fromEntries(
    Array.from({ length: 24 }, (_, index) => [
      `f${index + 1}`,
      `F${index + 1}`,
    ]),
  ),
  space: "Space",
  comma: "Comma",
  period: "Period",
  slash: "Slash",
  semicolon: "Semicolon",
  quote: "Quote",
  backquote: "Backquote",
  bracketleft: "BracketLeft",
  bracketright: "BracketRight",
  backslash: "Backslash",
  minus: "Minus",
  equal: "Equal",
  tab: "Tab",
  capslock: "CapsLock",
  enter: "Enter",
  backspace: "Backspace",
  delete: "Delete",
  insert: "Insert",
  home: "Home",
  end: "End",
  pageup: "PageUp",
  pagedown: "PageDown",
  arrowup: "ArrowUp",
  arrowdown: "ArrowDown",
  arrowleft: "ArrowLeft",
  arrowright: "ArrowRight",
  printscreen: "PrintScreen",
  scrolllock: "ScrollLock",
  pause: "Pause",
  numlock: "NumLock",
};

const MODIFIER_ORDER = ["Ctrl", "Alt", "Shift", "Super"] as const;

export type RecordedKeysResult =
  // 只按了修饰键（或还没按主键），组合未完成
  | { status: "waiting" }
  | { status: "ready"; accelerator: string }
  | { status: "invalid"; reason: "missing-modifier" | "unsupported-key" };

// 以「最后按下的键是主键」为完成判定：按下即录，修饰键先按、主键收尾。
export function normalizeRecordedKeys(
  keys: ReadonlySet<string>,
): RecordedKeysResult {
  if (keys.size === 0) return { status: "waiting" };
  const recorded = [...keys];
  const last = recorded[recorded.length - 1];
  if (last in MODIFIER_CODES) return { status: "waiting" };
  const primary = KEY_CODES[last];
  if (primary === undefined)
    return { status: "invalid", reason: "unsupported-key" };
  const modifiers = [
    ...new Set(recorded.map((code) => MODIFIER_CODES[code]).filter(Boolean)),
  ];
  if (modifiers.length === 0)
    return { status: "invalid", reason: "missing-modifier" };
  const ordered = MODIFIER_ORDER.filter((modifier) =>
    modifiers.includes(modifier),
  );
  return { status: "ready", accelerator: [...ordered, primary].join("+") };
}
