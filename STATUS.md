# STATUS — Estado atual do Game Now

**Atualizado:** 2026-11-10  
**Branch de referência:** `main` (integração da branch `feat/gn003-contract-and-offline-demo`)  
**Projeto:** https://github.com/vmendesneto/game_now  
**Fase atual:** F01 — demonstração offline implementada; F02 ainda pendente.  
**Próxima tarefa executável:** **GN-020 — CRUD da partida**. Depois GN-021 (elencos) e GN-023 (SQLite).  
**Bloqueio paralelo:** **GN-012 — validar o launcher no Windows físico do usuário**.

## Últimas entregas

- ✅ **GN-003:** contrato Pydantic v1 com `Match`, `Team`, `Player`, `AudioSource`, `TranscriptSegment`, `FootballEvent`, `EstimatedBallState`, confidências independentes, timestamps com fuso e zona 5×3; schema versionado em `schemas/v1.schema.json` e três fixtures (lance, publicidade, duas fontes atrasadas).
- ✅ **GN-004:** decisão de arquitetura documentada em `docs/ADR-0001.md` (FastAPI, SVG sem Node, contratos, limites de inferência, SQLite posterior, Windows local).
- ✅ **GN-005:** workflow Python 3.11/3.12 com validação do schema e suíte de testes.
- ✅ **GN-010:** FastAPI, site HTML/CSS/JS e SVG servidos via HTTP em `127.0.0.1:8000`.
- ✅ **GN-011:** dependências Python fixadas, procedimento de venv/documentação e instalação limpa de pacotes exercitada pelo CI em duas versões. FFmpeg é opcional no modo demo.
- ✅ **GN-013:** `GET /health` com diagnóstico explícito de FFmpeg, ASR não configurado, memória volátil e fontes sintéticas.
- ✅ **GN-014:** roteiro sintético offline com duas fontes, comercial, cruzamento, gol duplicado, replay e expiração; `/api/demo/next`, `/api/demo/reset` e transmissão de estado via `/ws`.

## Evidência verificada

- Workflow: https://github.com/vmendesneto/game_now/actions/runs/42878455255
- SHA dos testes aprovados antes da exportação versionada: `ef18b1d08216d65cea97e3fec5b9e48e731f38da`.
- Python 3.11: job `tests (3.11)` passou.
- Python 3.12: job `tests (3.12)` passou, com **13 testes aprovados**, incluindo contrato/fixtures, regras sintéticas, API HTTP e dois clientes WebSocket simultâneos.
- Comandos CI: `python -m pip install -r requirements-dev.txt`, `python scripts/export_schema.py`, `python -m pytest -q`.
- O contrato JSON exportado por CI foi incorporado na mesma alteração de atualização de progresso.
- **Não houve teste de navegador gráfico nem teste no Windows físico.** CI Linux não comprova integração com rádio, YouTube, GPU ou estabilidade em Windows.

## Estado que ainda NÃO está pronto

| Item | Estado |
| --- | --- |
| GN-012 — `iniciar_windows.bat` | Script criado, mas não executado em Windows real; continua [ ] |
| GN-070 a GN-074 — interface completa | Campo SVG e dados em tela implementados como base; responsividade visual, troca de lados e fluxo de configuração ainda não validados |
| GN-020/021/023 — cadastro e persistência | A demo usa equipes fixas e estado volátil; nenhuma implementação de SQLite ou CRUD |
| GN-030/031 — rádios e YouTube | Não iniciados; verificar condições e permissões das fontes |
| GN-040 a GN-043 — ASR pt-BR | Não iniciados; modelo não instalado |
| GN-050 a GN-065 — classificação e fusão reais | Não iniciados; `app/demo.py` usa poucas palavras-chave e chaves de duplicação predeterminadas |
| Windows CPU/RAM/FFmpeg | Não aferidos; não assumir compatibilidade |
| Posições em campo | Zonas estimadas apenas; nunca coordenadas físicas precisas |

## Como continuar

1. Conferir o HEAD real de `main` e reler este arquivo, `ROADMAP.md` e `AGENTS.md`.
2. **GN-020:** adicionar CRUD de uma partida com dois clubes, direção do ataque, período, relógio e placar. Primeiro escrever testes de criação/edição/validação; não reutilizar estado de demo como banco.
3. Depois **GN-021**, **GN-023** e configuração web. Preservar o contrato v1, ou versionar mudança incompatível.
4. Para rodar demo: instalar Python 3.11/3.12, executar `iniciar_windows.bat` no Windows ou `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000` com venv e requirements. Abrir http://127.0.0.1:8000.
5. **GN-012, quando o Windows estiver disponível:** registrar versão Python, instalação do launcher, acesso ao site em dois navegadores, `/health` e erros; não fechar a tarefa antes dessa evidência.
6. Para novos commits: `python scripts/export_schema.py` e `python -m pytest -q`. Marcar [x] somente após CI/teste aplicável; atualizar STATUS e ROADMAP juntos.

**Proibido** registrar como testada uma fonte real ou validação de hardware não realizada.
