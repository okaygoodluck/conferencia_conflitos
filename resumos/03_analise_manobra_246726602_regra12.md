# Análise: Manobra 246726602 (Regra 12 - Posicionamento na Macro MA66)

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

## 3. Conclusão
O apontamento do Conferidor é **correto e legítimo**. Não se trata de falso positivo. A macro `MA66` (Etapa 90, Item 4) está com `Pos: Não`.

## 4. Melhoria Proposta de Usabilidade (Aguardando Autorização)
Na Regra 12 de `src/core/conferidor_manobras.py`, incluir o nome da etapa e/ou linha na mensagem de erro para evitar que o operador confunda operações de abertura (Etapa 20) com operações de fechamento (Etapa 90) no mesmo equipamento:
- *Formato atual*: `Equipamento '28 - 89080': Operação pela Região (MA66) exige marcar 'SIM' na coluna Posicionamento.`
- *Formato aprimorado*: `Etapa '90' - Equipamento '28 - 89080': Operação pela Região (MA66) exige marcar 'SIM' na coluna Posicionamento.`
