# Diagnóstico e Implementação: Regra 26 (Horário de Desligamento na Manobra 245738775)

## 1. Problema Apontado
Na manobra `245738775`, o conferidor aprovou o cronograma ("tudo correto"), apesar de o horário de Desligamento na Manobra divergir da Solicitação:
- **Solicitação**: Início `21/09/2026 11:00` | Término `21/09/2026 15:00`
- **Manobra (Etapa 30 DESLIGAMENTO)**: `21/09/2026 12:00` (divergência de 1 hora)

## 2. Causa Raiz Identificada no Código (`src/core/conferidor_manobras.py`)
1. **Verificação Unidirecional de Início na Regra 26**:
   Nas linhas 2178-2180, o conferidor apenas acusava falha se o início fosse **antecipado** (`ini_man_ref < sol_ini_ref`). Quando o desligamento ocorria **mais tarde** que a solicitação (12:00 > 11:00), a condição era falsa e o atraso era ignorado silenciosamente.
2. **Cálculo de `horarios_deslig` cego a etapas prévias**:
   O cálculo de `horarios_deslig` exigia que a etapa contivesse a palavra `"DESLIGAMENTO"` no título. O equipamento da solicitação `24 - 198574` foi aberto com `MA31` na **Etapa 20 (11:00)** e não constava na Etapa 30, resultando em `horarios_deslig = []` e contornando a checagem de início para este equipamento.
3. **Ausência de Validação do Cabeçalho Global da Etapa de Desligamento**:
   Não havia checagem direta entre o horário do cabeçalho da etapa `DESLIGAMENTO` e o campo `Data Início` da solicitação.

## 3. Implementação Realizada

### `src/core/conferidor_manobras.py`
1. **Validação Global do Cabeçalho de Desligamento**:
   - Adicionada verificação direta antes do laço por equipamento confrontando o horário do cabeçalho da etapa `DESLIGAMENTO` contra `dt_sol_ini`.
   - Emite `ERRO` para início antecipado ou início divergente/postergado (`ini > sol_ini`).
   - Emite `ALERTA` para data programada em dia diferente da solicitação.
2. **Validação Bidirecional por Equipamento**:
   - Incluída a condição `elif ini_man_ref > sol_ini_ref:` gerando a falha:
     `Início divergente/postergado ({ini_man_real.strftime('%H:%M')}) vs Autorizado ({lim_ini.strftime('%H:%M')})`.
3. **Detecção de Abertura em Equipamentos da Solicitação**:
   - No cálculo de `horarios_deslig`, se o equipamento for da solicitação (`info_sol`) e possuir macro de abertura (`MA01`, `MA31`, `MA30`), o horário dessa etapa passa a compor o início da interrupção do equipamento, mesmo fora da etapa formal de desligamento.

### `tests/unit/test_regra26_cronograma.py`
- Atualizada função `simular_regra_26` para refletir a validação bidirecional.
- Adicionado teste `test_regra26_detecta_inicio_postergado_real`.
- Adicionado teste `test_regra26_cenario_manobra_245738775` reproduzindo exatamente o caso da manobra 245738775 e comprovando a detecção da divergência das 12:00 vs 11:00.

## 4. Resultados dos Testes
- Suíte `test_regra26_cronograma.py`: 6/6 aprovados via `pytest`.
- Suíte unitária global: 48/48 testes aprovados (`Ran 48 tests in 0.211s - OK`).
- Linter: `ruff check` 100% aprovado sem pendências.
