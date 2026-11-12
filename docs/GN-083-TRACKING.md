# GN-083 — ações e participantes independentes da posição

A prévia anterior dependia de uma frase com posse, equipe e zona completa para
exibir jogador/equipe; uma anotação de corredor apenas mantinha a bola em uma
âncora. O teste de dois pontos em60s comprovava somente essa anotação, não o
acompanhamento de dez minutos, passes ou recuperações.

`app/narration_tracking.py` extrai ações **na ordem do texto** com nomes
inequívocos do elenco salvo: recepção, domínio, condução, recuperação, ação com
bola e destinatário de passe. O destinatário é rotulado separadamente, pois sua
menção não confirma recepção. Um nome sozinho não atualiza nada. Referências
ambíguas e jogadores citados como marcadores adversários não viram passadores.
Oferecimento/replay bloqueiam toda a janela; análise, especulação e discussão
de formação bloqueiam a frase; negativas/perguntas/receber atendimento ou cartão
não viram toques. Os exemplos de teste são artificiais, sem acurácia de áudio.

`LivePreviewRegistry` guarda até96 ações por partida/fonte, com identificação,
intervalo real da janela de ASR e trecho textual. Ordem de caracteres não é
timestamp de palavra. Repetições idênticas em janelas sobrepostas são descartadas
conservadoramente; isso não prova deduplicação de lances reais ou fusão de fontes.
A ação atual vence em15s contando a idade inicial; uma janela sem ação válida
limpa a hipótese atual. Histórico continua claramente histórico até reset/parada.
O último trecho com região também é guardado separadamente: um passe seguinte
sem zona não apaga essa região e não a transforma em posição do destinatário.
O nome junto ao símbolo corresponde à ação que forneceu a região, enquanto o
quadro de atleta/equipe pode indicar o próximo lance sem localização conhecida.
Estado/placar/bola no SQLite e ContractBundle v1 permanecem separados.

O painel mostra **Equipe do lance** e **Atleta do lance**, inclusive sem região,
e lista ações anteriores com intervalos relativos à captura. O nome e a cor da
equipe junto ao símbolo permitem perceber troca de participante na mesma zona.
Essa anotação não confirma posse atual nem evento oficial. Ela não altera o
resolvedor estrito GN-052 ou a guarda GN-056.

Geografia parcial associada à ação pode informar corredor e/ou conjunto de
faixas: defesa abrange1–2, meio-campo3, ataque4–5; corredor sem faixa abrange as
cinco. Um corredor ausente permanece desconhecido (toda a largura). A faixa
tracejada cobre toda a área de incerteza e o símbolo usa seu centro **como
âncora visual**, sem afirmar coordenada exata. Sem pista espacial nova, o último
marcador fica cinza; passes não ganham coordenadas arbitrárias ou animação por
tempo. Região não é emprestada através de outro nome de jogador no mesmo texto.

O teste real deve avaliar a sequência inteira. `scripts.gn083_browser_check`
aceita `--seconds 600 --expect-actions --expect-movement`: exige pelo menos dez
ações nomeadas, atualização visível de quatro atletas e duas equipes em dois
navegadores, além de duas regiões diferentes. Esses limiares são verificações de
integração; não são metas de acurácia nem medem cobertura de todas as jogadas.
O teste também verifica início/reinício/parada, estado persistido intacto,
símbolo sempre visível e ausência de mídia/requisições externas/erro JS.

Limitações: ASR ainda erra nomes e verbos; comentários longos podem não descrever
a bola. O sistema não recupera posições que não foram narradas. Vários lances
na mesma janela chegam juntos, com intervalo de janela, sem tempo exato por
palavra. Não afirmar atualização por passe em tempo real, posse validada,
trajetória completa ou precisão GN-083 sem avaliação independente.

Com duas fontes, a captura permanece independente por fonte e a seleção escolhe
um relato atual alinhado, com histerese e failover. Não combina região e atleta
de narradores diferentes. Os apitos informados pelo usuário são o ponto inicial
do alinhamento; o watermark bloqueia regressões. Esse modo é descrito em
`docs/GN-083-CAPTURE.md` e não comprova que as duas rádios narram o mesmo instante.

## Evidência Windows em 2026-11-12

- Suíte local final: **806 passed, 4 skipped**; sete casos Node do marcador,
  schema v1 sem mudança e sintaxe JS válida. Regressões adicionais cobrem fase
  compartilhada sem conceder permissão de posição à fonte, publicidade após zona
  em cache e nova evidência completa na mesma região após vencer a anterior.
- Uma fonte/600s:59 textos,30 anotações,nove atletas visíveis/três âncoras.
- Primeiro paralelo/180s de cada:36 textos e quatro trocas de fonte. Um roteiro
  curto posterior não atingiu duas posições parciais diferentes; o teste foi
  ampliado para dez minutos, mantendo os mesmos critérios de aceitação.
- Paralelo/600s **de cada**:59+60 textos,32 ações anotadas,dez atletas e duas
  equipes visíveis nos dois clientes; quatro âncoras parciais e quatro trocas de
  fonte. Término, reinício e parada após ambas receberem1s PCM passaram. Sem
  retrocesso, alteração de estado persistido, mídia/HTTP externo/erro JS no
  navegador.565 consultas health, máximo0,062s observado (não é latência ponta a
  ponta). Relatório privado `data/dual-final-ten-minute-browser/report.json`.

Essas quantidades medem saídas e verificações de integração; não contam todos os
passes reais e não medem acurácia, WER ou qualidade de posse. **GN-083 segue [ ].**
