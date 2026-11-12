"""Opt-in real-media test through the actual browser start/stop controls.

Requires an isolated local database containing the authorized match and source.
Reports metadata only; Playwright traces/screenshots remain private in data/.
"""
import argparse
import json
import re
from pathlib import Path
import time
from urllib.parse import urlsplit


def run(args):
    from playwright.sync_api import expect, sync_playwright
    base = f"http://127.0.0.1:{args.port}"
    path = "/api/matches/" + args.match_id
    output = args.output
    output.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch()
        contexts, pages, errors, external, media = [], [], [], [], []
        report = {}
        started = False
        try:
            for _ in range(2):
                context = browser.new_context(viewport={"width": 1360, "height": 1000})
                contexts.append(context)
                context.tracing.start(screenshots=True, snapshots=True)
                context.on("request", lambda request: (
                    external.append(request.url) if urlsplit(request.url).netloc != f"127.0.0.1:{args.port}" else None))
                page = context.new_page()
                page.on("pageerror", lambda error: errors.append(str(error)))
                context.on("request", lambda request: media.append(request.url)
                           if request.resource_type == "media" else None)
                pages.append(page)
                page.goto(base)
                expect(page.locator("#field .ball-marker")).to_have_count(1)
                page.locator("#match-picker").select_option(args.match_id)
                expect(page.locator("#capture-source option[value='" + args.source_id + "']")).to_have_count(1)
            first, second = pages
            persisted_before = first.request.get(base + path + "/state").json()
            first.locator("#capture-source").select_option(args.source_id)
            first.locator("#capture-model").select_option(args.model)
            first.locator("#capture-start").fill(str(args.start_seconds))
            first.locator("#capture-seconds").fill(str(args.seconds))
            first.locator("#capture-window").fill(str(args.window_seconds))
            if args.parallel_source_id:
                first.locator("#capture-parallel").check()
                first.locator("#capture-kickoff").fill(str(args.kickoff_seconds))
                first.locator("#capture-second-source").select_option(args.parallel_source_id)
                first.locator("#capture-second-kickoff").fill(str(args.parallel_kickoff_seconds))
            first.locator("#capture-permission").check()
            first.locator("#capture-start-button").click()
            expect(first.locator("#capture-message")).to_contain_text("Acompanhamento iniciado")
            started = True
            deadline = time.monotonic() + args.seconds + 300
            requests, max_api_seconds = 0, 0.
            in_play_observed = False
            spatial_mention_observed = False
            marker_positions = []
            observed_actions = {}
            visible_players, visible_teams = set(), set()
            selected_sources, last_visual_time = [], 0.
            while time.monotonic() < deadline:
                at = time.monotonic()
                health = second.request.get(base + "/health")
                max_api_seconds = max(max_api_seconds, time.monotonic() - at)
                assert health.ok
                status = first.request.get(base + path + "/capture").json()
                preview = first.request.get(base + path + "/live/preview").json()
                if args.parallel_source_id and preview and preview.get("fusion"):
                    assert preview["visual_timeline"] >= last_visual_time
                    last_visual_time = preview["visual_timeline"]
                    selected = preview["fusion"]["active_source_id"]
                    if selected and (not selected_sources or selected_sources[-1] != selected):
                        selected_sources.append(selected)
                tracking = preview.get("latest_narration_action") if preview else None
                spatial_tracking = (preview.get("latest_narration_region_action") or tracking) if preview else None
                region = spatial_tracking.get("region") if spatial_tracking else None
                mention = preview.get("spatial_mention") if preview and not tracking else None
                if args.expect_actions and preview:
                    for action in preview.get("narration_actions", []):
                        observed_actions[action["id"]] = action
                    if tracking:
                        for page in pages:
                            marker = page.locator("#field .ball-marker")
                            expect(marker).to_have_attribute("data-latest-player-id", tracking["player_id"] or "")
                            expect(marker).to_have_attribute("data-latest-team-id", tracking["team_id"])
                            expect(page.locator("#possession-label")).to_have_text("Equipe do lance")
                        if tracking["player_id"]:
                            visible_players.add(tracking["player_id"])
                        visible_teams.add(tracking["team_id"])
                if args.expect_movement and (region or mention):
                    transforms = []
                    for page in pages:
                        expected = page.evaluate("""({region,mention}) => {
                          const cell=region?GameNowBallMarker.regionBounds(region):
                            GameNowField.zoneCellBounds({band:3,lane:mention.lane},mention.attack_direction||'left_to_right');
                          return `translate(${cell.x+cell.width/2} ${cell.y+cell.height/2})`;
                        }""", {"region": region, "mention": mention})
                        marker = page.locator("#field .ball-marker")
                        expect(marker).to_have_attribute("data-ball-state", "partial")
                        expect(marker).to_have_attribute("transform", expected)
                        transforms.append(marker.get_attribute("transform"))
                    if transforms[0] not in marker_positions:
                        marker_positions.append(transforms[0])
                        first.locator("#field").screenshot(path=str(output / f"movement-{len(marker_positions)}.png"))
                if (region or mention) and not spatial_mention_observed:
                    spatial_mention_observed = True
                    if args.expect_spatial_mention:
                        for page in pages:
                            rect = page.locator("#field .spatial-mention, #field .narration-region")
                            expect(rect).to_have_count(1)
                            assert float(rect.get_attribute("width")) > 900
                            expect(page.locator("#ball-status")).to_have_text(re.compile(r"(?:Corredor citado|Região parcial citada) · bola incerta"))
                            expect(page.locator("#field .region-highlight")).to_have_count(0)
                            marker=page.locator("#field .ball-marker")
                            expect(marker).to_have_attribute("data-ball-state","partial")
                            if (region or mention)["lane"]=="center":
                                expect(marker).to_have_attribute("transform","translate(500 310)")
                        first.locator("#field").screenshot(path=str(output / "partial-corridor.png"))
                if preview and preview["active"] and preview["phase"] == "in_play" and not in_play_observed:
                    in_play_observed = True
                    if args.expect_in_play:
                        for page in pages:
                            expect(page.locator("#live-monitor-state")).to_contain_text("Jogo em andamento")
                        first.screenshot(path=str(output / "in-play.png"), full_page=True)
                requests += 1
                if status["state"] in ("finished", "error", "stopped"):
                    break
                first.wait_for_timeout(1000)
            else:
                raise AssertionError("Capture did not finish within bounded browser test")
            assert status["state"] == "finished", status
            assert status["captured_seconds"] == args.seconds, status
            assert status["observations"] > 0, status
            if args.parallel_source_id:
                assert len(status["streams"]) == 2 and all(s["observations"] > 0 for s in status["streams"])
                assert len(set(selected_sources)) == 2, "Both sources must actually contribute selected play"
            if args.expect_in_play:
                assert in_play_observed, "Current play was not confirmed during the recording"
            if args.expect_spatial_mention:
                assert spatial_mention_observed, "No partial corridor reached the actual pitch"
            if args.expect_movement:
                assert len(marker_positions) >= 2, "Narration did not produce two different visible positions"
            if args.expect_actions:
                assert len(observed_actions) >= 10, "Fewer than ten named action annotations"
                assert len(visible_players) >= 4 and len(visible_teams) == 2, "Actors/teams did not update in both browsers"
            for page in pages:
                expect(page.locator("#transcript-entry-list li")).not_to_have_count(0)
                expect(page.locator("#transcript-entry-list")).not_to_contain_text("Nenhuma transcrição")
                expect(page.locator("#field .ball-marker")).to_have_count(1)
                expect(page.locator("#field .ball-marker")).to_have_attribute(
                    "data-ball-state", "stale" if spatial_mention_observed else "unknown")
                expect(page.locator("#field .spatial-mention")).to_have_count(0)
            assert first.request.get(base + path + "/state").json() == persisted_before
            assert not external and not media and not errors, (external, media, errors)
            assert first.locator("audio,video,iframe").count() == 0
            (output / "transcripts.json").write_text(json.dumps(
                first.request.get(base + path + "/transcripts").json(),
                ensure_ascii=False, indent=2), encoding="utf-8")
            first.screenshot(path=str(output / "finished.png"), full_page=True)
            first.locator("#capture-demo").click()
            expect(first.locator("#live-monitor-state")).to_be_hidden()
            expect(first.locator("#progress")).to_contain_text("relatos")

            # A second session must reset text epochs on both clients and stop via UI.
            expect(first.locator("#capture-start-button")).to_be_enabled(timeout=5000)
            first.locator("#capture-seconds").fill("60")
            first.locator("#capture-start-button").click()
            expect(first.locator("#capture-stop")).to_be_enabled()
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                active = first.request.get(base + path + "/capture").json()
                if active["captured_seconds"] >= 1:
                    break
                assert active["state"] not in ("error", "stopped", "finished"), active
                first.wait_for_timeout(250)
            assert active["captured_seconds"] >= 1, active
            expect(first.locator("#live-monitor-state")).to_be_visible()
            first.locator("#capture-stop").click()
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                stopped = first.request.get(base + path + "/capture").json()
                if stopped["state"] == "stopped":
                    break
                first.wait_for_timeout(250)
            assert stopped["state"] == "stopped", stopped
            assert first.request.get(base + path + "/live/preview").json() is None
            assert first.request.get(base + path + "/state").json() == persisted_before
            report = {"ok": True, "browser": browser.version, "model": args.model,
                      "start_seconds_requested": args.start_seconds, "media_start_verified": False,
                      "window_seconds": args.window_seconds, "captured_seconds": status["captured_seconds"],
                      "observations": status["observations"], "health_requests_during_capture": requests,
                      "max_health_request_seconds": round(max_api_seconds, 3), "two_browser_contexts": True,
                      "ui_start_restart_stop": True, "persisted_state_changed": False,
                      "stop_after_pcm_seconds": stopped["captured_seconds"],
                      "cpu_threads": status.get("cpu_threads"),
                      "audio_retransmitted": False, "javascript_errors": errors,
                      "external_browser_requests": len(external), "media_browser_requests": len(media),
                      "accuracy_measured": False}
            report["in_play_observed"] = in_play_observed
            report["spatial_mention_observed"] = spatial_mention_observed
            report["distinct_visible_positions"] = marker_positions
            report["movement_observed"] = len(marker_positions) >= 2
            report["named_actions"] = len(observed_actions)
            report["visible_players"] = sorted(visible_players)
            report["visible_teams"] = sorted(visible_teams)
            report["selected_source_sequence"] = selected_sources
            report["capture_streams"] = status.get("streams", [])
            report["ball_symbol_persisted_after_evidence_expired"] = True
            (output / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
            return report
        finally:
            if started and pages:
                pages[0].request.post(base + path + "/capture/stop")
            for index, context in enumerate(contexts):
                context.tracing.stop(path=str(output / f"trace-{index}.zip"))
                context.close()
            browser.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--match-id", required=True)
    parser.add_argument("--source-id", required=True)
    parser.add_argument("--permission-confirmed", action="store_true")
    parser.add_argument("--start-seconds", type=float, default=0)
    parser.add_argument("--seconds", type=int, default=30, choices=range(5, 601))
    parser.add_argument("--window-seconds", type=int, default=12, choices=range(6, 31))
    parser.add_argument("--model", choices=("tiny", "base", "small", "medium"), default="base")
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--port", type=int, default=8000, choices=range(1, 65536))
    parser.add_argument("--expect-in-play", action="store_true",
                        help="Require live-play phase in both browsers during this known game excerpt")
    parser.add_argument("--expect-spatial-mention", action="store_true",
                        help="Require a visibly partial five-band corridor without a confirmed ball zone")
    parser.add_argument("--expect-movement", action="store_true",
                        help="Require two different marker positions matching the received corridors in both browsers")
    parser.add_argument("--expect-actions", action="store_true",
                        help="Require ten named actions and visible updates of four players and both teams")
    parser.add_argument("--parallel-source-id")
    parser.add_argument("--kickoff-seconds", type=float)
    parser.add_argument("--parallel-kickoff-seconds", type=float)
    args = parser.parse_args()
    if args.parallel_source_id and (args.kickoff_seconds is None or args.parallel_kickoff_seconds is None):
        parser.error("Parallel recordings require both kickoff anchors")
    if not args.permission_confirmed:
        parser.error("Confirm authorization for the registered source")
    print(json.dumps(run(args), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
