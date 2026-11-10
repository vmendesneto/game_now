# Game Now — acompanhamento de futebol a partir de narrações

**Estado:** demonstração offline, configuração de partidas/fontes e controle/auditoria persistentes; módulo de captura rádio FFmpeg em CLI com fixtures aprovadas, ainda sem ingestão de rádio/YouTube pelo site ou ASR. Acompanhe [STATUS.md](STATUS.md) e [ROADMAP.md](ROADMAP.md).

## Executar a demonstração offline

Requer Python 3.11 ou 3.12. O modo demo não precisa de FFmpeg, GPU, modelo Whisper, rádio ou conexão de streaming. Dependências Python são instaladas na primeira execução.

**Windows:** execute `iniciar_windows.bat` na pasta do repositório. Ele cria `.venv`, instala as dependências e inicializa o servidor.

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
| `/api/matches/{id}/flow` | GET | Período, titulares em campo, substituições, expulsões, acréscimos e histórico |
| `/api/matches/{id}/actions` | POST | Registrar operação de jogo (GN-024) |
| `/api/matches/{id}/corrections` | GET, POST | Corrigir placar, posse e eventos com auditoria (GN-025) |
| `/api/matches/{id}/sources` | GET, PUT | Criar, editar, habilitar e desabilitar fontes persistidas (GN-032; sem ingestão) |
| `/api/matches/{id}/state` | GET, PUT | Snapshot do contrato v1, incluindo eventos, transcrições e bola |

## Configuração e banco de dados

A seção **Partidas e elencos**, abaixo da demonstração, permite criar/editar/excluir partidas e cadastrar os dois elencos pelo navegador, sem editar Python. Posição é metadado de elenco separado do contrato de eventos v1. Cada PUT de elenco/fontes substitui a lista integral; 409 significa conflito de referências históricas, camisa duplicada ou equipe inválida. Dados são escritos em `data/game_now.sqlite3` por padrão (não versionado); escolha outro caminho com `GAME_NOW_DB_PATH` antes de iniciar. Copiar o arquivo com o servidor parado permite backup manual. Não apagar o arquivo para atualizar o aplicativo.

A GN-022 acrescenta identificação conservadora de atletas: `POST /api/matches/{id}/resolve-player` recebe `{"mention":"camisa 10","team_id":null}`. Nomes são normalizados por caixa, acentos e pontuação. Sem equipe de contexto, dois atletas com a mesma camisa ou apelido geram `ambiguous`, nunca um palpite. O formulário no painel de elencos permite testar. Isso **não** é transcrição nem resolução de entidades em texto livre (GN-051).

O snapshot persistente está disponível em `/api/matches/{id}/state`. Ele exige um `ContractBundle` v1 válido e não altera a configuração da partida; edite partida/elenco pelos endpoints próprios. **O botão Próximo relato continua operando a demo separada**, sem preencher histórico das partidas cadastradas; integração entre eles ocorrerá numa etapa futura. Fontes reais e sua captura continuam não implementadas.

## Testar

```bash
python -m pip install -r requirements-dev.txt
python scripts/export_schema.py
python -m pytest -q
```

O contrato reside em `app/contracts.py`, o schema exportado em `schemas/v1.schema.json`, fixtures em `fixtures/`, e a decisão de arquitetura em [docs/ADR-0001.md](docs/ADR-0001.md). Não edite o JSON schema manualmente: regenere com o script e revise o diff. Os testes verificam ambos.

## FFmpeg (GN-030 — conversão de áudio em ferramenta de diagnóstico)

Para o modo demo não é necessário instalar FFmpeg. A ferramenta GN-030 precisa de FFmpeg no PATH. A CI instala FFmpeg e testa decodificação real de fixtures MP3, AAC e HLS como PCM mono 16k (`tests/test_audio_capture.py`). Para testar sem acessar a internet:

```bash
python -m app.audio_capture --file caminho/arquivo.mp3 --seconds 5
```

Para diagnosticar uma rádio pública permitida, cuja URL você fornece:

```bash
python -m app.audio_capture --url https://exemplo.radio/stream.mp3 --seconds 5
```

O comando apenas imprime estatísticas JSON, **não** reproduz ou salva áudio e não alimenta o site. O URL ilustrativo acima não é uma estação verificada. A função Python `pcm_chunks` oferece blocos binários de 16 kHz para etapas seguintes. A opção `--file` é somente CLI/testes e não é exposta pela API. A resolução DNS inicial bloqueia IPs não públicos, mas segurança contra redirecionamentos e substreams HLS exige GN-090. **Nenhuma rádio real ou Windows foi validado nesta etapa.**

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

O cadastro de fontes permite várias rádios e vídeos públicos do YouTube, cada qual com nome, tipo, URL e flag `enabled`. O `PUT /sources` substitui a lista completa; alterações que removem fontes citadas em eventos/transcrições retornam 409. São aceitos URLs públicos HTTP(S) para rádio e HTTPS de `youtube.com` / `youtu.be` para YouTube, sem credenciais ou IP local. URLs ausentes são placeholders, não fontes operacionais. **A validação de cadastro não substitui uma defesa de rede no capturador**, que precisará validar DNS, redirecionamentos e IP de destino na GN-090. Nenhuma fonte é executada/reproduzida pelo cadastro.

Testes de integração `tests/test_match_flow.py`, `tests/test_corrections.py`, `tests/test_sources.py` comprovam rejeições, atomicidade, edição, consulta, reinício SQLite e interface HTTP. CI Linux, **28 testes em Python 3.11 e 3.12**, schema v1 preservado e JS sintaticamente válido: https://github.com/vmendesneto/game_now/actions/runs/42884686478. Persistem validações físicas no Windows, rádio real e modelos ASR.

## Logs estruturados (GN-015)

O servidor grava requisições HTTP em JSON em `data/game_now.log` por padrão; configure outro arquivo antes de iniciar com `GAME_NOW_LOG_PATH`. Log contém timestamp UTC, status, caminho (sem query), método, duração e ID devolvido ao cliente via header `X-Request-ID`, sem o corpo das solicitações ou as URLs de rádio do formulário. Há rotação a cada 2 MB, 3 backups (máximo nominal 8 MB de arquivos), e testes cobrindo rotatividade, ausência de credenciais no corpo e códigos de erro. Não é necessário manter o arquivo para preservar as partidas, que seguem no SQLite.

CI após GN-015/GN-030: **35 testes passaram em Python 3.11 e 3.12**: https://github.com/vmendesneto/game_now/actions/runs/42886144524. O contrato v1 segue inalterado. A validação do Windows físico está pendente.

## Buffer e resolução de YouTube (GN-034 / GN-031 parcial)

A GN-034 implementa `MultiSourceAudioBuffer` em `app/audio_buffer.py`, com frames PCM mono 16 kHz, marca temporal de captura, remoção por idade/bytes, limite de fontes e snapshots thread-safe. O teste `tests/test_audio_buffer.py` inseriu 20.000 chunks em duas fontes independentes sem ultrapassar os limites. Esse buffer está disponível para o futuro orquestrador, mas ainda não recebe blocos automaticamente do site.

A GN-031 **continua pendente**. O arquivo `app/youtube_capture.py` já contém uma implementação preliminar: invoca `yt-dlp` sem cookies/configuração pessoal e sem autenticação, exige transmissão pública ativa, seleciona apenas formato de áudio, não salva URLs assinadas e envia o endereço transitório ao conversor FFmpeg de GN-030. O código descarta headers de autenticação e bloqueia URLs privadas iniciais; redirecionamentos, substreams e URLs expiradas exigem medidas adicionais. Os testes com `tests/test_youtube_capture.py` usam um executável yt-dlp **falso**, portanto **não comprovam funcionamento com YouTube Live real**. Em um ambiente autorizado, instalar yt-dlp oficial no PATH e fornecer uma transmissão pública que permita a captação; sem isso, não afirmar GN-031 finalizada. Nada é embutido no site.

**Última CI:** 47 testes em Python 3.11/3.12, JSON schema v1 preservado, JavaScript válido, codec FFmpeg real em fixtures: https://github.com/vmendesneto/game_now/actions/runs/42888042259. Testes físicos no Windows e mídia pública autorizada seguem pendentes.


## Diagnóstico YouTube Live e retomada de áudio (GN-031 parcial / GN-033)

**GN-031 requer ainda uma validação real autorizada.** O projeto não baixa nem transmite vídeo: o yt-dlp consulta uma transmissão pública *ao vivo*, escolhe apenas um formato de áudio oferecido sem DRM e passa o link temporário ao FFmpeg para produzir PCM mono 16 kHz. A ferramenta de diagnóstico devolve somente contadores e tempo; nunca a URL assinada, mídia, cookies ou credenciais. Os testes automatizados usam metadados sintéticos, **não** uma transmissão real.

No Windows, com FFmpeg instalado no PATH e Python 3.11/3.12 configurado, instale o yt-dlp oficial *opcionalmente* no mesmo ambiente virtual (não é necessário para o modo demo):

```bat
.venv\Scripts\activate.bat
python -m pip install --upgrade yt-dlp
python -m app.youtube_capture --url "https://www.youtube.com/watch?v=ID_DE_LIVE_AUTORIZADA" --seconds 5
```

Substitua a URL ilustrativa pela transmissão pública **ativa e com uso permitido**. Se o vídeo estiver off-line, inacessível sem login, protegido, não tiver áudio-only ou requerer DRM, a ferramenta deve falhar com uma mensagem clara; não adicionar cookies, assinatura artificial, extração de DRM nem bypass. Para validar em ambiente diferente, execute o mesmo comando com `python` apropriado e yt-dlp/FFmpeg no PATH. Exemplo de **formato esperado**, não resultado de execução real:

```json
{"source_id":"youtube-diagnostic","sample_rate":16000,"channels":1,"format":"s16le","bytes":160000,"chunks":10,"seconds":5.0,"audio_retransmitted":false}
```

O processamento não grava arquivos de mídia. Para diagnosticar um stream offline, a execução retorna código diferente de zero. Os endereços dos servidores de mídia expiram: `app/capture_supervisor.py` permite criar um worker independente por fonte, com timeout de ausência de PCM, backoff exponencial de 1 a 30 segundos por padrão e encerramento ao acionar `asyncio.Event`. A cada tentativa de YouTube, o worker chama o resolvedor novamente; não reutiliza o endereço expirado. Blocos PCM são guardados no `MultiSourceAudioBuffer` por fonte, com limites de memória e sem transmissão ao site. Os estados internos não incluem URLs ou mensagens de erro potencialmente sensíveis.

Esse supervisor **ainda não é iniciado pelos botões de fontes nem integra ASR ou o site**; integração operacional/telemetria será tratada nos próximos itens. Testes da GN-033 simulam desconexão, reconexão, fluxo sem áudio, fonte travada, múltiplas fontes, expiração de URL e parada segura. Nada disso equivale à validação de uma live real, de políticas dos criadores, da estabilidade por 90 minutos, de redirecionamentos/HLS com DNS ou do Windows físico.
