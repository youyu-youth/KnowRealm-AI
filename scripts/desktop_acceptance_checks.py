"""浏览器与 WebView2 共用的桌面验收断言；不操作业务或自动滚动。"""

from collections.abc import Iterable
from typing import TYPE_CHECKING, Literal, TypedDict, cast

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page

Status = Literal["PASS", "FAIL", "NOT_RUN", "NOT_TRIGGERED"]


class GeometryCheck(TypedDict):
    status: Status
    violations: list[str]
    rect: dict[str, float]
    container: dict[str, float]
    viewport: dict[str, float]


def summarize_checks(statuses: Iterable[Status]) -> Status:
    """仅当所有必验项均通过时返回 PASS；未触发不能替代通过。"""
    values = list(statuses)
    if "FAIL" in values:
        return "FAIL"
    return "PASS" if values and all(value == "PASS" for value in values) else "NOT_RUN"


def assert_keyboard_order(
    page: "Page", start: "Locator", retry: "Locator", accept: "Locator"
) -> None:
    """从动作区外进入，实际验证 Tab/Shift+Tab；不替用户触发业务动作。"""
    start.focus()
    for _ in range(80):
        page.keyboard.press("Tab")
        if retry.evaluate("e => e === document.activeElement"):
            break
    else:
        raise AssertionError("80 次 Tab 内未到达重试按钮")
    page.keyboard.press("Tab")
    assert accept.evaluate("e => e === document.activeElement"), "Tab 未到达接受按钮"
    page.keyboard.press("Shift+Tab")
    assert retry.evaluate("e => e === document.activeElement"), "Shift+Tab 未返回重试按钮"


def inspect_geometry(button: "Locator", container: "Locator") -> GeometryCheck:
    """等待连续两帧几何稳定，检查控件、所属容器与祖先裁切边界。"""
    handle = container.element_handle()
    try:
        return cast(
            GeometryCheck,
            button.evaluate(
                """(element, container) => new Promise(resolve => {
                const rect = e => {
                    const r = e.getBoundingClientRect();
                    return {left:r.left, top:r.top, right:r.right, bottom:r.bottom,
                            width:r.width, height:r.height};
                };
                const measure = () => {
                    const box = rect(element), owner = rect(container);
                    const viewport = {left:0, top:0,
                        right:document.documentElement.clientWidth,
                        bottom:document.documentElement.clientHeight};
                    const violations = [];
                    const contains = (outer, inner, x=true, y=true) =>
                        (!x || inner.left >= outer.left - 1 && inner.right <= outer.right + 1) &&
                        (!y || inner.top >= outer.top - 1 && inner.bottom <= outer.bottom + 1);
                    const style = getComputedStyle(element);
                    if (box.width <= 0 || box.height <= 0 ||
                        style.visibility !== 'visible') violations.push('not_visible');
                    if (!contains(viewport, box)) violations.push('viewport');
                    if (!container.contains(element) || !contains(owner, box))
                        violations.push('container');
                    if (element.scrollWidth > element.clientWidth + 1 ||
                        element.scrollHeight > element.clientHeight + 1)
                        violations.push('text_overflow');
                    const clips = [];
                    for (let parent = element.parentElement; parent;
                         parent = parent.parentElement) {
                        const s = getComputedStyle(parent), r = rect(parent);
                        const x = /^(hidden|clip|scroll|auto)$/.test(s.overflowX);
                        const y = /^(hidden|clip|scroll|auto)$/.test(s.overflowY);
                        if (!x && !y) continue;
                        const clip = {left:r.left + parent.clientLeft,
                            top:r.top + parent.clientTop,
                            right:r.left + parent.clientLeft + parent.clientWidth,
                            bottom:r.top + parent.clientTop + parent.clientHeight};
                        clips.push([clip, x, y]);
                        if (!contains(clip, box, x, y))
                            violations.push('ancestor:' + parent.tagName.toLowerCase() +
                                (parent.id ? '#' + parent.id : ''));
                    }
                    return {status:violations.length ? 'FAIL' : 'PASS', violations,
                        rect:box, container:owner, viewport, clips};
                };
                let previous = '', stable = 0, frame, latest;
                const finish = result => {
                    clearTimeout(timer);
                    cancelAnimationFrame(frame);
                    delete result.clips;
                    resolve(result);
                };
                const timer = setTimeout(() => {
                    const result = latest || measure();
                    result.violations.push('unstable_layout');
                    result.status = 'FAIL';
                    finish(result);
                }, 2000);
                const tick = () => {
                    latest = measure();
                    const signature = JSON.stringify(latest);
                    stable = signature === previous ? stable + 1 : 0;
                    previous = signature;
                    if (stable >= 2) finish(latest);
                    else frame = requestAnimationFrame(tick);
                };
                frame = requestAnimationFrame(tick);
            })""",
                handle,
            ),
        )
    finally:
        handle.dispose()
