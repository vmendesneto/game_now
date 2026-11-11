# GN-092 — exportação, backup e restauração do Game Now

Ferramenta local, apenas Python padrão, para um **snapshot consistente de todo o banco SQLite**, incluindo partidas, escalações, fontes, trilha de correções e estado persistido. É um backup de todas as partidas do banco, não um arquivo de mídia nem um exportador de um único clube. A demo em memória não é incluída.

## Backup no Windows

No PowerShell, dentro do repositório Game Now, use o Python da .venv:

~~~powershell
.\.venv\Scripts\python.exe -m scripts.gn092_backup backup --db .\data\game_now.sqlite3 --output "$HOME\Documents\game-now-backup.zip"
~~~

A CLI gera um ZIP com game_now.sqlite3 e manifest.json contendo versão, identificadores das partidas, SHA-256 e tamanho do snapshot. A cópia usa a API nativa SQLite Backup, consistente também quando há transações abertas. Se o ZIP já existir, a operação falha sem sobrescrever.

Para exportar **opcionalmente** logs locais da aplicação e três arquivos rotacionados, adicione:

~~~powershell
.\.venv\Scripts\python.exe -m scripts.gn092_backup backup --db .\data\game_now.sqlite3 --output "$HOME\Documents\game-now-com-logs.zip" --include-logs
~~~

Os logs são metadados técnicos, mas podem conter horários, caminhos e outros dados confidenciais. O ZIP contém dados de configuração, nomes e URLs de fontes. **Mantenha esses arquivos privados. Não faça commit, anexo público ou upload não autorizado.** Nenhuma mídia, PCM, MP3 ou vídeo é empacotada pela CLI.

O local de logs padrão é data/game_now.log (pode ser alterado com --log-file). O banco padrão pode ser alterado com --db. Use os caminhos reais ao trabalhar com variáveis GAME_NOW_DB_PATH ou GAME_NOW_LOG_PATH.

## Restauração segura

**Encerre o servidor antes de restaurar** (Ctrl+C). Recupere primeiro em um caminho **novo**, preservando a instalação original:

~~~powershell
.\.venv\Scripts\python.exe -m scripts.gn092_backup restore --archive "$HOME\Documents\game-now-backup.zip" --db .\data\game_now-restaurado.sqlite3
~~~

A ferramenta verifica a lista de entradas do ZIP, limites de tamanho, SHA-256, integridade do SQLite, chaves estrangeiras e referências entre partidas e estados. Apenas depois cria o banco restaurado via substituição atômica. Não extrai caminhos arbitrários do ZIP.

Confirme que o banco restaurado corresponde ao esperado antes de usá-lo. Para restaurar diretamente em data\game_now.sqlite3 já existente, faça **um backup separado do banco atual**, encerre todas as instâncias do servidor e confira que não há arquivos WAL/SHM pendentes. Somente então execute, conscientemente:

~~~powershell
.\.venv\Scripts\python.exe -m scripts.gn092_backup restore --archive "$HOME\Documents\game-now-backup.zip" --db .\data\game_now.sqlite3 --replace-existing
~~~

Por padrão a ferramenta **recusa substituir** um SQLite ou log existente. Restaurar um backup antigo substitui **todas as partidas** do banco de destino; não é uma mesclagem de duas instalações. Se o servidor estiver aberto, o comportamento do Windows pode impedir a troca; não force remoção de arquivos auxiliares enquanto ele estiver ativo.

Para extrair logs históricos **somente em pasta nova**, acrescente --logs-dir .\data\logs-importados. Logs restaurados não substituem os logs ativos da aplicação.

## Diagnóstico, limites e testes

- O manifesto em JSON expõe apenas contagens e IDs técnicos; a mídia nunca integra o ZIP. Banco limitado a 256 MiB, logs a 12 MiB combinados, 4 arquivos de log conhecidos.
- Testes em tests/test_gn092_backup.py cobrem backup/restauração real de SQLite em disco, escalação, fontes, integridade, checksums, arquivos maliciosos e negação de sobrescrita.
- Uma aprovação na CI Linux Python 3.11/3.12 **não equivale** a um teste físico de restauração em Windows (GN-085).
- O ZIP guarda dados sensíveis do usuário sem criptografia integrada; para transporte ou nuvem, utilize armazenamento criptografado sob seu controle.
