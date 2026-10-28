# Análise e Implementação: Manobra 246726602 (Regra 12 - Posicionamento na Macro MA66)

## 1. Problema Relatado
O usuário questionou o apontamento de erro da Regra 12 na Manobra 246726602:
```text
REGRA 12 []: Equipamento '28 - 89080': Operação pela Região (MA66) exige marcar 'SIM' na coluna Posicionamento.
```
Alegação: o item já estaria marcado com 'SIM'.

## 2. Auditoria dos Dados da Manobra
Ao inspecionar os 56 itens da manobra, o equipamento `28 - 89080` sofre duas operações distintas em etapas diferentes:

1. **Etapa 20 (Item 5)**:
   - Texto: `50 MA31 - ABRIR E SINALIZAR EQUIPAMENTO 28 - 89080 ... REGIAO SIM`
   - Posicionamento: `SIM` (Válido).
2. **Etapa 90 (Item 4)**:
   - Texto: `40 MA66 - RETIRAR SINALIZACAO E FECHAR EQUIPAMENTO 28 - 89080 ... REGIAO NÃO`
   - Posicionamento: `NÃO` (Inválido).

O apontamento do Conferidor é **correto e legítimo**. Não se trata de falso positivo. A macro `MA66` (Etapa 90, Item 4) está com `Pos: Não`.

## 3. Implementação da Melhoria de Usabilidade
Para evitar que operadores confundam operações de abertura com operações de fechamento do mesmo equipamento, a Regra 12 foi aprimorada:

### `src/core/conferidor_manobras.py`
- Modularizada a função `validar_regra_12(eq, manobra_items, prefixo="", is_manobra_terceiros=False)` no escopo do módulo.
- A mensagem de erro agora agrupa e referencia explicitamente a etapa correspondente de cada ocorrência:
  - *Exemplo*: `Equipamento '28 - 89080': Operação pela Região em [Etapa '90 MANOBRA COM RISCO SISTEMA PRRU015' (MA66)] exige marcar 'SIM' na coluna Posicionamento.`

### `tests/unit/test_regra_12.py`
- Criado teste unitário `test_regra_12_manobra_246726602_cenario` replicando exatamente o caso da manobra 246726602 e confirmando o apontamento preciso na Etapa 90.
- Criado teste `test_regra_12_valida_quando_todos_posicionados` garantindo status `OK` quando todas as etapas estão com `SIM`.
- Criado teste `test_regra_12_isenta_etapa_pique` confirmando isenção de Posicionamento para etapas com Pique (que utilizam MA27).

## 4. Resultados dos Testes
- Suíte unitária: 48/48 testes aprovados (`Ran 48 tests in 0.233s - OK`).
- Linter: `ruff check` 100% aprovado sem apontamentos.
