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

## Primeiro trabalho indicado

**GN-003: schema de eventos**, conforme `STATUS.md`; seguir GN-004 e implementação vertical mínima no Windows. Manter esta indicação sincronizada com `STATUS.md` nas futuras edições.
