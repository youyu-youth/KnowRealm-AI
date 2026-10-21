"""隔离服务的只读浏览器预检；使用已安装的 Python Playwright。"""

import argparse
import json
import os
import re
from pathlib import Path
from urllib.parse import urlsplit

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--frontend-url", required=True)
    parser.add_argument("--api-url", required=True)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args()
    token = os.environ.get("KNOWREALM_SMOKE_TOKEN")
    if not token:
        parser.error("请通过 KNOWREALM_SMOKE_TOKEN 提供隔离服务的启动令牌")
    args.output.mkdir(parents=True, exist_ok=True)
    locales = [
        json.loads((ROOT / f"apps/desktop/src/i18n/locales/{lang}.json").read_text("utf-8"))["chat"]
        for lang in ("zh", "en")
    ]
    mocks = (ROOT / "apps/desktop/node_modules/@tauri-apps/api/mocks.js").read_text("utf-8")
    mocks = mocks.replace("export { clearMocks, mockConvertFileSrc, mockIPC, mockWindows };", "")
    config = json.dumps({"baseUrl": args.api_url.rstrip("/"), "token": token})
    report: dict[str, object] = {"status": "FAILED", "page_errors": [], "http_errors": []}
    page_errors: list[str] = []
    http_errors: list[dict[str, str | int]] = []
    with sync_playwright() as playwright, playwright.chromium.launch() as browser:
        context = browser.new_context(viewport={"width": 1440, "height": 1000}, locale="zh-CN")
        context.add_init_script(
            mocks + f"\nmockIPC(cmd => cmd === 'get_sidecar_config' ? {config} : "
            "cmd === 'get_onboarding_state' ? true : null, {shouldMockEvents:true}); "
            "mockWindows('main');"
        )
        page = context.new_page()
        page.on("pageerror", lambda error: page_errors.append(str(error)))
        # AVATAR_NOT_SET 的 404 是空头像正常态，其余业务失败继续报错。
        page.on(
            "response",
            lambda response: (
                http_errors.append({"status": response.status, "path": urlsplit(response.url).path})
                if "/api/" in response.url
                and response.status >= 400
                and not (
                    response.status == 404 and urlsplit(response.url).path == "/api/profile/avatar"
                )
                else None
            ),
        )
        try:
            response = context.request.get(
                args.api_url.rstrip("/") + "/api/agents", headers={"X-KnowRealm-Token": token}
            )
            report["api_status"] = response.status
            assert response.status == 200, f"Agent 目录 HTTP {response.status}"
            frontend = urlsplit(str(args.frontend_url))
            origin = f"{frontend.scheme}://{frontend.netloc}"
            cors = context.request.fetch(
                args.api_url.rstrip("/") + "/api/agents",
                method="OPTIONS",
                headers={
                    "Origin": origin,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "X-KnowRealm-Token",
                },
            )
            report["cors_status"] = cors.status
            assert cors.headers.get("access-control-allow-origin") == origin, (
                f"隔离 API 未允许前端 Origin {origin}；"
                "请在测试服务 create_app(cors_origins=[...]) 中显式允许该 Origin"
            )
            page.goto(args.frontend_url.rstrip("/") + "/chat")
            sidebar = page.get_by_role(
                "complementary",
                name=re.compile(
                    "^(" + "|".join(re.escape(locale["listLabel"]) for locale in locales) + ")$"
                ),
            )
            trigger = sidebar.get_by_role(
                "button",
                name=re.compile(
                    "^(" + "|".join(re.escape(locale["newSession"]) for locale in locales) + ")$"
                ),
            )
            expect(trigger).to_have_count(1)
            expect(trigger).to_be_enabled()
            trigger.click()
            menu = page.get_by_role("menu")
            expect(menu).to_be_visible()
            expect(menu.get_by_role("menuitemradio")).to_have_count(len(response.json()))
            page.keyboard.press("Escape")
            expect(trigger).to_be_focused()
            assert not page_errors and not http_errors, "页面或业务 HTTP 出错"
            report["status"] = "PASSED"
        except Exception as error:
            report["error"] = str(error).replace(token, "<REDACTED>")
            raise
        finally:
            report["page_errors"] = page_errors
            report["http_errors"] = http_errors
            page.screenshot(path=str(args.output / "page.png"))
            (args.output / "result.json").write_text(
                json.dumps(report, ensure_ascii=False, indent=2).replace(token, "<REDACTED>"),
                encoding="utf-8",
            )
            print(f"{report['status']}: {args.output / 'result.json'}")


if __name__ == "__main__":
    main()
