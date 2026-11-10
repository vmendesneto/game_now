# STATUS — Estado atual do Game Now

**Atualizado:** 2026-11-10
**Branch de referência:** `main` (após integração da entrega GN-020/021/023)
**Projeto:** https://github.com/vmendesneto/game_now
**Fase atual:** F02 — cadastro e persistência iniciais implementados; motor de demo permanece separado.
**Próxima tarefa executável:** **GN-022 — normalização de nomes, apelidos e “camisa 10” com ambiguidades entre equipes**.
**Bloqueio paralelo:** **GN-012 — testar launcher no Windows físico.**

## Entrega desta etapa

- ✅ **GN-020**: `POST/GET/PUT/DELETE /api/matches` e `/api/matches/{id}`; mandante/visitante, cores, sentido do ataque, período, relógio e placar. Validação Pydantic usa a estrutura `Match` do contrato v1; equipe duplicada, direção incompatível, cores e placar inválidos são rejeitados.
- ✅ **GN-021**: `GET/PUT /api/matches/{id}/players`, cadastro dos elencos com camisa, nome, apelidos, posição e titular/reserva; edição e exclusão pelo navegador. Camisa única por equipe; no máximo 11 titulares; IDs de atleta únicos; referência à equipe validada. `position` fica fora de `Player` v1, mantendo schema e fixtures intocados.
- ✅ **GN-023**: banco SQLite em `data/game_now.sqlite3` (ou `GAME_NOW_DB_PATH`); partidas, elencos, fontes, snapshot completo `ContractBundle`, transcrições, eventos e bola persistidos. `GET/PUT /api/matches/{id}/sources` e `GET/PUT /api/matches/{id}/state`. Operações sobre elenco/equipe/fonte com referências históricas inválidas retornam HTTP 409 sem remover o estado salvo. Deleção em cascata.
- Interface web em `app/static/` com formulário de partida, troca de partida e inclusão/edição/exclusão de atletas.
- `README.md`, `AGENTS.md`, GitHub Actions e testes de integração atualizados.
- **Contrato v1 preservado**: `app/contracts.py`, `schemas/v1.schema.json` e fixtures não foram modificados.

## Testes e evidência

- Testes automatizados incluídos em `tests/test_configuration.py`: CRUD, campos inválidos, conflitos, elencos independentes, números repetidos, persistência de fontes e eventos, reabertura de SQLite após recriar o aplicativo, esquema e UI HTTP.
- Testes de regressão existentes da demo, contrato, WebSocket e fixtures continuam na suíte.
- Pipeline GitHub Actions: Python **3.11 e 3.12**, exportação/comparação do schema, `node --check app/static/app.js`, `python -m pytest -q`.
- **Resultado do CI desta entrega:** verificar o PR e a execução mais recente do GitHub Actions; a validação só deve ser afirmada após o workflow concluir.
- Antiga evidência da fase F01: https://github.com/vmendesneto/game_now/actions/runs/42878455255 (13 testes em Python 3.12).

## Limitações e bloqueios

- **O estado da demonstração em `GET /api/state` e em `/ws` continua volátil.** `/api/demo/next` e `/api/demo/reset` não gravam eventos nas partidas cadastradas. A persistência GN-023 é do **estado configurado via `/api/matches/{id}/state`**, não uma falsa integração do simulador.
- O `/health` agora informa `storage=sqlite_persistent` e `demo_state=volatile_memory_only`; FFmpeg/ASR/fontes reais não implementados.
- `GN-022` ainda não implementou resolução de nomes e “camisa 10” quando o mesmo termo existe em ambos os clubes.
- **GN-012, GN-085** e demais testes Windows, navegador gráfico, áudio, yt-dlp, CPU/RAM, GPU e FFmpeg reais não realizados.
- `GN-070` a `GN-074`: campinho SVG e demo prontos como base; visualização de partida cadastrada e integração da configuração com narração ainda pendentes. Não marcar completos.
- Nunca exibir coordenada exata da bola a partir de uma narração.

## Continuar

1. Conferir HEAD real de `main`, `ROADMAP.md`, este arquivo, `AGENTS.md` e CI da última integração.
2. **GN-022**: criar resolução conservadora e com contexto de clube para nome, apelido e camisa; testar colisões de nomes e camisas entre os dois times, sem inventar identidade. Depois seguir GN-024/GN-025 conforme priorização e dependências.
3. Para executar localmente: `python -m pip install -r requirements-dev.txt`; `python scripts/export_schema.py`; `python -m pytest -q`.
4. Servidor: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`, interface em http://127.0.0.1:8000. Em Windows físico, usar `iniciar_windows.bat` e registrar evidências antes de marcar GN-012.
5. Para simular persistência, cadastrar uma partida no formulário, adicionar atletas, fechar e reabrir o processo: os dados permanecem no arquivo SQLite. A demo reinicia separadamente; não é bug de persistência da configuração.
6. Ao alterar o contrato v1, criar versão adequada e atualizar schema, fixtures e adaptadores; não alterar silenciosamente.
