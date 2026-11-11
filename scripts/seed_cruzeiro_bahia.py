"""Registra no SQLite Cruzeiro x Bahia com escalações fornecidas ao Game Now.

34ª rodada. Sem capturar áudio, inferir placar real ou sobrescrever elenco editado.
Uso: python -m scripts.seed_cruzeiro_bahia
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.configuration import MatchConfig, RosterPlayer
from app.contracts import Team
from app.storage import SQLiteStore, StoreConflict

MATCH_ID = "cruzeiro-bahia-gn083"

# Camisa, nome, posição. As posições dos atletas de linha não constam da imagem.

CRUZEIRO_TITULARES = (
    (81, "Otávio", "goalkeeper"),
    (23, "Fagner", "other"),
    (15, "Fabrício Bruno", "other"),
    (34, "Jonathan Jesus", "other"),
    (27, "Rojas", "other"),
    (29, "Lucas Romero", "other"),
    (5, "Zé Lucas", "other"),
    (8, "Gerson", "other"),
    (9, "Bruno Rodrigues", "other"),
    (99, "Arroyo", "other"),
    (19, "Kaio Jorge", "other"),
)

CRUZEIRO_RESERVAS = (
    (1, "Cássio", "goalkeeper"),
    (41, "Léo Aragão", "goalkeeper"),
    (2, "Kauã Moraes", "other"),
    (6, "Viña", "other"),
    (16, "Lucas Silva", "other"),
    (7, "Matheus Henrique", "other"),
    (11, "Marquinhos", "other"),
    (20, "Wesley", "other"),
    (67, "João Costa", "other"),
    (94, "Wanderson", "other"),
    (22, "Neyser", "other"),
    (97, "Lucho Rodríguez", "other"),
)

BAHIA_TITULARES = (
    (1, "Ronaldo", "goalkeeper"),
    (44, "Marcos Victor", "other"),
    (33, "David Duarte", "other"),
    (4, "Kanu", "other"),
    (46, "Luciano Juba", "other"),
    (5, "Acevedo", "other"),
    (14, "Erick", "other"),
    (11, "Nestor", "other"),
    (10, "Everton Ribeiro", "other"),
    (99, "Kike Oliveira", "other"),
    (9, "Alejo Véliz", "other"),
)

BAHIA_RESERVAS = (
    (17, "Guido Herrera", "goalkeeper"),
    (43, "Luiz Gustavo", "other"),
    (31, "Roman Gomez", "other"),
    (66, "Zé Guilherme", "other"),
    (8, "Caio Alexandre", "other"),
    (6, "Jean Lucas", "other"),
    (15, "Michel Araújo", "other"),
    (16, "Erick Pulga", "other"),
    (23, "Sanabria", "other"),
    (7, "Ademir", "other"),
    (77, "Ruan Pablo", "other"),
    (27, "Everaldo", "other"),
)


def match_config() -> MatchConfig:
    # Ataque, horário, placar e relógio reais não constam das duas imagens.
    return MatchConfig(
        id=MATCH_ID,
        home=Team(id="cruzeiro", name="Cruzeiro", short_name="CRU",
                  color="#0047AB", attack_direction="left_to_right"),
        away=Team(id="bahia", name="Bahia", short_name="BAH",
                  color="#E44148", attack_direction="right_to_left"),
    )


def roster() -> list[RosterPlayer]:
    players: list[RosterPlayer] = []
    for team_id, starters, reserves in (
        ("cruzeiro", CRUZEIRO_TITULARES, CRUZEIRO_RESERVAS),
        ("bahia", BAHIA_TITULARES, BAHIA_RESERVAS),
    ):
        for starter, group in ((True, starters), (False, reserves)):
            for number, name, position in group:
                players.append(RosterPlayer(
                    id=f"{team_id}-{number}", team_id=team_id, name=name,
                    number=number, starter=starter, position=position,
                ))
    return players


def seed(store: SQLiteStore) -> str:
    """Cria o cadastro; não sobrescreve escalações manualmente alteradas."""
    config = match_config()
    expected = roster()
    existing = store.get_match(MATCH_ID)
    if existing is None:
        store.create_match(config)
        result = "created"
    else:
        if existing.home.id != config.home.id or existing.away.id != config.away.id:
            raise StoreConflict("Existing match ID belongs to different teams")
        current = store.get_roster(MATCH_ID)
        if current == expected:
            return "already_exists"
        if current:
            raise StoreConflict("Existing roster differs; refusing to overwrite manual edits")
        result = "roster_added"
    store.replace_roster(MATCH_ID, expected)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Seed Cruzeiro x Bahia 34ª rodada (GN-083)")
    parser.add_argument("--db", type=Path, help="SQLite path; default Game Now data directory")
    args = parser.parse_args(argv)
    try:
        store = SQLiteStore(args.db)
        status = seed(store)
        saved = store.get_match(MATCH_ID)
        assert saved is not None
    except (ValueError, StoreConflict, OSError) as exc:
        parser.exit(2, f"Cadastro Cruzeiro x Bahia: {exc}\n")
    print(json.dumps({
        "status": status,
        "match_id": saved.id,
        "home": saved.home.name, "away": saved.away.name,
        "players": len(saved.players),
        "starters": sum(p.starter for p in saved.players),
        "reserves": sum(not p.starter for p in saved.players),
    }, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
