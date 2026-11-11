# GN-050 — Separação de narração esportiva (pt-BR)

O classificador `app/narration_classifier.py` recebe texto **já transcrito** e devolve `kind`, `reason` e `eligible_for_live_state`. Não instala modelos, não capta mídia e não utiliza serviços pagos. Tipos: `live_play`, `ad`, `conversation`, `analysis`, `replay`, `unknown`.

O feed volátil (`GET /api/matches/{id}/transcripts` e WebSocket) passa a incluir `narration_kind`, `classification_reason` e `eligible_for_live_state` em cada entrada, mantendo texto, fonte e horários existentes. `conversation` é apenas categoria do feed, **não modifica o ContractBundle v1**; nenhuma categoria altera placar, posse ou bola automaticamente.

## Corpus e teste

`fixtures/narration_corpus_v1.json` contém 50 frases **sintéticas e originais** em português, rotuladas manualmente (10 lances atuais; 8 de cada categoria não-live/unknown). Casos de gol em comercial, chute em análise e lance em replay são cobertos. `tests/test_narration_classifier.py` confere todos os rótulos, negação de elegibilidade para não-live, isolamento de fontes e campos no feed. Executar `python -m pytest -q tests/test_narration_classifier.py`.

## Limitações declaradas

Regras lexicais têm cobertura restrita e **não fornecem probabilidade estatística**. Acurácia em 50 frases criadas para teste não é acurácia em transmissões reais; não substituir GN-058 (corpus real licenciado), nem GN-083 (validação). Uma frase com indicação explícita de propaganda/replay/análise/conversa prevalece sobre lances no mesmo segmento. Um `live_play` é apenas candidato à análise: GN-051 a GN-056 precisam confirmar entidades, lances, tempo e posição. Em caso de dúvida classificar como `unknown` e não atualizar o estado. Nenhum áudio, URL assinada ou credencial aparece nos metadados de classificação.

## Evidência de CI (2026-11-11)

Workflow completo Python 3.11/3.12: **170 passed, 2 skipped, 1 warning**, incluindo o corpus novo e compatibilidade com o feed, em https://github.com/vmendesneto/game_now/actions/runs/43021883387. Smoke ASR real separado: https://github.com/vmendesneto/game_now/actions/runs/43021883417. O teste do classificador usa somente frases sintéticas, sem validação com transmissão real.
