# AGENTS.md — Orientações para Codex, ChatGPT e novos colaboradores

Este arquivo é uma instrução de continuidade do projeto Game Now. **Comece sempre lendo `STATUS.md` e `ROADMAP.md`.**

## Missão

Construir um site que mostra o andamento **de uma partida** em campinho de futebol, estimando **região da bola, posse, jogador e eventos** a partir de **múltiplas narrações de rádio e YouTube Live**, com Windows do usuário como servidor inicial. **Não** reproduzir áudio ou vídeo das fontes no site.

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
