# Game Now — instalação e operação no Windows (GN-091)

Este roteiro cobre **Windows 10/11**, PowerShell, Git e Python **3.11/3.12**. Primeiro instala a **demonstração offline**; FFmpeg, YouTube e ASR são opcionais. Os testes automatizados não equivalem à comprovação física GN-012/GN-085.

**Prova física em 2026-11-12:** GN-012/GN-031/GN-085 concluídas no Windows 11 com instalação limpa, Chromium/Playwright, parada/reinício preservando SQLite e gravação real autorizada processada por FFmpeg/Whisper. Veja o checklist executado em [GN-085-WINDOWS.md](GN-085-WINDOWS.md). GN-083/084 ainda exigem métricas humanas/partida completa. O checklist em branco abaixo serve para uma nova instalação.

## 1. Instalação limpa

1. Instale Git e Python 3.12 (ou 3.11) com o launcher `py`. Abra novo PowerShell e confira:

   ~~~powershell
   git --version
   py -3.12 --version
   # Se tiver somente 3.11: py -3.11 --version
   ~~~

2. Clone e execute:

   ~~~powershell
   cd "$HOME\Documents"
   git clone https://github.com/vmendesneto/game_now.git
   cd game_now
   .\iniciar_windows.bat
   ~~~

   O `.bat` escolhe Python 3.12 ou 3.11 (launcher `py` ou fallback `python`), e `scripts.gn012_launch` valida a versão da `.venv`, cria o ambiente quando ausente, instala `requirements.txt` (incluindo transporte WebSocket) e executa Uvicorn somente em `127.0.0.1:8000`. Se uma `.venv` existente estiver incompleta ou em versão incompatível, o programa **não a remove**; informe a falha e renomeie-a manualmente só após verificar seus dados. Não precisa habilitar scripts PowerShell. A instalação inicial exige acesso ao PyPI.

3. Com o terminal do servidor aberto, visite **http://127.0.0.1:8000**. Use **Próximo relato** e **Reiniciar** para observar a partida fictícia. Em **outro** PowerShell, na pasta do projeto:

   ~~~powershell
   .\.venv\Scripts\python.exe -m scripts.windows_check --json
   .\.venv\Scripts\python.exe -m scripts.windows_check --health
   Invoke-RestMethod http://127.0.0.1:8000/health
   ~~~

   `demo_ready=true` indica que Python e bibliotecas da demo estão disponíveis; `health.status=ok` confirma que o servidor local respondeu. Sem servidor aberto, `--health` retorna status de indisponibilidade e código de saída 1. Sem FFmpeg instalado, `radio_tools_ready=false` é esperado e **não impede a demo**.

## 2. Ferramentas opcionais para diagnóstico de áudio

A demo funciona sem FFmpeg, yt-dlp, Deno, Whisper ou transmissão real. Para analisar somente arquivos próprios ou streams de captura autorizada:

~~~powershell
# FFmpeg, via winget ou distribuição oficial
winget install --id Gyan.FFmpeg -e
# Abra novo PowerShell para atualizar o PATH:
ffmpeg -version
# YouTube: ferramentas opcionais no venv
.\.venv\Scripts\python.exe -m pip install "yt-dlp[default]" yt-dlp-ejs
.\.venv\Scripts\python.exe -m scripts.windows_check --json
~~~

Certas lives precisam de runtime JavaScript compatível com yt-dlp (por exemplo Deno). Consulte a documentação do yt-dlp quando ocorrer erro de formato. Nunca use cookies, logins ou meios de contornar restrições. Os modelos ASR são opcionais e configurados separadamente.

Com arquivo de áudio próprio, teste sem rede externa:

~~~powershell
.\.venv\Scripts\python.exe -m app.audio_capture --file "C:\caminho\audio-permitido.mp3" --seconds 5
~~~

A resposta contém apenas estatísticas JSON de PCM, não reproduz mídia. Se `yt-dlp.exe` estiver na `.venv` mas fora do PATH, a CLI do YouTube aceita `--yt-dlp ".\.venv\Scripts\yt-dlp.exe"`.

## 3. Encerrar, reiniciar e atualizar

**Parar:** no terminal do servidor, pressione **Ctrl+C**. Não mate todos os processos `python.exe` indiscriminadamente: identifique o processo/PID se necessário.

**Reiniciar:** execute `.\iniciar_windows.bat` na pasta do projeto. Caso a porta 8000 esteja ocupada, confira se há uma instância anterior aberta.

**Atualizar:** pare o servidor, confirme que `git status --short` não revela mudanças locais inesperadas, e faça backup do SQLite. O utilitário GN-092 documentado em [BACKUP_RESTORE.md](BACKUP_RESTORE.md) exporta uma cópia validada de todas as partidas com SHA-256 e restauração protegida, com logs opcionais. A cópia manual abaixo permanece uma alternativa simples quando o servidor está parado. Depois:

~~~powershell
Copy-Item .\data\game_now.sqlite3 "$HOME\Documents\game_now-backup.sqlite3" -ErrorAction SilentlyContinue
git pull --ff-only
.\iniciar_windows.bat
~~~

Se o pull falhar devido a mudanças locais, **não** use `git reset --hard` nem apague o banco. Partidas/elencos são guardados em `data/game_now.sqlite3` (ou `GAME_NOW_DB_PATH`), enquanto o modo demo é volátil e reinicia com o processo. Atualizações não devem apagar o SQLite.

## 4. Diagnóstico de falhas

| Sintoma | Ação segura |
| --- | --- |
| `py` não é reconhecido | Reinstale Python 3.11/3.12 com launcher e abra novo terminal; `py -0p` lista instalações |
| Erro de `pip` | Confira conexão ao PyPI/proxy, ambiente virtual e tente o `.bat` novamente |
| Porta 8000 ocupada | Feche apenas a instância anterior identificada do Game Now |
| Página indisponível | Mantenha o `.bat` aberto; confira `--health` em outro terminal |
| FFmpeg ausente após instalação | Abra novo terminal; execute `where.exe ffmpeg` |
| yt-dlp instalado mas não encontrado | Use o executável da `.venv\Scripts` ou ative o ambiente |
| Fontes cadastradas não capturam | Selecione fonte habilitada em Acompanhar narração, confirme autorização e inicie; ASR e FFmpeg são opcionais e precisam estar instalados no servidor. Veja GN-083-CAPTURE.md |
| Partida demo desapareceu | Esperado após reiniciar; partidas salvas no SQLite permanecem |
| Precisa abrir na LAN | Não use `0.0.0.0`; segurança de acesso remoto depende da GN-093 |

Logs estruturados ficam em `data/game_now.log` ou no caminho configurado por `GAME_NOW_LOG_PATH`. O verificador `scripts/windows_check.py` não altera arquivos, não baixa modelos nem faz consultas a hosts externos (exceto a verificação opcional de `127.0.0.1`).

## 5. Checklist de instalação limpa em Windows físico

Preencher **somente após observar cada etapa**, com data, versão e resultado. Testes Linux não validam hardware Windows.

- [ ] Windows 10/11, Python 3.11/3.12 e Git identificados num novo PowerShell.
- [ ] Clone limpo e `iniciar_windows.bat` criaram a `.venv` e instalaram os pacotes.
- [ ] Navegador abriu a demo local; **Próximo relato** e **Reiniciar** funcionaram.
- [ ] `scripts.windows_check --json` indicou `demo_ready=true`, e `--health` retornou `status=ok`.
- [ ] Ctrl+C parou o servidor; `--health` deixou de responder `ok` e a porta 8000 foi liberada.
- [ ] Partida cadastrada persistiu no SQLite depois de reiniciar o servidor.
- [ ] Backup do SQLite realizado com servidor parado.
- [ ] `git pull --ff-only` com árvore limpa e reinício preservaram a partida, quando houver atualização.
- [ ] **Opcional:** FFmpeg/yt-dlp/modelo foram verificados separadamente, sem afirmar captura real sem autorização.
- [ ] Data, commit, versão Windows/Python, resultados e erros foram registrados no STATUS.

**Limitações:** este roteiro e os testes determinísticos preparam GN-091, mas não comprovam validação física GN-012/GN-085. GN-083 ainda requer cinco a dez minutos autorizados de narração brasileira e anotações de referência; GN-084 requer partida completa. Nunca exponha o servidor à rede antes da GN-093.
