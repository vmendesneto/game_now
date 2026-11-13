# GN-084 — observação operacional da captura

O painel oferece **Ver relatório** e **Baixar relatório** durante e depois da
escuta. `GET /api/matches/{id}/capture/report` retorna o mesmo diagnóstico, sem
URLs, transcrições ou mídia. Os dados são voláteis: baixe antes de iniciar uma
nova execução completa ou reiniciar o servidor. Reiniciar apenas uma fonte
preserva contadores totais e as últimas64 tentativas encerradas daquela execução.

## Significado das medidas

| Campo | O que mede |
| --- | --- |
| `pcm_to_text` | Disponibilidade do último bloco PCM da janela no servidor até a entrega do texto processado |
| `pcm_to_first_render_ack` | Mesmo ponto inicial até a primeira confirmação de um navegador, após dois frames; inclui o retorno HTTP |
| `recognition_call_wall_time` | Tempo de cada chamada nativa de ASR, incluindo chamadas que terminam após pedido de cancelamento |
| `maximum_queued_pcm_seconds` | Maior fila de áudio aguardando processamento; não inclui a janela já em processamento |
| `unprocessed_audio_seconds` | PCM recebido além do fim da última janela processada; inclui uma janela parcial normal |
| `windows_without_new_text` | Janelas processadas que não acrescentaram texto, inclusive deduplicação; não são necessariamente silêncio |
| `sequence_gaps` | Saltos na sequência dos textos; não comprovam perda de áudio |
| `windows_with_*` | Cobertura de saída das regras, sem gabarito independente de acerto |

Os atrasos começam no fim da janela. Não incluem o tempo necessário para reunir
a janela, nem medem o atraso original da emissora ou o instante oficial do
lance. `broadcast_to_browser_latency_seconds` permanece `null`. Percentis são
intervalos de histograma fixo, identificados como tal; não são percentis exatos.
O primeiro navegador confirma uma janela uma única vez por época/fonte/sequência.
A confirmação de uma execução anterior ou de um replay textual é rejeitada.
Sem navegador visível, pode haver texto sem confirmação de renderização.

## Perfil do reconhecimento

O perfil `live`, padrão da captura pelo painel/API, usa VAD local e temperatura
única0.0 no faster-whisper. Evita as várias tentativas de temperatura do perfil
anterior em janelas difíceis. Mantém modelo, beam e limites de fila; não é garantia
de precisão ou capacidade para qualquer quantidade de fontes. O perfil
`standard` preserva a configuração anterior. A CLI ASR continua com seu padrão
anterior. Modelo, threads, janela e perfil de uma nova fonte devem corresponder
à execução ativa; mudar o seletor só afeta o próximo início.

## Observador sem controle da captura

Depois de iniciar a escuta manualmente, pode-se observar o servidor existente:

```powershell
.\.venv\Scripts\python.exe -m scripts.gn084_watch --base-url http://127.0.0.1:8000 --match-id ID_DA_PARTIDA --seconds 600 --output data/observacao-nova.json
```

O comando faz somente GETs no loopback, nunca inicia/para a captura, e recusa
sobrescrever o relatório. O teto do observador é10800s; isso não autoriza novos
ensaios de áudio além dos limites do projeto. `--until-capture-ends` encerra o
observador ao ver todas as fontes encerradas ou três erros HTTP consecutivos.
`--include-transcript-tail` é opção explícita para guardar os últimos100 textos
em arquivo privado; nunca salva áudio. O padrão exporta só metadados.

GN-084 exige ensaio completo e relatório de falhas. Aprovação de teste virtual,
transcrição parcial, disponibilidade de URL ou detecção textual de fim não
comprovam que uma partida inteira foi acompanhada corretamente.

## Ensaio real de 2026-11-13

Fonte autorizada `KHLaE8n0aTY`, início solicitado2070s, Small/12s/4threads/live,
SQLite temporário e dois Chromium: **7864,077125s de PCM (131min),776 textos e787
janelas processadas** até o fim da fonte. Sem erro de captura/JavaScript, sem
áudio pendente no encerramento, sem mídia salva/retransmitida nem estado persistido
alterado. Houve11 janelas sem texto novo e nove saltos de sequência textual, sem
prova de perda de áudio. Fila máxima6,5s. PCM→texto média2,955s/máximo6,766s;
PCM→primeira confirmação média3,610s/máximo6,797s,776 confirmações. Percentis são
intervalos de histograma; isso não mede atraso da emissora.

**Falha funcional observada:** a versão carregada confirmou início, mas não
intervalo/segundo tempo/fim. O relatório original preserva essa falha. Regras
posteriores reconheceram as expressões reais retidas e, por reanálise textual,
produziram as fases até o fim na janela7242s. Essa reanálise não transforma a
execução original em acompanhamento de fases aprovado. Outra correção posterior
de distribuição de atletas também não integra as métricas originais.

Cobertura original das regras:17 janelas com ação nomeada, três com região parcial,
zero com posição completa. São contadores de saída, **sem precisão demonstrada**.
GN-083/GN-084 continuam abertas. Relatórios privados em
`data/full-match-second-source-latest/final.json` e `phase-reanalysis-fixed.json`.
O servidor isolado encerrou ao concluir; o principal não foi iniciado/alterado.
