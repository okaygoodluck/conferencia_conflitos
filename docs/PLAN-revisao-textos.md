# Plano de Ação: Revisão e Humanização de Mensagens (Conferidor)

Este documento descreve a padronização das mensagens de saída do Conferidor de Manobras para torná-las mais claras, acionáveis e visualmente organizadas para o usuário final.

## 🎯 Objetivos
1. **Clareza Imediata**: O usuário deve entender o problema sem precisar consultar o manual de regras.
2. **Tom Acionável**: Sugerir o que deve ser verificado ou corrigido.
3. **Padronização Visual**: Uso de cores e etiquetas de nível (ERRO, ALERTA, OK).

## 📐 Novo Padrão de Mensagens
Todas as regras seguirão o formato:
`[EMOJI] REGRA [XX] [[NÍVEL]]: [MENSAGEM]`

| Nível | Emoji | Cor ANSI (Terminal) | Descrição |
|-------|-------|---------------------|-----------|
| **ERRO** | 🔴 | Vermelho (\033[91m) | Falha crítica que impede a execução segura. |
| **ALERTA**| 🟡 | Amarelo (\033[93m) | Inconsistência ou ponto de atenção que requer análise humana. |
| **OK** | 🟢 | Verde (\033[92m) | Validação concluída com sucesso. |
| **INFO** | 🔵 | Azul (\033[94m) | Informação contextual ou regra ignorada justificadamente. |

---

## 📋 Lista de Revisão por Regra

### Fase 1: Identidade e Contexto
- **REGRA 1 (Presença)**: 
  - *De*: "FALHA (Equipamento da Solicitação 'X' NÃO ESTÁ na Manobra)."
  - *Para*: "🔴 REGRA 01 [ERRO]: Equipamento 'X' da solicitação não encontrado na manobra. Verifique se houve erro de digitação ou se o item foi omitido."
- **REGRA 3 (Alimentador)** e **REGRA 4 (Local)**:
  - Seguir o mesmo padrão de comparação clara (Esperado vs. Encontrado).

### Fase 2: Regras de Engenharia e Macros
- **REGRA 5 (Bloqueio de RA)**: 
  - *De*: "FALHA (Exige RA na Solicitação...)"
  - *Para*: "🔴 REGRA 05 [ERRO]: Solicitação exige Bloqueio de RA, mas macros MA52/MA14/MA28 estão ausentes. Verifique a segurança do desligamento."
- **REGRA 6 (Incompatibilidade)**: 
  - *Para*: "🔴 REGRA 06 [ERRO]: O equipamento 'X' possui ações proibidas para seu prefixo: {acoes}. Revise as macros utilizadas."

### Fase 3: Regras de Executor e Prazos (Novas)
- **REGRA 27 (Executor D/R)**:
  - *Para*: "🟡 REGRA 27 [ALERTA]: Executor '{exec}' encontrado em etapa de Desligamento/Religamento. O padrão exige 'Supervisor'."
- **REGRA 42 (Sinalização)**:
  - *Para*: "🔴 REGRA 42 [ERRO]: Equipamento 'X' foi aberto, mas não foi sinalizado (MA06) até a etapa de Desligamento."

---

## 🛠️ Cronograma de Implementação

1. **Refatoração dos Prints (Linhas 1100-1450)**: Atualizar as strings de todas as 42 regras no arquivo `src/core/conferidor_manobras.py`.
2. **Integração de Cores**: Implementar uma classe simples `Colors` para gerenciar os códigos ANSI e facilitar a manutenção.
3. **Validação Final**: Executar uma manobra real e capturar o print para aprovação do usuário.

> [!NOTE]
> O código da regra (ex: REGRA 01) sempre virá no início para facilitar a busca rápida no manual técnico, mas a descrição será expandida.
