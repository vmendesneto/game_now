# Classificação no feed de transcrições — extensão GN-050

O classificador `app/narration_classifier.py` já existente recebe textos ASR. Esta extensão liga o resultado à publicação do feed volátil `GET /api/matches/{id}/transcripts` e `/ws/matches/{id}/transcripts`. Cada entrada inclui `narration_kind` (live_play/ad/conversation/analysis/replay/unknown), `classification_reason` (regra literal ou ausência de pista) e `eligible_for_live_state` (booleano).

Metadados são independentes por fonte e aditivos: texto, idioma, sequência e timestamps continuam como antes. Textos acima do limite de 2048 caracteres do classificador recebem `unknown` e `eligible_for_live_state=false`, **sem perder a transcrição**. Resultados de regras são apenas candidatos para GN-051–056, não alteram bola, posse, jogadores nem placar; não há mídia, URL de streaming ou novos endpoints de ingestão.

Verificar com `python -m pytest -q tests/test_transcription_feed.py tests/test_narration_classifier.py`. Este teste usa texto sintético: não comprova narração real nem análise correta de eventos. O contrato persistente v1 não muda.
