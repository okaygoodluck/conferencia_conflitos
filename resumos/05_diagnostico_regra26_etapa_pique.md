# Diagnóstico e Implementação: Regra 26 (Etapa de Pique vs Desligamento na Manobra 246263155)

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

## 3. Implementação Realizada

### `src/core/conferidor_manobras.py`
Ajustada a linha 2161 para isolar a coleta de horários de desligamento estritamente a etapas que contenham `DESLIGAMENTO` e não contenham `PIQUE`:
```python
if "DESLIGAMENTO" in etapa_full and "PIQUE" not in etapa_full:
    horarios_deslig.append(dt_obj)
```

### `tests/unit/test_regra26_cronograma.py`
1. Atualizada a função auxiliar `simular_regra_26` com a condição restrita `if "DESLIGAMENTO" in etapa_full and "PIQUE" not in etapa_full:`.
2. Adicionado o teste `test_regra26_cenario_manobra_246263155_pique` reproduzindo com exatidão a manobra `246263155` (Etapa 20 às 10:00, Etapa 30 às 11:00, Solicitação às 11:00) e comprovando que a Regra 26 é aprovada sem apontamentos.

## 4. Resultados dos Testes
- Suíte `test_regra26_cronograma.py`: 7/7 aprovados via `pytest`.
- Suíte unitária global: 48/48 testes aprovados (`Ran 48 tests in 0.244s - OK`).
- Linter: `ruff check` 100% aprovado sem pendências.
