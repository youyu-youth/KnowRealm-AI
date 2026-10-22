"""使用已安装的 Playwright/Chromium 验收固定 HTML，无 API 或模型调用。"""

import unittest
from typing import ClassVar

from desktop_acceptance_checks import (
    GeometryCheck,
    Status,
    assert_keyboard_order,
    inspect_geometry,
    summarize_checks,
)
from playwright.sync_api import Browser, Page, Playwright, expect, sync_playwright


class DesktopAcceptanceChecksTest(unittest.TestCase):
    playwright: ClassVar[Playwright]
    browser: ClassVar[Browser]
    page: Page

    @classmethod
    def setUpClass(cls) -> None:
        cls.playwright = sync_playwright().start()
        cls.browser = cls.playwright.chromium.launch()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.browser.close()
        cls.playwright.stop()

    def setUp(self) -> None:
        self.page = self.browser.new_page(viewport={"width": 720, "height": 480})
        self.addCleanup(self.page.close)

    def fixture(
        self, button_style: str = "", card_style: str = "", wrapper_style: str = ""
    ) -> None:
        self.page.set_content(f"""
            <style>* {{ box-sizing:border-box }} body {{ margin:0 }}
            #card {{ position:relative; width:600px; height:300px }}
            #retry {{ position:absolute; left:20px; top:20px; width:120px; height:40px;
                      border:0; padding:0; {button_style} }}</style>
            <button id="before">Before</button><div id="wrapper" style="{wrapper_style}">
            <section id="card" style="{card_style}"><button id="retry">Retry</button>
            <button id="accept">Accept</button></section></div>
            <script>window.actions=[]; for (const id of ['retry','accept'])
            document.getElementById(id).onclick=()=>window.actions.push(id);</script>
        """)

    def geometry(self) -> GeometryCheck:
        return inspect_geometry(self.page.locator("#retry"), self.page.locator("#card"))

    def test_normal_button_passes(self) -> None:
        self.fixture()
        self.assertEqual(self.geometry()["status"], "PASS")

    def test_horizontal_viewport_clipping_fails(self) -> None:
        self.fixture("left:680px")
        expect(self.page.locator("#retry")).to_be_visible()
        self.assertIn("viewport", self.geometry()["violations"])

    def test_vertical_viewport_clipping_fails(self) -> None:
        self.fixture("top:440px")
        self.assertIn("viewport", self.geometry()["violations"])

    def test_button_outside_card_fails_even_without_clipping(self) -> None:
        self.fixture("left:550px")
        result = self.geometry()
        self.assertNotIn("viewport", result["violations"])
        self.assertIn("container", result["violations"])

    def test_ancestor_clipping_fails_on_both_axes(self) -> None:
        for wrapper_style in ("width:100px;overflow:hidden", "height:35px;overflow:hidden"):
            with self.subTest(wrapper_style=wrapper_style):
                self.fixture(wrapper_style=wrapper_style)
                expect(self.page.locator("#retry")).to_be_visible()
                self.assertIn("ancestor:div#wrapper", self.geometry()["violations"])

    def test_scrollbar_and_border_are_not_visible_content(self) -> None:
        self.fixture(
            "left:0;width:120px", wrapper_style="width:122px;border:2px solid;overflow:auto"
        )
        self.assertIn("ancestor:div#wrapper", self.geometry()["violations"])

    def test_text_overflow_fails(self) -> None:
        self.fixture("width:15px;white-space:nowrap;overflow:hidden")
        self.assertIn("text_overflow", self.geometry()["violations"])

    def test_hidden_button_fails(self) -> None:
        self.fixture("visibility:hidden")
        self.assertIn("not_visible", self.geometry()["violations"])

    def test_unstable_layout_fails(self) -> None:
        self.fixture()
        self.page.evaluate("""() => {
            let left = 20;
            const move = () => {
                left = left === 20 ? 40 : 20;
                document.querySelector('#retry').style.left = left + 'px';
                requestAnimationFrame(move);
            };
            requestAnimationFrame(move);
        }""")
        self.assertIn("unstable_layout", self.geometry()["violations"])

    def test_programmatic_focus_does_not_prove_tab_reachability(self) -> None:
        self.fixture()
        retry = self.page.locator("#retry")
        retry.evaluate("e => e.tabIndex = -1")
        retry.focus()
        expect(retry).to_be_focused()
        with self.assertRaisesRegex(AssertionError, "未到达重试按钮"):
            assert_keyboard_order(
                self.page, self.page.locator("#before"), retry, self.page.locator("#accept")
            )

    def test_actual_tab_order_and_enter_actions(self) -> None:
        self.fixture()
        assert_keyboard_order(
            self.page,
            self.page.locator("#before"),
            self.page.locator("#retry"),
            self.page.locator("#accept"),
        )
        self.page.keyboard.press("Enter")
        self.page.keyboard.press("Tab")
        self.page.keyboard.press("Enter")
        self.assertEqual(self.page.evaluate("window.actions"), ["retry", "accept"])

    def test_only_complete_passes_summarize_as_pass(self) -> None:
        self.assertEqual(summarize_checks(["PASS", "PASS"]), "PASS")
        cases: list[list[Status]] = [[], ["PASS", "NOT_RUN"], ["PASS", "NOT_TRIGGERED"]]
        for values in cases:
            with self.subTest(values=values):
                self.assertEqual(summarize_checks(values), "NOT_RUN")
        self.assertEqual(summarize_checks(["FAIL", "NOT_RUN", "PASS"]), "FAIL")


if __name__ == "__main__":
    unittest.main()
