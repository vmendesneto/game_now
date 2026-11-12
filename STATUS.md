# STATUS — Game Now

## GN-044 — ferramenta de benchmark Whisper (parcial; validação Windows pendente, 2026-11-11)

- `scripts/benchmark_gn044_whisper.py`: executa cada modelo em processo independente, com parâmetros CPU ou CUDA (opt-in), amostras WAV locais de até 30s e texto de referência humana; mede WER por edição normalizada de palavras (rotina GN-083), latência, wall/CPU e pico RSS/working set do processo. Não serializa PCM, referências ou transcrições, nem abre YouTube. Configuração explicitamente exige `--permission-confirmed`; instalação ASR opt-in.
- `tests/test_gn044_benchmark.py` testa manifesto, WER, processo independente, segurança de erros e modo worker usando modelo falso. `docs/GN-044.md` explica execução CPU/GPU no Windows, restrições e interpretação. **GN-044 fica [ ]** porque CI sintética não mede modelos reais em Windows, e ainda faltam referência humana autorizada e comparação real. Próxima ação humana eventual: coletar amostra autorizada + transcrição própria e executar a CLI no Windows, sem refazer testes de captura GN-083.
- GN-093 PR #54 incorporada à main (commit `9e344a2`), CI final PR 43136963648: 660 passed/3 skipped em Python 3.11/3.12; CI pós-merge `43137044232` verde. Não foi testado handshake TLS/Windows físico.


## GN-093 — segurança de acesso remoto (2026-11-11)

- Adicionado guard ASGI para HTTP e WebSocket: por padrão bloqueia peers não-loopback, host não local e cross-origin; com `GAME_NOW_REMOTE_ACCESS=1`, recusa HTTP simples e exige token forte, segredo HMAC independente, cookie HttpOnly/Secure/SameSite e Origin em mutações/WS. Comando opt-in `scripts.serve_secure` exige certificado/chave TLS para bind remoto; não ativa acesso LAN automaticamente.
- `docs/GN-093.md` tem matriz de ameaças e limites. `tests/test_gn093_security.py` é teste de transporte ASGI/HTTPS simulado, **não** prova handshake/certificado/firewall/Windows. CI do PR #54 antes da atualização final de documentação/teste (run 43136644521): **660 passed/3 skipped** em Python 3.11/3.12. Prefixo `__Host-` já estava correto e ganhou asserção explícita; comandos Windows alterados para compatibilidade com PowerShell 5.1. GN-093 [x], sujeito a nova CI verde do último commit antes do merge; sem teste TLS/Windows físico.

## GN-086 — comprovada em CI, 2026-11-11

- PR #53 incorporado na main (commit `dd8b890`). CI 43135477752: **654 passed, 3 skipped** em Python 3.11 e 3.12. Smoke CPU real 43135477705: **3 passed** com duas sessões de Whisper tiny independentes e fala TTS pt-BR; 6 inferências, duas simultâneas em pico, 5,008 s por fonte, **717,16 MiB de RSS pico**, **266,1% de CPU de um núcleo**, **0,97 segundos de áudio agregado por segundo de parede**. O conjunto de duas fontes não sustentou tempo real nessa VM. Modelo/duração/buffer ajustáveis por CLI. Sem desempenho real Windows, rádio, precisão ou 90 min. GN-086 [x] no ROADMAP; próximo GN-093.


## GN-016 — limpeza das sessões de captura (2026-11-11)

- `CaptureSessionController` é dono das tarefas de captura, permite iniciar/parar por fonte e fecha os workers de forma cooperativa ou por cancelamento após timeout, aguardando `CaptureSupervisor.run` e seu encerramento final. Reinício recria novo controlador, sem restauração de workers/URLs assinadas.
- Proteção contra corrida `ProcessLookupError` no kill do subprocesso em `app/audio_capture.py`.
- `tests/test_gn016_shutdown.py`: fontes concorrentes simuladas, parada idempotente, reinício e verificações de reap do PID de um subprocesso REAL que emite PCM sintético. Evidência Linux na CI; nenhuma sessão real de rádio/YouTube ou ciclo de reinício foi testado fisicamente em Windows.
- **Limites:** controlador é primitivo Python; não existe botão start/stop de captura real na API. GN-085 exige validação física de ausência de processos órfãos no Windows. GN-083 continua [ ] aguardando início real do jogo e avaliação com gabarito. Depois: GN-036 (VAD com benchmark) ou GN-086 (desempenho simultâneo).


## GN-094 — política de fontes e retenção de transcrições (2026-11-11)

- `docs/GN-094.md`: inventário de licenças das dependências **diretas** declaradas e executáveis opcionais com links oficiais, restrições de uso de fontes e lista explícita de pontos que exigem auditoria antes de redistribuir. Esta revisão não concede autorização para captar YouTube/rádio nem valida termos de binários instalados.
- `app/retention_policy.py` define TTL 60..604800 segundos (padrão 3600) e limite 1..500 entradas por fonte (padrão 100) via ambiente, com validação estrita. O feed purga texto expirado ao consultar/publicar, sem gravá-lo no SQLite. A UI descarta textos vencidos e recebe `retention_seconds`. Logs, backups e registros persistidos têm ciclos de vida separados.
- Testes novos: `tests/test_gn094_retention.py` e `tests/test_gn094_retention.cjs`; validação de integração Python 3.11/3.12 via CI do PR antes do merge. Testes não são parecer jurídico, captação real nem Windows físico.
- Próximo trabalho independente: GN-016 (limpeza/recuperação de processos). GN-036 exige benchmark; GN-031/GN-083 e GN-085 continuam pendentes de autorização e/ou ensaio físico.


## GN-035 — telemetria diagnóstica por fonte (2026-11-11)

- Implementação: `app/source_telemetry.py` acompanha somente metadados de PCM recebido e interpretação textual por fonte, com timeout e retenção limitada às fontes do feed. `AsyncSourceTranscriber.push` envia somente contagem de bytes, sem mídia; `TranscriptFeed` acrescenta metadados a HTTP e WebSocket. Painel GN-075 passa a apresentar disponibilidade observada de PCM, silêncio/ausência recente, comercial/narração prováveis e atraso captura→processamento.
- Distinções importantes: `online` prova apenas PCM chegando ao transcritor, **não disponibilidade de rádio remota**; comercial e narração vêm de classificação heurística de transcrição; atraso é local captura→texto, não atraso entre rádios. Nenhuma transcrição ou observação move a bola. Quando a captura não está conectada ao feed, exibir `não observado`.
- Testes: módulo puro validado localmente em Python 3.13 com **2 passed**; integração em `tests/test_gn035_telemetry.py` e painel Node em `tests/test_gn035_telemetry.cjs` aguardam CI Python 3.11/3.12 do PR. Não houve teste físico Windows nem fonte externa.
- GN-083 permanece **[ ]**, aguardando teste real e gabarito. Próximo trabalho independente: GN-016 (encerramento/recuperação) ou GN-094 (políticas/retenção); GN-036 exige benchmark de VAD.


**Atualizado:** 2026-11-11
**Branch:** `main`
**Últimas tarefas concluídas:** GN-091, GN-090, GN-082, GN-081, GN-080, GN-076, GN-075, GN-074, GN-073, GN-072, GN-071, GN-070, GN-065, GN-064, GN-063, GN-062, GN-061, GN-060, GN-057, GN-056, GN-055, GN-054, GN-053, GN-052, GN-051, GN-050, GN-046, GN-043, GN-042, GN-041, GN-040, GN-024, GN-025, GN-032, GN-030, GN-015, GN-034 e **GN-033/GN-037 (recuperação de captura e política de mídia)**.
**Última tarefa concluída:** GN-092 [P1]. **GN-083 [P0] em andamento:** pipeline WAV/PCM e fluxo direto YouTube autorizado para ASR e interpretação; avaliação com gabarito preparada, sem valores reais de acurácia. **GN-092 [P1] concluída:** snapshot SQLite com SHA-256, logs opcionais e restore seguro (PR #42, CI 43078344748: 586 passed/2 skipped Python 3.11/3.12). GN-066 [x] integrada no PR #41. **Próxima GN-035 [P1]**: telemetria de fontes; GN-036 [P1] precisa avaliação de VAD; GN-083/084/085 permanecem sujeitas a provas reais com autorização e gabarito. GN-083 requer áudio permitido e referência; GN-012/GN-085 requerem Windows físico.
**Fixture Cruzeiro x Bahia GN-083 (2026-11-11):** imagens fornecidas pelo usuário permitem registrar 46 atletas (11 titulares e 12 reservas em cada clube). `scripts/seed_cruzeiro_bahia.py` faz cadastro idempotente na SQLite local, preservando elencos editados, ID `cruzeiro-bahia-gn083`. Testes de persistência/reexecução e instruções em `docs/GN-083.md`. Ainda não executado no Windows do usuário; requer `git pull` e execução local. Não constitui validação ASR real e GN-083 continua [ ].
**Diagnóstico Windows GN-083 (2026-11-11):** após cadastrar Cruzeiro x Bahia (46 atletas) no SQLite local, o usuário instalou `faster-whisper==1.2.1` em Python 3.12; o ASR real falhou com `CPU ASR inference failed` (exceção raiz ainda não identificada) e aviso secundário `Event loop is closed` durante teardown do subprocesso. Adicionado `scripts/gn083_asr_check.py` para autoteste CPU sintético sem recapturar mídia e opção `--diagnose-asr` para erro sanitizado; `app/audio_capture.py` agora drena stdout/stderr do FFmpeg após parada precoce. Aguardar prova física do autoteste, não presumir correção em Windows sem executar. GN-083 [ ] continua.
**Causa identificada GN-083/Windows (2026-11-11):** usuário executou autoteste real da GN-083; `TypeError: open() got an unexpected keyword argument 'metadata_errors'`, com `faster-whisper==1.2.1` e PyAV 19.0.2 instalados. Incompatibilidade upstream confirmada (faster-whisper issue #1589). `requirements-asr.txt` agora fixa `av==17.1.0` e inclui regressão estática; `docs/GN-083.md` instrui reinstalar requirements e repetir autoteste sem refazer captura de 300 s. Falta validação de inferência após atualização no Windows. GN-083 [ ] permanece aberta.
**Execução física GN-083 (2026-11-11):** usuário corrigiu PyAV 17.1.0 e confirmou autoteste de inferência CPU `ok=true`, 6 segundos sintéticos. Com a fonte Cruzeiro x Bahia houve primeiro ASR real (`tiny`, 6.0s/192000 bytes, uma previsão textual; posse/região/evento desconhecidos sem referência). Tentativa de 300s com `base` falhou com `upstream_http_403` na origem; tempo capturado antes da falha era desconhecido. Novo `--capture-first` opt-in bufferiza ≤19,2MB em RAM, processa só após fechar captura e relata segundos de PCM recebidos se falhar; **não ignora/reintenta 403**. Validar o modo novo em Windows com fonte autorizada e janela pequena, sem alegar 300s concluídos. GN-083 [ ] e métricas de acurácia pendentes.
**Compatibilidade GN-031/GN-083:** o diagnóstico YouTube aceita gravações concluídas e amostras de até 600 s. **Prova física informada pelo usuário em 2026-11-11:** `Ls4qkPrh4Tk` capturado no Windows por **300 s / 9.600.000 bytes de PCM / 600 blocos** (`audio_retransmitted=false`). O áudio não foi fornecido a este ambiente e a permissão específica de uso tampouco foi confirmada; portanto ainda não houve reconhecimento de voz real, medição humana ou gabarito. GN-031 e GN-083 permanecem [ ].
**Bloqueio físico paralelo:** GN-012 exige Windows do usuário; GN-085 exigirá áudio/navegador/modelos reais.

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

## Evidência de captura real no Windows — 2026-11-11
- Ambiente: Windows (prompt `C:\\Users\\...\\Documents\\game_now`), FFmpeg 9.0.2, Python 3.12, yt-dlp 2026.10.26 com yt-dlp-ejs e Deno 2.9.8. `git pull --ff-only` atualizou main até `00a4846`.
- Teste executado pelo usuário (URL pública que estava ao vivo no momento): `python -m app.youtube_capture --yt-dlp ".\\.venv\\Scripts\\yt-dlp.exe" --url "https://www.youtube.com/watch?v=SWEYimqD_50" --seconds 5`.
- **Saída efetivamente observada**: `source_id=youtube-diagnostic`, `captured_at=2026-11-11T11:46:24.386336+00:00`, `sample_rate=16000`, `channels=1`, `format=s16le`, `seconds=5.0`, `bytes=160000`, `chunks=10`, `audio_retransmitted=false`. Nenhum áudio foi retransmitido ao site.
- **Conclusão**: resolução do fluxo YouTube Live e decodificação real FFmpeg → PCM no Windows validadas por cinco segundos. Não comprova funcionamento por 90 minutos, ASR, integração do painel ou captura de uma partida de futebol.
- **Limite de aceite**: o vídeo estava publicamente acessível, mas o usuário não confirmou autorização/licença específica para captar seu áudio. A exigência de `link de teste permitido` de GN-031 segue pendente e o checkbox permanece [ ]. O próximo desenvolvimento independente é GN-040, sem repetir a comprovação técnica concluída.

## Diagnóstico adicional Windows — 2026-11-11
- No Windows o Deno 2.9.8, o FFmpeg 9.0.2 e o `yt-dlp[default]` (com `yt-dlp-ejs`) estão instalados.
- O `yt-dlp -F` para `SWEYimqD_50` listou formatos **233 e 234** (`mp4 audio only`, `m3u8`), com `ACODEC unknown`, mas a versão anterior do Game Now retornou `No publicly accessible format containing audio was offered`.
- Causa reproduzida em teste Linux: `acodec=None` em variantes HLS exclusivamente de áudio era descartado apesar de `vcodec="none"`. O resolvedor agora considera este caso como candidato (sem aceitar `acodec="none"` explícito, fontes com DRM ou vídeo-only). Quando não há bitrate anunciado, prefere a variante posterior 234. FFmpeg ainda é responsável por verificar se o fluxo contém PCM decodificável.
- **Resultado posterior: captura técnica real bem-sucedida no Windows em 2026-11-11**. Logs recebidos do usuário comprovam 5 segundos/160.000 bytes PCM após atualizar a main. A permissão do titular da transmissão não foi informada; GN-031 permanece [ ] apenas por esse requisito explícito do roteiro.

## Diagnóstico Windows informado pelo usuário — 2026-11-10
- Clone em Documentos, Python 3.12, ambiente virtual e yt-dlp instalados. FFmpeg foi instalado via winget; a primeira sessão PowerShell não tinha o novo PATH, e nenhum resultado de decodificação de áudio real foi comprovado.
- A URL de Shorts retornou `The YouTube broadcast is not currently live` (tratamento esperado).
- A URL de live `https://www.youtube.com/watch?v=3Z-oNlt1XO0` retornou `No publicly accessible audio-only format was offered`. Isso comprova consulta/identificação como live, **não** a captura.
- A correção GN-031 permite fallback para um formato público combinado com áudio, caso não haja áudio-only; FFmpeg mantém saída exclusiva PCM. Foi adicionada prova automatizada Linux de decodificação de um fixture real com vídeo+áudio. A prova técnica Windows foi concluída posteriormente, conforme o registro de 2026-11-11; a autorização da fonte permanece pendente.
- Na variante combinada, tráfego de rede pode conter vídeo mesmo que apenas PCM de áudio seja gerado; não se grava nem entrega vídeo. Nunca alegar que houve extração apenas de áudio no transporte de entrada.

## Testes e evidências
- GitHub Actions: https://github.com/vmendesneto/game_now/actions/runs/42888042259
- **66 testes aprovados** em **Python 3.11 e 3.12** para a branch de entrega, exportação/verificação de JSON schema, `node --check app/static/app.js` e FFmpeg decodificando MP3/AAC/HLS de teste. Evidência: https://github.com/vmendesneto/game_now/actions/runs/42892117487.
- Novos testes: `tests/test_match_flow.py`, `tests/test_corrections.py`, `tests/test_sources.py`, `tests/test_audio_capture.py`, `tests/test_logging.py`, `tests/test_audio_buffer.py` (sessão longa, isolamento, limites, concorrência) e `tests/test_youtube_capture.py` (metadados sintéticos, falhas e diagnóstico seguro, **não** transmissão real), `tests/test_capture_supervisor.py` e `tests/test_media_policy.py`. Suíte anterior permanece verde.
- Um aviso de depreciação de dependência observado na CI, sem falha. Não houve teste com rádio, YouTube ou Windows reais.

## Limitações importantes
- **GN-031 tecnicamente validada no Windows, mas [ ] no ROADMAP até confirmar fonte permitida**: `app/youtube_capture.py` invoca yt-dlp e FFmpeg para obter PCM mono s16le 16 kHz sem retransmitir mídia; prefere áudio-only, incluindo HLS 233/234 com codec ausente. Há testes automatizados Linux e uma **prova real de 5 segundos / 160.000 bytes no Windows** em 2026-11-11. A autorização de uso do sinal da transmissão testada não foi informada. A captura ainda não está conectada ao site nem ao ASR; estabilidade de 90 minutos não foi demonstrada.
- `/api/demo/next`, `/api/state` e `/ws` operam demo **volátil** separada de `/api/matches/{id}/state` e operações de partida.
- Modelo de substituições não impõe limite/regra de competição (5 substituições, janelas, cartões amarelos e suspensões futuras). Corrigir a regra por competição antes de jogo oficial.
- Auditoria é durável no SQLite, mas administradores locais podem alterar o arquivo; não é trilha assinada. Servidor apenas `127.0.0.1`.
- Validação das URLs é superficial e feita no cadastro; ainda faltam regras DNS/redirecionamentos no processo de captura.
- `iniciar_windows.bat`, browsers físicos e GPU/CPU não foram testados em Windows. FFmpeg real foi testado apenas no Linux GitHub Actions.

## Continuar
1. Ler `STATUS.md`, `ROADMAP.md` e `AGENTS.md`; verificar HEAD de `main` e testes.
2. **GN-031:** o teste técnico real no Windows já passou e não precisa ser repetido. Verificar a autorização de captação da fonte para cumprir o critério de aceite do ROADMAP; até lá, manter [ ]. Não contornar autenticação/DRM.
3. GN-033 já implementa reconexão em workers simulados, mas NÃO é iniciado pelo cadastro nem pelo site, e GN-037 estabeleceu política inicial sem gravação de mídia. Próximo trabalho independente é ASR em CPU (GN-040) e, depois, integração operacional; GN-012 exige teste do Windows físico em seus próprios critérios.
4. Para rodar CI local: `python -m pip install -r requirements-dev.txt && python scripts/export_schema.py && python -m pytest -q`. Testes GN-030 precisam FFmpeg no PATH.
5. Servidor: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. Logs em `data/game_now.log`, registro JSON sem corpo das requisições.

## GN-040 — validada em CI Linux (2026-11-11)

- Branch `feat/gn040-asr-cpu`, PR #7: `app/asr.py` aceita WAV mono 16 kHz/PCM s16le com limites de duração, integra faster-whisper opcional, oferece modelos tiny/base/small/medium e CPU int8. `requirements-asr.txt` é opt-in.
- O modo demo permanece sem modelo; o diagnóstico `/health` não faz download, nem inicia inferência. A CLI só imprime JSON com texto/segmentos; não guarda áudio e não acessa fontes remotas.
- `tests/test_asr.py` usa modelo falso para validação determinística; o workflow `asr-smoke.yml` foi configurado para gerar **fala sintetizada em português** e executar o modelo real em CPU. **GN-040 comprovada**: run 43016056292 (modelo real base/CPU, 1 teste aprovado), e run 43016091200 (suíte geral aprovada em Python 3.11/3.12).
- Em seguida: GN-041 (janelas sobrepostas e deduplicação) e GN-042 (feed por fonte), sem presumir teste físico Windows.

- Evidência de inferência real: https://github.com/vmendesneto/game_now/actions/runs/43016056292. Log: `REAL_CPU_ASR_RESULT: O jodo de futebol comeceu a guarda. A bola está no meio do campo. Ata-cante chuto e fez um globo.` O ASR reconheceu fala em português, com erros esperados do TTS sintético. **Não é benchmark de precisão/WER, nem validação de narração real/Windows**.

## GN-041 — validada em CI Linux (2026-11-11)

- `app/asr_windows.py`: montagem de janelas PCM de 6 s com 2 s de sobreposição (configuráveis), offsets relativos por fonte, memória limitada e isolamento; `TextOverlapDeduplicator` compara somente sequências de 2+ tokens coincidentes, preservando palavras únicas como "gol". `RollingASRProcessor` entrega texto incremental com idioma e intervalo relativo. Não injeta áudio no site nem é agendado pelo servidor.
- Suíte de testes Python 3.11/3.12: **100 passed, 1 skipped** na CI (teste pesado opt-in ignorado pela suíte geral) em https://github.com/vmendesneto/game_now/actions/runs/43016881008. Teste pesado separado e real: **1 passed**, 3 janelas de fala sintetizada portuguesa com modelo `base` CPU em https://github.com/vmendesneto/game_now/actions/runs/43016880967.
- Microbenchmark Linux Python 3.12 (somente montagem, não inferência): 2 fontes × 10 min de chunks; 149 janelas por fonte, 128.000 bytes de buffer restante por fonte, 0,0406 s de tempo de montagem. Script `python -m scripts.benchmark_asr_windows`. **Não** representa latência ASR real, Windows, WER ou transmissão esportiva.
- Limitação observada: no teste real de fala sintética, diferentes janelas transcreveram as mesmas palavras de modo diferente; a deduplicação literal conservadora não remove todos os ecos. GN-044 continua responsável por benchmark de acurácia, GN-042 por feed e GN-043 por execução assíncrona.

## GN-042/GN-043 — feed textual e CPU fora do loop HTTP (2026-11-11)

- `app/transcription_feed.py`: guarda transcrições **somente de texto** em memória com limite de partidas/fontes/entradas, timestamps UTC de captura/processamento, início/fim relativo de janelas, idioma, sequência e estado por fonte (`idle/buffering/processing/ready/error/stopped`). Filtra fontes não cadastradas para clientes. O feed é **volátil** e ainda não alimenta snapshots duráveis das partidas.
- `app/main.py`: `GET /api/matches/{id}/transcripts` com filtro `source_id` e limite 1..200; `/ws/matches/{id}/transcripts` transmite snapshots e atualizações em tempo real. O canal só envia metadados e texto; não expõe PCM, áudio, vídeo nem URLs.
- `app/transcription_runtime.py`: `AsyncSourceTranscriber.push/finish` chama `RollingASRProcessor` em `asyncio.to_thread` com lock por fonte. HTTP segue atendendo mesmo durante inferência lenta; filas por cliente são limitadas e descartam atualizações antigas quando saturam.
- Testes `tests/test_transcription_feed.py` verificam duas fontes isoladas, limite de retenção, URLs de erro não vazadas, HTTP/WebSocket para dois clientes, latência da API com inferência sintética deliberadamente bloqueada e fechamento/cancelamento seguro. **106 passed, 1 skipped** em Python 3.11/3.12: https://github.com/vmendesneto/game_now/actions/runs/43018620370. Smoke real GN-040/041 continua: https://github.com/vmendesneto/game_now/actions/runs/43018616281.
- **Limite fundamental:** a captura real ainda NÃO é iniciada pela interface nem conectada ao `AsyncSourceTranscriber`. A prova GN-043 usa modelo lento artificial, não garante inferência de Whisper durante uma partida real ou comportamento em Windows. Integração da captura, controles de start/stop e segurança de rede devem ser realizadas nas GN-074/GN-090, sem reabrir o risco SSRF prematuramente. GN-031 ainda depende de fonte permitida.

## GN-046 — vocabulário e A/B com ASR CPU real (2026-11-11)

- `app/asr_vocabulary.py`: gera `initial_prompt` de até 500 caracteres a partir dos nomes de clubes, atletas, apelidos e termos futebolísticos de partida salva; limita nomes e remove caracteres de controle. `app/asr.py` aceita `ASRSettings.initial_prompt` opcional e oferece `--match-id` na CLI, consultando a partida do SQLite (sem alterar ContractBundle v1). O modelo continua CPU int8 e com carregamento opcional.
- Testes determinísticos `tests/test_asr_vocabulary.py` cobrem conteúdo, limite e encaminhamento do prompt ao modelo real. CI geral: **109 passed, 2 skipped** em Python 3.11/3.12: https://github.com/vmendesneto/game_now/actions/runs/43019542054.
- Teste A/B real e reprodutível em Linux: mesma fala pt-BR sintetizada por `espeak-ng`, mesmo modelo `base` CPU int8, com e sem contexto. Alvos "Otávio, Mendes, Caio, Ventura, Azul, escanteio"; **1/6** alvos presentes no resultado sem vocabulário e **6/6** com vocabulário. A inferência real e 2 testes pesados foram aprovados: https://github.com/vmendesneto/game_now/actions/runs/43019542053.
- **Interpretação correta**: 1/6 → 6/6 demonstra benefício nesta **única amostra sintética**, não WER estatisticamente representativo, não narração de futebol real, não Windows ou garantia de acerto. O prompt pode enviesar nomes ausentes no sinal; GN-051 deverá manter resolução conservadora.

## GN-050 — classificador de contexto de narração (2026-11-11)

- `app/narration_classifier.py`: categorização textual determinística com seis classes internas (`live_play`, `ad`, `conversation`, `analysis`, `replay`, `unknown`), regras com prioridade de comercial/replay/análise sobre pistas de lance, normalização de acentos e limites de entrada. Retorna `matched_cue` como explicação de regra, **não confiança estatística**. Somente a classe `live_play` é elegível como candidato a análise de futebol; o módulo **não** gera evento, jogador, placar, posse ou zona.
- O contrato v1 permanece congelado e não possui a categoria `conversation`: `to_contract_category` faz mapeamento seguro para `unknown`, sem schema novo.
- `fixtures/narration_labeled.json` inclui **39 frases originais sintéticas em português**, com seis categorias e casos negativos; `tests/test_narration_classifier.py` verifica todos os rótulos, precedência, falsos positivos, palavras acentuadas e limites. Correção de alongamentos de "GOOOOOL" reproduzida no corpus.
- Evidência: **115 passed, 2 skipped** em Python 3.11/3.12, run https://github.com/vmendesneto/game_now/actions/runs/43020798677; smoke real ASR permanece verde (run https://github.com/vmendesneto/game_now/actions/runs/43020798636).
- Limitação: as 39 frases são inventadas e rotuladas para o teste; acerto nesse corpus não mede generalização a narradores reais ou ASR ruidoso. O classificador está conectado **somente ao feed textual volátil** (PR #12, commit `0cc7b77`), expondo `narration_kind`, `classification_reason` e `eligible_for_live_state`; **não** está conectado à lógica que movimenta a bola. O complemento passou na CI Python 3.11/3.12 com **117 passed, 2 skipped** (https://github.com/vmendesneto/game_now/actions/runs/43022961852). Avaliação real e refinamento dependerão de GN-058 (corpus autorizado).

## GN-051 — resolução conservadora de entidades em narração (2026-11-11)

- `app/narration_entities.py` extrai nomes e aliases cadastrados, nomes/abreviações de clubes e camisas 1–99 (algarismos ou palavras, incluindo "camisa nove"). Comparação com fronteiras de palavras, caixa e acentos normalizados; devolve posição da menção, candidatos e motivo auditável. Nome ou número repetido entre equipes permanece `ambiguous` até haver referência explícita "do/da/pelo/pela [clube]"; não atribui posse ou posição de bola.
- Referências "ele/dele" usam apenas um atleta explicitamente identificado antes do pronome na mesma frase; dois candidatos, comercial, replay ou ausência de antecedente permanecem desconhecidos. Contexto entre janelas é opcional, passado pelo chamador, válido somente no mesmo match/source, sequência imediatamente seguinte e intervalo de -2 a +8 s; não se propaga a partir de pronomes. Nenhum contexto persistente é registrado.
- `POST /api/matches/{id}/resolve-narration` lê a escalação no SQLite e retorna dados de diagnóstico, sem mutar contrato v1, feed ou snapshot do jogo. Documentado no README; teste de integração cobre reinício e integridade do estado.
- Prova: `python -m pytest -q` na CI do PR #13, Python 3.11 e 3.12: **125 passed, 2 skipped, 1 warning** em cada versão; schema/JS/FFmpeg fixtures e benchmark de montagem aprovados. https://github.com/vmendesneto/game_now/actions/runs/43024972166. Sete testes unitários de GN-051 também executados localmente com dependências mínimas (não substituem CI).
- **Limite:** corpus de testes é sintético; resultado é resolução textual diagnóstica, não identifica jogador em áudio real, não produz evento ou posse, não alimenta automaticamente o feed nem campo. **Próximo item: GN-052**, depois GN-053; GN-044/045, GN-012/085 e GN-031 mantêm bloqueios próprios.

## GN-052 — posse textual explícita sem alterar jogo (2026-11-11)

- `app/possession.py` recebe o texto de uma narração e elenco salvo, usa GN-050 e GN-051 para rejeitar anúncios/replays, nomes ambíguos e frases vagas. Somente âncoras explícitas de posse ("com a bola", "bola com", "recebe a bola", "rouba/recupera a bola", "retoma a posse") permitem emitir `status=explicit`. Duas pistas na mesma frase, passes sem recepção ou relato incompatível resultam `unknown`.
- O identificador `previous_team_id` é fornecido pelo chamador, validado contra os clubes da partida e comparado com a nova hipótese para derivar `changed_team`. Ausência de contexto anterior dá `null`, não inventa turnover. Não manipula o histórico ou a posse persistida.
- `POST /api/matches/{id}/resolve-possession`: consulta partida/elenco no SQLite, responde hipótese textual e motivo, sem escrever eventos, bola, posse ou schema v1. O classificador GN-050 passou a reconhecer "bola com" e equivalentes como candidatos a lance atual, mantendo a precedência de replay/anúncio.
- `tests/test_possession.py` cobre mudanças explícitas, camisa por extenso, ambiguidades, frases sem evidência, replay, anúncios, pistas múltiplas e API com snapshot inalterado. **CI do PR #14: 129 passed, 2 skipped, 1 warning em Python 3.11 e 3.12**, schema e JS aprovados: https://github.com/vmendesneto/game_now/actions/runs/43025807453. Teste local de núcleo: 3 passed.
- **Limitações:** resultado é diagnóstico, não estado persistido de posse, nem comparação entre narradores ou interpretação automática de stream; inferência não foi validada com áudio esportivo real. **Próxima GN-053** (regiões 5×3 e lados). Bloqueios Windows/autorizações de fontes permanecem.

## GN-053 — localização textual conservadora (2026-11-11)

- `app/field_regions.py`: recebe texto de lance atual e identifica **somente** quando há equipe inequívoca, faixa longitudinal específica (1..5, da própria área até a adversária) e corredor esquerda/centro/direita. Os 15 setores são relativos ao ataque da equipe; `field_band`/`field_lane` convertem para eixo fixo de campo (esquerda → direita) levando em conta `attack_direction` atual na partida, já invertido pela GN-024 quando inicia o segundo tempo. Um `team_id` opcional é exclusivamente contexto explícito fornecido pelo chamador e nunca posse inferida.
- `POST /api/matches/{id}/resolve-region` retorna `status=explicit/unknown`, `zone`, equipe, direção, setor orientado, pistas textuais e razão auditável; não modifica SQLite, contrato v1, bola, histórico ou feed de transcrição. Termos amplos como “campo de ataque” ou “na área” **não** localizam uma faixa de cinco. Contextos conflitantes, região parcial, replay, publicidade, análise e intervalo/fim retornam `unknown`.
- `tests/test_field_regions.py` inclui matriz de 5 faixas × 3 corredores × 2 direções, inversão de ataque no segundo tempo, conflitos e API read-only com persistência intacta. CI de PR #15: **175 passed, 2 skipped** (Python 3.11 e 3.12), schema e JavaScript aprovados. Evidência: https://github.com/vmendesneto/game_now/actions/runs/43027201520. Testes em Linux com texto sintético; **não** valida áudio brasileiro real/Windows nem movimentação no site.
- **Próxima tarefa:** GN-054 (classificar tipos de lance com pistas textuais explícitas/fixtures), sem mover automaticamente a bola e sem reaproveitar contexto obsoleto. GN-044/045, GN-031, GN-012/085 e GN-090 seguem condicionadas a evidências específicas.

## GN-054 — eventos explícitos em narração textual (2026-11-11)

- `app/event_detection.py` classifica **somente lances atuais afirmativos** em 11 tipos do contrato EventKind v1: passe, cruzamento, chute, defesa, gol, escanteio, lateral, impedimento, falta, pênalti e tiro de meta. O resultado `EventEvidence` contém `kind`, a pista textual normalizada e explicação. Uma frase com vários tipos de ação retorna `unknown`, sem escolher arbitrariamente gol ou chute; negação, hipótese, tentativa, anulação, comercial, replay e período inativo também bloqueiam interpretação.
- `POST /api/matches/{id}/resolve-event` é **diagnóstico read-only**: não altera placar, posse, bola, histórico, SQLite ou o contrato v1; texto limitado a 2.048 caracteres. `fixtures/events_labeled.json` contém **36 frases originais fictícias** (positivas e negativas). `tests/test_event_detection.py` cobre fixtures, conflitos de tipos, limites, intervalo e API sem mutação.
- Em revisão de CI inicial, um texto com `chuta e marca o gol` foi incorretamente reduzido a chute; corrigida a detecção do presente `marca o gol` para rejeitar múltiplos tipos. **CI pós-correção** https://github.com/vmendesneto/game_now/actions/runs/43027994130: **218 passed, 2 skipped, 1 warning** nas versões Python 3.11 e 3.12, schema/JS/FFmpeg aprovados. Não há avaliação com áudio real nem estimativa estatística de precisão.
- **Próxima tarefa GN-055**: score heurístico e expiração por componente (jogador/equipe/zona/evento/atualidade) com casos negativos; não confundir score fixo com confiança calibrada. Manter GN-031/044/045/012/085 e GN-090 sob seus portões de evidência.

## GN-055 — pontuação heurística dos componentes da evidência (2026-11-11)

- `app/confidence.py` conecta os diagnósticos de entidades (GN-051), região (GN-053) e eventos (GN-054) sem alterar o jogo. `POST /api/matches/{id}/resolve-confidence` devolve `scores.player/team/region/event/freshness` em [0,1], `reasons` por componente e `mode=heuristic_strength_not_calibrated_v1`. **Estes números são intensidade de regra**, não probabilidades de acerto, nem cobertura de narração esportiva real. Não existe score global capaz de compensar uma região ausente com outro atributo.
- Referência inequívoca no texto pontua 1.0 para jogador, equipe, região ou tipo de evento; uma equipe fornecida exclusivamente pelo chamador pode pontuar 0.5 em equipe/região, com origem visível. Ambiguidade, conflitos, anúncios, replay e período encerrado reduzem componentes a zero. Atualidade é pontuada separadamente com `observed_age_seconds` informado pelo chamador: 1.0 para até 5s, declínio linear até 0 em 30s; idade não informada é zero. **A idade não é aferida contra relógio de jogo, PTS ou áudio** (GN-060/061 são pendentes).
- `tests/test_confidence.py` valida positivos/negativos, equipe de contexto, expiração, categorias não-live, limites, persistência intacta e integração HTTP/SQLite. Um aviso novo do Pydantic (`model_fields` em instância) foi eliminado antes do fechamento. **CI Linux pós-correção:** https://github.com/vmendesneto/game_now/actions/runs/43029006109 — **234 passed, 2 skipped**, Python 3.11 e 3.12, schema/JS/FFmpeg verificados; sem prova de narração real ou Windows.
- **Próximo passo GN-056**: projetar a decisão conservadora que proíba movimento por texto impreciso, sem simular ingestão produtiva. GN-031/044/045/012/085 e GN-090 mantêm suas pendências externas.

## GN-056 — guarda conservadora da bola (2026-11-11)

- `app/ball_guard.py`: política **fail-closed** que retorna `hold` ou `candidate` para movimentação proposta. Exige narração de lance atual sem publicidade/replay/análise/negação/hipótese; posse explícita e única (GN-052), faixa e corredor com equipe textual inequívoca (GN-053) e consistência entre evidências GN-055. A idade declarada pelo cliente deve existir e ser <=5s; **não foi verificada contra horário real da fonte**, portanto nenhum estado é atualizado automaticamente.
- `POST /api/matches/{id}/guard-ball` retorna estado da bola **atual** e zona *candidata*, quando houver; é **somente leitura** e não escreve no SQLite/WS, não altera placar, não liga ASR nem movimenta o campinho. Posições atuais permanecem intactas para texto vago, região/posse incompletas, contradições, fontes não-live, ausência de idade, idade >5s e jogo parado. Sem alteração do `ContractBundle v1`.
- `tests/test_ball_guard.py` valida cenários negativos e positivos, idade 0/5/5.001 s, inversão no segundo tempo, não reutilização de posição e integração HTTP/SQLite com snapshot idêntico antes/depois. **CI Linux:** 263 passed, 2 skipped, 1 warning em Python 3.11 e 3.12; schema, JS, FFmpeg aprovados: https://github.com/vmendesneto/game_now/actions/runs/43031120226. Smoke ASR real CPU também verde: https://github.com/vmendesneto/game_now/actions/runs/43031120176.
- **Limites:** evidências são frases artificiais e idade informada pelo chamador, não sincronizada ao áudio. O resultado `candidate` não comprova nem altera localização real, e deve passar por tempo lógico/fusão GN-060..GN-065 antes de alimentar o site. GN-031 e testes físicos Windows ainda sujeitos aos critérios próprios.
- **Próximo passo:** GN-057 (LLM local opcional / validação JSON), depois GN-060 (tempo lógico) e demais dependências do fluxo real. Não repetir GN-053..GN-055.

## GN-057 — sugestão opcional com LLM local e JSON estrito (2026-11-11)

- `app/llm_local.py`: comparação das regras textuais GN-050/052/053/054 com saída estruturada de modelo **Ollama local opt-in**, apenas em `127.0.0.1:11434/api/generate` usando `http.client` (sem seguir redirects, sem endpoint configurável, sem baixar modelos); `use_local_llm=false` por padrão. Limites de duração de 1..20s, corpo HTTP e saída JSON. Validação rígida de tipos, chaves duplicadas/extra, zona, eventos, IDs de equipe/jogador e conflitos com as regras explícitas; qualquer anomalia, replay ou comercial bloqueia/abstém.
- `POST /api/matches/{id}/compare-language`: consulta o elenco atual e devolve `baseline` das regras e `suggestion` opcional identificada como **hipótese não verificada**, `eligible_for_state_update=false` em todos os casos. A chamada local roda fora do event loop HTTP. Não altera bola, placar, SQLite, feed, contrato v1 ou fontes reais.
- `tests/test_llm_local.py` cobre comparação de frase complexa com baseline de regras, fake do modelo local, JSON malformado/duplicado/inesperado, região incompatível, IDs alucinados, rede indisponível sem vazamento de detalhes, localhost fixo, categorias proibidas e API SQLite read-only. **CI Linux:** 297 passed, 2 skipped, 1 warning em Python 3.11 e 3.12: https://github.com/vmendesneto/game_now/actions/runs/43032445652. Fluxo ASR CPU anterior permanece independente.
- **Limites honestos:** testes do modelo são *doubles* determinísticos; não houve inferência Ollama real ou avaliação de desempenho/qualidade com narração de futebol, e nenhum palpite da IA atualiza o campo. Avaliação com áudio autorizado é GN-058/083. Próxima GN-060 (relógio lógico), depois GN-061..065.

## GN-060/GN-061/GN-062 — concluídas, CI e merges confirmados (2026-11-11)

- **GN-060 [x]**: PR #20 mesclado previamente em `main` (`398a152`). `app/logical_clock.py` e `tests/test_logical_clock.py` implementam relógio baseado na captura e simulação de chegada tardia, em uma única fonte. A CI original travada foi cancelada; **a suíte atual já inclui GN-060 e passou**.
- **GN-061 [x]**: PR #21 mesclado em `main` (`a1a3d1f`). `app/source_delay.py`, `tests/test_source_delay.py` e endpoint `/api/matches/{id}/sources/delay/preview` estimam atraso relativo por IDs de eventos explícitos, com limites/janela e proteção contra divergência. Suíte da branch: 326 passed / 2 skipped em Python 3.11/3.12 (run 43043216756).
- **GN-062 [x]**: PR #22 mesclado em `main` (`b4898d7`). `app/event_deduplication.py`, `tests/test_event_deduplication.py` e endpoint `/api/matches/{id}/events/deduplicate/preview` agrupam conservadoramente dois relatos de um mesmo evento sem alterar o estado persistido. Suíte da branch: 341 passed / 2 skipped (run 43043274805).
- **CI pós-merge**: https://github.com/vmendesneto/game_now/actions/runs/43045479371 — **341 passed, 2 skipped, 1 warning em Python 3.11 e 3.12**. O ASR real CPU teve 2 testes aprovados em https://github.com/vmendesneto/game_now/actions/runs/43044664124, mas isso é um teste sintético separado.
- **Limites**: GN-060/061/062 são diagnósticos/simulações, não alinhamento automático de rádio/YouTube em operação. Os IDs de eventos correspondentes e offsets são informados pelo chamador; relógios de captura precisam estar em domínio sincronizado. Não há prova de áudio real alinhado, inferência confiável ao vivo, persitência automática de eventos ou Windows validado nessas tarefas. GN-090 permanece bloqueio de segurança para ativação de fontes.
- **Próxima tarefa: GN-063** — escolher fonte ativa por comercial, atualidade, confiança e saúde da conexão; criar cenários de transição e testes. Depois GN-064 e GN-065, respeitando dependências.

## GN-063 — seleção conservadora da fonte ativa (2026-11-11)

- `app/source_selection.py`: seleciona apenas fonte habilitada, conectada (`online`), com texto `live_play`, captura recente e força heurística mínima. Comercial, replay, análise, conexão ruim, captura velha, timestamps futuros ou sinal fraco excluem a fonte, independentemente de ranking.
- Transições diagnósticas `selected/switched/retained/lost/none`; troca imediata quando a fonte atual fica inelegível; margem de histerese evita oscilações entre duas fontes válidas. Ranking combina força heurística e idade do momento de captura, não chegada do texto; empate determinístico.
- `POST /api/matches/{id}/sources/selection/preview` é somente prévia: `persisted=false`, `eligible_for_state_update=false`; não ativa FFmpeg/ASR, não escreve SQLite, não muda bola, não garante sincronismo de streams. Os sinais de entrada são fornecidos pelo chamador e exigem relógio comum confiável. A força heurística NÃO é probabilidade calibrada.
- `tests/test_source_selection.py`: comerciais, replay, saúde, atrasos de entrega, confiança, silêncio, mudança e retenção de fonte, validação estrita e API sem mutação. **CI PR #23: 361 passed, 2 skipped em Python 3.11 e 3.12**: https://github.com/vmendesneto/game_now/actions/runs/43047629361. O warning pré-existente não causou falha.
- **Próxima: GN-064** (contradições entre fontes e monotonicidade), depois GN-065. GN-090 permanece bloqueio de captação real iniciada pelo site; GN-031 depende de fonte autorizada. Nenhum teste com rádio ou YouTube reais foi feito nesta tarefa.

## GN-064 — contradições entre fontes sem retrocesso (2026-11-11)

- `app/fusion_conflicts.py` recebe escolha explícita da fonte ativa, observações com timestamps já alinhados (fornecidos pelo chamador) e último lance previamente aceito. Recusa texto não-live, fonte sem observação, tempo não alinhado/futuro, equipe ou zona ausente e atualização no mesmo instante ou antes do lance anterior.
- Observações simultâneas de outra fonte que afirmem equipe, zona, jogador ou tipo de evento conflitante vetam a proposta; ignoram-se análises/replays e registros sem alinhamento como prova de conflito. Informação ausente em fontes secundárias não pode preencher coordenadas ausentes da fonte escolhida. Não há voto de maioria nem conversão de texto em posição real.
- Endpoint `POST /api/matches/{id}/events/fusion/preview`: `accepted_for_preview` é apenas consistência hipotética, sempre `persisted=false` e `eligible_for_state_update=false`. Sem alterações de partidas, bola, relógio ou SQLite.
- `tests/test_fusion_conflicts.py` cobre múltiplas contradições, retrocesso, falta de zona/equipe, tempo, classificação, integração com seleção GN-063 e API somente leitura. **PR #24, CI: 380 passed, 2 skipped em Python 3.11 e 3.12**: https://github.com/vmendesneto/game_now/actions/runs/43048616845. Um warning de dependência já conhecido permanece.
- **Próxima: GN-065**, expirar informação de bola após silêncio. Integração com áudio/ASR reais continua pendente e sujeita à GN-090; nenhuma fonte real foi testada na GN-064.

## GN-065 — expiração de região após silêncio de narração (2026-11-11)

- `app/ball_freshness.py` usa `FusionPlay` (último lance explícito com timestamp alinhado) e fonte ativa GN-063 fornecida pelo chamador para construir prévia de apresentação. Até 5 s após o lance, com a mesma fonte ainda ativa, devolve `estimated`; depois de 5 s de silêncio, `uncertain` e a etiqueta `posição incerta`; após 15 s, `expired`. Limites são configuráveis e têm validação estrita.
- Perda ou troca da fonte ativa invalida imediatamente a exibição de coordenadas; quando o estado é incerto/expirado, `zone`, `team_id` e `player_id` são devolvidos como `null` (sem reutilizar posição velha). Não há recomputação por hora de chegada ou requisição HTTP.
- `POST /api/matches/{id}/ball/freshness/preview` é apenas prévia; sempre `persisted=false` e `eligible_for_state_update=false`. Não inicia relógio contínuo, não liga captura, não escreve SQLite, não altera bola real, e ainda não atualiza visualização do site — integração de UI nas GN-070/071.
- `tests/test_ball_freshness.py` valida bordas exatas 5 s/15 s, silêncio, troca de fonte, ausência de lance, ressurgimento com evidência nova, rejeição de futuro e API sem mutação. **CI PR #25: 397 passed, 2 skipped em Python 3.11 e 3.12**: https://github.com/vmendesneto/game_now/actions/runs/43049429978.
- **Próxima prioritária GN-070** (campo SVG responsivo), seguida GN-071 (render de incerteza). GN-066 [P1] permanece aberto; GN-090 continua bloqueando integração de fontes reais pelo site.

## GN-070 — campo SVG responsivo e inversão de lados (2026-11-11)

- O frontend já tinha um SVG e grade rudimentar; GN-070 reutilizou essa base sem reescrever o site. `app/static/field_geometry.js` agora define `fieldCells`, `zoneToGrid` e `zoneCellBounds` testáveis isoladamente para as 15 zonas físicas (5 faixas × 3 corredores). A mesma zona relativa ao ataque percorre colunas/linhas invertidas quando as direções mudam no 2º tempo (o backend de GN-024 já inverte as equipes).
- `app/static/app.js` usa os cálculos centrais para destacar somente um retângulo de região, nunca ponto exato da bola. SVG com `viewBox` e descrição `aria-label` para região conhecida/incerta; `index.html` carrega módulo antes da UI; `styles.css` preserva a proporção 1000×620 e evita transbordo em telas pequenas.
- `tests/test_field_geometry.cjs` verifica 15 zonas sem sobreposição, todos os 15 mapeamentos únicos para ambas as direções, inversão de eixos, escalonamento 1000 px/320 px e inputs inválidos. `tests/test_field_ui.py` integra esses testes no pytest usando Node disponível na CI e verifica layout/ordem de scripts. Testes não substituem validação visual real em navegador móvel.
- A primeira CI identificou teste de comparação de ponto flutuante excessivamente estrita, corrigido com tolerância; **CI final PR #26: 400 passed, 2 skipped em Python 3.11 e 3.12**, mais 6 testes Node passando: https://github.com/vmendesneto/game_now/actions/runs/43050305053.
- **Próxima GN-071**: integração/animação da posição estimada e indicação visual de incerteza, com roteiro demonstrável. GN-066 P1 permanece pendente; o SVG ainda lê a demo separada e não captação real (GN-090).

## GN-071 — indicador de incerteza e animação conservadora (2026-11-11)

- `app/static/pitch_presentation.js` fornece apresentação determinística de zona, equipe, jogador e força de evidência da demo. Oculta informações quando a bola estiver `uncertain/expired`, quando a região for inválida ou a equipe não existir. Não transforma scores heurísticos em probabilidade de acerto.
- `app/static/app.js` mostra somente retângulo discreto de região explícita e indicação textual acessível `Posição incerta` em caso de incerteza. Uma transição de destaque de 320 ms ocorre apenas para novo ID de evento que realmente altere a região. Repetição de snapshots, mesmo evento ou nova descrição da mesma região não produz movimento. `styles.css` respeita movimento reduzido; `index.html` carrega o módulo e usa `aria-live`.
- Testes: `tests/test_pitch_presentation.cjs` (7 casos Node) e `tests/test_pitch_ui.py` (2 casos Python) cobrem estado incerto, dados inválidos, duplicações, mudança explícita e acessibilidade estática. Corrigida também a expectativa antiga em `tests/test_field_ui.py` para o novo adaptador.
- **CI final PR #27**: 402 passed, 2 skipped em Python 3.11 e 3.12, https://github.com/vmendesneto/game_now/actions/runs/43051118268. A primeira CI falhou por asserção desatualizada do teste GN-070, não por erro de execução do adaptador; o teste foi atualizado e a suíte passou.
- **Limites**: visuais ainda exibem dados da demo sintética, não captura/ASR ao vivo nem estado do SQLite para partidas reais. Não há comprovação de aparência em navegador móvel físico. **Próxima GN-072**, painel de jogo em demo; GN-066 [P1] ainda pendente; GN-090 bloqueia ativação de captação pelo site.

## GN-072 — painel de status fiel à demonstração (2026-11-11)

- O painel já continha placar, relógio, posse provável, atleta provável e evento, mas repetia o último evento como se fosse atual durante comercial/replay. `app/static/demo_scoreboard.js` extrai a apresentação do estado confirmado, sem buscar/gerar dados novos. O módulo distingue último lance confirmado de relato recebido agora e indica comercial, replay, análise, texto sem evento ou relato deduplicado. O placar só lê valores da partida; não pontua a partir do texto ou da UI.
- `app/static/app.js` usa o novo apresentador para nome dos clubes, placar, relógio/parada, direção de ataque, relato e evento da vez. `index.html` explicita a origem de demonstração, fornece rótulos acessíveis e campo separado de último evento; `styles.css` evita confundir informações passadas com novos lances. A posse/atleta continuam seguindo a proteção de incerteza de GN-071.
- `tests/test_demo_scoreboard.cjs` (8 casos Node) cobre marcador, relógio por período, nenhum evento, comercial/replay/análise e segmentos repetidos. `tests/test_demo_dashboard_ui.py` (3 testes) verifica HTML/JS e consome 9 snapshots reais da API sintética (estado inicial + 8 etapas), executando apresentador Node para conferir mensagens, placares e relógios em todos os passos.
- **CI PR #28**: 405 passed, 2 skipped em Python 3.11 e 3.12: https://github.com/vmendesneto/game_now/actions/runs/43051812981. Testes automatizados não equivalem a navegador real/Windows; nada neste trabalho ativa rádio, YouTube ou ASR.
- **Próxima: GN-073** WebSocket e múltiplos navegadores, respeitando demo separada; GN-066 [P1] ainda pendente. GN-090 antes de habilitar captura via site.

## GN-073 — WebSocket versionado e dois clientes de navegação (2026-11-11)

- PR #29: `feat/gn073-browser-websocket-sync`. `DemoEngine` acrescenta `stream_id` por processo e `revision` monotônica a cada relato/reset somente no envelope de demonstração. `ContractBundle` v1 e o SQLite não foram alterados.
- `app/main.py` usa lock assíncrono na demo para impedir envio fora de ordem entre cadastro de novos WebSockets e broadcasts de alterações; `/api/state` e comandos `/api/demo/next` e `/api/demo/reset` compartilham essa ordenação.
- `app/static/demo_sync.js` integra o navegador com validação de envelope, descarte de revisões antigas/duplicadas, uso de GET como fallback inicial, reconexão com backoff limitado e troca de época quando o servidor reinicia. `app.js` preserva o quadro e o feed sem retransmitir mídia.
- Testes novos: `tests/test_demo_websocket_sync.py` abre **dois clientes WebSocket** do FastAPI e observa relatos/reset idênticos, além de simular a recriação do processo; `tests/test_demo_sync.cjs` simula duas abas independentes, snapshots fora de ordem, HTTP atrasado e reconexão. São clientes/sessões simulados, **não** ensaio físico com dois navegadores reais.
- A primeira CI falhou apenas pelo novo teste omitir o campo `schema_version` preexistente; teste corrigido. CI final: https://github.com/vmendesneto/game_now/actions/runs/43052978721 — **408 passed, 2 skipped** em Python 3.11 e 3.12, com Node.js nos testes. Sem transmissão de áudio/vídeo e sem validação de rede LAN ou Windows físico.
- **Próxima GN-074 [P0]:** fluxo completo na interface para partida, elencos e fontes com teste integrado; GN-066 [P1] também pendente. GN-090 continua pré-requisito da captura real.

## GN-074 — configuração guiada da partida (2026-11-11)

- A interface já possuía CRUD de partida, atletas e fontes. Novo painel em 3 etapas mostra o progresso do cadastro sem confundir fonte habilitada com captura iniciada. `app/static/setup_progress.js` não acessa áudio/rede. Alterações no cadastro, elenco e fontes atualizam o resumo; criar nova partida zera a contagem.
- Novos testes `tests/test_setup_progress.cjs` e `tests/test_configuration_flow_ui.py` exercitam contadores, cadastro de duas equipes, URLs de rádio/YouTube e persistência após reinício do SQLite. **Não há validação física em navegador/Windows nem captura de áudio integrada.**
- **Próxima GN-075 [P1]**: UI do feed de transcrições e eventos; GN-066 [P1] pendente; GN-090 precede captura real.

## GN-075 — painel textual de diagnósticos (2026-11-11)

- `app/static/transcript_diagnostics.js` limita transcrições a 50 e eventos salvos a 10, filtra por fontes registradas, descarta sequências textuais duplicadas, expõe o motivo da regra de classificação e exibe pontuações heurísticas sem apresentá-las como probabilidades calibradas. Não expõe URL, PCM, vídeo, binários ou chave de stream.
- UI dedicada à partida cadastrada com status/erro safe-code por fonte, transcrições voláteis e eventos persistidos. API HTTP inicial e `/ws/matches/{id}/transcripts` para atualização; reconexão limitada e cancelamento ao trocar partida. Não influencia demo sintética nem move a bola.
- `tests/test_transcript_diagnostics.cjs` verifica duas fontes, filtro, segurança, status, eventos; `tests/test_transcript_diagnostics_ui.py` cobre API/WebSocket com fala sintética injetada em memória. Sem teste físico de navegador/Windows nem áudio real.
- **Próxima GN-076 [P1]**; GN-066 [P1] pendente, GN-090 bloqueia ativação de fontes externas pelo site.

## GN-076 — controles de demo e correções da partida cadastrada (2026-11-11)

- `app/static/demo_playback.js` implementa avanço automático sintético em intervalos de 2,5 s, botão iniciar/pausar e cancelamento da programação; para quando a demo termina/erro e aguarda qualquer comando em andamento antes de reiniciar. O botão reiniciar já usa a API compartilhada versionada e é visto pelos outros navegadores.
- A edição auditada de placar, posse ou eventos de uma partida SQLite continua em formulário separado do campo sintético, com mensagem explicativa. `tests/test_demo_playback.cjs` cobre controle de timers, operação pendente e término; `tests/test_demo_playback_controls.py` cobre demo/reset e correção persistida sem confundir estado.
- **Escopo limitado à interface/demo:** iniciar/pausar NÃO inicia nem interrompe a captura/ASR real; sem teste de navegador físico ou Windows. GN-090 e integração operacional ainda necessárias para operação ao vivo.
- **Próximo GN-080 [P0]**; GN-066 [P1] permanece aberta.

## GN-080 — regressões unitárias de interpretação e estado (2026-11-11)

- `tests/test_gn080_unit_matrix.py` acrescenta 67 casos de teste unitários/parametrizados para classificação de texto, eventos, ambiguidades de jogadores/camisas, antecedentes por fonte e limite de tempo, períodos e esquema de ações, além de rejeição de referências inválidas, duplicadas e inconsistentes no `ContractBundle` v1. Testes usam fixtures sintéticas originais, sem serviços externos.
- **Evidência executada antes de marcar concluída:** PR #33, commit `9c1da69`, CI https://github.com/vmendesneto/game_now/actions/runs/43057714416 — **481 passed, 2 skipped** em Python 3.11 e 3.12. Checagem do schema e sintaxe JavaScript também aprovadas.
- **Limites:** não houve execução local/Windows físico, validação com rádio/YouTube real, nem ensaio integrado novo de API + WebSocket + SQLite. Esses critérios pertencem à GN-081/GN-083–085; GN-090 continua bloqueando ativação de fontes remotas pelo site.
- **Próxima GN-081 [P0]:** testes de integração ponta a ponta da API, WebSocket e persistência SQLite com reinício, usando fontes e lances simulados. GN-066 [P1] segue aberta.

## GN-081 — integração API + WebSocket + SQLite (2026-11-11)

- `tests/test_gn081_integration.py` valida um fluxo integrado de duas partidas via API: elencos/fontes, transcrição **sintética** publicada para dois clientes WebSocket e consulta HTTP, isolamento entre partidas, interpretação read-only sem movimentação, gravação explícita de segmento/evento e bola, correção de placar auditada, intervalo e limpeza de bola obsoleta.
- Reabrindo o aplicativo no mesmo SQLite, preserva partida, eventos, correções e histórico de ações, **sem restaurar transcrições voláteis**; a demo `/api/state` permanece independente. Escrita inválida não altera estado ou auditoria. Excluir/recriar uma partida também não reaproveita textos da antiga.
- **Evidência antes da conclusão:** PR #34, commit `8cd6baa`, CI https://github.com/vmendesneto/game_now/actions/runs/43058719362 — **483 passed, 2 skipped** em Python 3.11 e 3.12. Testes de integração baseados em `TestClient`, SQLite temporário e entradas inventadas, sem dispositivos físicos.
- **Limites:** não há captura de rádio/YouTube ligada à UI, ASR real nesse cenário, execução no Windows físico, ensaio temporal de duas fontes sintéticas conflitantes, nem benchmark de partida real. GN-082 cobre simulação de atrasos/comerciais; GN-083–085 exigem evidências com fontes permitidas e Windows.
- **Próxima GN-082 [P0]:** simulador reprodutível de duas rádios, atrasos, anúncios, contradições e silêncios. GN-090 deve preceder entrada de URLs externas pela API/site.

## GN-082 — simulador determinístico de duas rádios (2026-11-11)

- `scripts/simulate_two_radios.py` reproduz quatro fases com relógio UTC **inventado e estável**: lances comuns nas duas fontes com +8 s de atraso fornecido por correspondências explícitas, agrupamento de um gol duplicado, descarte de relato comercial, failover da rádio A para B, contradição após retorno à A, e silêncio/perda de fonte com expiração da região.
- Reutiliza os diagnósticos **somente de prévia** GN-061/062/063/064/065; nenhum resultado escreve no SQLite, inicia subprocessos, resolve URL, retransmite mídia ou constitui alinhamento real de rádios. A comparação das observações contraditórias supõe timestamps já alinhados, não determina automaticamente que se referem ao mesmo lance.
- **Reprodução:** `python -m scripts.simulate_two_radios` imprime JSON determinístico; `python -m pytest -q tests/test_gn082_simulator.py` verifica atraso, deduplicação, comerciais, alternância de fontes, contradição, TTL, ausência de permissão de escrita e igualdade CLI/função.
- **Evidência:** PR #35, commit `2dfe000`, CI https://github.com/vmendesneto/game_now/actions/runs/43059870772 — **486 passed, 2 skipped** em Python 3.11 e 3.12, testes com dados sintéticos.
- **Limites e próximo passo GN-083 [P0]:** obter gravação/permissão de 5–10 min de narração pt-BR e anotar equipe/atleta/zona; calcular métricas reais sem substituir pela simulação. Enquanto isso, GN-090 [P0] de SSRF/URL/localhost pode ser feito independentemente, sem ativar fontes. GN-012/085 dependem do Windows físico.

## GN-090 — segurança de captação HTTP(S) (2026-11-11)

- **GN-083 não executada:** não há no repositório gravação brasileira autorizada de 5–10 minutos com anotações de equipe/jogador/zona. Continuou [ ]; não foram criadas métricas fictícias.
- **GN-090 implementada:** `app/secure_ingest.py` serve apenas no loopback com token efêmero, valida DNS público por conexão, fixa IP de TCP mantendo Host/SNI, revalida até cinco redirecionamentos e recursos HLS (variantes, segmentos, init maps, chaves). Bloqueia DNS privado/misto, credenciais, headers malformados, caminhos inseguros, playlists variáveis ou referências não transformadas.
- `app/audio_capture.py` encaminha mídia remota ao FFmpeg por URI local e whitelist de protocolos `http,tcp,crypto`, não passando URL externa, headers de CDN, TLS, arquivo ou data diretamente a esse processo. Arquivos de teste permanecem opcionais apenas na CLI. A execução usa lista de argumentos (sem shell). A API não inicia captura e não retransmite áudio/vídeo.
- **Evidência local executada antes da entrega:** `python -m pytest -q tests/test_secure_ingest.py` — **22 passed** (Linux, Python 3.13, HLS sintetizado realmente decodificado pelo FFmpeg, além de testes de redirects/DNS/URI/header). `tests/test_gn090_runtime.py` e a suíte Python 3.11/3.12 dependem da CI do PR, e não foram afirmados como aprovados antecipadamente.
- **Limites:** sem narração real autorizada, sem ensaio físico Windows, sem teste de CDN real ou 90 minutos; HLS incomuns podem ser rejeitados. O relay não é um firewall de saída do sistema operacional. O yt-dlp permanece restrito a URL pública YouTube para resolução de metadados; não confundir com captação do site.
- **Próxima GN-091 [P0]:** revisar e documentar instalação, atualização, início e parada no Windows. GN-083 aguarda material autorizado; GN-066 [P1] segue aberta.

## GN-091 — documentação operacional Windows (2026-11-11)

- `docs/INSTALL_WINDOWS.md` reúne instalação limpa PowerShell/Python 3.11 ou 3.12, comandos de início/parada, verificação local `127.0.0.1:8000/health`, atualização por `git pull --ff-only`, cópia SQLite com servidor parado e troubleshooting. Checklist de aceitação física incluído e explicitamente **não preenchido**.
- `scripts/windows_check.py` verifica dependências obrigatórias da demo versus ferramentas opcionais FFmpeg/yt-dlp/ASR, localiza executável yt-dlp ao lado do Python da `.venv`, não baixa modelos, não escreve arquivos e só consulta `127.0.0.1:8000` quando solicitado com `--health`; fornece resumo e `--json`.
- **Evidência local executada:** `python -m pytest -q tests/test_windows_check.py` — **10 passed** no Linux/Python 3.13 (testes simulados de Windows, sem execução física); Python 3.11/3.12 e suíte completa serão verificados na CI. Sem alegar instalação limpa executada no Windows.
- **Pendências físicas reais:** GN-012 (script Windows inicializar de verdade), GN-085 (FFmpeg/yt-dlp/ASR/navegador no Windows), GN-083 (narração autorizada, métricas reais) e GN-084 (partida inteira). GN-091 cobre somente preparo operacional e checklist.
- **Próxima tarefa GN-066 [P1]** (painel diagnóstico de fusão + ajuste de atraso); GN-092 [P1] (backup/export/import) depois.


## GN-031 — permitir partidas gravadas para testes de desenvolvimento (2026-11-11)

- **Motivo:** não é viável depender de jogo transmitido ao vivo durante a implementação. A regra anterior rejeitava automaticamente `is_live=False` mesmo em vídeos disponíveis gravados; isso impedia testes reprodutíveis e frustrava a GN-083.
- **Mudanças:** `app/youtube_capture.py` passa a aceitar `live_status=is_live` (ao vivo), `not_live` (vídeo normal) e `was_live` (transmissão encerrada com gravação); em versões sem `live_status`, aceita duração positiva finita com `is_live=False`. Rejeita `is_upcoming`, `post_live`, estados não confirmados, DRM, `private/premium_only/subscriber_only/needs_auth`, vídeos sem áudio e URLs inseguras. Não remove políticas de segurança GN-037/GN-090, nem baixa arquivo ou repassa áudio/vídeo à API/site.
- **Amostras prolongadas:** `python -m app.youtube_capture --url URL_PERMITIDA --seconds 300` (limite de 600 s) conta PCM mas **não transcreve ou mede precisão do classificador**. Testes determinísticos alterados/novos em `tests/test_youtube_capture.py` verificam vídeo comum, live arquivada, estados futuros, DRM, autorização, metadados antigos e amostra de cinco minutos artificial.
- **Referência de teste do usuário:** https://www.youtube.com/watch?v=Ls4qkPrh4Tk — parece ser narração gravada conforme informado, mas acesso ao áudio, titularidade, permissão específica e desempenho real **não foram verificados** neste ambiente. Nada foi baixado ou coletado dessa URL; não presumir autorização apenas por ser pública.
- **Reprodução no Windows, somente se a captação for permitida:** `.\.venv\Scripts\python.exe -m app.youtube_capture --yt-dlp ".\.venv\Scripts\yt-dlp.exe" --url "https://www.youtube.com/watch?v=Ls4qkPrh4Tk" --seconds 300`. Use `--seconds 5` para prova curta antes. A captação por CLI não inicia o site nem o ASR.
- **Estado das tarefas:** melhoria do resolvedor pronta mediante testes/CI; GN-031 **permanece [ ]** aguardando prova real permitida, GN-083 **permanece [ ]** até 5–10 min transcritos e avaliação com gabarito, GN-012/GN-085 requerem Windows físico. **Próxima GN-066 [P1]** conforme STATUS e ROADMAP (GN-092 depois).


## GN-031/GN-090 — relatório Windows de 5XX no relay e melhoria (2026-11-11)

- **Evidência real recebida:** `git pull --ff-only` atualizou a `main` de `00a4846` a `1529df7`. No Windows, `python -m app.youtube_capture --yt-dlp ".\.venv\Scripts\yt-dlp.exe" --url "https://www.youtube.com/watch?v=Ls4qkPrh4Tk" --seconds 5` terminou com `Capture error: FFmpeg failed to decode stream: ... Server returned 5XX Server Error reply` (`[private media relay]`). **O 5XX é resposta da camada local GN-090; a causa remota não era revelada.** Não confirmar HTTP 403 sem diagnóstico adicional.
- **Hipótese externa conhecida:** formatos `googlevideo.com/videoplayback` recém resolvidos podem retornar 403 nos primeiros ~5 s (relatos yt-dlp/Nuclear em 2026). `app/youtube_capture.py` agora aguarda 5,5 s **somente** nesses URLs de mídia, sem acrescentar tentativas automáticas que contornem restrições. HLS e outras fontes não recebem espera artificial.
- **Erro seguro:** `app/secure_ingest.py` guarda um motivo de falha sintético, sem revelar URLs assinadas, tokens ou cabeçalhos, e `app/audio_capture.py` o apresenta quando FFmpeg falha por 502 do relay. Ex.: `upstream_http_403` indica resposta do provedor, diferente de `destination_or_playlist_rejected` e `transport_error`. Não altera isolamento, não usa cookies e não disponibiliza mídia no site.
- **Testes:** `tests/test_gn031_relay_recovery.py` adiciona regressões de espera seletiva, retorno seguro e cenário real de FFmpeg ligado a upstream simulado 403. Prova local parcial: testes existentes de `tests/test_secure_ingest.py` — 22 passed; cenário isolado de 502 local com `upstream_http_403`. Suíte PR 3.11/3.12 será validação antes do merge.
- **Ainda pendente:** retorno físico do Windows ao executar novamente o vídeo autorizado; GN-031/GN-083 permanecem [ ]. **GN-066 [P1]** ainda próxima tarefa independente conforme roadmap.


### GN-083 — pipeline offline e prova física de captura (2026-11-11)

- **Evidência fornecida pelo usuário:** diagnóstico YouTube gravado no Windows por 300 segundos, 9.600.000 bytes s16le mono 16 kHz, 600 chunks, sem retransmissão de áudio. Não recapturar. Essa evidência confirma ingestão, não a qualidade do ASR.
- **Implementação parcial preparada:** `app/gn083_offline.py` (leitura PCM/WAV local em blocos, GN-040/041 ASR opcional, classificadores GN-050–055 e avaliação temporal conservadora); CLI `scripts/gn083_audit.py` que não baixa mídia nem escreve no banco; testes sintéticos `tests/test_gn083_offline.py` e guia `docs/GN-083.md`. Não ativar ingestão por API nem mudar estado da partida.
- **Validação:** smoke local da lógica de métricas e validação estrutural realizado em ambiente Linux Python 3.13 com amostras artificiais; testes integrais da implementação e CI Python 3.11/3.12 devem ser verificados no PR antes de merge. **Nenhum teste de reconhecimento de fala na gravação foi realizado** (bytes PCM e gabarito ausentes no ambiente).
- **Bloqueio [ ]:** para fechar GN-083, executar o CLI sobre amostra local autorizada e comparar com gabarito manual independente; registrar precisão, recall, cobertura e WER observados, inclusive falhas. Autorizações não devem ser presumidas apenas porque o vídeo está público. GN-031 também [ ] por esse requisito.
- **Próxima tarefa independente:** GN-066 [P1] (fusão/calibração manual de atraso), depois GN-092; GN-084 e GN-085 somente com provas reais correspondentes.

### GN-066 — painel de prévia de fusão (2026-11-11)

- Implementação candidata: app/fusion_diagnostics.py, app/static/fusion_diagnostics.js, app/main.py, painel de diagnóstico. Une GN-061/063/064 em resposta exclusivamente diagnóstica, com ajustes temporários de -120 a +120 segundos e razões legíveis; nunca grava dados, não ativa captura, não move bola.
- Testes criados: tests/test_gn066_fusion_diagnostics.py e tests/test_fusion_diagnostics.cjs (alinhamento e conflito, fontes isoladas por partida, validação, imutabilidade, UI).
- **Validação confirmada:** PR #41, run 43076830181, **577 passed/2 skipped** em Python 3.11 e 3.12; testes Node do modelo visual integrados ao pytest. Ajustes de intervalo e decisões foram simulados; **nenhum offset foi medido em transmissão real**.
- **GN-066 [x]**. Próxima GN-092 [P1] (backup/exportação/importação), GN-083 [ ] até áudio permitido e gabarito.


### GN-092 — exportação e recuperação SQLite (2026-11-11)

- Candidata: scripts/gn092_backup.py exporta banco SQLite consistente via API sqlite3.backup, com ZIP de manifesto e hashes SHA-256. Inclui logs rotativos opcionalmente e **nunca inclui áudio**. Restore verifica schema, integridade, chaves e referências antes de trocar banco de destino; recusa sobrescrita por padrão e WAL/SHM residuais. Guia docs/BACKUP_RESTORE.md e referência em docs/INSTALL_WINDOWS.md.
- Testes de restauração real de SQLite com fontes, escalação, metadados e integridade; rejeição de arquivos maliciosos, ZIP alterado, logs e sobrescrita. Arquivo: tests/test_gn092_backup.py.
- **Validação aprovada:** CI PR #42, run 43078344748, **586 passed/2 skipped** Python 3.11 e 3.12, incluindo recuperação real de SQLite, rosters/fontes, SHA-256, logs opcionais e rejeição de ZIP malicioso. GN-092 **[x]**. Não foi feita restauração física no Windows do usuário; GN-085 ainda pendente.
- **Próxima GN-035 [P1]** (telemetria por fonte), GN-036 [P1] (VAD apenas depois de benchmark), GN-084/085 (ensaios reais); GN-083 [ ] aguarda áudio autorizado e gabarito.

### GN-083 — continuação: fluxo direto de transcrição de YouTube (2026-11-11)

- Novo app/gn083_stream.py e opção --youtube-url em scripts/gn083_audit.py: GN-031/GN-090 transmite PCM somente em memória, GN-041 processa janelas, inferência ASR em thread, e classificadores textuais geram relatório; usa --yt-dlp, --seconds e --permission-confirmed para fonte pública autorizada. Nenhuma revalidação de captura realizada, nenhuma mídia gravada ou exposta.
- Testes unitários tests/test_gn083_stream.py usam capturador e ASR **falsos** para checar limite de duração, fechamento do stream, recusa de URL privada, formato PCM, exigência de permissão e relatório sem áudio/URL.
- **Validação inicial pendente de CI** nesta alteração; ainda não foi executado ASR real do vídeo de referência por falta de permissão específica/gabarito, e GN-083 [ ] permanece pendente.


## GN-083 — subescopo de detector contínuo (2026-11-11)

- **Implementação entregue para testes/CI:** app/match_start_detection.py,
  app/gn083_live.py e scripts/gn083_live.py: fases inferidas por evidências
  independentes, sem início manual, bloqueio de falso início, áudio contínuo
  com PCM limitado e ASR em worker. Campinho alterna para prévia efêmera via
  app/main.py e app/static/app.js quando o monitor da partida está ativo.
- API de ingestão textual restrita ao loopback; nenhuma mídia, evento,
  placar, cronômetro ou posição é persistido. Posição só aparece com texto
  explícito e após confirmação da fase, expirando em 8 segundos. A força
  da regra não é confiança calibrada; atraso real ainda não foi verificado.
- Regressões sintéticas adicionadas: tests/test_gn083_match_start.py e
  tests/test_gn083_live.py. Conferir CI Python 3.11 e 3.12 no PR antes de
  alegar resultados aprovados.
- **GN-083 [ ]**: falta validar início/intervalo/retomada com narração
  real autorizada e um gabarito anotado, além de métricas de 5–10 minutos.
  Evidência anterior de 300 s / 9.600.000 bytes PCM demonstra apenas
  decodificação. relatorio083.json não está versionado.
- **Como continuar:** docs/GN-083.md contém comandos do monitor para Windows;
  observar falsos disparos, relógio, estabilidade, atraso e métricas reais
  sem repetir a prova já realizada de decodificação de PCM. GN-084/085 depois.
