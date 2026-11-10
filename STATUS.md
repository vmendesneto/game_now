# STATUS — Estado atual do Game Now

**Atualizado:** 2026-11-10  
**Branch de referência:** `main`  
**Projeto:** https://github.com/vmendesneto/game_now  
**Fase atual:** F00 — Planejamento e preparação técnica  
**Próxima tarefa:** **GN-003 — contrato dos eventos de futebol**. Em seguida GN-004, GN-010 a GN-014.

## O que está realmente pronto

- ✅ **GN-001:** repositório GitHub `vmendesneto/game_now` criado pelo usuário e inicializado com `README.md`.
- ✅ **GN-002:** arquivos de rastreamento `ROADMAP.md`, `STATUS.md` e `AGENTS.md` criados no repositório.
- ✅ Escopo inicial decidido: **uma única partida**, **Windows como servidor**, entradas de **rádios online e transmissões públicas do YouTube**, **somente áudio para inferência**, **sem áudio nem vídeo retransmitido no site**.
- ✅ Direção técnica provisória: Python/FastAPI, FFmpeg, faster-whisper, yt-dlp, SQLite, React/TypeScript ou frontend SVG leve, WebSocket e módulo próprio de reconciliação.

**Não está pronto ainda:** backend, interface, transcrição, fontes reais, interpretação de lances, sincronização, testes físicos no Windows. **Não existe MVP testável na main neste estado.**

## Próximo passo exato (GN-003)

Especificar um contrato JSON tipado e testado para `Match`, `Team`, `Player`, `AudioSource`, `TranscriptSegment`, `FootballEvent` e `EstimatedBallState`, incluindo:

1. IDs estáveis; versão do schema; marcações de tempo da captura, transcrição e partida.
2. Equipe, jogador e posse opcionais (desconhecido é permitido).
3. Região do campo como **zona**, não como coordenada precisa inventada. Modelo inicial: 5 faixas × 3 corredores, orientação relativa ao sentido de ataque.
4. Categoria do texto `live_play | ad | analysis | replay | unknown`; evento `pass | cross | shot | save | goal | corner | throw_in | offside | foul | penalty | goal_kick | possession | unknown`.
5. Confianças independentes para equipe, jogador, região, ação e tempo, não uma confiança mágica única.
6. Fonte que produziu a observação, ID de evento deduplicado e estado de incerteza/expiração.
7. Exemplos de três tipos: lance válido, comercial, duas fontes relatando o mesmo lance com atraso.

**Aceite de GN-003:** schema e fixtures versionados com testes automatizados que validem os exemplos acima. Somente então marcar GN-003 no ROADMAP.

## Dependências e fatos ainda não verificados

| Item | Estado |
| --- | --- |
| Processador e RAM do Windows servidor | Não informados; medir no equipamento antes de selecionar modelo definitivo |
| FFmpeg no Windows | Não verificado |
| Python 3.11/3.12 e venv no Windows | Não verificados |
| yt-dlp com uma live pública específica | Não testado |
| Transcrição pt-BR de rádio real | Não testada |
| Latência CPU/GPU com duas fontes | Não medida |
| Permissões/condições dos streams selecionados | A verificar fonte a fonte |

## Regras de execução e atualização

- A próxima pessoa/agente deve **ler este STATUS primeiro** e conferir HEAD/arquivos reais no GitHub.
- Escolher a próxima tarefa não concluída compatível com dependências, iniciar implementação e teste.
- Ao terminar: marcar `[x]` na linha correspondente de `ROADMAP.md`, registrar aqui **o que foi entregue**, **provas/testes**, **o que falta**, **o novo ID próximo** e **o SHA do commit/PR se disponível**.
- Se um teste depende do Windows físico, descrever como executá-lo e **não** marcá-lo como feito antes do resultado.
- Não apagar tarefas, não renumerar IDs e não mascarar um bloqueio como concluído.
- Se o usuário disser apenas “continue”, executar a próxima tarefa daqui, sem rediscutir todo o planejamento.
