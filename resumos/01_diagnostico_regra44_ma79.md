# Diagnóstico e Solução: Regra 44 (Manobra com Pique e Macro MA79 em Religadores)

## 1. Problema Apontado
O Conferidor exige a macro `MA79` (Confirmar Equipamento Comunicando) para qualquer religador presente em etapas de Manobra com Pique, mesmo quando o religador é manual / operado em campo sem módulo de telecontrole.

## 2. Causa Raiz Identificada no Código
1. **Isolamento de Dados na Regra 44**: Em `src/core/conferidor_manobras.py`, a função `validar_regra_44(manobra_dados)` é chamada na linha 3430 sem repassar `dados_equipamentos` (topologia do GDIS). A função avalia o equipamento sem acesso aos atributos reais cadastrados (`telecom`, `r_controle`, `telecontrolado`).
2. **Inferência Padrão por Prefixo**: Na função `_verificar_telecontrole(eq_nome, ...)` (linha 641), a ausência de dados do GDIS ou menção textual explícita aciona o fallback:
   ```python
   return prefixo in ["02", "19", "20", "21", "22", "23"]
   ```
   Dessa forma, qualquer religador (prefixo `22`) é forçado para `telecontrolado = True`.
3. **Exigência de MA79 na Etapa**: Em `validar_regra_44` (linha 735), a presença de qualquer equipamento classificado como telecontrolado na etapa exige a macro `MA79` sob pena de erro de validação.

## 3. Análise de Impacto nas Demais Regras de Conferência

| Regra | Finalidade | Impacto da Alteração | Risco |
|---|---|---|---|
| **Regra 44** (Pique) | Exige MA79 se telecontrolado; MA27 se manual com carga | Elimina falso positivo para religadores manuais. Mantém exigência de MA79 para religadores telecontrolados e passa a validar MA27 para manuais. | Baixo / Correção direta |
| **Regra 07** (Modo Local - MA64) | Exige MA64 para equipamentos telecontrolados antes de intervenção | Benéfico. Evita falso positivo na Regra 7, que também exigia MA64 indevidamente para religadores manuais operados pela Região. | Zero |
| **Regra 15** (Operação COD) | COD só opera equipamentos telecontrolados | Zero impacto. Operações do COD possuem verificação própria (`tem_operacao_cod`), mantendo o equipamento marcado como telecontrolado. | Zero |
| **Regra 13** (Abertura Região) | Exige 'CORTE DE CARGA' ou 'CARGA ALIVIADA' se telecontrolado | Mantém coerência: equipamentos manuais já são isentos na Regra 13. | Zero |
| **Regras 45 / 46** (Paralelismo / RT) | Topologia e cálculo de fluxo em grafo | Nulo. Utilizam topologia física do alimentador e numeração de equipamentos, sem dependência do status de telecontrole. | Zero |

## 4. Solução Técnica Proposta (Aguardando Autorização)
1. Atualizar assinatura de `validar_regra_44(manobra_dados, dados_equipamentos=None)` e chamada na linha 3430 de `conferidor_manobras.py`.
2. Em `validar_regra_44`, passar o registro do equipamento obtido de `dados_equipamentos` para `_verificar_telecontrole`.
3. Ajustar `_verificar_telecontrole`: se o equipamento for prefixo `22`, mas operado exclusivamente pela Região/Equipe em campo, sem macro de telecontrole (MA64, MA79, MA14, etc.) e o cadastro GDIS indicar `telecontrolado == False` (ou não houver telecontrole indicado), classificar como manual (`telecontrolado = False`).
4. Criar teste unitário em `tests/unit/test_regra_44.py` cobrindo etapa de pique com religador manual (sem exigência de MA79).

