# STATUS — Game Now

**Atualizado:** 2026-11-10
**Branch:** `main`
**Últimas tarefas concluídas:** GN-024, GN-025, GN-032, **GN-030 (captura FFmpeg com testes em arquivos)** e **GN-015 (logs estruturados)**.
**Próxima tarefa executável:** **GN-031 — resolver áudio de transmissões públicas YouTube Live via yt-dlp e FFmpeg**, sem contornar restrições; exigir link de teste permitido para validar a operação real.
**Bloqueio físico paralelo:** GN-012 exige Windows do usuário; GN-085 exigirá áudio/navegador/modelos reais.

## Implementado e validado
- **GN-030:** `app/audio_capture.py` oferece capturador FFmpeg por subprocesso assíncrono para rádio MP3/AAC/HLS, PCM s16le mono 16 kHz, chunks alinhados, término de processo mesmo ao interromper e diagnóstico `python -m app.audio_capture --file arquivo.mp3 --seconds 5` ou `--url URL_PUBLICA`. A CI executou FFmpeg real contra fixtures geradas para MP3, AAC e HLS, mas **não** capturou uma rádio pública real nem foi executada no Windows. Para URL remota, verifica DNS público inicial; redirecionamentos/segmentos HLS e DNS rebind exigem GN-090.
- **GN-015:** `app/logging_setup.py` e middleware em `app/main.py` registram JSON por requisição com timestamp UTC, ID de requisição, método, caminho, status e duração, sem corpo/query/cookies, e adicionam header `X-Request-ID`. Log em `data/game_now.log` (ou `GAME_NOW_LOG_PATH`), rotativo a 2 MB com 3 backups. Testes para rotação e ausência de credenciais.
- **GN-024:** `app/match_flow.py`; `GET /api/matches/{id}/flow` e `POST /api/matches/{id}/actions`. Substituições com titulares/reservas elegíveis da mesma equipe; expulsões sem reposição; intervalo e início do segundo tempo com inversão automática de lado; acréscimos monotônicos e encerramento. Relógio não retrocede. Opções inválidas retornam 409/422; transação atômica atualiza partida, bundle v1 e log. Elenco e mudanças diretas de período/direção bloqueados após iniciar operações. Painel na interface.
- **GN-025:** `app/corrections.py`; `GET/POST /api/matches/{id}/corrections`. Correções de placar, posse e evento com motivo, autor, estado anterior/posterior e histórico imutável via API. Transações rejeitam entidade ou ID inválido. Editor legado de placar e troca de snapshot por PUT também geram auditoria. Formulário no site.
- **GN-032:** `app/source_validation.py`; cadastro/edição/ativação/desativação de fontes de rádio e YouTube pelo navegador e API existente. Persistência SQLite, URLs públicas básicas, rejeição de credenciais, esquemas inadequados e IPs locais. Não há captura nem reprodução de mídia no site.
- GN-020, GN-021, GN-022, GN-023 permanecem implementados: CRUD de partidas, elenco, identificação conservadora e SQLite. Contrato `ContractBundle` v1 não mudou.

## Testes e evidências
- GitHub Actions: https://github.com/vmendesneto/game_now/actions/runs/42886144524
- **35 testes aprovados** em **Python 3.11 e 3.12**, exportação/verificação de JSON schema, `node --check app/static/app.js`, FFmpeg instalado e executando codecs reais para testes.
- Novos testes: `tests/test_match_flow.py`, `tests/test_corrections.py`, `tests/test_sources.py`, `tests/test_audio_capture.py` (MP3/AAC/HLS, subprocesso e DNS) e `tests/test_logging.py` (log JSON/rotação). A suíte anterior permanece verde.
- Um aviso de depreciação de dependência observado na CI, sem falha. Não houve teste com rádio, YouTube ou Windows reais.

## Limitações importantes
- **GN-031 pendente**: GN-030 converte fontes de teste por FFmpeg e oferece CLI para rádio, mas o cadastro do navegador ainda não aciona capturadores. Não há transcrição ASR nem captura YouTube, nem rádio pública testada.
- `/api/demo/next`, `/api/state` e `/ws` operam demo **volátil** separada de `/api/matches/{id}/state` e operações de partida.
- Modelo de substituições não impõe limite/regra de competição (5 substituições, janelas, cartões amarelos e suspensões futuras). Corrigir a regra por competição antes de jogo oficial.
- Auditoria é durável no SQLite, mas administradores locais podem alterar o arquivo; não é trilha assinada. Servidor apenas `127.0.0.1`.
- Validação das URLs é superficial e feita no cadastro; ainda faltam regras DNS/redirecionamentos no processo de captura.
- `iniciar_windows.bat`, browsers físicos e GPU/CPU não foram testados em Windows. FFmpeg real foi testado apenas no Linux GitHub Actions.

## Continuar
1. Ler `STATUS.md`, `ROADMAP.md` e `AGENTS.md`; verificar HEAD de `main` e testes.
2. **GN-031**: adicionar resolução yt-dlp de transmissão pública permitida, extrair somente áudio e alimentar capturador FFmpeg. Não contornar DRM, paywall, login, restrições e não salvar cookies/tokens. Testar URL pública que autorize consumo e indisponibilidade; sem link validado, manter `[ ]`.
3. Avançar GN-033 (reconexão e URLs expiráveis), GN-034 (buffer PCM por fonte), F04 (ASR), sempre com testes. GN-012 precisa ser executado no Windows do usuário para conclusão.
4. Para rodar CI local: `python -m pip install -r requirements-dev.txt && python scripts/export_schema.py && python -m pytest -q`. Testes GN-030 precisam FFmpeg no PATH.
5. Servidor: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. Logs em `data/game_now.log`, registro JSON sem corpo das requisições.
