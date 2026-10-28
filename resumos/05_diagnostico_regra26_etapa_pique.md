# Diagnóstico e Solução Proposta: Regra 26 (Etapa de Pique vs Desligamento na Manobra 246263155)

## 1. Problema Apontado
Na manobra `246263155`, o conferidor apontou erro indevido de cronograma:
```text
REGRA 26 []: Equipamento '22 - 359169': Divergência no cronograma (Início antecipado (10:00) vs Autorizado (11:00)). Ajuste o horário da etapa.
```
- **Solicitação**: Início `09/10/2026 11:00` | Término `09/10/2026 15:30`
- **Manobra**:
  - `Etapa 20: MANOBRA COM PIQUE CP:131 - DADOS BTZD206 09/10/2026 10:00`
  - `Etapa 30: DESLIGAMENTO BTZD206 09/10/2026 11:00`
  - `Etapa 40: RELIGAMENTO BTZD206 09/10/2026 15:30`
  - `Etapa 50: MANOBRA COM PIQUE CP:131 - DADOS BTZD206 09/10/2026 15:30`

## 2. Causa Raiz Identificada no Código (`src/core/conferidor_manobras.py`)
No commit anterior (`1ee9f83`), na tentativa de capturar aberturas antecipadas de equipamentos da solicitação, foi adicionada a seguinte condição na linha 2161:
```python
if "DESLIGAMENTO" in etapa_full or info_sol and any(re.search(r'\b\d*' + m + r'\b', mi.get('texto_linha', ''), re.IGNORECASE) for m in ["MA01", "MA31", "MA30"]):
    horarios_deslig.append(dt_obj)
```
Como o equipamento `22 - 359169` consta na solicitação (`info_sol`) e foi aberto com `MA01` na **Etapa 20 (MANOBRA COM PIQUE)** às 10:00 para transferência transitória de carga sob pique, o horário das 10:00 foi incorporado indevidamente a `horarios_deslig`.
Com isso, o conferidor considerou que o desligamento da obra começou às 10:00, acusando falso positivo de início antecipado em relação às 11:00 autorizadas.

## 3. Análise de Impacto nas Demais Regras
- **Regra 26**: 
  - Restringe `horarios_deslig` exclusivamente a etapas de `DESLIGAMENTO` (garantindo que `"PIQUE" not in etapa_full`), eliminando falsos positivos gerados por manobras transitórias de transferência de carga e alívio preliminar.
  - Mantém a validação bidirecional (`ini_man_ref < sol_ini_ref` e `ini_man_ref > sol_ini_ref`) e a validação do cabeçalho global da etapa de desligamento, assegurando que desvios reais (como o atraso das 12:00 vs 11:00 da manobra `245738775`) continuem sendo barrados.
- **Regra 44 (Manobra com Pique)**: Impacto zero. A Regra 44 continuará validando independentemente os cabeçalhos CP:xx, as macros de comunicação MA79 e as sequências de abertura/fechamento em etapas de pique.
- **Regra 43 (Supervisor em Desligamento/Religamento)**: Impacto zero. Mantém verificação exclusiva do executor nas etapas de Desligamento/Religamento.
- **Regras 02, 12, 22, 30 e 31**: Impacto zero. Nenhuma destas regras consome a lista `horarios_deslig`.

## 4. Solução Proposta
Ajustar a linha 2161 de `src/core/conferidor_manobras.py` para isolar a coleta de horários de desligamento estritamente a etapas que contenham `DESLIGAMENTO` e não sejam etapas de `PIQUE`:
```python
if "DESLIGAMENTO" in etapa_full and "PIQUE" not in etapa_full:
    horarios_deslig.append(dt_obj)
```
Adicionar teste unitário cobrindo o cenário da manobra `246263155` em `tests/unit/test_regra26_cronograma.py`.
