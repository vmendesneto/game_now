# Game Now — acompanhamento de futebol a partir de narrações

**Estado:** demonstração offline e cadastro persistente de partidas, elencos e snapshots implementados; captura real ainda pendente. Não há ingestão de rádio/YouTube nem ASR conectados. Acompanhe [STATUS.md](STATUS.md) e [ROADMAP.md](ROADMAP.md).

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
| `/api/matches/{id}/sources` | GET, PUT | Lista persistida de fontes (sem ingestão) |
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

## FFmpeg (futura ingestão)

Para o modo demo não é necessário instalar FFmpeg. Ao testar captura de rádio/YouTube no Windows, instalar uma versão oficial/confiável de FFmpeg, adicionar o executável ao PATH e verificar com `ffmpeg -version`. O endpoint `/health` indica se foi detectado. Esse teste físico pertence a GN-012/GN-030 e ainda não foi executado.

## Limitações (importante)

- **Não há captação/transcrição de fontes reais.** FFmpeg e yt-dlp permanecem etapas futuras.
- A interpretação no modo demo é um conjunto pequeno de palavras-chave e dados de cenário. O agrupamento de fontes é pré-indicado no script sintético; não é fusão real.
- A posição mostrada é **uma zona de 15** relativa ao sentido de ataque, não coordenada precisa. Comerciais e replays não devem mover a região; sem evidência, o estado pode ser desconhecido/expirado.
- O **demo sintético** é volátil e reinicia com o processo. Partidas cadastradas, elencos, fontes e snapshots de eventos são persistidos em SQLite (GN-023). São ambientes separados até integrar narrações reais.
- `iniciar_windows.bat` ainda exige validação no computador Windows físico.
- Servidor escuta **somente 127.0.0.1**. Não publique a porta na Internet sem autenticação e HTTPS.

## Continuidade

Leia [STATUS.md](STATUS.md), [ROADMAP.md](ROADMAP.md) e [AGENTS.md](AGENTS.md) antes de trabalhar. Marque tarefas somente depois de evidências reais; testes de CI Linux não equivalem a testes do Windows.
