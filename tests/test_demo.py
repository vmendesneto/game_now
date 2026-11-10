from app.demo import DemoEngine, interpret_demo_text
from app.contracts import Category, EventKind, ContractBundle


def test_interpretation_conservatively_rejects_ads_replays_and_vague_text():
    for text, category in [
        ("Oferecimento especial!", Category.AD),
        ("Replay do gol do atacante.", Category.REPLAY),
        ("Agora a análise do jogo.", Category.ANALYSIS),
        ("Futebol muito movimentado.", Category.UNKNOWN),
    ]:
        actual, event, zone = interpret_demo_text(text)
        assert actual == category
        assert event is None and zone is None


def test_demo_deduplicates_preidentified_scenario_keys_and_expires_ball():
    engine = DemoEngine()
    state = engine.step()
    first_zone = state["data"]["ball"]["zone"]
    assert first_zone == {"band": 3, "lane": "right"}
    state = engine.step()
    assert len(state["data"]["events"]) == 1
    assert len(state["data"]["events"][0]["source_ids"]) == 2
    state = engine.step()
    assert state["data"]["ball"]["zone"] == first_zone
    assert len(state["data"]["events"]) == 1
    state = engine.step()
    assert state["data"]["ball"]["zone"] == {"band": 4, "lane": "center"}
    state = engine.step()
    assert state["data"]["match"]["home_score"] == 1
    state = engine.step()
    assert state["data"]["match"]["home_score"] == 1
    assert len(state["data"]["events"]) == 3
    state = engine.step()
    assert state["data"]["ball"]["zone"] == {"band": 5, "lane": "center"}
    state = engine.step()
    assert state["data"]["ball"]["zone"] is None
    assert state["data"]["ball"]["uncertainty"] == "expired"
    assert len(state["data"]["segments"]) == 8
    ContractBundle.model_validate(state["data"])
    assert engine.step() == state
    reset = engine.reset()
    assert reset["step"] == 0
    assert reset["data"]["events"] == []


def test_unknown_location_does_not_invent_zone():
    category, kind, zone = interpret_demo_text("Caio chuta!")
    assert category == Category.LIVE_PLAY
    assert kind == EventKind.SHOT
    assert zone is None
