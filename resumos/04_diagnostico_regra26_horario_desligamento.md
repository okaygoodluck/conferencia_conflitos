# Diagnóstico e Solução: Regra 26 (Horário de Desligamento na Manobra 245738775)

## 1. Problema Apontado
Na manobra `245738775`, o conferidor aprovou o cronograma ("tudo correto"), apesar de o horário de Desligamento na Manobra divergir da Solicitação:
- **Solicitação**: Início `21/09/2026 11:00` | Término `21/09/2026 15:00`
- **Manobra (Etapa 30 DESLIGAMENTO)**: `21/09/2026 12:00` (divergência de 1 hora)

## 2. Causa Raiz Identificada no Código (`src/core/conferidor_manobras.py`)
1. **Verificação Unidirecional de Início na Regra 26**:
   Nas linhas 2178-2180, o conferidor apenas acusa falha se o início for **antecipado** (`ini_man_ref < sol_ini_ref`):
   ```python
   if ini_man_ref < sol_ini_ref:
       falhas_r26.append(f"Início antecipado ({ini_man_real.strftime('%H:%M')}) vs Autorizado ({lim_ini.strftime('%H:%M')})")
   ```
   Quando o Desligamento na manobra ocorre **mais tarde** que a solicitação (12:00 > 11:00), a condição é falsa e o atraso/divergência é ignorado silenciosamente.
2. **Cálculo de `horarios_deslig` cego a etapas prévias**:
   O cálculo de `horarios_deslig` exige que a etapa contenha a palavra `"DESLIGAMENTO"` no título (linha 2137). O equipamento da solicitação `24 - 198574` foi aberto com `MA31` na **Etapa 20 (11:00)** e não consta na Etapa 30, resultando em `horarios_deslig = []` e contornando a checagem de início para este equipamento.
3. **Ausência de Validação do Cabeçalho Global da Etapa de Desligamento**:
   Não há validação direta entre o horário do cabeçalho da etapa `DESLIGAMENTO` e o campo `Data Início` da solicitação.

## 3. Análise de Impacto nas Demais Regras
- **Regra 26**: Passará a alertar/acusar divergência quando o início do desligamento for postergado (`ini > sol_ini`), garantindo alinhamento exato entre a autorização e a execução da manobra.
- **Regra 25 (Variação de horários)**: Inalterada.
- **Regras 42 e 02 (Abertura até desligamento)**: Inalteradas, pois utilizam `_obter_limite_pre_desligamento`.
- **Regras 44, 45, 46**: Inalteradas (sem relação com cronograma de solicitação).

## 4. Solução Proposta (Aguardando Autorização)
1. **Validação Bidirecional na Regra 26**:
   Acusar `Início postergado / divergente ({ini_man_real.strftime('%H:%M')}) vs Autorizado ({lim_ini.strftime('%H:%M')})` quando `ini_man_ref > sol_ini_ref`.
2. **Checagem de Desligamento Global**:
   Validar o cabeçalho da etapa `DESLIGAMENTO` diretamente contra `dt_sol_ini`. Se divergir, emitir apontamento na Regra 26.
3. **Considerar Aberturas de Delimitação**:
   Para equipamentos listados nos `Locais de Interrupção`, considerar como início operativo a primeira etapa de abertura com `MA01`/`MA31` caso ocorra antes da etapa formal de desligamento.
