# ROADMAP — Game Now

> **Fonte oficial do planejamento.** Atualizado em **2026-11-12**. Antes de trabalhar, ler [STATUS.md](STATUS.md), este arquivo e [AGENTS.md](AGENTS.md).
>
> Regra: `[x]` significa **implementado + evidência verificável**; `[ ]` significa pendente. Não marcar como concluído só por ter escrito código. Atualizar `STATUS.md` e `ROADMAP.md` no mesmo commit em que a tarefa é concluída.

## Objetivo e escopo do MVP

Um único jogo de futebol é acompanhado por **duas ou mais fontes de narração**, incluindo rádios online e transmissões públicas do YouTube. O servidor local Windows capta somente o áudio, realiza transcrição e interpretação; o site exibe **um campinho com a região estimada da bola**, provável posse, nomes dos jogadores, placar e eventos com nível de confiança. **Não retransmitir áudio ou vídeo no site**. Nunca apresentar localização aproximada como coordenada física real.

A primeira entrega deve rodar em **Windows 10/11**, localmente, sem chaves de API pagas, com modo demonstração e comandos de instalação/reinício. A ingestão de YouTube não poderá contornar DRM, login não autorizado, paywalls ou restrições técnicas. Uso privado não equivale automaticamente a autorização sobre o sinal; revisar as condições das fontes antes do uso.

## Convenções e definição global de pronto

- **P0** = indispensável ao MVP; **P1** = melhora importante; **P2** = fase posterior.
- Estado por tarefa: `[ ]` não pronta; `[x]` validada. Impedimentos e resultados de testes devem estar em `STATUS.md`.
- Cada mudança deve ter teste automatizado adequado, documentação curta e indicação clara de limitações.
- Não afirmar sucesso em rádio/YouTube reais, GPU ou Windows até testar esses cenários no próprio ambiente.
- Atualizar `STATUS.md` com: última entrega, próxima tarefa, comandos executados, resultados, bloqueios e decisões.
- **MVP aprovado** somente com demonstração funcional, ao menos uma fonte real reproduzível em teste, duas fontes com lógica de reconciliação validada, interface atualizando, e persistência/reinício coerente.

## F00 — Repositório, rastreabilidade e decisões

- [x] **GN-001 [P0]** Criar repositório `vmendesneto/game_now` na branch `main`; evidência: repositório acessível.
- [x] **GN-002 [P0]** Criar ROADMAP, STATUS e AGENTS versionados, com regra de passagem entre chats; evidência: arquivos na `main`.
- [x] **GN-003 [P0]** Definir contrato dos eventos e nomenclatura padronizada (ação, tempo, equipe, jogador, região, fonte, confiança); evidência: exemplos e validação de schema.
- [x] **GN-004 [P0]** Registrar decisões de arquitetura, dependências e alternativas; evidência: documento revisável.
- [x] **GN-005 [P1]** Criar CI (lint + testes) para alterações no GitHub; evidência: workflow passando.

## F01 — Executar e operar no Windows

- [x] **GN-010 [P0]** Criar backend Python e site estático funcional, separados por camadas; evidência: servidor HTTP inicializa.
- [x] **GN-011 [P0]** Fixar versões e dependências Python, com instruções Python 3.11/3.12, venv, FFmpeg e configurações; evidência: instalação limpa documentada.
- [x] **GN-012 [P0]** `iniciar_windows.bat` validado em Windows 11/Python 3.12.0: cópia limpa cria .venv, instala dependências e inicia em 127.0.0.1:8000; Ctrl+C encerra Uvicorn/libera porta, reinício preserva partida/elenco/fonte no SQLite. Playwright Chromium 158 com dois clientes, oito passos e viewport móvel; relatório `docs/GN-085-WINDOWS.md`. Corrigidas dependência WebSocket ausente e conexões abertas do backup. Suíte local: 708 passed/4 skipped.
- [x] **GN-013 [P0]** Criar `/health` e diagnóstico de FFmpeg, modelo ASR, armazenamento e sources; evidência: respostas verificáveis.
- [x] **GN-014 [P0]** Modo demonstração totalmente offline para testar campo, interpretação e WebSocket sem downloads; evidência: roteiro reproduzível.
- [x] **GN-015 [P1]** Logs estruturados, rotação e mensagens de erro compreensíveis; evidência: testes de falhas.
- [x] **GN-016 [P1]** Controlador de lifecycle por fonte com stop idempotente e timeout/cancelamento de fallback, cleanup do FFmpeg com proteção contra corrida na terminação, reinício limpo e testes de subprocesso real/PID sem órfão no Linux CI. Verificação física Windows é separada (GN-085) e permanece pendente; CI do PR obrigatória.

## F02 — Partida, escalação e persistência

- [x] **GN-020 [P0]** Criar esquema de partida (mandante/visitante, cores, lado de ataque, período, relógio, placar); evidência: CRUD e testes.
- [x] **GN-021 [P0]** Cadastro dos dois elencos com número, nome, apelidos, posição e titular/reserva; evidência: fluxo web/API.
- [x] **GN-022 [P0]** Normalizar nomes, apelidos e “camisa 10” sem misturar atletas de equipes; evidência: testes com ambiguidades.
- [x] **GN-023 [P0]** Persistir configuração, fontes, estado e histórico de eventos em SQLite; evidência: reiniciar sem perder dados.
- [x] **GN-024 [P1]** Substituições, expulsões, intervalo, troca de lados e acréscimos; evidência: testes de regras.
- [x] **GN-025 [P1]** Correções manuais de placar, posse e evento com trilha de auditoria; evidência: API/UI + registro.

## F03 — Entradas de áudio: rádios e YouTube

- [x] **GN-030 [P0]** Capturar URL de rádio MP3/AAC/HLS via FFmpeg, converter para PCM mono 16 kHz; evidência: arquivo/stream de teste.
- [x] **GN-031 [P0]** Capturar PCM de YouTube ao vivo **ou gravações de partidas** via yt-dlp + FFmpeg, com tratamento de indisponibilidade. Usuário confirmou autorização para Cruzeiro x Bahia (`Ls4qkPrh4Tk`) em 2026-11-12. Nesta entrega o fluxo autorizado YouTube→FFmpeg→Whisper processou **300s/9.600.000 bytes/75 janelas textuais**, `audio_duration_complete=true`, sem retransmissão. Mais dois testes de 30s a partir de 9:35 com tiny/base. Falhas/formatos cobertos pela suíte Windows. Não comprova 90min, qualidade ASR ou autorização de outras fontes.
- [x] **GN-032 [P0]** Cadastrar, editar, ativar e desativar múltiplas fontes independentes; evidência: API/UI.
- [x] **GN-033 [P0]** Detectar desconexão e reconectar com backoff, incluindo URLs de YouTube que expiram; evidência: simular perda e retomada.
- [x] **GN-034 [P0]** Buffer de áudio por fonte com timestamps e limites de memória; evidência: teste de longas sessões.
- [x] **GN-035 [P1]** Telemetria por fonte no feed HTTP/WebSocket e painel: PCM recebido/ausente/encerrado, classificação provável comercial/narração e atraso captura→texto (não atraso entre rádios), com expiração, isolamento e testes determinísticos. Não ativa captura pelo site; CI PR obrigatória.
- [x] **GN-036 [P1]** Alternativa offline/opt-in de filtro RMS de silêncio para janelas PCM (não classifica propaganda nem voz), preservando offsets e deduplicação, com benchmark sintético de 4 janelas e contagem de chamadas ASR evitadas. Não equivale a WER, benefício em narração real nem benchmark Windows; CI PR obrigatória.
- [x] **GN-037 [P1]** Política de URLs, ausência de transmissão embutida no site e limpeza de arquivos temporários; evidência: testes e inspeção.

## F04 — Transcrição pt-BR

- [x] **GN-040 [P0]** Integrar faster-whisper com escolha de modelo e operação CPU; evidência: transcrever áudio em português.
- [x] **GN-041 [P0]** Processar blocos contínuos de áudio com sobreposição e deduplicação de texto; evidência: benchmark e testes.
- [x] **GN-042 [P0]** Gerar transcrições independentes por fonte com timestamps, idioma e estado de processamento; evidência: feed acessível.
- [x] **GN-043 [P0]** Não bloquear API/site durante inferência; evidência: dois clientes recebendo updates simultâneos.
- [ ] **GN-044 [P1]** Benchmark Whisper tiny/base/small/medium em Windows CPU/GPU com WER, latência, RAM. Preparado CLI local `scripts/benchmark_gn044_whisper.py`, testes de métricas/manifesto e `docs/GN-044.md`; ainda faltam resultados físicos Windows e narração autorizada com referência humana antes de marcar [x].
- [ ] **GN-045 [P1]** Benchmark Parakeet pt-BR ONNX contra Whisper em narração real, sem afirmar backend nativo; evidência: relatório comparativo.
- [x] **GN-046 [P1]** Vocabulário personalizado de atletas, clubes e termos futebolísticos; evidência: teste A/B.

## F05 — Interpretação do futebol

- [x] **GN-050 [P0]** Separar narração de lance atual, anúncio, conversa, análise e replay; evidência: corpus rotulado/testes.
- [x] **GN-051 [P0]** Resolver entidades de jogador, clube e referências (“ele”, “camisa nove”); evidência: testes de ambiguidade (PR #13, CI 43024972166).
- [x] **GN-052 [P0]** Detectar posse e troca de posse com evidência explícita; evidência: testes de sequência e ambiguidades (PR #14, CI 43025807453).
- [x] **GN-053 [P0]** Detectar regiões do campo (5 faixas × 3 corredores) e sentido de ataque; evidência: 30 combinações de faixas/corredores e lados, inversão no segundo tempo, negativos e API read-only (PR #15; CI 43027201520, 175 passed/2 skipped em 3.11 e 3.12).
- [x] **GN-054 [P0]** Detectar passe, cruzamento, chute, defesa, gol, escanteio, lateral, impedimento, falta, pênalti e tiro de meta; evidência: 36 fixtures originais, negativas/conflitos e API read-only (PR #16; CI 43027994130, 218 passed/2 skipped, Python 3.11/3.12).
- [x] **GN-055 [P0]** Pontuar força heurística por jogador, equipe, região, evento e atualidade, explicitamente não calibrada; evidência: casos positivos/negativos, envelhecimento, conflitos e API read-only (PR #17; CI 43029006109, 234 passed/2 skipped em 3.11/3.12).
- [x] **GN-056 [P0]** Impedir movimentação sem posse, equipe, região e atualidade explícitas; bloquear texto vago/comercial/replay/negações e preservar bola no SQLite. Candidatura read-only, não atualização automática; testes conservadores (PR #18, CI 43031120226, 263 passed/2 skipped em Python 3.11/3.12).
- [x] **GN-057 [P1]** Comparar interpretação de frases complexas via LLM local opcional com baseline das regras; JSON estrito, bloqueio de alucinações e saída diagnóstica sem escrita. Testes comparativos simulados e API read-only: PR #19, CI 43032445652 (297 passed/2 skipped em Python 3.11/3.12). Ollama real não testado.
- [ ] **GN-058 [P1]** Corpus real de português esportivo rotulado e versão de avaliação, respeitando direitos das fontes; evidência: conjunto documentado. Ferramenta de validação de manifesto/segmentos humanos e separação sem vazamento em `scripts/gn058_corpus.py`, guia `docs/GN-058.md` e testes somente sintéticos; **continua [ ] porque corpus REAL licenciado não foi disponibilizado/anotado**.

## F06 — Fusão das rádios e relógio

- [x] **GN-060 [P0]** Implementar relógio lógico da partida, independente do instante em que chega o texto; evidência: teste de atrasos.
- [x] **GN-061 [P0]** Calcular atraso relativo por fonte usando eventos comuns e janela de observação; evidência: simulação com delays.
- [x] **GN-062 [P0]** Deduplicar o mesmo lance narrado por várias fontes; evidência: dois relatos geram um evento.
- [x] **GN-063 [P0]** Selecionar fonte ativa considerando comercial, atualidade, confiança e saúde da conexão; evidência: transição entre fontes.
- [x] **GN-064 [P0]** Tratar contradições sem “voltar no tempo” nem inventar coordenadas; evidência: teste de fontes conflitantes.
- [x] **GN-065 [P0]** Expirar posição antiga/mostrar “posição incerta” quando faltar narração válida; evidência: teste de silêncio.
- [x] **GN-066 [P1]** Painel de diagnóstico das decisões da fusão e calibração manual do atraso; evidência: logs legíveis. API read-only com offsets temporários por fonte, painel e testes Node/Python; CI PR #41 primeira rodada 577 passed/2 skipped Python 3.11/3.12 (run 43076830181); nenhuma medição real de atraso.

## F07 — Site e campo

- [x] **GN-070 [P0]** Desenhar campo responsivo via SVG, com 15 zonas, sentido do ataque e troca de lados; evidência: desktop/móvel.
- [x] **GN-071 [P0]** Exibir posição/região estimada, indicador de incerteza e animação limitada ao que foi narrado; evidência: roteiro demonstrável.
- [x] **GN-072 [P0]** Exibir posse, placar, relógio, jogador provável e evento atual; evidência: UI em demo.
- [x] **GN-073 [P0]** Atualizar site por WebSocket sem transmitir mídia; evidência: dois navegadores sincronizados.
- [x] **GN-074 [P0]** Tela de configuração para partida, elencos e fontes (rádio/YouTube); evidência: fluxo sem editar código.
- [x] **GN-075 [P1]** Feed de transcrições, eventos e status de cada fonte, com explicação da confiança; evidência: inspeção UI.
- [x] **GN-076 [P1]** Controles iniciar/pausar/reiniciar e correções manuais; evidência: testes UX.

## F08 — Qualidade e prova real

- [x] **GN-080 [P0]** Testes unitários de parsing, entidades, períodos e validação de estado; evidência: `tests/test_gn080_unit_matrix.py`, PR #33, CI 43057714416 (481 passed/2 skipped em Python 3.11/3.12; fixtures sintéticas).
- [x] **GN-081 [P0]** Testes de integração API + WebSocket + SQLite; evidência: `tests/test_gn081_integration.py`, PR #34, CI 43058719362 (483 passed/2 skipped Python 3.11/3.12; `TestClient` e entradas sintéticas).
- [x] **GN-082 [P0]** Simulador de duas rádios com comerciais, atrasos, contradições e silêncios; evidência: `python -m scripts.simulate_two_radios`, `tests/test_gn082_simulator.py`, PR #35 e CI 43059870772 (486 passed/2 skipped em Python 3.11/3.12; somente dados sintéticos).
- [ ] **GN-083 [P0]** Testar cinco a dez minutos de narração brasileira autorizada e medir equipe/jogador/zona com **gabarito humano independente**. Em 2026-11-12, fluxo real Windows YouTube→FFmpeg→Whisper tiny concluiu 300s/9.600.000 bytes/75 janelas com texto, mas todas desconhecidas (texto sugere pré-jogo). Usuário indicou início por volta de 9:35; novo `--start-seconds 575` testado com PCM exato/FFmpeg real, apenas para gravações. Trecho de 30s concluído com tiny (cinco janelas) e base (sete); ambos sem hipóteses de lance, com erros de ASR. `metrics=null`, sem atualizar estado. Faltam cinco minutos relevantes com bola rolando e gabarito de qualidade; não tratar execução como acurácia. Guia `docs/GN-083.md` e evidências `docs/GN-085-WINDOWS.md`.
  **Subentrega operacional GN-083 (2026-11-12):** controles de captura de fonte cadastrada no navegador → ASR local → texto HTTP/WS e prévia segura, sem mídia/alteração do SQLite. Correção posterior aceita entrar no meio do jogo: três narrações distintas, sem exigir apito ou três verbos diferentes; variações espaciais/sair jogando contam só para fase, mantendo vetos e separação da bola. Replay de texto real confirmou fase após 32s; Playwright capturando desde **9:35/575s** mostrou **Jogo em andamento em dois clientes**, sem referência manual injetada. Apito humano em 9:23/563s é referência, não regra. Suíte Windows **738 passed/4 skipped**, mais 10 testes live após adicionar separação fase/bola. `docs/GN-083-CAPTURE.md`; uma fonte por partida, sem fusão automática. **GN-083 continua [ ]** até avaliar qualidade com gabarito.
  **Apresentação espacial GN-083 (2026-11-12):** corredor citado aparece como faixa tracejada longitudinal completa, sem inventar faixa/posse. Símbolo da bola sempre visível por pedido do usuário: no círculo central quando o corredor citado é central; cinza no último marcador visual quando a informação vence, indicando posição atual desconhecida. Antes da primeira evidência, na margem. Guarda de posição completa preservada e memória isolada/limitada. Windows **756 passed/4 skipped**; Playwright real com dois clientes, 60s PCM desde575s, símbolo central e persistência após expirar, sem mídia/escrita de estado. **GN-083 segue [ ]**, pois apresentação testada não comprova acurácia.
- [ ] **GN-084 [P0]** Ensaiar uma partida inteira, medir latência fim a fim, cobertura e falhas de fonte; evidência: relatório com erros.
- [x] **GN-085 [P0]** Validação executada pelo agente no Windows físico do usuário com sua autorização: FFmpeg 9.0.2, yt-dlp 2026.10.26, faster-whisper tiny/PyAV 17.1.0 processando gravação real autorizada, Chromium/Playwright, dois clientes WS, launcher limpo, persistência, backup/restore e encerramento antecipado de FFmpeg nativo sem processo pendente. Checklist `docs/GN-085-WINDOWS.md`. Não comprova precisão GN-083, partida inteira GN-084, GPU, celular físico ou ligação da captura ao painel.
- [x] **GN-086 [P1]** Benchmark concorrente 2–4 fontes com CPU/RSS/throughput/buffer. CI PR #53: 654 passed/3 skipped em Python 3.11 e 3.12; smoke CPU real tiny Linux: 2 modelos, 6 chamadas, 717,16 MB de RSS pico e 0,97× throughput agregado. Não sustenta duas rádios em tempo real neste ambiente; Windows GN-085 ainda pendente.

## F09 — Segurança e operacionalização

- [x] **GN-090 [P0]** Servidor local por padrão, relay HTTP(S) efêmero com pinagem de DNS/IP e verificação de redirecionamentos e HLS; FFmpeg recebe só URI local. Evidência: `tests/test_secure_ingest.py` (22 passed em Linux, com FFmpeg), `tests/test_gn090_runtime.py` (validação CI pendente antes do merge).
- [x] **GN-091 [P0]** Documentadas instalação limpa, início/parada, atualização e diagnóstico local Windows em `docs/INSTALL_WINDOWS.md`; verificador read-only `scripts/windows_check.py` e `tests/test_windows_check.py` (10 passed em Linux simulando condições Windows). Checklist físico pronto para execução; GN-012/GN-085 seguem pendentes.
- [x] **GN-092 [P1]** Backup/exportação/importação da partida e logs diagnósticos; evidência: restauração. `scripts/gn092_backup.py` + `docs/BACKUP_RESTORE.md`: snapshot SQLite e ZIP com SHA-256, logs opcionais e restauração protegida; testes reais de roundtrip SQLite, corrupção e ZIP malicioso, **586 passed/2 skipped** Python 3.11/3.12 no PR #42 (CI 43078344748). Windows físico ainda GN-085.
- [x] **GN-093 [P1]** Gate de rede por padrão loopback (HTTP/WS, Host/Origin), modo LAN opt-in com token forte, HTTPS/WSS, cookie de sessão `__Host-` assinado, proteção CSRF, runner que exige TLS e revisão de ameaças. CI PR #54: 660 passed/3 skipped em Python 3.11/3.12 na revisão funcional, exigindo resultado verde no HEAD final antes do merge. Sem prova TLS/Windows físico, não autoriza publicação direta na Internet.
- [x] **GN-094 [P1]** Inventário de dependências diretas e pendências de redistribuição em `docs/GN-094.md`, checklist de autorização de fontes e retenção de texto configurável (TTL 60 s–7 dias, 1–500 entradas/fonte), com expiração lazy no backend e descarte na UI. Testes determinísticos; CI PR obrigatória. Revisão de binários, transitivas e fontes específicas permanece operacional.

## F10 — Depois do primeiro jogo validado

- [ ] **GN-100 [P2]** Melhorar classificador com corpus rotulado pt-BR.
- [ ] **GN-101 [P2]** Adicionar eventos avançados (cartões, VAR, substituições, replay e estatísticas).
- [ ] **GN-102 [P2]** Adaptar para várias partidas simultâneas.
- [ ] **GN-103 [P2]** Implantação em servidor remoto, métricas e escalabilidade.
- [ ] **GN-104 [P2]** Avaliar vídeo de fonte permitida para rastreamento óptico; escopo separado do MVP por áudio.

## Portões de entrega

| Marco | Critério de saída | Status |
| --- | --- | --- |
| M0 Planejamento | GN-001 e GN-002; próximo item explícito | ✅ |
| M1 Demonstração offline | GN-010 a GN-014, GN-020 a GN-023, GN-070 a GN-074 em modo demo | Pendente |
| M2 Uma rádio ao vivo | GN-030, GN-040 a GN-043, GN-050 a GN-056 | Pendente |
| M3 Rádio + YouTube | GN-031 a GN-035, GN-060 a GN-065 | Pendente |
| M4 Windows validado | GN-080 a GN-085 e GN-090 a GN-091 | Pendente |

## Protocolo para continuidade em qualquer chat ou Codex

1. Ler **[STATUS.md](STATUS.md)**, **[AGENTS.md](AGENTS.md)** e este ROADMAP; examinar os arquivos e últimos commits reais antes de alegar conclusão.
2. Seguir a **próxima tarefa explícita** em STATUS, respeitando dependências. Se uma tarefa estiver parcialmente pronta, mantê-la desmarcada e documentar a lacuna.
3. Implementar o menor conjunto coerente com testes; não mudar arquitetura ou escopo sem registrar decisão.
4. Ao concluir, marcar `[x]` no ROADMAP **no mesmo commit** que registra o resultado; atualizar STATUS com commit, testes, limitações e próximo ID.
5. Em ambiente sem Windows/áudio real, não marcar validações do Windows como concluídas. Não remover evidências de falhas.
6. Se a execução for interrompida, registrar exatamente onde parou e o próximo comando a executar.

## Referências do projeto

- [STATUS.md](STATUS.md): fotografia atual, pendências e próximo passo.
- [AGENTS.md](AGENTS.md): instruções operacionais para Codex e qualquer novo chat.
- Repositório: https://github.com/vmendesneto/game_now


### GN-060–062 validadas e integradas (2026-11-11)

- **GN-060 [x]:** PR #20, relógio lógico por captura com atrasos simulados; validação incluída na suíte pós-merge.
- **GN-061 [x]:** PR #21 (`a1a3d1f`), atraso relativo entre fontes com eventos comuns fornecidos pelo chamador, simulações e limites; CI 326 passed / 2 skipped em 3.11/3.12 (run 43043216756).
- **GN-062 [x]:** PR #22 (`b4898d7`), agrupamento de dois relatos em um evento diagnóstico sem persistência; CI 341 passed / 2 skipped em 3.11/3.12 (run 43043274805).
- **CI pós-merge na main:** https://github.com/vmendesneto/game_now/actions/runs/43045479371 — **341 passed, 2 skipped em Python 3.11 e 3.12**. Nenhuma dessas simulações comprova captação/alinhamento real de streams ou Windows. **Próxima: GN-063 [ ].**

### GN-063 integrada (2026-11-11)

- **GN-063 [x]:** PR #23, `app/source_selection.py` + endpoint de prévia e testes de failover de fonte, comerciais, atualidade, saúde, força heurística e histerese. CI 361 passed / 2 skipped Python 3.11 e 3.12: https://github.com/vmendesneto/game_now/actions/runs/43047629361. Seleção diagnóstica `persisted=false` e sem alterar estado da partida; sem captação real. **Próxima GN-064 [ ].**

### GN-064 integrada (2026-11-11)

- **GN-064 [x]:** PR #24, guarda read-only contra tempo atrasado e alegações contraditórias entre fontes, sem inventar região. `app/fusion_conflicts.py` e teste `tests/test_fusion_conflicts.py`; CI: **380 passed, 2 skipped** Python 3.11 e 3.12 em https://github.com/vmendesneto/game_now/actions/runs/43048616845. Prévia hipotética; não é sincronismo real de emissoras. **Próxima GN-065 [ ].**

### GN-065 integrada (2026-11-11)

- **GN-065 [x]:** PR #25, validade de último lance por captura alinhada, incerteza após silêncio ou perda da fonte, e expiração da zona com TTL; saída somente de prévia sem escrita. `app/ball_freshness.py`, `tests/test_ball_freshness.py`. CI **397 passed, 2 skipped** Python 3.11 e 3.12 em https://github.com/vmendesneto/game_now/actions/runs/43049429978. Ainda sem render automático no navegador (GN-071). **Próxima GN-070 [P0]**; GN-066 [P1] pendente.

### GN-070 integrada (2026-11-11)

- **GN-070 [x]:** PR #26, campo SVG responsivo de 15 zonas com geometria isolada e testada em Node, inversão conforme o sentido de ataque, rótulos acessíveis e layout móvel. CI https://github.com/vmendesneto/game_now/actions/runs/43050305053 (**400 passed, 2 skipped** em Python 3.11/3.12 + 6 testes Node); houve uma falha inicial de arredondamento numérico corrigida. Não houve inspeção visual em navegador físico. **Próxima GN-071 [ ].**

### GN-071 integrada (2026-11-11)

- **GN-071 [x]:** PR #27, destaque da região estimada, ocultação de posição/atleta/equipe quando incerta ou expirada, rótulos acessíveis e transição visual curta somente após evento novo com mudança explícita de região. `app/static/pitch_presentation.js`, testes Node/Python e ajuste do teste GN-070. CI https://github.com/vmendesneto/game_now/actions/runs/43051118268 (**402 passed, 2 skipped** Python 3.11/3.12). Visual somente sobre demo sintética; sem navegador móvel físico. **Próxima GN-072 [ ].**

### GN-072 integrada (2026-11-11)

- **GN-072 [x]:** PR #28, painel com posse/atleta provável de GN-071, placar e relógio da demo, narração atual separada do último lance confirmado, comercial/replay/análise e relatos duplicados distinguíveis sem gols artificiais. Testes `tests/test_demo_scoreboard.cjs` e `tests/test_demo_dashboard_ui.py` incluem a API sintética completa de 8 passos, CI https://github.com/vmendesneto/game_now/actions/runs/43051812981 (**405 passed, 2 skipped** Python 3.11/3.12). Não há partida ao vivo nem teste físico. **Próxima GN-073 [ ].**

### GN-073 integrada (2026-11-11)

- **GN-073 [x]:** PR #29. Envelope da demo com `stream_id` e `revision` para que duas sessões de navegador nunca exibam uma resposta HTTP antiga por cima de um broadcast WebSocket mais novo; reconexão com backoff, reset versionado e tratamento de reinício do servidor. Testes de dois WebSockets via TestClient + duas sessões independentes simuladas em Node. CI https://github.com/vmendesneto/game_now/actions/runs/43052978721 (**408 passed, 2 skipped** em Python 3.11/3.12). **Não houve teste físico com dois navegadores;** não há captura real nem alteração do `ContractBundle` v1. **Próxima GN-074 [ ].** GN-066 [P1] segue pendente.

### GN-074 integrada (2026-11-11)

- **GN-074 [x]:** Formularios existentes de partidas/elencos/fontes agora incluem resumo progressivo em três etapas (partida salva, atletas mandante/visitante, fontes com URL) sem iniciar captura nem alterar ContractBundle v1. Testes: `tests/test_setup_progress.cjs` (contadores e casos vazios) e `tests/test_configuration_flow_ui.py` (API de cadastro, duas equipes, rádio/YouTube e reabertura SQLite). Sem teste físico com navegador/Windows. **Próxima GN-075 [P1]**; GN-090 antes de captação real.

### GN-075 integrada (2026-11-11)

- **GN-075 [x]:** Painel de diagnósticos por partida mostrando status das fontes, transcrições de texto/razão da classificação e eventos persistidos com pontuações heurísticas explicitamente não calibradas. Cliente HTTP inicial + WebSocket de feed com filtro por fonte, limitação de histórico, descarte de sequência repetida e desligamento ao trocar partida. Testes em `tests/test_transcript_diagnostics.cjs` e `tests/test_transcript_diagnostics_ui.py` (API/WebSocket sintéticos). Não transmite mídia, não ativa captura ou transcrição real; **sem ensaio em navegador físico**. **Próxima GN-076 [P1]**; GN-066 [P1] aberta e GN-090 precede captura.

### GN-076 integrada (2026-11-11)

- **GN-076 [x], escopo demo:** Controles locais para iniciar/pausar avanço automático da demonstração sintética, reinício global existente por HTTP/WebSocket e formulário preexistente de correções manuais auditadas para partidas SQLite. O timer não emite pedidos sobrepostos, aguarda requisição pendente antes do reset e pausa ao chegar ao último passo ou falhar; reiniciar sincroniza com outros navegadores. `app/static/demo_playback.js`, `tests/test_demo_playback.cjs` e `tests/test_demo_playback_controls.py`. **Não controla captação de áudio real nem pausa transcritores externos** (GN-090 e integração operacional pendentes). GN-066 [P1] continua aberta. Próximo trabalho GN-080 [P0] (testes de parsing e estado) ou GN-090 [P0] para segurança antes de ativar captura.

### GN-080 integrada (2026-11-11)

- **GN-080 [x]:** matriz paramétrica de regressões unitárias para parsing, nomes/camisas/pronomes, períodos/ações e integridade de referências do bundle v1, sem precisar de áudio real. Arquivo: `tests/test_gn080_unit_matrix.py`. CI pré-documentação: https://github.com/vmendesneto/game_now/actions/runs/43057714416 (**481 passed/2 skipped**, Python 3.11 e 3.12). Ainda não substitui os ensaios GN-081 (API + WebSocket + SQLite) ou GN-083–085 (narração/Windows real). **Próxima GN-081 [P0]**; GN-090 antes de fontes externas.

### GN-081 integrada (2026-11-11)

- **GN-081 [x]:** dois cenários de integração de API + WebSocket + SQLite, com duas partidas isoladas, dois clientes de feed, fonte sintética, alterações explícitas auditadas, intervalo e recuperação após reinício, sem transmitir áudio/vídeo. `tests/test_gn081_integration.py`; CI pré-documentação https://github.com/vmendesneto/game_now/actions/runs/43058719362 (**483 passed/2 skipped**, Python 3.11/3.12). Sem ensaio Windows ou duas transmissões reais. **Próxima GN-082 [P0]**; GN-090 antes de captura de URLs no painel.

### GN-082 integrada (2026-11-11)

- **GN-082 [x]:** CLI de quatro fases reproduzíveis, duas fontes artificiais com atraso +8 s, descarte de comercial, deduplicação, failover, contradição e silêncio com TTL, sem inferir mídia real ou alterar banco. `scripts/simulate_two_radios.py`, `tests/test_gn082_simulator.py`; CI https://github.com/vmendesneto/game_now/actions/runs/43059870772 (**486 passed/2 skipped** nas versões 3.11/3.12). **Próxima GN-083 [P0]**, condicionada a narração real autorizada; GN-090 [P0] permanece pré-requisito de captura operacional.

### GN-090 — proteção da entrada de mídia (2026-11-11)

- **GN-090 [x]:** `app/secure_ingest.py` introduz relay exclusivamente em 127.0.0.1 para rádio e CDN de YouTube, com DNS validado/pinado a cada conexão, redirecionamentos limitados, playlists HLS reescritas e whitelist de protocolos de FFmpeg sem acesso direto HTTPS ou a arquivos.
- Testes locais: `python -m pytest -q tests/test_secure_ingest.py` — **22 passed** (Linux e FFmpeg real sintetizado); o PR também valida `tests/test_gn090_runtime.py` e a suíte completa em 3.11/3.12. Sem teste Windows ou narração real.
- **Próxima GN-091 [P0]** (instruções de instalação/operação no Windows); GN-083 [P0] espera narração autorizada.

### GN-091 — guia operacional Windows e verificador (2026-11-11)

- **GN-091 [x]:** `docs/INSTALL_WINDOWS.md` explica instalação, verificação de execução local, parada, backup SQLite, `git pull --ff-only`, diagnóstico de FFmpeg/yt-dlp e checklist físico ainda não preenchido. `scripts/windows_check.py` identifica prontidão separada para demo, rádio, YouTube e servidor `127.0.0.1` (sem download de mídia/modelos).
- Prova local determinística: `python -m pytest -q tests/test_windows_check.py` — **10 passed**, Linux Python 3.13. CI em Python 3.11/3.12 deve passar antes do merge. **GN-012/GN-085** requerem execução física no Windows; não afirmar que este checklist foi realizado.
- **Próxima GN-066 [P1]** (diagnóstico de fusão e ajuste de atraso) ou GN-092 [P1] (backup/exportação), após CI e merge. GN-083 continua condicionada à narração autorizada.


### GN-031 — vídeos gravados para testes reprodutíveis (2026-11-11)

- **Subescopo implementado:** resolvedor de YouTube passa a aceitar `is_live`, `was_live` e `not_live`, além de metadados legados que indiquem vídeo encerrado com duração positiva; não exige transmissão ativa. Diagnóstico permite `--seconds 300` a `600` para cinco a dez minutos. `tests/test_youtube_capture.py` cobre vídeo comum, live arquivada, formatos áudio-only/alternativa A/V, falhas para vídeos ainda futuros, DRM/autenticação e saída JSON sem mídia.
- **GN-031 e GN-083 permanecem [ ]:** a URL fornecida para o roteiro (https://www.youtube.com/watch?v=Ls4qkPrh4Tk) não foi efetivamente captada/transcrita neste ambiente, nem houve autorização específica confirmada ou métricas reais com gabarito. Não confundir o vídeo gravado com a categoria linguística `replay` de um lance narrado.
- **Próxima entrega independente:** GN-066 [P1] e, depois, GN-092 [P1]; GN-083 pode prosseguir quando houver material permitido e dados de referência.


### GN-031/GN-090 — diagnóstico de erro 5XX na captura de vídeo gravado (2026-11-11)

- **Erro reproduzido no Windows do usuário:** após `git pull --ff-only` até `1529df7`, o teste com `https://www.youtube.com/watch?v=Ls4qkPrh4Tk` e `--seconds 5` falhou no FFmpeg com `Server returned 5XX` do relay local. Isso confirma que a etapa de resolver metadados avançou, mas **não** prova que a origem retornou HTTP 403 especificamente.
- **Correção candidata implementada:** o consumidor espera 5,5 s antes de acessar URLs `https://*.googlevideo.com/videoplayback` recentemente resolvidas, acompanhando a espera de playback do próprio yt-dlp, sem cookies, autenticação ou bypass. O relay torna falhas de origem diagnosticáveis por códigos seguros (`upstream_http_403`, etc.), em vez de um 5XX opaco, preservando a validação SSRF.
- **Evidência:** `tests/test_gn031_relay_recovery.py` cobre espera seletiva, relay HTTP 403 sem repetição nem vazamento e erro seguro da captura; suíte CI PR Python 3.11/3.12 obrigatória. **GN-031 [ ] e GN-083 [ ]** até teste autorizado de áudio real e métricas; não marcar sucesso físico por testes simulados.

### Fixture local para GN-083 (2026-11-11)

- Escalações das imagens fornecidas: 11 titulares e 12 reservas por clube. Cadastro local por `scripts/seed_cruzeiro_bahia.py`, idempotente, sem alterar GN-083 [ ]. Testes `tests/test_seed_cruzeiro_bahia.py` e guia `docs/GN-083.md`; execução no Windows e ASR real ainda pendentes.

### Diagnóstico de falha Windows GN-083 (2026-11-11)

- Instalação do faster-whisper no Windows/Python 3.12 confirmada; primeira inferência ASR retornou erro genérico e teardown de subprocesso incompleto. `scripts/gn083_asr_check.py`, `app/asr_diagnostics.py`, `--diagnose-asr` em `scripts/gn083_audit.py` e fechamento de pipes em `app/audio_capture.py` adicionados para descobrir causa com autoteste sintético e sem novo teste de captura de 300 s. **GN-083 [ ]** até evidência de ASR real autorizado e métricas com gabarito.

### GN-083 — correção da incompatibilidade PyAV/Whisper (2026-11-11)

- Diagnóstico físico de `scripts.gn083_asr_check` revelou incompatibilidade entre `faster-whisper==1.2.1` e `av==19.0.2` (`metadata_errors`). Dependência opcional fixada em `av==17.1.0`, com teste de regressão `tests/test_gn083_asr_requirements.py` e guia de reparo. GN-083 permanece [ ] até execução real pós-atualização e métricas validadas.


### GN-083 — isolamento CPU/ingestão e diagnóstico 403 (2026-11-11)

- O usuário concluiu ASR físico de 6s em Cruzeiro x Bahia com `tiny`, mas `base`/300s encontrou `upstream_http_403` de mídia. `--capture-first` opcional coleta até 600s PCM (19,2MB) só na RAM antes de transcrever, para evitar pausas do stream por inferência CPU; erro 403 permanece definitivo, com registro do PCM recebido. Testes determinísticos cobrem modo e recusa sem retry, guia `docs/GN-083.md`. **GN-083 [ ]** ainda sem 300s real ou gabarito de qualidade.


### GN-083 — subescopo automático, sem validação física (2026-11-11)

- Implementação textual e testes sintéticos: fases pre_game, probable_start,
  in_play, half_time, second_half; proteção de comentários, anúncios,
  históricos, futuro e replay; monitor contínuo PCM/ASR, API de prévia
  efêmera e campinho de partida selecionada. Arquivos e comandos em
  docs/GN-083.md, tests/test_gn083_match_start.py e tests/test_gn083_live.py.
- **GN-083 [ ]** ainda depende de teste Windows com áudio de uso permitido,
  apito/intervalo anotados e métricas reais com gabarito independente.
  A prévia não atualiza estado persistido e não representa rastreamento real.
- **--seconds** é opcional no monitor, somente para teste curto; sem ele
  acompanha o pré-jogo por tempo indeterminado até o fluxo terminar.
