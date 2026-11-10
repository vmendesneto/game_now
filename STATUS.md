# STATUS — Game Now

**Atualizado:** 2026-11-10
**Branch:** `main`
**Últimas tarefas concluídas:** GN-024, GN-025, GN-032, GN-030, GN-015, GN-034 e **GN-033/GN-037 (recuperação de captura e política de mídia)**.
**Próxima tarefa:** **GN-031 — prova com YouTube Live real e permitido**. Código de diagnóstico já existe, mas este ambiente não pode comprovar uma transmissão real autorizada; manter `[ ]`. Próxima implementação independente possível: GN-040 (ASR CPU, exige modelo real e benchmark).
**Bloqueio físico paralelo:** GN-012 exige Windows do usuário; GN-085 exigirá áudio/navegador/modelos reais.

## Diagnóstico Windows de 2026-11-10 (correção aguardando nova execução física)

- No primeiro teste no Windows 11 com Python 3.12: **49 passaram, 17 falharam**. Desses, quatro decorreram de FFmpeg ausente do `PATH` no PowerShell ainda aberto após a instalação pelo winget. Os outros treze apontaram `WinError 193`: os mocks de yt-dlp eram arquivos com shebang Unix, não executáveis Win32.
- Os scripts falsos de `tests/test_youtube_capture.py` e `tests/test_media_policy.py` agora terminam em `.py` e são lançados pelo próprio `sys.executable`, de forma portátil. O resolvedor passou a aceitar o módulo oficial `yt_dlp` instalado no mesmo ambiente Python quando o entrypoint não estiver no `PATH`. Foi acrescentado teste do fallback.
- O teste manual tentou `youtube.com/shorts/...`, que **não é YouTube Live**. Mesmo com yt-dlp localizado, esse link não comprovaria GN-031.
- **Ainda falta confirmar o resultado após essa correção no Windows físico e depois capturar cinco segundos de uma Live real autorizada**. Não declarar a suíte Windows aprovada, nem marcar GN-031 ou GN-012 como concluídas sem evidência. Ver instruções no README.

## Implementado e validado
- **GN-033:** `app/capture_supervisor.py` mantém um worker por fonte, reconecta com backoff exponencial limitado, detecta fluxo terminado/sem PCM e encerra rapidamente por `asyncio.Event`; cada retomada de YouTube invoca o resolvedor novamente. Acumula apenas PCM limitado pelo `MultiSourceAudioBuffer`, não URLs assinadas. `tests/test_capture_supervisor.py` cobre desconexão, retentativas, sessão parada, isolamento e timeout (fontes simuladas; não é validação de rádio/YouTube ao vivo).
- **GN-037:** URLs de fontes permanecem sob `app/source_validation.py`; yt-dlp agora é chamado com `--ignore-config`, `--no-cache-dir` e `--skip-download`. `tests/test_media_policy.py` valida rejeição de links indevidos, ausência de players no frontend e nenhuma gravação no diretório de simulação. O FFmpeg continua emitindo PCM por stdout. Verificação de SSRF em redirecionamentos/substreams continua GN-090.
- **GN-034:** `app/audio_buffer.py` implementa anel PCM 16 kHz por fonte, com timestamps timezone-aware monotônicos, janelas de tempo e orçamento em bytes, limitação explícita da quantidade de fontes e leitura protegida por lock. `tests/test_audio_buffer.py` simula 20.000 blocos em duas fontes com uso limitado de memória; não grava mídia no SQLite nem retransmite ao browser. O módulo ainda precisará ser conectado ao orquestrador de captura da GN-033/F04.
- **GN-030:** `app/audio_capture.py` oferece capturador FFmpeg por subprocesso assíncrono para rádio MP3/AAC/HLS, PCM s16le mono 16 kHz, chunks alinhados, término de processo mesmo ao interromper e diagnóstico `python -m app.audio_capture --file arquivo.mp3 --seconds 5` ou `--url URL_PUBLICA`. A CI executou FFmpeg real contra fixtures geradas para MP3, AAC e HLS, mas **não** capturou uma rádio pública real nem foi executada no Windows. Para URL remota, verifica DNS público inicial; redirecionamentos/segmentos HLS e DNS rebind exigem GN-090.
- **GN-015:** `app/logging_setup.py` e middleware em `app/main.py` registram JSON por requisição com timestamp UTC, ID de requisição, método, caminho, status e duração, sem corpo/query/cookies, e adicionam header `X-Request-ID`. Log em `data/game_now.log` (ou `GAME_NOW_LOG_PATH`), rotativo a 2 MB com 3 backups. Testes para rotação e ausência de credenciais.
- **GN-024:** `app/match_flow.py`; `GET /api/matches/{id}/flow` e `POST /api/matches/{id}/actions`. Substituições com titulares/reservas elegíveis da mesma equipe; expulsões sem reposição; intervalo e início do segundo tempo com inversão automática de lado; acréscimos monotônicos e encerramento. Relógio não retrocede. Opções inválidas retornam 409/422; transação atômica atualiza partida, bundle v1 e log. Elenco e mudanças diretas de período/direção bloqueados após iniciar operações. Painel na interface.
- **GN-025:** `app/corrections.py`; `GET/POST /api/matches/{id}/corrections`. Correções de placar, posse e evento com motivo, autor, estado anterior/posterior e histórico imutável via API. Transações rejeitam entidade ou ID inválido. Editor legado de placar e troca de snapshot por PUT também geram auditoria. Formulário no site.
- **GN-032:** `app/source_validation.py`; cadastro/edição/ativação/desativação de fontes de rádio e YouTube pelo navegador e API existente. Persistência SQLite, URLs públicas básicas, rejeição de credenciais, esquemas inadequados e IPs locais. Não há captura nem reprodução de mídia no site.
- GN-020, GN-021, GN-022, GN-023 permanecem implementados: CRUD de partidas, elenco, identificação conservadora e SQLite. Contrato `ContractBundle` v1 não mudou.

## Testes e evidências
- GitHub Actions: https://github.com/vmendesneto/game_now/actions/runs/42888042259
- **66 testes aprovados** em **Python 3.11 e 3.12** para a branch de entrega, exportação/verificação de JSON schema, `node --check app/static/app.js` e FFmpeg decodificando MP3/AAC/HLS de teste. Evidência: https://github.com/vmendesneto/game_now/actions/runs/42892117487.
- Novos testes: `tests/test_match_flow.py`, `tests/test_corrections.py`, `tests/test_sources.py`, `tests/test_audio_capture.py`, `tests/test_logging.py`, `tests/test_audio_buffer.py` (sessão longa, isolamento, limites, concorrência) e `tests/test_youtube_capture.py` (metadados sintéticos, falhas e diagnóstico seguro, **não** transmissão real), `tests/test_capture_supervisor.py` e `tests/test_media_policy.py`. Suíte anterior permanece verde.
- Um aviso de depreciação de dependência observado na CI, sem falha. Não houve teste com rádio, YouTube ou Windows reais.

## Limitações importantes
- **GN-031 parcialmente implementada, ainda [ ] no ROADMAP**: `app/youtube_capture.py` oferece diagnóstico CLI `python -m app.youtube_capture --url URL_LIVE_PERMITIDA --seconds 5` e resolução com subprocesso `yt-dlp` (`--ignore-config`, sem cookies/login), escolhe formato somente de áudio, valida URL retornada, descarta cabeçalhos de autenticação, usa FFmpeg e trata transmissão off-line, metadados inválidos, timeout e formatos indisponíveis. `tests/test_youtube_capture.py` exercita binário yt-dlp **simulado** e verificações de formatos DRM, metadados e captura de PCM fictício; **nenhum YouTube Live permitido real foi capturado**, `yt-dlp` real não foi instalado/testado no Windows. Precisa da URL autorizada e prova de execução real para marcar concluída. GN-030 converte fontes de teste e oferece CLI de rádio, mas o cadastro do navegador ainda não inicia captação. Não há ASR.
- `/api/demo/next`, `/api/state` e `/ws` operam demo **volátil** separada de `/api/matches/{id}/state` e operações de partida.
- Modelo de substituições não impõe limite/regra de competição (5 substituições, janelas, cartões amarelos e suspensões futuras). Corrigir a regra por competição antes de jogo oficial.
- Auditoria é durável no SQLite, mas administradores locais podem alterar o arquivo; não é trilha assinada. Servidor apenas `127.0.0.1`.
- Validação das URLs é superficial e feita no cadastro; ainda faltam regras DNS/redirecionamentos no processo de captura.
- `iniciar_windows.bat`, browsers físicos e GPU/CPU não foram testados em Windows. FFmpeg real foi testado apenas no Linux GitHub Actions.

## Continuar
1. Ler `STATUS.md`, `ROADMAP.md` e `AGENTS.md`; verificar HEAD de `main` e testes.
2. **GN-031 pendente**: `app/youtube_capture.py` já resolve metadados fictícios yt-dlp e prepara o fluxo áudio-only. Instalar uma versão confiável de yt-dlp, obter URL de transmissão pública com autorização de uso do sinal, testar resolução real e FFmpeg durante período reproduzível e validar indisponibilidade sem contornar DRM, paywall, login ou restrições. Até então, manter `[ ]`.
3. GN-033 já implementa reconexão em workers simulados, mas NÃO é iniciado pelo cadastro nem pelo site, e GN-037 estabeleceu política inicial sem gravação de mídia. Próximo trabalho após a prova real de GN-031 é integrar supervisão às fontes do painel e ASR (GN-040); GN-012 exige Windows do usuário.
4. Para rodar CI local: `python -m pip install -r requirements-dev.txt && python scripts/export_schema.py && python -m pytest -q`. Testes GN-030 precisam FFmpeg no PATH.
5. Servidor: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. Logs em `data/game_now.log`, registro JSON sem corpo das requisições.
