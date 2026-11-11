# Game Now — acompanhamento de futebol a partir de narrações

**Estado:** demonstração offline, configuração de partidas/fontes e controle/auditoria persistentes; módulo de captura rádio FFmpeg em CLI com fixtures aprovadas, ainda sem ingestão de rádio/YouTube pelo site ou ASR. Acompanhe [STATUS.md](STATUS.md) e [ROADMAP.md](ROADMAP.md).

## Executar a demonstração offline

Requer Python 3.11 ou 3.12. O modo demo não precisa de FFmpeg, GPU, modelo Whisper, rádio ou conexão de streaming. Dependências Python são instaladas na primeira execução.

**Windows:** execute `iniciar_windows.bat` na pasta do repositório. Ele cria `.venv`, instala as dependências e inicializa o servidor.

**Instalação limpa, atualização, parada e diagnóstico:** siga [docs/INSTALL_WINDOWS.md](docs/INSTALL_WINDOWS.md), incluindo checklist de verificação física e `python -m scripts.windows_check --json`.

**Terminal (Windows/macOS/Linux):**

```bash
python -m venv .venv
# Linux/macOS: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Abra http://127.0.0.1:8000 no navegador. Clique em **Próximo relato** para simular dois narradores com atraso, um comercial, um cruzamento, um gol duplicado, replay e silêncio. O estado de ambos os navegadores é compartilhado pelo WebSocket `/ws`.

## Endpoints

| Endpoint | Método | Uso |
| --- | --- | --- |
| `/` | GET | Interface de campo SVG responsiva |
| `/health` | GET | Diagnóstico honesto sobre FFmpeg, ASR e persistência |
| `/api/schema` | GET | JSON Schema derivado do contrato tipado v1 |
| `/api/state` | GET | Snapshot atual da demo |
| `/api/demo/next` | POST | Próximo relato sintético, difunde por WebSocket |
| `/api/demo/reset` | POST | Reinicia partida de demonstração |
| `/ws` | WebSocket | Snapshots de estado do demo (sem mídia) |
| `/api/matches` | GET, POST | Listar e cadastrar partidas |
| `/api/matches/{id}` | GET, PUT, DELETE | Detalhar, editar e excluir partida |
| `/api/matches/{id}/players` | GET, PUT | Elenco completo dos dois clubes, com posição, camisa, apelidos e titularidade |
| `/api/matches/{id}/resolve-player` | POST | Resolver menção isolada (nome, apelido, camisa), retornando `resolved`, `ambiguous` ou `unknown` |
| `/api/matches/{id}/resolve-narration` | POST | Resolver nomes de equipes/atletas, camisas e pronomes em texto livre sem alterar a partida (GN-051) |
| `/api/matches/{id}/resolve-possession` | POST | Detectar posse/troca de posse com referência explícita no texto, sem persistir a hipótese (GN-052) |
| `/api/matches/{id}/resolve-region` | POST | Identificar faixa 1–5 e corredor esquerdo/centro/direito com evidência textual, sem alterar a posição real/persistida (GN-053) |
| `/api/matches/{id}/resolve-event` | POST | Identificar um único tipo de lance afirmativo do contrato v1 por evidência textual (GN-054; não grava eventos/placar) |
| `/api/matches/{id}/resolve-confidence` | POST | Pontuar separadamente evidência de jogador, equipe, região, evento e atualidade (GN-055; heurística não calibrada) |
| `/api/matches/{id}/flow` | GET | Período, titulares em campo, substituições, expulsões, acréscimos e histórico |
| `/api/matches/{id}/actions` | POST | Registrar operação de jogo (GN-024) |
| `/api/matches/{id}/corrections` | GET, POST | Corrigir placar, posse e eventos com auditoria (GN-025) |
| `/api/matches/{id}/sources` | GET, PUT | Criar, editar, habilitar e desabilitar fontes persistidas (GN-032; sem ingestão) |
| `/api/matches/{id}/state` | GET, PUT | Snapshot do contrato v1, incluindo eventos, transcrições e bola |

## Configuração e banco de dados

A seção **Partidas e elencos**, abaixo da demonstração, permite criar/editar/excluir partidas e cadastrar os dois elencos pelo navegador, sem editar Python. Posição é metadado de elenco separado do contrato de eventos v1. Cada PUT de elenco/fontes substitui a lista integral; 409 significa conflito de referências históricas, camisa duplicada ou equipe inválida. Dados são escritos em `data/game_now.sqlite3` por padrão (não versionado); escolha outro caminho com `GAME_NOW_DB_PATH` antes de iniciar. Copiar o arquivo com o servidor parado permite backup manual. Não apagar o arquivo para atualizar o aplicativo.

A GN-022 acrescenta identificação conservadora de atletas: `POST /api/matches/{id}/resolve-player` recebe `{"mention":"camisa 10","team_id":null}`. Nomes são normalizados por caixa, acentos e pontuação. Sem equipe de contexto, dois atletas com a mesma camisa ou apelido geram `ambiguous`, nunca um palpite. O formulário no painel de elencos permite testar. Isso **não** é transcrição nem resolução de entidades em texto livre (GN-051).

Na **GN-051**, `POST /api/matches/{id}/resolve-narration` recebe `{"text":"João do Azul recebe a bola, ele chuta"}` e devolve menções com índices no texto original, IDs somente quando únicos, lista de candidatos quando ambíguos e indicação da regra usada. O texto é limitado a 2.048 caracteres; a identificação se baseia exclusivamente no elenco salvo e nos nomes dos clubes, sem adivinhar posse, jogador ou zona no estado da partida. Referências como `ele` somente são vinculadas a um único antecedente explícito na frase. O uso opcional de `source_id`, `sequence`, `start_seconds`, `end_seconds` e `previous` permite carregar uma referência de uma janela anterior **apenas na mesma fonte**, em sequência imediata e com intervalo máximo de 8 segundos. Replay, comercial e texto sem pista de lance não criam contexto futuro. A API é diagnóstica e não altera o feed, o placar, a bola nem o contrato v1.

O snapshot persistente está disponível em `/api/matches/{id}/state`. Ele exige um `ContractBundle` v1 válido e não altera a configuração da partida; edite partida/elenco pelos endpoints próprios. **O botão Próximo relato continua operando a demo separada**, sem preencher histórico das partidas cadastradas; integração entre eles ocorrerá numa etapa futura. Fontes reais e sua captura continuam não implementadas.

## Testar

```bash
python -m pip install -r requirements-dev.txt
python scripts/export_schema.py
python -m pytest -q
```

O contrato reside em `app/contracts.py`, o schema exportado em `schemas/v1.schema.json`, fixtures em `fixtures/`, e a decisão de arquitetura em [docs/ADR-0001.md](docs/ADR-0001.md). Não edite o JSON schema manualmente: regenere com o script e revise o diff. Os testes verificam ambos.

## Controle de captura e encerramento (GN-016)

O `CaptureSessionController` em `app/capture_supervisor.py` coordena o ciclo de vida dos workers no backend, encerra por fonte e espera o FFmpeg sair antes de retornar. Ele não habilita captura pela interface: a operação real permanece separada do modo demo. Testes Linux simulam fontes e confirmam que um subprocesso termina sem ficar órfão; o ensaio Windows ainda pertence à GN-085.

## Política de fontes e retenção das transcrições (GN-094)

O uso de mídia pública depende de autorização e termos aplicáveis, independentemente de a aplicação não retransmitir o áudio. O inventário de licenças e o checklist de utilização estão em [docs/GN-094.md](docs/GN-094.md). O texto volátil do feed pode ser limitado por `GAME_NOW_TRANSCRIPT_TTL_SECONDS` (padrão 3600) e `GAME_NOW_TRANSCRIPT_MAX_ENTRIES` (padrão 100); reinicie o servidor após alterar as variáveis. Essas opções não apagam eventos, correções ou backups persistidos.

## FFmpeg (GN-030 — conversão de áudio em ferramenta de diagnóstico)

Para o modo demo não é necessário instalar FFmpeg. A ferramenta GN-030 precisa de FFmpeg no PATH. A CI instala FFmpeg e testa decodificação real de fixtures MP3, AAC e HLS como PCM mono 16k (`tests/test_audio_capture.py`). Para testar sem acessar a internet:

```bash
python -m app.audio_capture --file caminho/arquivo.mp3 --seconds 5
```

Para diagnosticar uma rádio pública permitida, cuja URL você fornece:

```bash
python -m app.audio_capture --url https://exemplo.radio/stream.mp3 --seconds 5
```

O comando apenas imprime estatísticas JSON, **não** reproduz ou salva áudio e não alimenta o site. O URL ilustrativo acima não é uma estação verificada. A função Python `pcm_chunks` oferece blocos binários de 16 kHz para etapas seguintes. A opção `--file` é somente CLI/testes e não é exposta pela API. A GN-090 agora protege redirecionamentos e HLS com relay local de DNS/IP público validado e TCP fixado ao endereço verificado. Ainda requer teste em fonte real/Windows. **Nenhuma rádio real ou Windows foi validado nesta etapa.**

## Limitações (importante)

- **O módulo GN-030 permite capturar e converter áudio de rádio por FFmpeg isoladamente**, mas não há conexão do cadastro ao capturador, transcrição ASR nem ingestão de YouTube pelo site. GN-031 continua pendente.
- A interpretação no modo demo é um conjunto pequeno de palavras-chave e dados de cenário. O agrupamento de fontes é pré-indicado no script sintético; não é fusão real.
- A posição mostrada é **uma zona de 15** relativa ao sentido de ataque, não coordenada precisa. Comerciais e replays não devem mover a região; sem evidência, o estado pode ser desconhecido/expirado.
- O **demo sintético** é volátil e reinicia com o processo. Partidas cadastradas, elencos, fontes e snapshots de eventos são persistidos em SQLite (GN-023). São ambientes separados até integrar narrações reais.
- `iniciar_windows.bat` ainda exige validação no computador Windows físico.
- Servidor escuta **somente 127.0.0.1**. Não publique a porta na Internet sem autenticação e HTTPS.

## Continuidade

Leia [STATUS.md](STATUS.md), [ROADMAP.md](ROADMAP.md) e [AGENTS.md](AGENTS.md) antes de trabalhar. Marque tarefas somente depois de evidências reais; testes de CI Linux não equivalem a testes do Windows.

## Operações, correções e fontes (GN-024/025/032)

Os três painéis aparecem ao selecionar uma partida salva. As **operações** alteram o jogo cadastrado, não o simulador: `POST /api/matches/{id}/actions` aceita `{"kind":"substitution","player_out_id":"player-001","player_in_id":"player-012","match_seconds":2800}`, `{"kind":"red_card","player_id":"player-001"}`, `{"kind":"half_time"}`, `{"kind":"second_half"}`, `{"kind":"added_time","seconds":240}` ou `{"kind":"finish"}`. O relógio é opcional e não pode retroceder. O segundo tempo troca os lados automaticamente; intervalos invalidam posse/posição antigos. A escalação fica congelada após a primeira operação para não perder referência do histórico. Não há limite de substituições por competição nesta etapa.

Para corrigir um resultado, use `POST /api/matches/{id}/corrections` com `{"kind":"score","home_score":1,"away_score":0,"reason":"Conferência do lance","actor":"operator"}`. `kind="possession"` exige `team_id` (nulo quando desconhecido), e aceita `player_id` da mesma equipe. `kind="event"` aceita `event_id` e `changes` com campos permitidos: `kind`, `team_id`, `player_id`, `zone`, `uncertainty`, `match_seconds`. A fonte/proveniência e o ID original do evento não podem ser substituídos. Toda correção tem motivo, autor, snapshot anterior e posterior auditados no SQLite; também há auditoria automática quando se altera placar via editor legado ou substitui o estado pela API anterior. Não fornece autenticação nem assinatura criptográfica da trilha; uso local somente.

O cadastro de fontes permite várias rádios e vídeos públicos do YouTube, cada qual com nome, tipo, URL e flag `enabled`. O `PUT /sources` substitui a lista completa; alterações que removem fontes citadas em eventos/transcrições retornam 409. São aceitos URLs públicos HTTP(S) para rádio e HTTPS de `youtube.com` / `youtu.be` para YouTube, sem credenciais ou IP local. URLs ausentes são placeholders, não fontes operacionais. **A validação do cadastro não substitui defesa de rede:** GN-090 faz verificação adicional no relay de captação (DNS, redirecionamentos, segmentos HLS e IP final). Nenhuma fonte é executada/reproduzida pelo cadastro.

Testes de integração `tests/test_match_flow.py`, `tests/test_corrections.py`, `tests/test_sources.py` comprovam rejeições, atomicidade, edição, consulta, reinício SQLite e interface HTTP. CI Linux, **28 testes em Python 3.11 e 3.12**, schema v1 preservado e JS sintaticamente válido: https://github.com/vmendesneto/game_now/actions/runs/42884686478. Persistem validações físicas no Windows, rádio real e modelos ASR.

## Logs estruturados (GN-015)

O servidor grava requisições HTTP em JSON em `data/game_now.log` por padrão; configure outro arquivo antes de iniciar com `GAME_NOW_LOG_PATH`. Log contém timestamp UTC, status, caminho (sem query), método, duração e ID devolvido ao cliente via header `X-Request-ID`, sem o corpo das solicitações ou as URLs de rádio do formulário. Há rotação a cada 2 MB, 3 backups (máximo nominal 8 MB de arquivos), e testes cobrindo rotatividade, ausência de credenciais no corpo e códigos de erro. Não é necessário manter o arquivo para preservar as partidas, que seguem no SQLite.

CI após GN-015/GN-030: **35 testes passaram em Python 3.11 e 3.12**: https://github.com/vmendesneto/game_now/actions/runs/42886144524. O contrato v1 segue inalterado. A validação do Windows físico está pendente.

## Buffer e resolução de YouTube (GN-034 / GN-031 parcial)

A GN-034 implementa `MultiSourceAudioBuffer` em `app/audio_buffer.py`, com frames PCM mono 16 kHz, marca temporal de captura, remoção por idade/bytes, limite de fontes e snapshots thread-safe. O teste `tests/test_audio_buffer.py` inseriu 20.000 chunks em duas fontes independentes sem ultrapassar os limites. Esse buffer está disponível para o futuro orquestrador, mas ainda não recebe blocos automaticamente do site.

A GN-031 **continua pendente**. O arquivo `app/youtube_capture.py` já contém uma implementação preliminar: invoca `yt-dlp` sem cookies/configuração pessoal e sem autenticação, aceita transmissões públicas em andamento ou gravações já concluídas, prioriza formato somente de áudio, não salva URLs assinadas e envia o endereço transitório ao relay protegido (GN-090) que alimenta o FFmpeg. O código descarta headers de autenticação e bloqueia URLs privadas iniciais; redirecionamentos e recursos HLS são protegidos pelo relay GN-090; URLs de CDN ainda podem expirar. Os testes com `tests/test_youtube_capture.py` usam um executável yt-dlp **falso**, portanto **não comprovam funcionamento com YouTube Live real**. Em um ambiente autorizado, instalar yt-dlp oficial no PATH e fornecer uma transmissão pública que permita a captação; sem isso, não afirmar GN-031 finalizada. Nada é embutido no site.

**Última CI:** 47 testes em Python 3.11/3.12, JSON schema v1 preservado, JavaScript válido, codec FFmpeg real em fixtures: https://github.com/vmendesneto/game_now/actions/runs/42888042259. Testes físicos no Windows e mídia pública autorizada seguem pendentes.


## Diagnóstico YouTube Live ou gravado e retomada de áudio (GN-031 parcial / GN-033)

**GN-031 requer ainda uma validação real autorizada.** O yt-dlp aceita metadados de transmissões públicas *ao vivo*, gravações comuns (`not_live`) ou lives arquivadas (`was_live`). Escolhe áudio-only quando existir ou formato combinado se for a única opção; a saída do FFmpeg é sempre PCM mono 16 kHz e nenhuma mídia é servida ao site. A ferramenta de diagnóstico devolve somente contadores e tempo; nunca a URL assinada, mídia, cookies ou credenciais. Os testes automatizados usam metadados sintéticos, **não** uma transmissão real.

No Windows, com FFmpeg instalado no PATH e Python 3.11/3.12 configurado, instale o yt-dlp oficial *opcionalmente* no mesmo ambiente virtual (não é necessário para o modo demo):

```bat
.venv\Scripts\activate.bat
python -m pip install --upgrade yt-dlp
python -m app.youtube_capture --url "https://www.youtube.com/watch?v=ID_DO_VIDEO_PERMITIDO" --seconds 5
```

Substitua a URL ilustrativa por um vídeo público **ao vivo ou gravado, com captura permitida**. Se estiver indisponível, em estreia futura, aguardando processamento, sem áudio decodificável, inacessível sem login ou com DRM, a ferramenta deve falhar com uma mensagem clara; não adicionar cookies, assinatura artificial, extração de DRM nem bypass. Para validar em ambiente diferente, execute o mesmo comando com `python` apropriado e yt-dlp/FFmpeg no PATH. Exemplo de **formato esperado**, não resultado de execução real:

```json
{"source_id":"youtube-diagnostic","sample_rate":16000,"channels":1,"format":"s16le","bytes":160000,"chunks":10,"seconds":5.0,"audio_retransmitted":false}
```

O processamento não grava arquivos de mídia. Uma transmissão encerrada **com gravação acessível** é aceita; somente conteúdo indisponível, ainda não iniciado ou restrito retorna erro. Os endereços dos servidores de mídia expiram: `app/capture_supervisor.py` permite criar um worker independente por fonte, com timeout de ausência de PCM, backoff exponencial de 1 a 30 segundos por padrão e encerramento ao acionar `asyncio.Event`. A cada tentativa de YouTube, o worker chama o resolvedor novamente; não reutiliza o endereço expirado. Blocos PCM são guardados no `MultiSourceAudioBuffer` por fonte, com limites de memória e sem transmissão ao site. Os estados internos não incluem URLs ou mensagens de erro potencialmente sensíveis.

Esse supervisor **ainda não é iniciado pelos botões de fontes nem integra ASR ou o site**; integração operacional/telemetria será tratada nos próximos itens. Testes da GN-033 simulam desconexão, reconexão, fluxo sem áudio, fonte travada, múltiplas fontes, expiração de URL e parada segura. Nada disso equivale à validação de uma live real, de políticas dos criadores, da estabilidade por 90 minutos, de redirecionamentos/HLS com DNS ou do Windows físico.


### YouTube Live sem formato áudio-only (GN-031 — compatibilidade)

Algumas transmissões públicas ao vivo não oferecem uma faixa de áudio separada. Nesses casos, o resolvedor prefere sempre um formato exclusivamente de áudio, mas agora pode selecionar uma **variante combinada de vídeo e áudio** quando essa for a única disponível sem DRM. O FFmpeg já recebe `-vn` e entrega apenas **PCM mono 16 kHz**, sem salvar vídeo, repassar mídia ao navegador ou publicar URLs de stream. **Limitação:** em uma variante combinada, a rede pode transferir bytes de vídeo juntamente com áudio antes do descarte; não é correto afirmar que o tráfego de origem tem somente áudio.

No PowerShell, após `git pull --ff-only`, teste com vídeo público gravado ou live ativa cuja captação seja permitida:

```powershell
.\.venv\Scripts\python.exe -m app.youtube_capture --yt-dlp ".\.venv\Scripts\yt-dlp.exe" --url "https://www.youtube.com/watch?v=ID_DA_LIVE" --seconds 5
```

Se a fonte não tiver áudio decodificável, não oferecer URL pública acessível ou exigir autenticação/DRM, a ferramenta continua falhando sem tentativas de contorno. Se o erro persistir, inspecione os formatos sem baixar mídia:

```powershell
.\.venv\Scripts\yt-dlp.exe --ignore-config --no-cache-dir --list-formats "https://www.youtube.com/watch?v=ID_DA_LIVE"
```

Testes Linux verificam prioridade do áudio-only, fallback combinado, rejeição de fonte sem áudio/DRM e conversão FFmpeg de arquivo real com vídeo e áudio. A validação da URL enviada pelo usuário no Windows ainda precisará ser repetida após atualizar o código.


### Correção dos formatos HLS YouTube Live 233/234 (Windows, 2026-11-11)

Em algumas lives `yt-dlp -F` lista `233` e `234` como **audio only / m3u8 / codec unknown**. Nesses casos, os metadados podem conter `vcodec="none"` com `acodec` ausente ou `null`. A captura aceita essas variantes HLS sem codec identificado, porque são marcadas pelo extrator como exclusivamente de áudio; o FFmpeg verifica a presença real de áudio ao decodificar. Formatos com `acodec="none"`, DRM ou somente vídeo continuam rejeitados. O teste Linux simula exatamente essa combinação sem usar o YouTube real.

Com `git pull --ff-only` na pasta Documentos, repita:

```cmd
.\.venv\Scripts\python.exe -m app.youtube_capture --yt-dlp ".\.venv\Scripts\yt-dlp.exe" --url "https://www.youtube.com/watch?v=SWEYimqD_50" --seconds 5
```

Para vídeos antigos a URL não precisa estar ao vivo; é necessário que a gravação esteja acessível e o uso do áudio seja permitido. Não divulgar URLs assinadas, cookies nem metadados completos de yt-dlp.

## GN-040 — ASR local opcional (português, CPU)

O **modo demonstração não instala nem carrega modelos**. Para transcrever uma amostra local em português, primeiro instale as dependências opcionais no mesmo venv (com Python 3.11/3.12):

```powershell
python -m pip install -r requirements-asr.txt
python -m app.asr --file exemplo-16k-mono.wav --model tiny --cpu-threads 2
```

A entrada deve ser arquivo **WAV PCM s16le mono, 16.000 Hz**, de até 30 segundos por padrão (ajustável com `--max-seconds` até 120). Para converter uma amostra autorizada via FFmpeg: `ffmpeg -i origem.wav -vn -ac 1 -ar 16000 -c:a pcm_s16le exemplo-16k-mono.wav`. O arquivo pertence ao operador; **não é criado nem distribuído pelo servidor**. A saída é JSON com idioma `pt`, texto, tempo e segmentos, sem mídia. Esta CLI não ativa fontes nem alimenta o site.

Os modelos disponíveis são `tiny` (padrão), `base`, `small` e `medium`. O primeiro uso do modelo baixa os pesos para o cache local do faster-whisper e exige Internet; execuções subsequentes podem utilizar o cache. A inferência roda exclusivamente na **CPU**, quantização `int8`. Memória e latência variam por modelo e computador; não há benchmark Windows/GPU ainda (GN-044). O endpoint `/health` só verifica se o pacote está instalado e **não** prova que os pesos estão baixados ou que houve transcrição.

`tests/test_asr.py` valida o contrato de áudio sem download; `.github/workflows/asr-smoke.yml` realiza inferência de verdade com fala portuguesa sintetizada offline por `espeak-ng` e modelo `base`. Resultados do workflow, quando disponíveis, estão nas Actions do GitHub. A integração com janelas contínuas, múltiplas fontes e feed web pertence às GN-041/042/043; isso **não** significa áudio de rádio/YouTube já transcrito nem validado em Windows.


## GN-041 — janelas contínuas (núcleo Python)

`app/asr_windows.py` combina os chunks PCM 16 kHz mono da captura em janelas sobrepostas por fonte (padrão 6 segundos, 2 segundos de sobreposição). `RollingASRProcessor(CPUTranscriber(...))` produz `WindowTranscript` com `source_id`, sequência, início/fim relativo, idioma, texto bruto e `new_text` com repetição reduzida. A deduplicação é conservadora (2 ou mais palavras idênticas após normalização); não substitui alinhamento semântico ou fusão entre fontes. `finish(source_id)` libera o buffer. O `RollingASRProcessor` é **síncrono**; nunca chamar diretamente em um handler `async` FastAPI (GN-043).

Teste de montagem, sem depender de modelo ou rede:

```bash
python -m scripts.benchmark_asr_windows
python -m pytest -q tests/test_asr_windows.py
```

A CI também executa modelo ASR real sobre janelas de fala sintética portuguesa; o teste **não** usa rádio/YouTube e não prova o desempenho ou a qualidade em transmissões esportivas ao vivo. Referência: https://github.com/vmendesneto/game_now/actions/runs/43016880967. A disponibilização do feed no site e o agendamento assíncrono serão implementados nas GN-042/043.

## GN-042/GN-043 — feed textual e workers assíncronos

Após cadastrar uma partida e suas fontes, consulte `GET /api/matches/{id}/transcripts` (opcional: `?source_id=radio-01&limit=50`). Resposta contém `mode=volatile_text_only`, `sources` com estado de processamento e `entries` com `source_id`, texto, `language=pt`, sequência e horários UTC. O WebSocket `/ws/matches/{id}/transcripts` envia `snapshot` inicial e mensagens `status`/`transcript`, sem mídia. Uma fonte não cadastrada não aparece no feed HTTP/WS.

O motor Python `AsyncSourceTranscriber` em `app/transcription_runtime.py` usa `asyncio.to_thread` para não executar o reconhecimento bloqueante dentro do loop FastAPI. Cada fonte mantém sua própria ordem, com locking por fonte; os listeners WebSocket têm filas limitadas e, se atrasarem, podem perder mensagens intermediárias. Para publicar, um futuro controlador de captura deverá instanciar o worker com `RollingASRProcessor(CPUTranscriber(...))`, fornecer blocos PCM e timestamp de captura. **Isso ainda não ocorre automaticamente.** Não há endpoints de upload de áudio, nem start/stop de rádio/YouTube; será adicionada ativação operacional controlada após tratar as restrições de rede (GN-090) e supervisão da sessão (GN-074).

A CI verifica duas conexões WebSocket recebendo o mesmo texto enquanto a CPU é artificialmente bloqueada e confirma que HTTP continua respondendo. O teste separado com Whisper real permanece exclusivo ao CPU Linux e ao áudio sintetizado. Evidência: https://github.com/vmendesneto/game_now/actions/runs/43018620370.


## GN-046 — vocabulário de times, atletas e termos esportivos

O faster-whisper aceita um `initial_prompt` opcional criado por `build_vocabulary_prompt(match)`, com nomes dos clubes, jogadores, apelidos e termos futebolísticos. Para testar no Windows/local com a partida já cadastrada no SQLite do Game Now:

```powershell
python -m pip install -r requirements-asr.txt
python -m app.asr --file exemplo-16k-mono.wav --model base --match-id match-001
```

Sem `--match-id`, o ASR funciona sem contexto, como antes. `GAME_NOW_DB_PATH` define o SQLite consultado, e a partida precisa existir. O prompt tem limite estrito de caracteres e é passado somente ao reconhecimento local; não altera as escalações nem o contrato persistente.

**Comparação A/B reproduzível:** teste `tests/test_asr_vocabulary_real.py` (CI https://github.com/vmendesneto/game_now/actions/runs/43019542053) usou **o mesmo áudio português sintetizado**, com modelo `base` CPU int8: 1 dos 6 termos de referência apareceu na condição sem contexto, contra 6 de 6 com o contexto. Isso é **taxa de presença dos termos nessa única frase**, não WER, não um estudo estatístico nem garantia de melhora em jogo real. Nomes sugeridos pelo prompt podem aparecer incorretamente; a resolução de atletas deve continuar exigindo evidência contextual (GN-051).


## GN-050 — distinguir o contexto da narração (núcleo conservador)

`app.narration_classifier.classify_narration(text)` reconhece indícios explícitos de **lance atual, publicidade, conversa, análise, replay ou desconhecido**. Uma frase sem evidência fica `unknown`; comercial, replay e análise têm prioridade para que a simples presença de "gol" não dispare uma atualização no campinho. O resultado informa a regra que casou, **não** uma probabilidade calibrada.

```python
from app.narration_classifier import classify_narration
print(classify_narration("No replay vemos o gol novamente."))
# NarrationDecision(label=<NarrationLabel.REPLAY: 'replay'>, matched_cue='no replay')
```

`fixtures/narration_labeled.json` contém **39 exemplos fictícios rotulados**. `python -m pytest -q tests/test_narration_classifier.py` compara cada exemplo com seu rótulo, inclui negativos, prioridade e proteção contra palavras parcialmente coincidentes. A classe interna `conversation` converte para `unknown` no contrato v1 para preservar compatibilidade. Nenhum evento/posição é criado pelo classificador, que ainda não é conectado ao fluxo real do feed. Isto é baseline de regras; avaliação em narração legítima e variada é GN-058, não um resultado obtido nesta etapa.

## GN-052 — identificação diagnóstica de posse

`POST /api/matches/{id}/resolve-possession` recebe `{"text":"Bruno do Vermelho com a bola","previous_team_id":"team-azul"}` e retorna `status=explicit`, `team_id`, `player_id` e `changed_team=true` apenas quando o texto de lance atual contém **evidência explícita de posse** vinculada sem ambiguidade a jogador/clube da escalação persistida. Frases como "Bola com o camisa nove do Azul" são aceitas; passe sem recepção explícita, nomes repetidos, comercial, replay, gol isolado ou relatos contraditórios retornam `unknown`. O identificador de posse anterior é fornecido pelo chamador e não é presumido como estado real. Esta API é **diagnóstica**; não altera o snapshot da bola nem registra eventos e ainda não processa áudio ao vivo automaticamente.

## GN-053 — região estimada por evidência textual (diagnóstico)

`POST /api/matches/{id}/resolve-region` com `{"text":"Azul com a bola na intermediária ofensiva pela direita"}` só responde `status=explicit` quando texto atual, equipe única, faixa e corredor são inequívocos. Retorna `zone: {"band":4,"lane":"right"}` para equipe atacando da esquerda para a direita, mais `attack_direction`, `field_band` e `field_lane` para a orientação fixa de exibição. `band=1` é próximo da própria linha de gol e `band=5` próximo da gol adversária; `lane` é sempre relativa ao sentido do ataque. Se a equipe ataca da direita para esquerda, o campo fixo inverte tanto a faixa (`6-band`) quanto esquerda/direita. O segundo tempo usa `attack_direction` já persistida pela virada da partida; não inverter de novo no frontend.

Opcionalmente, o chamador pode fornecer `team_id` como contexto externo explícito para uma frase sem nome de clube; não é posse consultada ou deduzida do banco. Se houver menção conflitante à equipe, região ampla, corredor ausente, duas zonas conflitantes, comercial, replay ou jogo parado, `status=unknown`, `zone=null` e nenhuma coordenada são devolvidos. O endpoint não move a bola, não gera eventos e não conecta automaticamente a transcrição ao campo. Exemplo verificável: `python -m pytest -q tests/test_field_regions.py` (CI Linux, PR #15).

## GN-054 — identificação diagnóstica de eventos

`POST /api/matches/{id}/resolve-event` recebe `{"text":"Bruno chutou forte"}` e pode responder `{"status":"explicit","kind":"shot","cue":"chutou","reason":"unique_affirmative_live_event_cue"}`. Os 11 tipos aceitos são `pass`, `cross`, `shot`, `save`, `goal`, `corner`, `throw_in`, `offside`, `foul`, `penalty`, `goal_kick`. São pistas de texto com regras explícitas, **não** certeza de que o lance ocorreu. Publicidade, replay, análise, tentativa, negação, gol anulado, período parado e frases com vários eventos explícitos retornam `unknown`. Não atribui jogador, hora ou zona, não mexe na bola/placar, não persiste eventos e não processa as fontes ao vivo. As 36 frases artificiais rotuladas ficam em `fixtures/events_labeled.json`. Validação: `python -m pytest -q tests/test_event_detection.py` e CI do PR #16.

## GN-055 — qualidade heurística por componente (não probabilidade)

`POST /api/matches/{id}/resolve-confidence` recebe `{"text":"João do Azul chuta na área adversária pela direita","observed_age_seconds":2}`. Consulta o elenco/partida existentes e devolve `player_id`, `team_id`, `zone`, `event_kind` e `scores` separados (`player`, `team`, `region`, `event`, `freshness`), acompanhados por `reasons`. Nenhum score mede porcentagem de acerto: `mode=heuristic_strength_not_calibrated_v1`. Evidência explícita e única vale 1.0; equipe passada apenas pelo chamador (`team_id`) permite no máximo 0.5 em equipe/região; sem pista/contradição é 0.0. Atualidade vale 1.0 se a idade declarada da observação for de 0 a 5 s, decai até 0.0 aos 30 s; sem idade conhecida é 0.0. **Nenhuma comparação com tempo do jogo/audio real é feita**. Publicidade, replay, análise e partida parada retornam todos os scores zerados. Não produz score agregado, alteração de bola/placar/evento ou escrita no feed/SQLite. Validação: `python -m pytest -q tests/test_confidence.py` e CI do PR #17.

## GN-056 — guarda da movimentação da bola (apenas diagnóstico)

`POST /api/matches/{id}/guard-ball` recebe, por exemplo:

```json
{"text":"Azul com a bola na própria área pela esquerda","observed_age_seconds":2}
```

A resposta é `decision: "candidate"` apenas para **lance atual afirmativo**, idade declarada de até cinco segundos, **posse textual inequívoca**, equipe explicitamente nomeada, faixa longitudinal e corredor exclusivos e evidência compatível com a GN-055. Nesse caso, `candidate_zone` contém a zona 5×3 *proposta* e `field_band/field_lane` orientam a exibição segundo o sentido de ataque. Em caso de anúncio, replay, análise, texto genérico, especulação, ausência de equipe/faixa/corredor, conflitos ou idade ausente/vencida, retorna `decision: "hold"`, `candidate_zone: null` e motivo legível. `current_ball` reflete sempre o estado persistido **sem modificação**; nem candidata nem rejeição alteram banco, placar, WebSocket ou áudio.

A idade informada é **não verificada**: esse gate é uma salvaguarda textual, não atualização operacional. Relógio da fonte (GN-060/061), fusão (GN-062..065), ingestão (GN-074) e segurança (GN-090) continuam necessários antes de acionar o campinho real. Testes: `python -m pytest -q tests/test_ball_guard.py`. CI Linux Python 3.11/3.12: [263 passed, 2 skipped](https://github.com/vmendesneto/game_now/actions/runs/43031120226) na suíte completa, **sem** validação de rádio/YouTube/Windows reais.

## GN-057 — interpretação opcional com LLM local (diagnóstico)

`POST /api/matches/{id}/compare-language` compara os resultados determinísticos de posse, região e evento com uma possível **sugestão** de modelo local. Por padrão `use_local_llm=false` e **nenhum modelo ou serviço adicional é necessário**. Para experimentar, instale e inicie separadamente um servidor Ollama na máquina local, disponibilize um modelo local com o nome enviado e execute:

```json
{"text":"O Azul encontrou espaço na intermediária ofensiva pelo lado direito","use_local_llm":true,"model":"qwen2.5:3b","timeout_seconds":8}
```

O servidor chama exclusivamente `127.0.0.1:11434/api/generate` via HTTP local, sem redirecionamentos nem configuração de URL arbitrária. Modelos não são baixados automaticamente. A saída é **objeto JSON obrigatório**: `status`, `team_id`, `player_id`, `zone`, `event_kind` e `reason`. Validação rejeita propriedades extras/duplicadas, tipos errados, regiões fora de 5×3, eventos desconhecidos, jogadores ausentes/pertencentes a outra equipe, contradições com as regras e JSON fora do limite. Comercial, replay e conversa não chegam sequer a consultar o modelo. Se o Ollama estiver desligado, a API retorna `unavailable` com o baseline e sem vazamento de detalhes da conexão.

**A resposta nunca é um estado de jogo**: `eligible_for_state_update=false` inclusive quando há `suggestion`; a hipótese da IA não move bola, placar nem cria evento. O objetivo é observar diferenças entre regras e interpretação local sem alucinação operacional. Os testes `python -m pytest -q tests/test_llm_local.py` usam modelos e transporte *simulados* para verificar rigor e falhas, não aferem qualidade/velocidade de um Ollama real. CI geral: https://github.com/vmendesneto/game_now/actions/runs/43032445652 (297 passed/2 skipped, Python 3.11/3.12). O relógio e as simulações GN-060..062 estão implementados; seleção/fusão operacional GN-063..065 ainda está pendente.


## GN-060/GN-061 — relógio lógico e atrasos relativos (diagnóstico)

`POST /api/matches/{id}/clock/preview` (GN-060) usa âncora explícita em segundos de jogo e instante **de captura** para projetar um relógio lógico monotônico em uma fonte. Atrasos de chegada não deslocam o relógio; observações regressivas são recusadas. Intervalo/fim congelam o tempo; o segundo tempo requer uma nova âncora. A API não grava dados. Código mesclado via PR #20 e validado na CI pós-merge (run 43045479371).

`POST /api/matches/{id}/sources/delay/preview` (GN-061, PR #21) recebe IDs de eventos **previamente associados pelo chamador** (não deduz se frases tratam do mesmo lance), ID da fonte de referência e instantes de captura/recebimento de cada observação. Exemplo em JSON:

```json
{
  "reference_source_id": "radio-a",
  "observations": [
    {"source_id":"radio-a","common_event_id":"lance-1","captured_at":"2026-11-11T12:00:00Z","received_at":"2026-11-11T12:00:02Z"},
    {"source_id":"youtube-b","common_event_id":"lance-1","captured_at":"2026-11-11T12:00:08Z","received_at":"2026-11-11T12:00:20Z"},
    {"source_id":"radio-a","common_event_id":"lance-2","captured_at":"2026-11-11T12:01:00Z","received_at":"2026-11-11T12:01:01Z"},
    {"source_id":"youtube-b","common_event_id":"lance-2","captured_at":"2026-11-11T12:01:08Z","received_at":"2026-11-11T12:01:18Z"}
  ]
}
```

O resultado diagnóstico da fonte `youtube-b` deverá indicar `relative_delay_seconds=8.0` e `status=aligned` (atraso positivo: lance apresentado oito segundos depois da referência). A estimativa usa apenas tempos de captura, exige pelo menos dois eventos em comum, janela padrão de dez minutos e concordância de até dois segundos; observações antigas, offsets inconsistentes ou excessivos não produzem alinhamento. Limites: 80 observações e oito fontes por chamada. **Instantes precisam estar no mesmo domínio de relógio**, por exemplo capturas realizadas numa única máquina; clocks não sincronizados podem gerar um offset falso. Não existe inferência de pares de eventos, fonte ativa, fusão automática ou validação de stream real nesta etapa. Nada é escrito no banco ou transmitido como mídia. Teste alvo: `python -m pytest -q tests/test_logical_clock.py tests/test_source_delay.py`. GN-061 concluída via PR #21; CI 326 passed, 2 skipped em 3.11/3.12 (run 43043216756).


## GN-062 — deduplicação de relatos de duas fontes (preview)

`POST /api/matches/{id}/events/deduplicate/preview` recebe `candidates` com `segment_id`, `source_id`, `kind`, `captured_at`, `received_at`, `team_id` e, se conhecido, `player_id`, mais `source_delays` conforme a saída da GN-061. Para o mesmo `goal` de um clube, narrado por rádio em T+10 s e YouTube em T+18 s, se o atraso relativo verificado do YouTube for +8 s e as demais evidências não forem contraditórias, o retorno possui um único grupo com dois `source_ids` e `merged=true`. Eventos da mesma fonte, equipes/tipos/jogadores conflitantes, fontes sem alinhamento e narrações marcadas como não atuais não são mesclados; passes/cruzamentos/chutes/laterais só se unem com o mesmo jogador resolvido. A comparação considera no máximo 2 s de separação normalizada por padrão.

Este endpoint **não persiste eventos, altera relógio, muda placar ou move a bola**. Os deslocamentos são fornecidos pelo chamador; a API não prova que foram obtidos de uma fonte de confiança nem identifica sozinha eventos comuns na narração. O resultado é um agrupamento hipotético de candidatos, não uma prova de que os dois sinais descreveram o mesmo lance. Testes: `python -m pytest -q tests/test_event_deduplication.py`; GN-062 concluída via PR #22; CI 341 passed, 2 skipped em 3.11/3.12 (run 43043274805) e suíte pós-merge na main aprovada (run 43045479371). Próxima GN-063.

## GN-063 — prévia da seleção de fonte ativa

Para simular alternância entre rádios ou YouTube sem iniciar captura real, faça `POST /api/matches/{id}/sources/selection/preview`. O corpo contém `evaluated_at` (ISO 8601 com fuso), `previous_source_id` opcional e até 8 itens `observations` com `source_id`, `enabled`, `connection_status` (`online/offline/connecting/error`), `narration_kind` (`live_play/ad/replay/analysis/conversation/unknown`), `captured_at`, `received_at` e `signal_strength` de 0 a 1. `max_age_seconds`, `min_signal_strength` e `switch_margin` são ajustáveis no corpo. Exige partida existente, mas aceita metadados hipotéticos de fontes para simulação; **não valida contra fluxo real**. A saída apresenta `active_source_id`, `transition`, `reason` e `diagnostics` por fonte, sempre com `persisted=false` e `eligible_for_state_update=false`. O score é heurístico; timestamps devem estar num relógio comum confiável. Não liga áudio, transcrição ou atualização automática da bola. GN-090 deve ser concluída antes da captura online pelo painel.

## GN-064 — prévia de contradições

`POST /api/matches/{id}/events/fusion/preview` aceita `evaluated_at` em ISO 8601 com fuso, `active_source_id` opcional, `previous_play` opcional e até 8 `observations`. Cada observação contém `source_id`, `segment_id`, `aligned_at` (timestamp já alinhado com timezone, ou `null` para falta de sincronismo), `current_live_play`, `team_id`, `player_id`, `zone` (faixa 1..5/corredor `left/center/right`) e `event_kind` opcional. `conflict_window_seconds` é configurável (0..5). O retorno `accepted_for_preview` não autoriza escrita: `persisted=false` e `eligible_for_state_update=false` sempre. A prévia veta conflito simultâneo e qualquer retrocesso em relação a `previous_play`, sem inventar zona quando faltarem dados. Não há captação nem alinhamento automático de rádios; consulte GN-061/063 e complete GN-090 antes da operação real.

## GN-065 — prévia da validade da região da bola

`POST /api/matches/{id}/ball/freshness/preview` recebe `evaluated_at` em ISO 8601 com fuso, `last_play` opcional com `FusionPlay` de GN-064, `active_source_id` opcional, `uncertain_after_seconds` (padrão 5) e `expire_after_seconds` (padrão 15, maior que o primeiro). Retorna `uncertainty` (estimated/uncertain/expired), `display_label` (posição estimada/incerta), idade e vencimento por timestamp alinhado, com `zone`, `team_id` e `player_id` ocultados após silêncio ou troca da fonte. Sem lance anterior válido retorna posição incerta. Sempre `persisted=false`, `eligible_for_state_update=false`. **Isto é apenas prévia calculada por requisição**, não atualiza continuamente a interface ou o SQLite, e não comprova narração real. Renderização do estado pendente nas GN-070/071.

## GN-070 — campo SVG de 15 zonas

`app/static/field_geometry.js` exporta `zoneToGrid`, `zoneCellBounds` e `fieldCells`; é carregado antes de `app/static/app.js`, também pode ser importado por Node (`node --test tests/test_field_geometry.cjs`). O SVG mantém `viewBox=0 0 1000 620` e 15 zonas 5×3 relativas ao sentido de ataque, com inversão de ambos os eixos após a troca de lados. O destaque é um retângulo de região aproximada, nunca posição exata da bola; `aria-label` indica a região ou incerteza. A folha CSS mantém proporção e evita transbordo móvel. Os testes automatizados verificam geometria desktop/móvel, **não** substituem validação visual física. O campo continua consumindo apenas demonstração sintética; conexão com dados reais e animação conservadora são tarefas futuras, GN-071 e GN-090.

## GN-071 — exibição segura da região e da incerteza

Na demonstração, o campinho destaca um **retângulo de região estimada**, jamais um ponto rastreado da bola. Se a posição for incerta ou expirada, o destaque desaparece e a interface mostra **Posição incerta**, escondendo também o atleta e a equipe que estavam associados à posição antiga. Uma breve transição visual de 320 ms ocorre somente quando um novo evento explícito altera a região, sem inventar trajetória; `prefers-reduced-motion` desativa a animação. Acessibilidade por `aria-live` e `aria-label` no campo. Testes `node --test tests/test_pitch_presentation.cjs` (executados também pela suíte Python). Ainda é **demonstração sintética**, não integração com áudio ou jogo real; a avaliação visual em dispositivos físicos segue pendente.

## GN-072 — painel de jogo da demonstração

O topo mostra placar e relógio **fornecidos pelo estado da partida simulada**, sem inferir gols a partir de texto repetido. O painel lateral mostra a **narração atual** e o **último evento confirmado** em lugares distintos: comercial, replay, análise e relato repetido não aparecem como gol novo. A posse e o jogador prováveis ficam desconhecidos quando a posição está incerta ou expirada (GN-071). `app/static/demo_scoreboard.js` calcula os rótulos; `node --test tests/test_demo_scoreboard.cjs` testa o módulo. Testes de integração com a API de demonstração percorrem os oito relatos sintéticos. O relógio representa os passos simulados e não avança sozinho entre relatos; o painel **ainda não recebe transmissões de rádio ou YouTube reais**.

## Simulador de duas rádios (GN-082)

Sem precisar de rádio real, YouTube, FFmpeg, ASR ou servidor aberto, execute com as dependências Python do projeto instaladas:

```bash
python -m scripts.simulate_two_radios
python -m pytest -q tests/test_gn082_simulator.py
```

A CLI imprime um JSON reproduzível de **quatro fases fictícias**, com duas rádios que narram o mesmo lance oito segundos apartadas, um comercial, alternância de fonte, contradição e silêncio que expira a posição. Os identificadores de eventos comuns e os timestamps de captura/alinhamento são fornecidos artificialmente: **não** se trata de descoberta automática de eventos nem de sincronização real de streams. Nenhuma URL é acessada, nenhuma amostra de mídia é produzida e nenhum estado de partida é gravado ou movido por essas prévias. Para desempenho real com narração brasileira, consultar GN-083/GN-084 e requisitos de autorização das fontes.

## GN-090 — proteção de rede da captação CLI

O servidor inicia em `127.0.0.1:8000`, incluindo `iniciar_windows.bat`. Não exponha `0.0.0.0` nem encaminhe a porta para a Internet antes da GN-093 (autenticação, HTTPS e revisão de ameaças). O cadastro de uma fonte não executa código nem inicia a captura; a interface permanece no modo demo.

`app/secure_ingest.py` fornece um relay temporário que escuta somente em `127.0.0.1`, protegido por token efêmero, para cada fonte HTTP(S). Cada solicitação remota verifica todos os IPs DNS, bloqueia IPs privados/locais/reservados e fixa a conexão TCP ao endereço público validado, mantendo o Host e a verificação TLS do servidor original. Redirecionamentos são limitados e submetidos à mesma verificação. Playlists HLS são reescritas para que variantes, segmentos, mapas e chaves passem pelo relay. HLS com construções incomuns/indefinidas falha fechado.

O FFmpeg remoto recebe exclusivamente a URL local do relay e protocolos de entrada limitados (`http,tcp,crypto`), não a URL assinada externa. Cabeçalhos HTTP são repassados apenas pelo relay, com lista restrita; cookies, tokens e autenticação não são aceitos. A opção CLI `--file` mantém o tratamento de arquivos de teste, e não é exposta pela API. A resolução de metadados do YouTube pelo yt-dlp continua separada do capturador e limitada às URLs públicas do YouTube já validadas.

Teste reproduzível: `python -m pytest -q tests/test_secure_ingest.py tests/test_gn090_runtime.py`. As provas usam HTTP remoto simulado e FFmpeg real em HLS/MP3 sintéticos, não uma narração de terceiros. O relay não é equivalente a firewall de saída do Windows; valide segurança operacional, compatibilidade com streams reais e direitos de utilização antes de ativar captação pelo site (GN-083, GN-085, GN-093).


### GN-031 — teste reproduzível com vídeo gravado (2026-11-11)

**Vídeos anteriores agora podem ser usados como fonte de diagnóstico**, independentemente do horário do jogo. O resolvedor aceita `live_status=not_live` (vídeo comum), `was_live` (live arquivada) e `is_live` (transmissão atual). Bloqueia lives futuras/em processamento, material restrito ou protegido por DRM e mantêm-se os controles de segurança SSRF da GN-090. `yt-dlp` não grava arquivo e o FFmpeg produz PCM de áudio sem enviá-lo ao navegador. Se o formato disponível combinar vídeo/áudio, bytes de vídeo podem trafegar na entrada, embora a saída seja apenas áudio.

Foi fornecida esta URL para servir como **referência de teste**: https://www.youtube.com/watch?v=Ls4qkPrh4Tk. **A disponibilidade e a autorização de captação desse material não foram verificadas na CI.** Para uma execução local no Windows, *se você tiver permissão de uso*:

```powershell
.\.venv\Scripts\python.exe -m app.youtube_capture --yt-dlp ".\.venv\Scripts\yt-dlp.exe" --url "https://www.youtube.com/watch?v=Ls4qkPrh4Tk" --seconds 300
```

O argumento `--seconds` aceita **até 600 segundos (10 minutos)**; não é necessário alterar o código quando não houver partidas ao vivo. Ele inicia do começo do vídeo e apresenta somente a quantidade de PCM decodificada. **Isso não mede a identificação de equipes, jogadores e zonas:** GN-083 ainda exige transcrição + gabarito rotulado e métricas reais, além de confirmar autorização para usar a narração; GN-085 requer ensaio no Windows. Não presumir que um URL público implica licença de uso.


### Diagnóstico de erro 5XX no relay com vídeos gravados (2026-11-11)

No primeiro teste físico com `https://www.youtube.com/watch?v=Ls4qkPrh4Tk`, depois de atualizar até `1529df7`, o Windows respondeu `FFmpeg ... Server returned 5XX` — isto era erro **local** genérico do relay, e não demonstra que o YouTube respondeu HTTP 500. Um possível causador é o atraso de ativação de URLs `googlevideo.com/videoplayback` recém emitidas: o downloader do yt-dlp aguarda cerca de cinco segundos antes da primeira requisição, enquanto o resolvedor do Game Now só consultava metadados e iniciava FFmpeg imediatamente.

O consumidor passou a aguardar 5,5 segundos **apenas** para essa classe de URL, antes da primeira requisição, e o relay informa códigos diagnósticos seguros quando uma resposta remota falha: `upstream_http_403` (acesso recusado), `destination_or_playlist_rejected` (filtro de segurança/playlist) ou `transport_error` (falha de conexão). Nenhum desses erros inclui URL assinada, cookie, token ou mídia. Não há tentativas de contornar restrições: se a origem retornar 403 depois da espera, o Game Now deve encerrar informando o código.

Após a atualização, para testar **somente com fonte cuja captação seja permitida**, execute novamente:

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m app.youtube_capture --yt-dlp ".\.venv\Scripts\yt-dlp.exe" --url "https://www.youtube.com/watch?v=Ls4qkPrh4Tk" --seconds 5
```

Se falhar, compartilhe apenas o erro **sanitizado** do terminal; não publique URLs de CDN temporárias, headers, cookies ou `--dump-json` completos. A CI usa upstream falso, não YouTube real. A GN-031/GN-083 continua aguardando teste real permitido e, para GN-083, gabarito de narração.
