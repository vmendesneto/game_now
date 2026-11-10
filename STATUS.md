# STATUS — Game Now

**Atualizado:** 2026-11-10
**Branch:** `main`
**Últimas tarefas concluídas:** GN-024 (operações de partida), GN-025 (correções auditadas), GN-032 (cadastro de fontes).
**Próxima tarefa executável:** **GN-030 — captura de rádio MP3/AAC/HLS via FFmpeg, PCM mono 16 kHz**.
**Bloqueio físico paralelo:** GN-012 exige Windows do usuário; GN-085 exigirá áudio/navegador/modelos reais.

## Implementado e validado
- **GN-024:** `app/match_flow.py`; `GET /api/matches/{id}/flow` e `POST /api/matches/{id}/actions`. Substituições com titulares/reservas elegíveis da mesma equipe; expulsões sem reposição; intervalo e início do segundo tempo com inversão automática de lado; acréscimos monotônicos e encerramento. Relógio não retrocede. Opções inválidas retornam 409/422; transação atômica atualiza partida, bundle v1 e log. Elenco e mudanças diretas de período/direção bloqueados após iniciar operações. Painel na interface.
- **GN-025:** `app/corrections.py`; `GET/POST /api/matches/{id}/corrections`. Correções de placar, posse e evento com motivo, autor, estado anterior/posterior e histórico imutável via API. Transações rejeitam entidade ou ID inválido. Editor legado de placar e troca de snapshot por PUT também geram auditoria. Formulário no site.
- **GN-032:** `app/source_validation.py`; cadastro/edição/ativação/desativação de fontes de rádio e YouTube pelo navegador e API existente. Persistência SQLite, URLs públicas básicas, rejeição de credenciais, esquemas inadequados e IPs locais. Não há captura nem reprodução de mídia no site.
- GN-020, GN-021, GN-022, GN-023 permanecem implementados: CRUD de partidas, elenco, identificação conservadora e SQLite. Contrato `ContractBundle` v1 não mudou.

## Testes e evidências
- GitHub Actions: https://github.com/vmendesneto/game_now/actions/runs/42884686478
- **28 testes aprovados** em **Python 3.11 e 3.12**, exportação/verificação de JSON schema, `node --check app/static/app.js`.
- Novos testes: `tests/test_match_flow.py` (inclui transição de fases e reinício), `tests/test_corrections.py` (auditoria, rollback e reinício), `tests/test_sources.py` (múltiplas fontes, URLs inválidas e persistência). A suíte anterior permanece verde.
- Um aviso de depreciação de dependência observado na CI, sem falha. Não houve teste com rádio, YouTube ou Windows reais.

## Limitações importantes
- **GN-030/031 pendentes**: cadastro de fonte não capta nem transcreve; não afirmar rádio/YouTube operacional.
- `/api/demo/next`, `/api/state` e `/ws` operam demo **volátil** separada de `/api/matches/{id}/state` e operações de partida.
- Modelo de substituições não impõe limite/regra de competição (5 substituições, janelas, cartões amarelos e suspensões futuras). Corrigir a regra por competição antes de jogo oficial.
- Auditoria é durável no SQLite, mas administradores locais podem alterar o arquivo; não é trilha assinada. Servidor apenas `127.0.0.1`.
- Validação das URLs é superficial e feita no cadastro; ainda faltam regras DNS/redirecionamentos no processo de captura.
- `iniciar_windows.bat`, execução com FFmpeg real, browsers físicos e GPU/CPU não foram testados em Windows.

## Continuar
1. Ler `STATUS.md`, `ROADMAP.md` e `AGENTS.md`, conferir HEAD da `main` e CI.
2. **GN-030**: construir capturador FFmpeg de rádio MP3/AAC/HLS que emita PCM mono 16 kHz, com encerramento de subprocesso e erros diagnósticos. Testar com fixture reproduzível/local antes de uma rádio real. Garantir URLs seguras (GN-090) no ponto de execução, sem alegar validação Windows.
3. Depois, seguir GN-031 (YouTube com yt-dlp), GN-033 (reconexão), GN-034 (buffer), mantendo itens incompletos em `[ ]` até seus testes.
4. Para testar: `python -m pip install -r requirements-dev.txt && python scripts/export_schema.py && python -m pytest -q`. Sintaxe JS: `node --check app/static/app.js`.
5. Servidor: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8000`. Em Windows, executar e validar `iniciar_windows.bat` fisicamente antes de concluir GN-012.
