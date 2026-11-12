"""Ordered textual football actions, independent of a complete ball zone.

This is a volatile narration annotation, not the GN-056 position guard. Names
must resolve against the saved roster; incomplete geography stays incomplete.
Character order is not an invented audio timestamp or a physical trajectory.
"""
from __future__ import annotations

import re
import unicodedata

from app.contracts import Match
from app.narration_entities import NarrationResolveRequest, resolve_narration

_BAD = re.compile(
    r"\b(?:ontem|no jogo (?:passado|anterior)|semana passada|amanha|"
    r"no replay|reprise|repeticao|revendo|oferecimento|patrocinio|patrocinador|"
    r"publicidade|comercial|desconto|compre|cupom|na minha opiniao|"
    r"taticamente|formacao|esquema tatico|costuma|costumava|habitualmente|"
    r"poderia|deveria|talvez|imagino|acredito|se tivesse|vai receber|vai recuperar)\b", re.I)
_SUBJECT = re.compile(
    r"\b(?:recebeu|recebe|recebendo|dominou|domina|recuperou|recupera|"
    r"carrega|carregando|conduz|avanca|avancando|leva|levando|"
    r"chuta|chutou|cruza|cruzou|devolve|devolveu|retorna|retornou|serve|serviu)\b", re.I)
_TARGET = re.compile(
    r"\b(?:serve|serviu|servindo|aciona|acionando|"
    r"retorna com|retornou com|retornando com|retornando para|"
    r"devolve (?:para|pra|pro)|devolveu (?:para|pra|pro)|devolviu (?:para|pra|pro)|devolvendo (?:para|pra|pro)|"
    r"toca (?:para|pra|pro)|tocou (?:para|pra|pro)|passe (?:para|pra|pro)|"
    r"leva (?:para|pra|pro)|levando (?:para|pra|pro)|"
    r"abrindo o jogo (?:para|pra|pro)|recupera|recuperou|bola com|"
    r"dominio (?:da equipe )?(?:do|da))\b", re.I)
_GAP = re.compile(r"^(?:[\s,:-]|\b(?:ja|ainda|agora|de novo|tambem|o|a|equipe|do|da|"
                  r"no|na|de|pelo|pela|setor|campo|zona|lado|corredor|direito|esquerdo|central|"
                  r"defesa|defensa|ataque|aqui|que|meio-campo|intermediaria|ofensiva|defensiva)\b)*$", re.I)
_NOT_BALL = re.compile(r"^\s*(?:o |um |uma )?(?:cartao|atendimento|premio|aplausos|homenagem|oferta)\b", re.I)
_LANES = re.compile(r"\b(?:(?:lado|setor|sector|corredor|ponta|faixa) (?:(?:do|de) )?(esquerd[ao]|direit[ao]|central)|pela (esquerda|direita)|pelo (meio|centro))\b", re.I)
_AREAS = (
    (re.compile(r"\b(?:campo|metade|defesa) (?:adversari[ao]|do adversario|da adversaria|do rival)\b", re.I), [4, 5], "campo adversário"),
    (re.compile(r"\bintermediaria defensiva (?:adversaria|do adversario)\b", re.I), [4], "intermediária adversária"),
    (re.compile(r"\b(?:proprio|nosso) campo\b|\b(?:na|pela) defesa\b|\bsaindo de tras\b", re.I), [1, 2], "campo defensivo"),
    (re.compile(r"\b(?:setor|sector|campo|zona)(?: (?:de )?(?:direito|esquerdo|central))? de (?:defesa|defensa)\b|\barea defensiva\b", re.I), [1, 2], "defesa"),
    (re.compile(r"\bmeio(?:-| )campo\b|\bmeio do campo\b|\bcirculo central\b", re.I), [3], "meio-campo"),
    (re.compile(r"\b(?:setor|campo|zona) de ataque\b", re.I), [4, 5], "ataque"),
    (re.compile(r"\b(?:na |pela )?intermediaria defensiva\b", re.I), [2], "intermediária defensiva"),
    (re.compile(r"\b(?:na |pela )?intermediaria ofensiva\b|\bentrada da area adversaria\b", re.I), [4], "intermediária ofensiva"),
    (re.compile(r"\b(?:propria|nossa) (?:grande )?area\b", re.I), [1], "área defensiva"),
    (re.compile(r"\barea adversaria\b|\b(?:invade|invadindo) a grande area\b", re.I), [5], "área de ataque"),
)


def _geography(text: str, direction: str) -> dict | None:
    lanes = list(_LANES.finditer(text))
    lane = None
    if lanes:
        word = next(g for g in lanes[-1].groups() if g is not None).lower()
        lane = "left" if word.startswith("esquerd") else "right" if word.startswith("direit") else "center"
    areas = [(found.start(), found.end(), bands, label) for rule, bands, label in _AREAS for found in rule.finditer(text)]
    if not lanes and not areas:
        return None
    # A longer opponent-relative phrase overrides its generic defensive prefix.
    areas = [a for a in areas if not any(b[0] <= a[0] and b[1] > a[1] for b in areas)]
    _, _, bands, label = max(areas, key=lambda item: (item[0], item[1])) if areas else (0, 0, [1, 2, 3, 4, 5], "corredor")
    depth_basis = "explicit_text" if areas else "not_determined"
    if not areas and re.search(r"\bponta (?:esquerd[ao]|direit[ao])\b", text, re.I):
        bands, label, depth_basis = [4, 5], "ponta de ataque (estimativa)", "attacking_wing_estimate"
    return {"bands": bands, "lane": lane, "attack_direction": direction, "label": label,
            "basis": "partial_geography_in_action_text", "depth_basis": depth_basis, "exact_position": False}


def track_narration(match: Match, text: str) -> list[dict]:
    """Return a bounded ordered list; never infer motion from a player name alone."""
    if match.period not in ("first_half", "second_half") or not isinstance(text, str) or not 0 < len(text) <= 2048:
        return []
    folded = "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))
    # Ads and replay can scope an entire multi-sentence window.
    if re.search(r"\b(?:oferecimento|patrocinio|patrocinador|publicidade|comercial|cupom|no replay|reprise|revendo)\b", folded, re.I):
        return []
    events = []
    for sentence in re.finditer(r"[^.!?;]+[.!?;]?", folded):
        clause = sentence.group()
        if _BAD.search(clause) or clause.rstrip().endswith("?"):
            continue
        resolution = resolve_narration(match, NarrationResolveRequest(text=clause))
        mentions = [m for m in resolution.mentions if m.kind in ("player", "team", "unknown")]
        candidates = []
        for target, pattern in ((False, _SUBJECT), (True, _TARGET)):
            for cue in pattern.finditer(clause):
                if _NOT_BALL.search(clause[cue.end():]):
                    continue
                nearby = [m for m in mentions if (
                    0 <= m.start - cue.end() <= 20 and _GAP.fullmatch(clause[cue.end():m.start])
                    if target else 0 <= cue.start() - m.end <= 45 and _GAP.fullmatch(clause[m.end:cue.start()]))]
                if not nearby:
                    continue
                mention = min(nearby, key=lambda m: m.start) if target else max(nearby, key=lambda m: m.end)
                if mention.status != "resolved" or mention.team_id is None:
                    continue
                if mention.kind == "team":
                    associated = [m for m in mentions if m.kind == "player" and m.status == "resolved"
                        and m.team_id == mention.team_id and (
                        0 <= m.start-mention.end <= 15 and re.fullmatch(r"\s+com\s*", clause[mention.end:m.start], re.I)
                        if target else 0 <= mention.start-m.end <= 10 and re.fullmatch(r"\s+(?:do|da)\s*", clause[m.end:mention.start], re.I))]
                    if len(associated) == 1:
                        mention = associated[0]
                if not target and re.search(
                    r"\b(?:marcacao|pressao|pernada|bracada|desarme) (?:do|da|de)\s*$",
                    clause[max(0, mention.start-45):mention.start], re.I):
                    continue  # An opponent being escaped is not the next passer.
                start, end = min(mention.start, cue.start()), max(mention.end, cue.end())
                # A negation immediately before the subject/verb is not a touch.
                if re.search(r"\b(?:nao|nunca|jamais|vai|iria|deveria|poderia)\b[^,.:;!?]{0,24}$", clause[max(0, start-40):start], re.I):
                    continue
                kind = "pass_target" if target else "ball_action"
                if re.match(r"recuper|bola com|dominio", cue.group(), re.I):
                    kind = "recovery" if cue.group().lower().startswith("recuper") else "control"
                candidates.append({"start": start, "end": end, "cue_start": cue.start(),
                    "player_id": mention.player_id, "team_id": mention.team_id,
                    "kind": kind, "cue": cue.group().lower()})
        # Elliptical play-by-play often cites the next teammate and corridor
        # without repeating a reception verb. Preserve that as a weaker mention,
        # never a confirmed touch and never a turnover inferred from a name.
        strong = candidates.copy()
        for mention in mentions:
            if mention.kind != "player" or mention.status != "resolved" or not strong:
                continue
            if any(item["start"] <= mention.start and mention.end <= item["end"] for item in strong):
                continue
            nearby = min(strong, key=lambda item: abs(item["cue_start"]-mention.start))
            if mention.team_id != nearby["team_id"] or abs(nearby["cue_start"]-mention.start) > 160:
                continue
            following = clause[mention.end:mention.end+50]
            preceding = clause[max(0, mention.start-45):mention.start]
            if re.match(r"^[\s,]*(?:trava|marca|pressiona|disputa|aperta|esta|ocupa|pede|espera|sem a bola)\b", following, re.I):
                continue
            if re.search(r"\b(?:marcacao|pressao|pernada|bracada|desarme) (?:do|da|de)\s*$", preceding, re.I):
                continue
            candidates.append({"start": mention.start, "end": mention.end,
                "cue_start": mention.start, "player_id": mention.player_id, "team_id": mention.team_id,
                "kind": "named_sequence", "cue": "menção em sequência"})
        candidates.sort(key=lambda e: (e["cue_start"], e["start"]))
        for index, item in enumerate(candidates):
            stop = candidates[index+1]["start"] if index+1 < len(candidates) else len(clause)
            stop = max(item["end"], stop)
            other_names = [m.start for m in mentions if m.kind == "player"
                           and m.player_id != item["player_id"] and m.start >= item["end"]]
            if other_names:
                stop = max(item["end"], min(stop, min(other_names)))
            fragment = clause[item["start"]:min(stop, item["end"]+140)].strip(" ,.;")
            # Spatial context immediately before a named receiver can be useful,
            # but never borrow geography across another named participant.
            prefix_start = max(0, item["start"]-55)
            prefix = clause[prefix_start:item["start"]]
            if any(m.start >= prefix_start and m.end <= item["start"] for m in mentions):
                prefix = ""
            team = match.home if match.home.id == item["team_id"] else match.away
            event = {"player_id": item["player_id"], "team_id": item["team_id"],
                     "kind": item["kind"], "cue": item["cue"], "text": fragment,
                     "touch_confirmed": False,
                     "text_offset": sentence.start()+item["cue_start"],
                     "region": _geography(prefix+fragment, team.attack_direction),
                     "basis": ("elliptical_teammate_mention_in_current_play" if item["kind"] == "named_sequence"
                               else "explicit_named_action_in_narration"), "audio_time_verified": False}
            if not events or (event["player_id"],event["kind"],event["text_offset"]) != (
                    events[-1]["player_id"],events[-1]["kind"],events[-1]["text_offset"]):
                events.append(event)
    depth = None
    for event in events:
        region = event["region"]
        same = depth is not None and depth["player_id"] == event["player_id"] and event["text_offset"]-depth["text_offset"] <= 120
        if region and region["lane"] in ("left", "right") and same and (
                region["depth_basis"] == "not_determined" or
                region["depth_basis"] == "attacking_wing_estimate" and depth["region"]["depth_basis"] == "explicit_text"):
            event["region"] = {**region, "bands": depth["region"]["bands"].copy(),
                "label": depth["region"]["label"], "depth_basis": "recent_same_player_context"}
        if event["region"] and event["region"]["bands"] != [1, 2, 3, 4, 5]:
            if not same or region["depth_basis"] == "explicit_text":
                depth = event
        elif not same or region and region["lane"] == "center":
            depth = None
    return events[-32:]
