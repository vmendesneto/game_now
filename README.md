# Game Now — Futebol acompanhado por narrações de áudio

**Situação atual: planejamento versionado; aplicação ainda não implementada.** Veja primeiro **[STATUS.md](STATUS.md)**.

## O que vamos construir

Site para acompanhar **uma partida de futebol** em um campinho visual, estimando **região da bola, posse de bola, jogador e acontecimentos** a partir de **duas ou mais rádios** e/ou de **transmissões públicas do YouTube Live**. O áudio é processado no servidor local Windows e **não será reproduzido no site**.

O sistema deverá combinar informações de fontes com comerciais e atrasos diferentes. A posição será **estimada a partir das palavras dos narradores**; não é rastreamento óptico nem posição exata.

## Documentos que mantêm o projeto organizado

1. **[STATUS.md](STATUS.md)** — o que está realmente pronto, a próxima tarefa e bloqueios.
2. **[ROADMAP.md](ROADMAP.md)** — fases, tarefas com checkboxes `[ ]` / `[x]`, prioridades e critérios de aceite.
3. **[AGENTS.md](AGENTS.md)** — instruções para Codex/ChatGPT/novos colaboradores retomarem o trabalho.

**Qualquer novo chat deve ler esses três arquivos nesta ordem, conferir o último commit e começar da tarefa indicada em STATUS.** Cada tarefa concluída atualiza ROADMAP e STATUS no mesmo commit. Não declarar tarefas prontas sem evidência de validação.

## Premissas

- Um jogo por vez no MVP.
- Windows 10/11 como servidor inicial.
- Ferramentas locais e open source; sem dependência obrigatória de API de IA paga.
- Recebimento de áudio de rádio e YouTube apenas quando a fonte puder ser acessada legitimamente, sem burlar DRM ou bloqueios.
- Nenhum áudio/vídeo original servido para visitantes.
- Funcionar inicialmente em `127.0.0.1`; avaliar segurança antes de expor na rede.
- Testes de áudio real e Windows físico serão realizados no computador do usuário e **não são considerados concluídos até essa validação acontecer**.

## Próximo passo

**GN-003: contrato dos dados e eventos da partida.** Detalhes e definição de pronto em [STATUS.md](STATUS.md).

Repositório: https://github.com/vmendesneto/game_now
