# ROADMAP — Game Now

> **Fonte oficial do planejamento.** Atualizado em **2026-11-10**. Antes de trabalhar, ler [STATUS.md](STATUS.md), este arquivo e [AGENTS.md](AGENTS.md).
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
- [ ] **GN-015 [P1]** Logs estruturados, rotação e mensagens de erro compreensíveis; evidência: testes de falhas.
- [ ] **GN-016 [P1]** Encerramento seguro dos processos de áudio e recuperação após reinício; evidência: nenhum processo órfão.

## F02 — Partida, escalação e persistência

- [x] **GN-020 [P0]** Criar esquema de partida (mandante/visitante, cores, lado de ataque, período, relógio, placar); evidência: CRUD e testes.
- [x] **GN-021 [P0]** Cadastro dos dois elencos com número, nome, apelidos, posição e titular/reserva; evidência: fluxo web/API.
- [x] **GN-022 [P0]** Normalizar nomes, apelidos e “camisa 10” sem misturar atletas de equipes; evidência: testes com ambiguidades.
- [x] **GN-023 [P0]** Persistir configuração, fontes, estado e histórico de eventos em SQLite; evidência: reiniciar sem perder dados.
- [ ] **GN-024 [P1]** Substituições, expulsões, intervalo, troca de lados e acréscimos; evidência: testes de regras.
- [ ] **GN-025 [P1]** Correções manuais de placar, posse e evento com trilha de auditoria; evidência: API/UI + registro.

## F03 — Entradas de áudio: rádios e YouTube

- [ ] **GN-030 [P0]** Capturar URL de rádio MP3/AAC/HLS via FFmpeg, converter para PCM mono 16 kHz; evidência: arquivo/stream de teste.
- [ ] **GN-031 [P0]** Capturar **somente áudio** de transmissões públicas YouTube Live via yt-dlp + FFmpeg; evidência: link de teste permitido e tratamento de indisponibilidade.
- [ ] **GN-032 [P0]** Cadastrar, editar, ativar e desativar múltiplas fontes independentes; evidência: API/UI.
- [ ] **GN-033 [P0]** Detectar desconexão e reconectar com backoff, incluindo URLs de YouTube que expiram; evidência: simular perda e retomada.
- [ ] **GN-034 [P0]** Buffer de áudio por fonte com timestamps e limites de memória; evidência: teste de longas sessões.
- [ ] **GN-035 [P1]** Telemetria por fonte: online, sem áudio, comercial, narrando, atraso estimado; evidência: painel atualizado.
- [ ] **GN-036 [P1]** VAD/silêncio com Silero ou alternativa: medir benefício sem confundir propaganda com silêncio; evidência: benchmark.
- [ ] **GN-037 [P1]** Política de URLs, ausência de transmissão embutida no site e limpeza de arquivos temporários; evidência: testes e inspeção.

## F04 — Transcrição pt-BR

- [ ] **GN-040 [P0]** Integrar faster-whisper com escolha de modelo e operação CPU; evidência: transcrever áudio em português.
- [ ] **GN-041 [P0]** Processar blocos contínuos de áudio com sobreposição e deduplicação de texto; evidência: benchmark e testes.
- [ ] **GN-042 [P0]** Gerar transcrições independentes por fonte com timestamps, idioma e estado de processamento; evidência: feed acessível.
- [ ] **GN-043 [P0]** Não bloquear API/site durante inferência; evidência: dois clientes recebendo updates simultâneos.
- [ ] **GN-044 [P1]** Benchmark de modelos Whisper (tiny/base/small/medium) em Windows CPU e, se disponível, GPU; evidência: WER, latência, RAM.
- [ ] **GN-045 [P1]** Benchmark Parakeet pt-BR ONNX contra Whisper em narração real, sem afirmar backend nativo; evidência: relatório comparativo.
- [ ] **GN-046 [P1]** Vocabulário personalizado de atletas, clubes e termos futebolísticos; evidência: teste A/B.

## F05 — Interpretação do futebol

- [ ] **GN-050 [P0]** Separar narração de lance atual, anúncio, conversa, análise e replay; evidência: corpus rotulado/testes.
- [ ] **GN-051 [P0]** Resolver entidades de jogador, clube e referências (“ele”, “camisa nove”); evidência: testes de ambiguidade.
- [ ] **GN-052 [P0]** Detectar posse e troca de posse com evidência explícita; evidência: testes de sequência.
- [ ] **GN-053 [P0]** Detectar regiões do campo (5 faixas × 3 corredores) e sentido de ataque; evidência: frases em ambos os lados.
- [ ] **GN-054 [P0]** Detectar passe, cruzamento, chute, defesa, gol, escanteio, lateral, impedimento, falta, pênalti e tiro de meta; evidência: fixtures.
- [ ] **GN-055 [P0]** Pontuar confiança por jogador, equipe, região, evento e atualidade; evidência: casos positivos/negativos.
- [ ] **GN-056 [P0]** Não mover bola em texto vago, comercial, replay ou ausência de evidência; evidência: testes conservadores.
- [ ] **GN-057 [P1]** Resolver linguagem complexa com LLM local opcional e validação estrita do JSON; evidência: testes comparativos.
- [ ] **GN-058 [P1]** Corpus real de português esportivo rotulado e versão de avaliação, respeitando direitos das fontes; evidência: conjunto documentado.

## F06 — Fusão das rádios e relógio

- [ ] **GN-060 [P0]** Implementar relógio lógico da partida, independente do instante em que chega o texto; evidência: teste de atrasos.
- [ ] **GN-061 [P0]** Calcular atraso relativo por fonte usando eventos comuns e janela de observação; evidência: simulação com delays.
- [ ] **GN-062 [P0]** Deduplicar o mesmo lance narrado por várias fontes; evidência: dois relatos geram um evento.
- [ ] **GN-063 [P0]** Selecionar fonte ativa considerando comercial, atualidade, confiança e saúde da conexão; evidência: transição entre fontes.
- [ ] **GN-064 [P0]** Tratar contradições sem “voltar no tempo” nem inventar coordenadas; evidência: teste de fontes conflitantes.
- [ ] **GN-065 [P0]** Expirar posição antiga/mostrar “posição incerta” quando faltar narração válida; evidência: teste de silêncio.
- [ ] **GN-066 [P1]** Painel de diagnóstico das decisões da fusão e calibração manual do atraso; evidência: logs legíveis.

## F07 — Site e campo

- [ ] **GN-070 [P0]** Desenhar campo responsivo via SVG, com 15 zonas, sentido do ataque e troca de lados; evidência: desktop/móvel.
- [ ] **GN-071 [P0]** Exibir posição/região estimada, indicador de incerteza e animação limitada ao que foi narrado; evidência: roteiro demonstrável.
- [ ] **GN-072 [P0]** Exibir posse, placar, relógio, jogador provável e evento atual; evidência: UI em demo.
- [ ] **GN-073 [P0]** Atualizar site por WebSocket sem transmitir mídia; evidência: dois navegadores sincronizados.
- [ ] **GN-074 [P0]** Tela de configuração para partida, elencos e fontes (rádio/YouTube); evidência: fluxo sem editar código.
- [ ] **GN-075 [P1]** Feed de transcrições, eventos e status de cada fonte, com explicação da confiança; evidência: inspeção UI.
- [ ] **GN-076 [P1]** Controles iniciar/pausar/reiniciar e correções manuais; evidência: testes UX.

## F08 — Qualidade e prova real

- [ ] **GN-080 [P0]** Testes unitários de parsing, entidades, períodos e validação de estado; evidência: suíte passando.
- [ ] **GN-081 [P0]** Testes de integração API + WebSocket + SQLite; evidência: execução local/CI.
- [ ] **GN-082 [P0]** Simulador de duas rádios com comerciais, atrasos, contradições e silêncios; evidência: cenário reproduzível.
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
