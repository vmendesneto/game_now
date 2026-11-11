# ROADMAP — Game Now

> **Fonte oficial do planejamento.** Atualizado em **2026-11-11**. Antes de trabalhar, ler [STATUS.md](STATUS.md), este arquivo e [AGENTS.md](AGENTS.md).
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
- [ ] **GN-012 [P0]** Script `iniciar_windows.bat` ou PowerShell, sem necessidade de IDE; evidência: inicializa em Windows.
- [x] **GN-013 [P0]** Criar `/health` e diagnóstico de FFmpeg, modelo ASR, armazenamento e sources; evidência: respostas verificáveis.
- [x] **GN-014 [P0]** Modo demonstração totalmente offline para testar campo, interpretação e WebSocket sem downloads; evidência: roteiro reproduzível.
- [x] **GN-015 [P1]** Logs estruturados, rotação e mensagens de erro compreensíveis; evidência: testes de falhas.
- [ ] **GN-016 [P1]** Encerramento seguro dos processos de áudio e recuperação após reinício; evidência: nenhum processo órfão.

## F02 — Partida, escalação e persistência

- [x] **GN-020 [P0]** Criar esquema de partida (mandante/visitante, cores, lado de ataque, período, relógio, placar); evidência: CRUD e testes.
- [x] **GN-021 [P0]** Cadastro dos dois elencos com número, nome, apelidos, posição e titular/reserva; evidência: fluxo web/API.
- [x] **GN-022 [P0]** Normalizar nomes, apelidos e “camisa 10” sem misturar atletas de equipes; evidência: testes com ambiguidades.
- [x] **GN-023 [P0]** Persistir configuração, fontes, estado e histórico de eventos em SQLite; evidência: reiniciar sem perder dados.
- [x] **GN-024 [P1]** Substituições, expulsões, intervalo, troca de lados e acréscimos; evidência: testes de regras.
- [x] **GN-025 [P1]** Correções manuais de placar, posse e evento com trilha de auditoria; evidência: API/UI + registro.

## F03 — Entradas de áudio: rádios e YouTube

- [x] **GN-030 [P0]** Capturar URL de rádio MP3/AAC/HLS via FFmpeg, converter para PCM mono 16 kHz; evidência: arquivo/stream de teste.
- [ ] **GN-031 [P0]** Capturar **somente áudio** de transmissões públicas YouTube Live via yt-dlp + FFmpeg; evidência: link de teste permitido e tratamento de indisponibilidade. Prova técnica de PCM de live real no Windows: 2026-11-11, 5 s / 160.000 bytes; autorização de uso da fonte ainda não verificada (ver STATUS).
- [x] **GN-032 [P0]** Cadastrar, editar, ativar e desativar múltiplas fontes independentes; evidência: API/UI.
- [x] **GN-033 [P0]** Detectar desconexão e reconectar com backoff, incluindo URLs de YouTube que expiram; evidência: simular perda e retomada.
- [x] **GN-034 [P0]** Buffer de áudio por fonte com timestamps e limites de memória; evidência: teste de longas sessões.
- [ ] **GN-035 [P1]** Telemetria por fonte: online, sem áudio, comercial, narrando, atraso estimado; evidência: painel atualizado.
- [ ] **GN-036 [P1]** VAD/silêncio com Silero ou alternativa: medir benefício sem confundir propaganda com silêncio; evidência: benchmark.
- [x] **GN-037 [P1]** Política de URLs, ausência de transmissão embutida no site e limpeza de arquivos temporários; evidência: testes e inspeção.

## F04 — Transcrição pt-BR

- [x] **GN-040 [P0]** Integrar faster-whisper com escolha de modelo e operação CPU; evidência: transcrever áudio em português.
- [x] **GN-041 [P0]** Processar blocos contínuos de áudio com sobreposição e deduplicação de texto; evidência: benchmark e testes.
- [x] **GN-042 [P0]** Gerar transcrições independentes por fonte com timestamps, idioma e estado de processamento; evidência: feed acessível.
- [x] **GN-043 [P0]** Não bloquear API/site durante inferência; evidência: dois clientes recebendo updates simultâneos.
- [ ] **GN-044 [P1]** Benchmark de modelos Whisper (tiny/base/small/medium) em Windows CPU e, se disponível, GPU; evidência: WER, latência, RAM.
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
- [ ] **GN-058 [P1]** Corpus real de português esportivo rotulado e versão de avaliação, respeitando direitos das fontes; evidência: conjunto documentado.

## F06 — Fusão das rádios e relógio

- [x] **GN-060 [P0]** Implementar relógio lógico da partida, independente do instante em que chega o texto; evidência: teste de atrasos.
- [x] **GN-061 [P0]** Calcular atraso relativo por fonte usando eventos comuns e janela de observação; evidência: simulação com delays.
- [x] **GN-062 [P0]** Deduplicar o mesmo lance narrado por várias fontes; evidência: dois relatos geram um evento.
- [x] **GN-063 [P0]** Selecionar fonte ativa considerando comercial, atualidade, confiança e saúde da conexão; evidência: transição entre fontes.
- [x] **GN-064 [P0]** Tratar contradições sem “voltar no tempo” nem inventar coordenadas; evidência: teste de fontes conflitantes.
- [x] **GN-065 [P0]** Expirar posição antiga/mostrar “posição incerta” quando faltar narração válida; evidência: teste de silêncio.
- [ ] **GN-066 [P1]** Painel de diagnóstico das decisões da fusão e calibração manual do atraso; evidência: logs legíveis.

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
- [ ] **GN-083 [P0]** Testar cinco a dez minutos de narração brasileira e medir identificação da equipe, jogador e zona; evidência: métricas reais.
- [ ] **GN-084 [P0]** Ensaiar uma partida inteira, medir latência fim a fim, cobertura e falhas de fonte; evidência: relatório com erros.
- [ ] **GN-085 [P0]** Validar no Windows físico do usuário: FFmpeg, yt-dlp, modelos, áudio real e navegador; evidência: checklist executado pelo usuário.
- [ ] **GN-086 [P1]** Medir memória/CPU em duas ou mais transcrições simultâneas, ajustar modelo e buffer; evidência: benchmark.

## F09 — Segurança e operacionalização

- [ ] **GN-090 [P0]** Servidor ouvindo somente `127.0.0.1` por padrão; validar URLs/fontes e não aceitar execução arbitrária; evidência: testes de segurança.
- [ ] **GN-091 [P0]** Instruções para instalar, iniciar, parar e atualizar no Windows; evidência: checklist de instalação limpa.
- [ ] **GN-092 [P1]** Backup/exportação/importação da partida e logs diagnósticos; evidência: restauração.
- [ ] **GN-093 [P1]** Autenticação e HTTPS se abrir acesso pela rede/Internet; evidência: revisão de ameaça antes de exposição.
- [ ] **GN-094 [P1]** Licenças das dependências, políticas das fontes e retenção configurável das transcrições; evidência: inventário/revisão.

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
