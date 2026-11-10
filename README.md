# Game Now — acompanhamento de futebol a partir de narrações

**Estado:** primeira implementação de demonstração sintética em desenvolvimento. Não há ingestão de rádio/YouTube nem ASR conectados. Acompanhe [STATUS.md](STATUS.md) e [ROADMAP.md](ROADMAP.md).

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
| `/ws` | WebSocket | Snapshots de estado (sem mídia) |

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
- O estado do demo é volátil e reinicia com o processo; SQLite será implementado em GN-023.
- `iniciar_windows.bat` ainda exige validação no computador Windows físico.
- Servidor escuta **somente 127.0.0.1**. Não publique a porta na Internet sem autenticação e HTTPS.

## Continuidade

Leia [STATUS.md](STATUS.md), [ROADMAP.md](ROADMAP.md) e [AGENTS.md](AGENTS.md) antes de trabalhar. Marque tarefas somente depois de evidências reais; testes de CI Linux não equivalem a testes do Windows.
