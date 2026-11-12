"""Opt-in real browser checks against an isolated launcher on 127.0.0.1:8000.

Use a disposable checkout/database: this scenario advances the demo and saves a
test match. No media is requested. Playwright is an optional test dependency.
Run again with --verify-persisted after stopping/restarting the launcher.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import platform
from urllib.parse import urlsplit

URL = "http://127.0.0.1:8000"
HOME = "Validação Windows GN-012"
AWAY = "Visitante de teste"


def run(output: Path, *, verify_persisted: bool = False) -> dict:
    from playwright.sync_api import expect, sync_playwright

    output.mkdir(parents=True, exist_ok=True)
    errors: list[str] = []
    external: list[str] = []
    media: list[str] = []
    checks: list[str] = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        contexts = []

        def new_page(**options):
            context = browser.new_context(**options)
            contexts.append(context)
            context.tracing.start(screenshots=True, snapshots=True)

            def request_seen(request):
                if urlsplit(request.url).hostname != "127.0.0.1":
                    external.append(request.url)
                if request.resource_type == "media":
                    media.append(request.url)

            context.on("request", request_seen)
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(URL)
            expect(page.locator("#connection-dot")).to_have_class("dot online")
            expect(page.locator("#field")).to_be_visible()
            return page

        try:
            page = new_page(viewport={"width": 1440, "height": 1000})
            health = page.request.get(URL + "/health")
            assert health.ok and health.json()["mode"] == "synthetic_demo"
            checks.append("HTTP health + real browser WebSocket connected")

            if verify_persisted:
                expect(page.locator("#home-input")).to_have_value(HOME)
                expect(page.locator("#away-input")).to_have_value(AWAY)
                expect(page.locator("#player-list")).to_contain_text("Atleta de teste")
                expect(page.locator("#source-list")).to_contain_text("Fonte de teste sem captura")
                checks.append("match, roster and source survived launcher restart")
            else:
                peer = new_page(viewport={"width": 1280, "height": 900})
                page.locator("#reset").click()
                for client in (page, peer):
                    expect(client.locator("#progress")).to_have_text("0 / 8 relatos")
                actions = [
                    "Posse identificada", "Relato repetido · lance já contabilizado",
                    "Intervalo comercial · sem novo lance", "Cruzamento", "GOL!",
                    "Relato repetido · lance já contabilizado", "Replay · sem novo lance",
                    "Sem novo lance confirmado",
                ]
                for step, action in enumerate(actions, 1):
                    page.locator("#next").click()
                    for client in (page, peer):
                        expect(client.locator("#progress")).to_have_text(f"{step} / 8 relatos")
                        expect(client.locator("#action")).to_have_text(action)
                        expect(client.locator("#home-score")).to_have_text("1" if step >= 5 else "0")
                expect(page.locator("#next")).to_be_disabled()
                peer.locator("#reset").click()
                expect(page.locator("#progress")).to_have_text("0 / 8 relatos")
                checks.append("eight demo steps + duplicate/replay scoring + two independent browser contexts")

                page.locator("#match-new").click()
                page.locator("#home-input").fill(HOME)
                page.locator("#away-input").fill(AWAY)
                page.locator("#home-short").fill("WIN")
                page.locator("#away-short").fill("TST")
                page.locator("#match-save").click()
                expect(page.locator("#match-message")).to_have_text("Partida salva no SQLite.")
                page.locator("#player-name").fill("Atleta de teste")
                page.locator("#player-number").fill("9")
                page.locator("#player-form button[type=submit]").click()
                expect(page.locator("#player-list")).to_contain_text("Atleta de teste")
                page.locator("#source-name").fill("Fonte de teste sem captura")
                page.locator("#source-url").fill("https://example.org/test.mp3")
                page.locator("#source-enabled").uncheck()
                page.locator("#source-form button[type=submit]").click()
                expect(page.locator("#source-list")).to_contain_text("Fonte de teste sem captura")
                checks.append("match + roster + disabled source saved through UI")

                mobile = new_page(viewport={"width": 390, "height": 844},
                                  is_mobile=True, has_touch=True, reduced_motion="reduce")
                assert mobile.evaluate("document.documentElement.scrollWidth <= innerWidth"), "mobile horizontal overflow"
                expect(mobile.locator("#field")).to_be_visible()
                mobile.screenshot(path=str(output / "mobile.png"), full_page=True)
                checks.append("390px mobile emulation + reduced motion + no horizontal overflow")

            page.screenshot(path=str(output / "desktop.png"), full_page=True)
            assert not errors, errors
            assert not external, external
            assert not media, media
            assert page.locator("audio,video,iframe").count() == 0
            checks.append("no JavaScript errors, external HTTP requests or media players")
            report = {"ok": True, "os": platform.platform(), "python": platform.python_version(),
                      "browser": browser.version, "verify_persisted": verify_persisted,
                      "checks": checks, "external_media_processed": False,
                      "limitations": "Mobile is emulated; no real narration, ASR quality or full match tested."}
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            return report
        finally:
            for index, context in enumerate(contexts):
                context.tracing.stop(path=str(output / f"trace-{index}.zip"))
                context.close()
            browser.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--verify-persisted", action="store_true")
    args = parser.parse_args()
    print(json.dumps(run(args.output, verify_persisted=args.verify_persisted), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
