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

Com quantidade variável de fontes, a seleção escolhe um relato atual por vez,
com histerese e failover. Não combina região e atleta de narradores diferentes.
No modo automático não se pede apito: início é reconhecido pela narração, e
fontes sem alinhamento confirmado têm contextos visuais separados. Uma troca
pode mostrar trecho anterior; não há garantia de cronologia entre emissoras.
Referências manuais e watermark ficam no modo opcional de teste com gravações.
Veja `docs/GN-083-CAPTURE.md`; nenhum modo comprova sincronização de rádios reais.

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

## Inspeção de ações e marcador parado

O painel **Por que a bola mudou — ou não mudou?** reanalisa os textos retidos
com o elenco atual, sem alterar a partida. Cada registro mostra fonte, janela,
frase original, ação, atleta/equipe, informação espacial e motivo do desenho:
área nova, mesma área representada, ausência de pista espacial ou ausência de
ação nomeada. Os filtros aceitam nomes sem acentos. A coordenada exibida é a
âncora SVG da área inteira; não é a posição física da bola.

`GET /api/matches/{id}/actions/diagnostics` processa até200 janelas em thread
separada. Retorna fingerprint da configuração usada e informa que não reconstrói
a seleção histórica de fontes. Depois de editar elenco/direções, reanalisar
pode produzir resultado diferente. O contexto original do áudio não é verificado.

Na sequência relatada pelo usuário, os textos130–142s citam Zé Lucas no corredor
direito do Cruzeiro;140–152s citam domínio de David Duarte sem região extraída;
200–212s citam Fagner no corredor direito. Esses corredores ocupam as cinco
faixas longitudinais; o centro do desenho fica igual. O esquerdo do Bahia e o
direito do Cruzeiro coincidem pela direção de ataque. Falta de identificação
entre janelas significa desconhecimento, não bola parada ou sem dono.

Para guardar uma reanálise por solicitação explícita:

```powershell
.\.venv\Scripts\python.exe -m scripts.export_action_diagnostics --match-id cruzeiro-bahia-gn083
```

O CLI também aceita `--input caminho/do/relatorio.json`, previamente exportado.
Salva somente texto/metadados em `data/action-audits`, sem prazo automático de
expiração; não é executado automaticamente durante capturas. **Abrir análise
salva** usa `?saved=true`, filtra fontes removidas e avisa se o contexto atual
mudou. Nunca importa o relatório como observação ao vivo ou escreve estado do
jogo. Arquivos privados não entram no Git.

Validação desta entrega:811 passed/4 skipped neste Windows, incluindo quatro
casos Node de área/motivo. Playwright real reanalisou texto já capturado, verificou
Zé Lucas/Fagner na mesma área, Duarte sem localização, filtros, estado intacto e
390px sem overflow. Isso não é nova validação de áudio nem medição de acurácia.

## Ordem de ações dentro de uma janela

O retorno “Everton Ribeiro na faixa central” do primeiro trecho era perdido por
não repetir um verbo de recepção. Menções elípticas de colegas agora são mantidas
perto de uma ação atual, sem chamar cada menção de toque confirmado. Adversário
na marcação/disputa e posicionamento sem bola não viram recepção; “devolviu pra”
produz destino citado. Não há criação de alias por proximidade fonética.

`current_narration_actions` entrega a lista da janela. O navegador exibe os
passos em ordem, com **ritmo de apresentação** entre180–800ms por passo e até
cerca de6s por bloco. Isso não mede o instante ou a duração de cada passe.
O aviso de atraso/ordem textual permanece visível. Sem região nova, o marcador
fica cinza no último ponto visual; a posição futura não aparece antes de sua
etapa. Polling não reinicia a sequência. Trecho novo/fonte nova substitui a
sequência anterior; pendências interrompidas são indicadas e timers antigos
são cancelados. Posição completa validada continua prioritária.

Na análise, **Ver sequência deste trecho no campo** usa o contexto do relatório,
sem importar observações ou alterar o banco. **Voltar ao acompanhamento** restaura
a prévia atual/demo; captação continua independente. O replay salvo fica
explicitamente identificado como reprodução textual.

Windows:815 passed/4 skipped e cinco testes Node do sequenciador. Playwright real
verificou sete etapas no trecho salvo e em nova captação autorizada de30s desde
575s/small/quatro threads/12s de janela, incluindo esquerdo→central, destino de
devolução, saída sem etapa antiga, estado intacto e zero erro JS. Não verifica
timestamps de palavras, recepção de todos os nomes, área de ataque ou posição
física. GN-083 continua aberta.
