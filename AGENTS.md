# AGENTS.md — Orientações para Codex, ChatGPT e novos colaboradores

Este arquivo é uma instrução de continuidade do projeto Game Now. **Comece sempre lendo `STATUS.md` e `ROADMAP.md`.**

**Diagnóstico de ações GN-083 (2026-11-12):** usuário pediu reconstruir Zé Lucas/Duarte/Fagner com marcador parado. Reanálise dos119 textos mostra Zé Lucas e Fagner no mesmo corredor direito do Cruzeiro, equivalente no desenho ao esquerdo do Bahia; faixa longitudinal desconhecida fixa âncora(500,516,67). Domínio de David Duarte não traz região extraída; ausência de identificação não é bola sem dono. Painel de auditoria/endpoint read-only e relatório salvo optativo permitem inspecionar frase, fonte, janela e motivo. É reanálise com contexto identificado, não reconstrução de seleção histórica nem gabarito de áudio. Windows811 passed/4 skipped e Playwright com texto real retido/desktop/mobile emulado passaram; sem nova captação. Fonte privada em data/ball-sequence e arquivo em data/action-audits; não versionar. GN-083 continua[ ]; próximos ajustes espaciais devem usar essa evidência, não movimento arbitrário.

**Continuidade atual GN-083, duas fontes (2026-11-12):** o usuário rejeitou os testes de um único movimento como evidência de acompanhamento e forneceu segunda narração autorizada `KHLaE8n0aTY`, apito 35:04=2104s. Primeira `Ls4qkPrh4Tk`, apito 9:23=563s; inícios 575s e 2116s correspondem a 12s após cada apito. `t=4269s` da URL não é apito. Agora o pedido de captura aceita duas fontes com âncoras manuais, até dois modelos no servidor; contextos separados, seleção GN-063, failover e watermark sem retrocesso. Finalizar uma fonte não limpa a outra. Isso substitui referências históricas a uma fonte por partida. Ações/atores não dependem de posição completa; destinatário não confirma recepção, e última região não é atribuída ao próximo jogador. Windows 806 passed/4 skipped; ensaio real de uma fonte 600s/30 anotações/nove atletas, e primeiro paralelo 180s de cada/36 textos/quatro trocas de fonte. Detalhes/validação final no topo de STATUS. GN-083 segue [ ], sem acurácia, clock calibrado ou trajetória completa; nunca preencher lacunas com movimento artificial.

**Correção GN-083 após bola parada (2026-11-12):** anotação de corredor usava indevidamente limite de5s da posição completa; ASR real levou5,18s e descartou lado esquerdo válido. Parcial agora usa TTL15s **contando atraso inicial**, sem prazo novo no recebimento; guarda completa segue5s. Expressões de distribuição espacial sem a palavra bola e sem “do campo” foram ampliadas conservadoramente, preservando veto a replay/comercial/análise/negação/futuro e exigência de direção inequívoca. Windows:769 passed/4 skipped e29 testes espaciais após asserção extra; Playwright real com dois clientes exigiu/observou duas posições do símbolo, centro e corredor esquerdo orientado pelo Bahia, em60s PCM desde575s, sem mídia/escrita de estado. GN-083 permanece[ ]; isso não é rastreamento nem métrica de acerto. Guia e evidência no topo de STATUS.

**Correção do pedido do usuário (2026-11-12): bola sempre dentro do campo.** A âncora inicial na margem foi rejeitada pelo usuário. Sem evidência prévia e após reset, usar símbolo cinza no círculo central (500,310) com posição desconhecida, sem inferir zona/posse. Com indicação prévia vencida, preservar último marcador visual dentro do campo. Essa regra substitui referências abaixo à margem. Playwright real confirmou símbolo inteiro dentro das linhas nos três estados; seis testes pytest de UI/marcador aprovados. GN-083 permanece [ ].

**Pedido explícito do usuário / apresentação GN-083 (2026-11-12):** a bola nunca deve desaparecer. Símbolo esquemático no centro do corredor citado (corredor central: círculo central do SVG), com faixa tracejada indicando que a faixa longitudinal não foi determinada. Isso não confirma posição exata nem posse; guarda GN-056 continua separada. Ao vencer a evidência, reter apenas âncora visual cinza com posição atual desconhecida, sem zona/equipe/jogador atuais. Antes da primeira evidência, símbolo na margem; memória limitada, isolada por contexto e reiniciada ao retroceder/resetar. Essa instrução substitui somente o desaparecimento do símbolo em orientações anteriores; a ocultação de dados atuais sem evidência permanece. Windows: 756 passed/4 skipped; Playwright real em dois clientes, 60s PCM desde575s, corredor central e símbolo em (500,310), persistência cinza após vencimento, sem mídia/escrita de estado. GN-083 segue [ ]; guia `docs/GN-083-CAPTURE.md` e topo de STATUS.

**Correção posterior GN-083 (2026-11-12):** entrar em 9:35 (575s do vídeo) deve reconhecer jogo em andamento mesmo sem apito inicial. Não confundir com o apito que o usuário identificou em 9:23 (563s), nem tornar um desses horários uma regra de fase. Detector corrigido para três narrações distintas em tempos distintos (mínimo 12s), inclusive verbo repetido e variações explícitas de condução espacial/sair jogando, preservando veto a replay/comercial/negação/histórico. Replay das transcrições reais confirmou `in_play` no fim de 32s; Playwright real com captura desde 575s confirmou **Jogo em andamento nos dois clientes**. Testes locais: 738 passed/4 skipped e depois 10 passed no módulo live (um teste adicional). Fase confirmada não preenche bola/posse/região. GN-083 permanece [ ]; detalhes no topo de STATUS e em `docs/GN-083-CAPTURE.md`.

**Entrega operacional posterior em 2026-11-12:** GN-083 agora inicia/para fonte cadastrada pelo painel (`app/capture_runtime.py`), publicando transcrição HTTP/WS e prévia volátil, com limites, erros seguros e cancelamento cooperativo. Playwright real executou base/30s, small/30s e small/60s a partir de 9:35 da fonte autorizada; dois clientes, parada após PCM real, sem mídia no navegador nem escrita de estado. Suíte Windows 727 passed/4 skipped. Guia `docs/GN-083-CAPTURE.md`. **GN-083 permanece [ ]**: não há qualidade demonstrada de jogador/posse/região nem gabarito independente/partida completa. Uma fonte por partida nesta operação; não afirmar fusão de rádios reais. Próximo trabalho é melhorar/avaliar interpretação; usuário pediu execução autônoma dos testes neste Windows, sem devolver comandos como substituto de trabalho possível.

**Continuidade atualizada em 2026-11-12:** GN-012/GN-031/GN-085 [x] neste Windows 11/Python 3.12: .venv limpa, dois contextos Chromium/Playwright, Ctrl+C/reinício/persistência, backup/restore e FFmpeg nativo encerrado antecipadamente. Suíte Windows 708 passed/4 skipped. Usuário confirmou autorização para Cruzeiro x Bahia (`Ls4qkPrh4Tk`); fluxo real YouTube→FFmpeg→Whisper tiny processou 300s/9.600.000 bytes em 75 janelas, sem retransmissão; seek 9:35 também testado com tiny/base por 30s. Evidências em `docs/GN-085-WINDOWS.md`; referências históricas abaixo a essas três tarefas pendentes foram superadas. Continuar GN-083, que permanece [ ] sem gabarito/métricas humanas; sem alegar precisão, GPU, captura no painel ou partida completa.

## Missão

Construir um site que mostra o andamento **de uma partida** em campinho de futebol, estimando **região da bola, posse, jogador e eventos** a partir de **múltiplas narrações de rádio e YouTube, ao vivo ou gravadas para testes reprodutíveis**, com Windows do usuário como servidor inicial. **Não** reproduzir áudio ou vídeo das fontes no site.

Não confundir **posição estimada pela linguagem** com rastreamento óptico. Não fabricar coordenadas, resultados de benchmark ou funcionamento de hardware não testado.

## Procedimento obrigatório antes de codificar

1. Inspecione branch, arquivos e mudanças existentes. Não sobrescreva trabalho alheio.
2. Leia `STATUS.md` para localizar a próxima tarefa; use `ROADMAP.md` para critérios de aceite e dependências.
3. Escolha a menor entrega útil; preserve os IDs GN-xxx sem renumerar.
4. Escreva testes que comprovem o comportamento. No Windows, verifique o sistema real quando a tarefa exigir FFmpeg, GPU, YouTube ou microfone/rádio.
5. Mantenha o MVP executável sem depender de serviço pago. Degradação aceitável: modo demo quando faltarem modelos/streams.
6. Nunca introduza credenciais no git ou contorne DRM, paywall, autenticação ou bloqueios de transmissão.
7. Ao concluir **cada tarefa**, atualize sua checkbox para `[x]` em `ROADMAP.md` **somente depois de testar**, e atualize `STATUS.md` no mesmo commit.
8. Se interrompido ou limitado, documente exatamente o que foi feito, o que falhou e o comando seguinte, mantendo a tarefa inacabada em `[ ]`.

## Processo obrigatório de commits, PR e GitHub Actions — evitar execuções redundantes (2026-11-11)

**Esta regra vale para todo novo chat, Codex ou colaborador.** O workflow `.github/workflows/test.yml` executa em `pull_request` e em `push` para `main`, com matriz Python 3.11/3.12. **Cada novo commit enviado para um PR pode iniciar a suíte completa novamente**, mesmo que só altere Markdown. `concurrency.cancel-in-progress: true` cancela runs anteriores do mesmo PR, mas não evita que sejam criados nem o desperdício inicial de recursos. O merge na `main` dispara **outra execução esperada**. Não tratar duas versões do Python como execuções duplicadas: são validações distintas na mesma run.

### Ordem obrigatória por tarefa GN-xxx

1. **Antes de trabalhar:** ler `STATUS.md`, `ROADMAP.md`, `AGENTS.md`, a `main`, os PRs/branches em andamento e as regras atuais da CI. Reutilizar trabalho existente. Criar a branch da tarefa a partir da `main` atual, sem reabrir trabalho concluído.
2. **Preparar tudo antes do primeiro push:** implementar código e testes, verificar lint/sintaxe/schema e executar os testes relevantes **localmente quando houver ambiente disponível**. Preparar também as alterações finais de `ROADMAP.md`, `STATUS.md`, `AGENTS.md` e/ou `README.md` que forem necessárias. Não criar commit remoto após cada arquivo, nem fazer commits separados só para atualizar esses documentos.
3. **Registrar a tarefa corretamente:** marcar `[x]` no ROADMAP **apenas com evidência de teste executado**; registrar no STATUS o que de fato foi validado e o que permanece pendente. Se só a CI conseguir validar, não alegar aprovação nem marcar a tarefa concluída antes do resultado. Não inventar número de testes ou run ID ainda inexistente.
4. **Publicar uma entrega coerente:** preferir **um único commit por tarefa** contendo código + testes + documentação (ou o menor conjunto de commits indispensável) e **um único push** na branch, então abrir/atualizar o PR. Se estiver usando API do GitHub, criar um commit multi-arquivos por Git Data API (blobs/tree/commit/ref) ou preparar os arquivos em clone local; o endpoint `update_file` gera um commit por arquivo e, portanto, não deve ser usado repetidamente em PR aberto quando for possível agrupá-los.
5. **Validar a CI uma vez para o HEAD definitivo do PR:** acompanhar a execução automática de `Testes Game Now`, incluindo os jobs Python 3.11 e 3.12. A execução do **último commit** precisa estar verde antes do merge. Se falhar, consultar o log, corrigir a causa e fazer novo commit/push **somente pela correção necessária**. Não disparar `workflow_dispatch`/rerun por hábito, nem fazer push só para acompanhar progresso.
6. **Depois da CI verde:** mesclar o PR conforme as regras do repositório e conferir a CI automática da `main`. Evitar commit adicional de Markdown apenas para anotar o número da run: registrar a evidência no PR/descrição/comentário ou agrupá-la com uma futura alteração relevante. Se a documentação realmente exigir atualização imediata na `main`, justificar e aceitar conscientemente **uma** execução adicional.
7. **Ao encerrar:** relatar tarefa, PR/merge, testes, limitações e próximo ID. Não iniciar uma nova tarefa sobre uma branch anterior não mesclada sem registrar essa dependência. Se não for possível validar, deixar `[ ]` e documentar o bloqueio.

### Exemplos a evitar

- `criar código → push → criar teste → push → STATUS → push → ROADMAP → push → AGENTS → push → README → push`: gera várias runs, cancelamentos e filas mesmo sem alteração funcional.
- Executar novamente a mesma suíte só porque a run aparece como `queued`/`in_progress`; primeiro aguardar ou diagnosticar o status da execução atual.
- Mesclar baseando-se na CI de um commit antigo quando o HEAD do PR mudou.
- Alterar o workflow para ignorar arquivos `.md` sem antes verificar as **checks obrigatórias/branch protection**; um filtro por caminhos mal planejado pode deixar PRs eternamente pendentes. Uma otimização de CI deve ser tratada e validada como tarefa própria.

**Exceções justificadas:** correção de falha real, urgência de segurança, conflito de merge e limitação técnica do ambiente. Nesses casos registrar o motivo da execução adicional; evitar execuções inúteis, **nunca** pular testes necessários.

---

## Arquitetura-alvo (ajustável por ADR, sem recomeços arbitrários)

- Backend: Python (FastAPI), processamento de áudio em jobs isolados e persistência SQLite.
- Captação: FFmpeg para MP3/AAC/HLS; yt-dlp para resolver streams públicos de YouTube permitidos (pode falhar; deve informar motivo).
- Reconhecimento de voz: faster-whisper como referência inicial; Parakeet pt-BR ONNX é alternativa **a comparar**, não integração pronta.
- Interpretação: identificação baseada na escalação fornecida, extração de zonas e eventos explícitos, classificador comercial/replay e confiança conservadora.
- Fusão: timestamps, atraso relativo, deduplicação e estado expirável, sem jogar lances antigos por cima de novos.
- Frontend: campinho SVG responsivo; atualizações por WebSocket; controles de partida, escalação e fontes.
- Privacidade: transmitir ao browser apenas estados, eventos e, se habilitado, transcrição textual; jamais repassar mídia original.

## Padrões de engenharia

- Python com type hints, funções pequenas, validação de entrada e erros compreensíveis.
- Evitar dependências pesadas no modo demo; oferecer instalação opcional dos modelos ASR.
- Testes determinísticos com duas fontes artificiais e atraso programável antes de testes ao vivo.
- Documentar requisitos do Windows, versões das dependências e comandos para reprodução.
- Preferir URLs de fontes fornecidas pelo usuário; não armazenar cookies, tokens ou senhas.
- Definir claramente portas/interfaces: padrão `127.0.0.1`; exposição LAN somente após revisão.
- Se alterar contrato de eventos, atualizar schema, fixtures e adaptadores.

## Formato para o STATUS.md após cada entrega

```text
Atualizado: YYYY-MM-DD
Última tarefa concluída: GN-xxx (descrição)
Evidência: arquivos/commit/teste executado/resultado observado
Limitações: ...
Próxima tarefa: GN-yyy (descrição)
Como continuar: comando/arquivo específico
```

## Critérios para marcar concluído

- **Código presente** não basta: execute teste aplicável e descreva o resultado.
- **Testes locais Linux/macOS** não equivalem a validação em Windows.
- **Teste simulado** não equivale a teste de áudio real.
- **YouTube URL resolvida** não prova estabilidade de transmissão por 90 minutos.
- **Transcrição criada** não prova extração correta de jogador/posse/região.
- **Duas fontes captadas** não prova alinhamento de tempos ou seleção correta.

## Próximo trabalho indicado

**Prova técnica GN-031 realizada em 2026-11-11 no Windows.** O usuário forneceu log real da CLI após atualizar a main até `00a4846`: YouTube Live `SWEYimqD_50` gerou 160.000 bytes de PCM mono s16le 16 kHz em 10 chunks, correspondendo a 5 segundos; `audio_retransmitted=false`. Este teste comprova áudio decodificado de uma live real no Windows e não deve ser refeito sem necessidade. Entretanto, a autorização para captar o sinal dessa transmissão **não foi confirmada**, e o critério "link de teste permitido" exige manter **GN-031 [ ]** até essa confirmação. Não presumir autorização apenas por ser público e não tentar contornar autenticação ou DRM.

**GN-040 [x]** validada com faster-whisper real em CPU Linux (teste de fala sintetizada em português na CI, run 43016056292). CLI, modelos opcionais e limites em `app/asr.py`/README; ainda não significa Windows nem rádio real. **GN-041 [x]** validada em CI Python 3.11/3.12 (100 testes, 1 skipped) e teste real CPU português em três janelas (run 43016880967); benchmark só mede montagem. **GN-042/GN-043 [x]** núcleo de feed e worker assíncrono validado em CI (106 testes, 1 skipped, dois clientes e API responsiva), sem captura real ligada. GN-046 [x] comprovada em A/B real com fala pt-BR sintética, 1/6 termos sem prompt e 6/6 com prompt (run 43019542053). GN-050 [x] implementa classificador textual isolado com corpus rotulado de 39 frases sintéticas, CI 115 passed/2 skipped em Python 3.11/3.12 (run 43020798677); sem inferência de bola e sem benchmark real. GN-051 [x] com resolução conservadora de nomes, clubes, camisas e referências, CI 125 passed/2 skipped nas duas versões Python (run 43024972166). GN-052 [x] com posse estritamente explícita/diagnóstica, CI 129 passed/2 skipped (run 43025807453). Próxima GN-053; GN-044/045 dependem de testes específicos reais; GN-090 antes de ativar URLs pela API. A execução em Windows e a validação da GN-031 estão documentadas em `STATUS.md`.

**GN-033 [x]** tem supervisão Python e retentativas com backoff, timeout, parada imediata e re-resolução por tentativa, comprovadas por simulação em Python 3.11/3.12. **GN-037 [x]** assegura política inicial de URLs, não embutir players no site e desabilitar cache/download do yt-dlp; GN-090 ainda precisa cuidar de DNS, redirecionamentos e substreams. Os dois componentes não iniciam automaticamente a captura no painel.

O reconhecimento GN-040 foi testado com modelo real e fala sintética em português. GN-041/042/043 ainda não têm fluxo de ingestão produtivo; não presumir esse funcionamento. GN-012 e GN-085 ainda exigem Windows físico. GN-034 [x] preserva os limites de memória; ContractBundle v1 e separação `/api/state` demo de `/api/matches/{id}/state` permanecem inalterados.


**GN-051 [x] (2026-11-11):** `app/narration_entities.py` + `POST /api/matches/{id}/resolve-narration` resolvem apenas menções textuais com elenco salvo e contexto estritamente limitado, sem atualizar bola/posse. `tests/test_narration_entities.py` inclui ambiguidade, número escrito por extenso, antecedente único, isolamento entre fontes e leitura da escalação após reinício. CI: https://github.com/vmendesneto/game_now/actions/runs/43024972166 (125 passed, 2 skipped em 3.11/3.12). **Continuar na GN-052**, sem afirmar que interpretação está ligada ao áudio real.


**GN-052 [x] (2026-11-11):** `app/possession.py` + `POST /api/matches/{id}/resolve-possession` geram apenas hipótese de posse e mudança de equipe com âncora textual explícita e elenco resolvido, nunca mutando o estado persistido. Passes vagos, anúncios, replay, múltiplas pistas e jogadores ambíguos retornam desconhecido. `tests/test_possession.py`; https://github.com/vmendesneto/game_now/actions/runs/43025807453 (129 passed/2 skipped em Python 3.11/3.12). **Continuar GN-053**, sem ligar áudio e sem afirmar posição da bola.

**GN-053 [x] (2026-11-11):** `app/field_regions.py` + `POST /api/matches/{id}/resolve-region`: faixas 1..5 × corredores 3 relativos à direção do ataque, somente para narração de lance atual com contexto de equipe inequívoco; sem estado automático. CI Python 3.11/3.12: 175 passed/2 skipped (run 43027201520). **Continuar GN-054**, detecção conservadora dos tipos de lance por texto e fixtures. GN-090 ainda bloqueia ativação de fontes sem revisão de SSRF.

**GN-054 [x] (2026-11-11):** `app/event_detection.py` e `POST /api/matches/{id}/resolve-event`: 11 categorias EventKind v1 detectadas somente com pista textual atual afirmativa; 36 fixtures sintéticas e teste read-only; não altera placar/bola e não interpreta múltiplos tipos na mesma frase. CI: https://github.com/vmendesneto/game_now/actions/runs/43027994130 (218 passed, 2 skipped em Python 3.11/3.12). **Continuar GN-055.**

**GN-055 [x] (2026-11-11):** `app/confidence.py` e `POST /api/matches/{id}/resolve-confidence` integram diagnósticos com pontuações independentes de jogador, equipe, região, evento e idade declarada (não verificada). Score é força de regra, **nunca** chance calibrada de acerto; API continua read-only. CI: https://github.com/vmendesneto/game_now/actions/runs/43029006109 (234 passed/2 skipped em Python 3.11/3.12). **Continuar GN-056**, guarda conservadora contra movimentação indevida.

**GN-056 [x] (2026-11-11):** `app/ball_guard.py` e `POST /api/matches/{id}/guard-ball` rejeitam movimento da bola por comercial, replay, texto vago, posse/região incompleta, contradições e idade não informada/antiga. Só produzem candidatura read-only quando texto confirma posse + equipe única + zona 5×3 completa e <=5s declarados; a idade não é verificada por áudio. `tests/test_ball_guard.py`; CI https://github.com/vmendesneto/game_now/actions/runs/43031120226 (263 passed/2 skipped Python 3.11/3.12). **Continuar GN-057** (LLM local opcional, saída JSON estrita) ou GN-060 (P0 de relógio lógico) se as dependências locais não estiverem disponíveis. Não apresentar candidato como movimento real; manter GN-090 antes de ativar fontes.

**GN-057 [x] (2026-11-11):** `app/llm_local.py` disponibiliza comparação de baseline com Ollama **opcional/local 127.0.0.1**, JSON estrito, IDs validados e rejeição de contradições/saídas extras ou duplicadas. API `POST /api/matches/{id}/compare-language` não escreve no banco nem move a bola, `use_local_llm=false` por padrão, e sempre informa `eligible_for_state_update=false`. `tests/test_llm_local.py` usa modelo e transporte simulados; CI https://github.com/vmendesneto/game_now/actions/runs/43032445652 (297 passed/2 skipped, Python 3.11/3.12). **Modelo real Ollama não executado/testado. Próximo GN-060**, construir relógio lógico e testes de atraso; não presumir sincronização de stream.


**GN-060/061/062 [x], 2026-11-11:** PRs #20, #21 e #22 mesclados em `main`, incluindo o relógio lógico por captura, estimador relativo por eventos comuns e deduplicação conservadora de candidatos textuais. CI completa **341 passed, 2 skipped** em Python 3.11/3.12, run https://github.com/vmendesneto/game_now/actions/runs/43045479371. GN-062 continua read-only, não é algoritmo comprovado em transmissão real nem altera a bola. O ASR real em CPU foi testado separadamente com fala sintética em run 43044664124, não em rádio real/Windows. **Próxima tarefa: GN-063** (seleção de fonte ativa), depois GN-064/065. A GN-090 precede ativação da captura real pelo site.

**GN-063 [x] (2026-11-11):** `app/source_selection.py` + `POST /api/matches/{id}/sources/selection/preview` fazem seleção conservadora somente de fontes atuais, saudáveis e com `live_play`, com histerese, failover e estados de perda, mas **sem armazenar escolha nem alterar a partida**. `tests/test_source_selection.py`, CI https://github.com/vmendesneto/game_now/actions/runs/43047629361 (361 passed, 2 skipped em Python 3.11/3.12). O score é heurística, não confiança calibrada, e a entrada de timestamps precisa compartilhar relógio confiável. **Continuar GN-064**, tratar contradições e retrocessos sem inventar região da bola. GN-090 antes de ativação real das fontes.

**GN-064 [x] (2026-11-11):** `app/fusion_conflicts.py` e `POST /api/matches/{id}/events/fusion/preview` implementam veto a informações conflitantes de equipe/atleta/zona/evento, replays, timestamps antigos e zonas ou equipes ausentes. Todas as saídas são somente prévias, sem modificar estado da partida. `tests/test_fusion_conflicts.py`; CI https://github.com/vmendesneto/game_now/actions/runs/43048616845 (380 passed, 2 skipped nas duas versões Python). Exige que o chamador forneça alinhamento confiável e uma fonte ativa; não prova alinhamento nem áudio ao vivo. **Continuar GN-065**, vencimento da posição durante silêncio da narração; GN-090 antes de captação real.

**GN-065 [x] (2026-11-11):** `app/ball_freshness.py` + `POST /api/matches/{id}/ball/freshness/preview` calculam `estimated/uncertain/expired` para o último lance explícito, ocultam zona/equipe/jogador se a fonte for perdida ou se o silêncio ultrapassar limites 5/15 s configuráveis, sem gravar no SQLite. `tests/test_ball_freshness.py`, CI https://github.com/vmendesneto/game_now/actions/runs/43049429978 (397 passed, 2 skipped Python 3.11/3.12). Ainda não existe atualização automática do campo/site; conectar na GN-071 após GN-070. **Próxima GN-070 [P0]**, GN-066 [P1] permanece aberta. GN-090 antes de ligar fontes reais.

**GN-070 [x] (2026-11-11):** `app/static/field_geometry.js` concentra mapeamento das 15 regiões com direção de ataque reversível; `app.js/index.html/styles.css` usam SVG responsivo e rótulos acessíveis. `tests/test_field_geometry.cjs` (6 testes Node) e `tests/test_field_ui.py` garantem invariantes de tela e escalonamento; CI https://github.com/vmendesneto/game_now/actions/runs/43050305053 (400 passed, 2 skipped Python 3.11/3.12). Apenas demo; sem teste visual físico em celular e sem mídia real. **Continuar GN-071**, indicador/animação e roteiro. GN-090 ainda bloqueia captura real.

**GN-071 [x] (2026-11-11):** `app/static/pitch_presentation.js` e `app.js` suprimem região/atleta/equipe quando a demonstração mostra incerteza, respeitam `aria-live`, animam somente mudança de região confirmada por novo ID de evento e desabilitam animação com preferência por movimento reduzido. Testes `tests/test_pitch_presentation.cjs` + `tests/test_pitch_ui.py` e ajuste retrocompatível de `tests/test_field_ui.py`; CI https://github.com/vmendesneto/game_now/actions/runs/43051118268 (402 passed, 2 skipped Python 3.11/3.12). **Próxima GN-072**, consolidar painel UI da demo, sem alterar contrato v1 e sem ativar captura real (GN-090).

**GN-072 [x] (2026-11-11):** `app/static/demo_scoreboard.js` centraliza placar e relógio estritamente dos dados da partida na demonstração, distingue evento atual, último lance confirmado, comerciais/replay/análises e narrações duplicadas. `app.js/index.html/styles.css` preservam status acessível e posse/atleta do adaptador seguro GN-071. `tests/test_demo_dashboard_ui.py` valida os oito passos da demo pela API com apresentação Node (9 snapshots), além de `tests/test_demo_scoreboard.cjs`; CI https://github.com/vmendesneto/game_now/actions/runs/43051812981 (405 passed, 2 skipped nas duas versões Python). **Próxima GN-073**, atualização da interface por WebSocket com dois clientes sem mídia. Demo e SQLite continuam separados; GN-090 antes de ativar fontes reais.

**GN-073 [x] (2026-11-11):** `app/static/demo_sync.js` evita estados desatualizados no navegador com revisão monotônica, reconecta o WebSocket e aceita reinício do servidor. `app/main.py` serializa broadcasts/assinaturas; novos testes usam dois WebSockets TestClient e dois navegadores *simulados* em Node. CI https://github.com/vmendesneto/game_now/actions/runs/43052978721 (**408 passed, 2 skipped**, Python 3.11/3.12). Não houve ensaio físico com dois navegadores, nem áudio real. **Próxima GN-074**, revisar fluxo de configuração visual já existente; GN-066 [P1] permanece pendente e GN-090 precede captura real.


## Compatibilidade de narrações gravadas (2026-11-11)

- A captação CLI deve aceitar vídeo público YouTube gravado (`not_live`, `was_live`) e ao vivo (`is_live`). Não restaurar a trava de live no resolvedor; partidas gravadas são essenciais para desenvolvimento sem depender de horários de jogos.
- **Gravação de uma partida** (modalidade da fonte) é distinta de **replay de um lance** (classificação semântica dentro da narração). Não classificar toda narração de vídeo gravado como `replay` ou congelar o campo só por não estar ao vivo.
- Preservar GN-037/GN-090: sem cookies, autenticação, DRM, URL local, execução arbitrária ou mídia para navegador. A autorização do titular da fonte ainda deve ser verificada; vídeo público não basta por si só.
- Limitar diagnósticos a até 10 minutos de PCM por comando; não inferir métricas reais GN-083 de testes com metadados/áudio sintético. GN-031/GN-083 ficam [ ] até evidenciação autorizada, GN-012/GN-085 continuam exigindo execução física no Windows.
