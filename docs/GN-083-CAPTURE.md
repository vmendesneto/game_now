# GN-083 — acompanhamento pelo navegador

Entrega de 2026-11-12: o site agora inicia e para a captura de uma fonte
cadastrada, executa ASR local e publica texto para os clientes conectados.
GN-083 permanece aberta: integração funcionando não é precisão demonstrada.

Correção de fase: o acompanhamento pode começar com o jogo já em andamento.
Não exige escutar o apito nem três expressões diferentes: confirma por três
narrações distintas da mesma fonte, em tempos distintos, abrangendo pelo menos
12s. A assinatura normalizada impede tratar repetição de ASR como nova evidência.
Condução com localização textual e saída jogando também contam para a fase,
preservando os vetos a replay/comercial/análise/histórico/negação. Essas pistas
**não** acrescentam evidência de posse/região à guarda da bola.

O usuário confirmou **9:35 = 575s** como trecho de jogo e localizou o anúncio
de apito em **9:23 = 563s**. Nenhum valor é hardcoded no detector. Replay das
30 transcrições reais capturadas desde 575s confirmou `in_play` no final dos
primeiros 32s, sem apito nem fase manual. Nova captura real de 60s, mesmo início,
small/contexto12s/quatro threads, passou pelo Playwright com **Jogo em andamento
nos dois clientes**. Relatório e screenshot privados em `data/midgame-browser`.
Suíte local da correção: 738 passed/4 skipped; depois dez testes live passaram,
incluindo um novo teste que mantém a bola desconhecida após confirmar fase.

## Operação

1. Execute `iniciar_windows.bat` e selecione a partida/elenco.
2. Em Fontes de narração, cadastre ou selecione uma fonte autorizada e habilitada.
3. Em Acompanhar narração, selecione a fonte, modelo e duração. Para a gravação
   Cruzeiro x Bahia já autorizada, o usuário indicou início por volta de 9:35:
   informe **575 segundos**. Lives devem usar início zero.
4. Confirme autorização e clique **Iniciar acompanhamento**. Áudio é processado
   no servidor; a transcrição aparece no painel existente, sem player de mídia.
5. **Parar acompanhamento** interrompe a entrada e aguarda a inferência nativa
   que já começou. Enquanto isso o status é Encerrando; a região é ocultada.
   **Ver demonstração** muda a visualização sem encerrar uma captura em curso.

O modo de teste aceita 5–600 segundos PCM. A opção de continuar até parar é
operação contínua, não prova de uma partida inteira ou benchmark de 90 minutos.
Fontes e escalações precisam ser salvas antes de iniciar; o servidor bloqueia
edição/exclusão da partida, fontes, elenco e operações durante a captura.

## Dependências e limites

Whisper é opcional para a demo. No servidor de captura:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-asr.txt
.\.venv\Scripts\python.exe -m pip install "yt-dlp[default]"
```

FFmpeg precisa estar instalado. O runtime procura yt-dlp também ao lado do
Python da .venv. O modelo é preparado antes de abrir a fonte, evitando acumular
áudio enquanto pesos são baixados pela primeira vez. O padrão usa até quatro
threads CPU, sem serviço de reconhecimento pago. Não há backend GPU novo.

Uma fonte é selecionada por partida, sem misturar transmissões não alinhadas.
O servidor limita a duas capturas ativas no total. Buffer de aproximadamente
40s; se a CPU não acompanhar, ocorre erro explícito. O FFmpeg é ritmado em
tempo real para gravações. URLs sempre passam por GN-037/GN-090; não aceita URL
arbitrária no corpo do comando, cookies, autenticação de fonte ou argumentos de
shell. Os comandos start/stop aceitam somente peers locais, além do middleware
de Host/Origin. Nenhuma captura inicia/restaura automaticamente com o servidor.

O feed e a prévia são voláteis; ASR não altera placar, eventos nem bola no
SQLite. Novo acompanhamento reinicia o feed para todos os clientes. Falhas de
origem e ASR aparecem com códigos seguros, sem exceções/URLs assinadas. Logs não
recebem texto de narração. Retenção de texto segue GN-094.

Timestamps medem tempo do trecho e chegada local de PCM, não o relógio oficial
do jogo. O runtime impede nova região se o final da janela tiver mais de cinco
segundos de atraso local. Mesmo áudio recente só gera região com as guardas
textuais de posse/equipe/zona e fase confirmada; caso contrário fica desconhecida.
Quando não há evidência de início, a interface informa **Início ainda não
confirmado**, sem afirmar que uma gravação em andamento está no pré-jogo.

## API

`GET /api/matches/{id}/capture` retorna estado e contagens, sem mídia/URL.
`POST .../capture/start` retorna 202 e recebe apenas:

```json
{"source_id":"youtube-authorized","permission_confirmed":true,"model":"small","start_seconds":575,"seconds":60,"window_seconds":12,"cpu_threads":4}
```

`seconds:null` seleciona operação contínua. `POST .../capture/stop` retorna 202;
consulte status até `stopped`. Não é permitida outra ativação enquanto o worker
anterior ainda estiver encerrando. Durante captura ativa, observações externas
de CLI para a mesma prévia são recusadas para impedir mistura de fontes.

## Evidência executada neste Windows

- Suíte completa: **727 passed, 4 skipped**, Python 3.12.0/Windows 11; verificações
  de JavaScript e schema v1 também aprovadas. Testes cobrem dois clientes WS,
  início/parada/reinício/shutdown, cancelamento antes do primeiro turno,
  espera da inferência nativa, reset de feed, limites/validação, dados read-only,
  sanitização de erro e roteamento rádio/YouTube com captura artificial.
- Playwright/Chromium real, fonte autorizada `Ls4qkPrh4Tk`, início solicitado 575s:
  **base/12s de contexto/2 threads**, 30s PCM, três trechos textuais; 61 consultas
  de saúde durante execução, maior duração 0,032s.
- **small/30s de contexto/2 threads**, 30s PCM, um trecho textual; 107 consultas
  de saúde, maior duração 0,046s. Preparação/download do modelo precedeu áudio.
- **small/12s de contexto/4 threads**, 60s PCM, seis trechos textuais; 77 consultas
  de saúde, maior duração 0,047s. Reinício e parada pelo botão após 1s PCM real;
  worker retornou `stopped`. Duas sessões independentes receberam texto. Sem
  mudança do estado salvo, erro JS, mídia/requisição externa no navegador.
- Esses tempos são observações do teste local de HTTP, **não** latência fim a
  fim GN-084. Os textos de jogo ainda tiveram erros e ficaram majoritariamente
  não classificados; não há precisão/WER/gabarito independente nem fusão real.

Artefatos privados em `data/capture-browser-base`, `capture-browser-small` e
`capture-browser-small-12s` (relatório, screenshot e traces; os dois últimos
também incluem transcrição local). Não versionar transcrições/traces privados.

Reprodução opcional em banco isolado com a fonte já cadastrada:

```powershell
.\.venv\Scripts\python.exe -m scripts.gn083_browser_check --match-id cruzeiro-bahia-gn083 --source-id youtube-authorized --start-seconds 575 --seconds 60 --window-seconds 12 --model small --permission-confirmed --output data/capture-check
```

O comando altera a sessão volátil, inicia/reinicia/para uma fonte autorizada e
verifica dois clientes e ausência de escrita em `/state`; não substitui avaliação
humana de lances, comparação GN-044/045 ou ensaio de partida completa GN-084.
Acrescente `--expect-in-play` para exigir que o estado Jogo em andamento apareça
efetivamente nos dois navegadores durante um trecho previamente conferido.

## Corredor citado e símbolo persistente (2026-11-12)

A narração pode indicar apenas um corredor, sem determinar sua faixa ao longo
do campo. Essa indicação aparece como faixa tracejada nas cinco regiões, com
`band:null` e sem confirmar posse. Lados exigem equipe/direção inequívocas;
o corredor central independe da direção. A guarda de posição completa não usa
essa indicação para autorizar um lance.

Por pedido do usuário, o símbolo da bola permanece visível: no centro do desenho
do corredor citado (círculo central em corredor central), em cinza no último
marcador visual quando faltam dados atuais, ou na margem antes da primeira
evidência. A âncora do símbolo não comprova uma faixa longitudinal ou coordenada
exata. Ao vencer a informação, zona/posse/jogador continuam desconhecidos e o
rótulo explica isso. Contextos e resets não reaproveitam posições alheias.

Validado com **756 passed/4 skipped** neste Windows, incluindo seis testes Node
do marcador. Playwright real em dois contextos: 60s PCM desde575s, small/12s de
janela/quatro threads, seis textos; corredor central com símbolo em (500,310),
fase em andamento e símbolo cinza após vencer a evidência. Reinício/parada com
PCM real, sem mídia/requisições externas/erro JS/escrita de estado. Relatório
privado `data/spatial-ball-browser/report.json`. Nenhuma acurácia foi medida.

O script aceita `--port 8001` para testar um servidor com banco isolado sem
interferir no painel principal. Acrescente `--expect-spatial-mention` para exigir
faixa tracejada das cinco regiões e marcador parcial nos dois clientes.
