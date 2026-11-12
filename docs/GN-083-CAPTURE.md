# GN-083 — acompanhamento pelo navegador

Entrega de 2026-11-12: o site agora inicia e para a captura de uma fonte
cadastrada, executa ASR local e publica texto para os clientes conectados.
GN-083 permanece aberta: integração funcionando não é precisão demonstrada.

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
