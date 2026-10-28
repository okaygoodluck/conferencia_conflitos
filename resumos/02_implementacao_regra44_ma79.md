# Implementação: Correção da Regra 44 (MA79 em Religadores Manuais)

## 1. Escopo da Alteração
Correção de falso positivo na Regra 44 onde qualquer religador (prefixo 22, 19, 20) em etapas de Manobra com Pique era considerado telecontrolado por padrão, gerando exigência indevida da macro `MA79` (Confirmar Equipamento Comunicando) mesmo para religadores manuais operados em campo pela Região.

## 2. Modificações Realizadas

### `src/core/conferidor_manobras.py`
1. **Topologia GDIS (`_consultar_topologia_gdis`)**:
   - Mapeamento explícito de `telecom in ["N", "NAO", "NÃO"]` para definir `telecontrolado = False`, impedindo que religadores sem comunicação permanecessem como `None` e caíssem no fallback de telecontrolado.
2. **Motor de Classificação (`_verificar_telecontrole`)**:
   - Inclusão da macro `MA79` no rol de macros que comprovam telecontrole (`re.search(r'\b\d*(MA64|MA65|MA14|MA15|MA16|MA17|MA52|MA79)\b', txt_mi)`).
   - Rastreamento dos executores da manobra (`todos_executores_regiao`): quando o equipamento é operado exclusivamente por equipes em campo (`REGIAO`, `CAMPO`, `EQUIPE`) sem macros de automação (`MA64`/`MA79`) e sem cadastro de telecontrole no GDIS, o equipamento não é mais inferido cegamente como telecontrolado por prefixo.
3. **Regra 44 (`validar_regra_44`)**:
   - Atualizada assinatura para `validar_regra_44(manobra_dados, dados_equipamentos=None)`.
   - Consulta de dados cadastrais no dicionário de topologia `dados_equipamentos` ao avaliar telecontrole via `_is_eq_telecontrolado`.
   - Restrição da checagem de telecontrole no cabeçalho/etapa estritamente a nomes válidos de equipamentos, sem avaliar nomes de alimentadores como equipamentos.
4. **Chamada Principal (`main`)**:
   - Linha 3441: repassado `dados_equipamentos` para `validar_regra_44(manobra_dados, dados_equipamentos=dados_equipamentos)`.

### `tests/unit/test_regra_44.py`
- Adicionado `test_regra_44_religador_manual_regiao_sem_ma79`: valida etapa de pique com religador manual e chave 28 operados pela Região com `MA27`, comprovando ausência de falso positivo de `MA79`.
- Adicionado `test_regra_44_religador_manual_gdis_sem_ma79`: valida desativação de `MA79` quando a topologia GDIS define `telecontrolado = False`.

## 3. Resultados dos Testes
- Suíte unitária: 45/45 testes aprovados (`Ran 45 tests in 0.212s - OK`).
- Linter: `ruff check` aprovado sem apontamentos.

