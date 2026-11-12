# Validação Windows — 2026-11-12

Execução pelo agente no próprio Windows do usuário, sem mocks de navegador.
GN-012/GN-031/GN-085 concluídas no escopo de inicialização, captura autorizada e
validação das ferramentas no Windows. Qualidade com referência humana pertence
à GN-083 e partida completa à GN-084; ambas permanecem abertas.

Ambiente: Windows 11 `10.0.26300`, Python 3.12.0, FFmpeg 9.0.2,
yt-dlp 2026.10.26, PyAV 17.1.0, faster-whisper 1.2.1,
Playwright 1.65.1, Chromium 158.0.8127.18.

## Checklist executado

- [x] Cópia dos arquivos versionados sem .venv/banco em `data/windows-clean`.
- [x] `.\iniciar_windows.bat` criou .venv, instalou requirements e iniciou localhost.
- [x] Instalação limpa revelou ausência de transporte WebSocket; corrigido com dependência explícita `websockets==17.4`.
- [x] `/health`: `status=ok`, `mode=synthetic_demo`; `scripts.windows_check --health --json` aprovado.
- [x] Playwright: Chromium real com dois contextos independentes recebendo WebSocket, oito relatos e reset compartilhado.
- [x] Placar não duplicou gols em relato repetido/replay; botão avançar desativado ao final.
- [x] Cadastro pelo navegador de partida, atleta e fonte **desativada**, sem iniciar captura.
- [x] Viewport móvel emulado 390×844 com preferência de movimento reduzido, campo visível e sem overflow horizontal.
- [x] Nenhum erro JavaScript, player de mídia ou requisição HTTP externa durante o cenário.
- [x] Ctrl+C na PTY: Uvicorn registrou shutdown completo; PID 1180 desapareceu, TCP 8000 recusou conexão (`10061`). Confirmado `S` no prompt padrão do cmd para finalizar o batch.
- [x] Reinício do .bat: novo PID 11672; navegador confirmou partida, elenco e fonte persistidos. Segunda parada também completou shutdown.
- [x] Backup/restore real do banco isolado: uma partida restaurada, sem áudio. Corrigido vazamento de conexões SQLite observado como WinError 32.
- [x] Suíte completa Windows: **708 passed, 4 skipped**, 14,58s; asserções finais do resolvedor: 41 passed. Os skips são três testes opt-in de ASR/fala sintética pesada e o probe de PID exclusivo Unix. Um aviso de depreciação AnyIO/Starlette permanece.
- [x] FFmpeg real decodificou fixtures MP3/AAC/HLS; nenhuma dessas fixtures é rádio real.
- [x] Autoteste CPU tiny: `ok=true`, 6s de silêncio sintético, zero segmentos, sem mídia externa.
- [x] FFmpeg nativo: parada antecipada de leitura de WAV sintético aguarda saída do processo real (`returncode` e `wait` confirmados); não usa o probe Unix `os.kill(pid,0)` no Windows.
- [x] Usuário confirmou autorização para gravação Cruzeiro x Bahia `Ls4qkPrh4Tk`. Fluxo real YouTube→FFmpeg→Whisper tiny processou **300s/9.600.000 bytes/75 janelas com texto**; sem áudio em disco/navegador nem escrita no banco. Resultado sem gabarito: 75 interpretações desconhecidas, `metrics=null`; texto sugere pré-jogo.
- [x] Início aproximado indicado pelo usuário: 9:35; novo `--start-seconds 575`, somente gravações, validado em FFmpeg real com amostras exatas após seek fracionário. Tempos de observações/gabarito relativos ao trecho; offset remoto solicitado não verificado independentemente.
- [x] Comparação diagnóstica do mesmo trecho a partir de 9:35, 30s/960.000 bytes: tiny produziu cinco janelas e base sete, todas sem hipóteses de equipe/jogador/posse/região/evento. Não há WER/gabarito; não é benchmark GN-044 nem melhoria de qualidade comprovada. Processos de áudio saíram ao fim.
- [x] Schema v1 sem mudança; exportação passou a fixar LF para evitar diff exclusivo de CRLF no Windows.
- [ ] Narração real autorizada com referência humana, qualidade equipe/atleta/zona e falhas de fonte.
- [ ] Partida completa, métricas de cobertura/latência e modelos CPU/GPU comparados.
- [ ] Celular físico; emulação não comprova hardware móvel.

## Reprodução

Use **uma cópia descartável** do projeto, sem banco pessoal. A CLI salva uma
partida de teste e avança a demo. Não a execute contra a instância de uso diário.
Os artefatos locais não são versionados porque podem conter dados de cadastro.

No projeto principal, instale apenas as dependências opcionais de teste:

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-browser.txt
.\.venv\Scripts\python.exe -m playwright install chromium
# Uma cópia limpa local, depois de o código estar commitado:
git clone --no-hardlinks . data/windows-checkout
```

Em outro terminal, execute `data/windows-checkout/iniciar_windows.bat`.
Com a porta 8000 atendendo apenas essa instância, no terminal principal:

```powershell
.\.venv\Scripts\python.exe -m scripts.gn085_browser --output data/windows-browser/initial
# Pare o .bat por Ctrl+C, confirme S se solicitado, confira a porta e reinicie.
.\.venv\Scripts\python.exe -m scripts.gn085_browser --output data/windows-browser/restart --verify-persisted
.\.venv\Scripts\python.exe -m pytest -q
```

Relatórios da execução observada: `data/windows-browser/initial/report.json` e
`restart/report.json`; screenshots desktop/mobile e traces ZIP acompanham cada
fase. Suíte em `data/windows-pytest.log`; backup de teste em
`data/windows-browser/backup.zip`, restauração em `restored.sqlite3`.
Os relatórios privados `data/windows-browser/gn083-authorized-300s.json`,
`gn083-kickoff-30s.json` e `gn083-kickoff-base-30s.json` registram a
execução sobre gravação real autorizada. Nenhum resultado sem gabarito mede
qualidade de interpretação em jogo real ou estabilidade por 90 minutos.
