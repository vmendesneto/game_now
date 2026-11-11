# GitHub Actions — operacao e diagnostico

A CI usa `ubuntu-24.04` explicitamente para nao herdar trocas imprevistas
de `ubuntu-latest`. A suite normal executa Python 3.11/3.12 em todo PR
e em pushes na `main`, com limite de 12 minutos por job. Cada PR/branch
mantem somente a execucao mais nova (concurrency/cancel-in-progress).

Os testes de FFmpeg nao usam `apt-get`: o executavel estatico vem do wheel
`imageio-ffmpeg==0.8.1`, colocado no PATH durante a job. Isso evita a
falha de DNS do mirror Ubuntu que travou execucoes em 11/11/2026.
A instalacao Python continua dependendo de conectividade com o index PyPI.

A prova pesada de ASR real (faster-whisper + pt-BR sintetizado) executa
em PRs que alteram arquivos ASR relacionados, em push na main com essas
alteracoes ou manualmente em Actions > ASR pt-BR CPU real > Run workflow.
Ela exige espeak-ng via `apt-get` e modelo externo, mas a instalacao de
pacotes do Ubuntu tem timeouts curtos; o resultado nao se confunde com a
suíte deterministica nem com audio real de uma partida.

O workflow `Limpar execucoes obsoletas` cancela execucoes antigas dos dois
workflows acima que nao correspondem ao HEAD atual de main ou de PR aberto.
Para cada branch/PR ainda ativo ele preserva no maximo a execucao valida
mais nova por workflow, priorizando o evento PR. Esta limpeza roda
automaticamente ao adicionar/alterar o proprio workflow na main e pode
ser acionada manualmente em Actions > Limpar execucoes obsoletas > Run workflow.
Nao apaga historico de CI nem cancela workflows nao relacionados.

Se a limpeza estiver enfileirada por indisponibilidade do GitHub-hosted runner,
ela so conseguira executar quando algum runner estiver disponivel; nesse caso
as execucoes antigas podem ser canceladas pela interface GitHub Actions.
Nunca declarar GN-060/061/062 concluidas antes de CI verde.

Em 11/11/2026, a versao 0.6.0 do wheel mostrou falha SIGSEGV (codigo -11)
ao ler a fixture HLS/MPEG-TS. O workflow passa a usar 0.8.1; esta
versao deve ser validada com a mesma fixture na CI e nao permite ignorar
falhas de codecs. O job de limpeza reconsulta estados finalizados e
repete cancelamentos quando a API responder transitoriamente com erro.

## Geracao de fala sintetica no smoke real (11/11/2026)

O teste ASR real nao usa mais `apt-get` para `espeak-ng`, porque o
mirror Ubuntu falhou por DNS/timeout ate na imagem 24.04. O workflow instala
`espeakng-loader==0.2.4` (biblioteca + dados de voz) via PyPI e usa
`scripts/synthetic_tts.py` para gerar PCM/WAV por callback nativo do
espeak-ng; FFmpeg 0.8.1 do wheel normaliza para 16 kHz. Nada e transmitido
a servico TTS remoto. O modelo faster-whisper real ainda depende do download
autorizado dos pesos e a execucao permanece opt-in em mudancas ASR ou manual.
