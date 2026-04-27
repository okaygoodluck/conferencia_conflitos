# Guia do Usuário: Regras de Verificação de Manobras

Este documento explica a essência das regras automáticas que garantem a segurança e a precisão no planejamento. Cada regra agora inclui as **Macros** relacionadas e **Exemplos** de aplicação.

---

### 🛡️ Fase 1: Integridade da Manobra

#### Regra 21 (Placeholder)
Evita o uso de textos genéricos como "AAA" nos campos de equipamento. Toda manobra deve ser específica.
*   **Macros:** Todas as ações.
*   **Exemplo ❌:** Item 'AAA' (Equipamento incompleto).
*   **Exemplo ✅:** Item '28-12345' (Equipamento identificado).

#### Regra 28 (Duplicidades)
Garante que você não pediu para realizar a mesma ação duas vezes no mesmo equipamento na mesma etapa.
*   **Macros:** Todas as ações.
*   **Exemplo ❌:** Etapa 1: MA01 e MA01 no mesmo religador.
*   **Exemplo ✅:** Etapa 1: MA01 no religador A e MA01 no religador B.

#### Regra 24 (Cabeçalho da 1ª Etapa)
Verifica se a primeira etapa contém as siglas obrigatórias (CI) e se todas as siglas presentes (EQUIPES, GMT, GBT, MJ, LV, DI) estão acompanhadas de suas quantidades numéricas (ex: CI:10).
*   **Macros:** Cabeçalho da Etapa 1.
*   **Exemplo ❌:** "CI: EQUIPES:1" (Falta quantidade em CI).
*   **Exemplo ✅:** "CI:10 EQUIPES:1 GMT:1 MJ:0".

#### Regra 25 (Variação de Horário)
Alerta se todas as etapas tiverem exatamente o mesmo horário, o que pode indicar que o cronograma ainda não foi ajustado.
*   **Macros:** Data/Hora da etapa.
*   **Exemplo ❌:** 10:00, 10:00, 10:00 (Para todas as etapas).
*   **Exemplo ✅:** 08:00, 08:15, 09:30 (Fluxo temporal lógico).

#### Regra 20 (Observação Obrigatória)
Certas ações, como Troca de Elo Fusível, exigem que você escreva detalhes no campo de observação.
*   **Macros:** MA63 (Troca de Fusível), MA77 (Troca de Lâmina).
*   **Exemplo ❌:** MA63 sem texto na observação.
*   **Exemplo ✅:** MA63 com obs: "Substituído Fusível 20K por 30K".

---

### 📋 Fase 2: Autorização e Planejamento

#### Regra 26 (Datas e Horários)
Garante que o Desligamento e o Religamento batem exatamente com o período Inicio e Termino autorizado na Solicitação.
*   **Macros:** MA01, MA02, MA31, MA66, MA30, MA67 (Ações que impactam a rede).
*   **Exemplo ❌:** Desligamento às 07:00 quando a solicitação determina início às 08:00.
*   **Exemplo ✅:** Desligamento às 08:00 quando a solicitação determina início às 08:00.

#### Regra 5 (Bloqueio de RA)
Se a solicitação exige bloqueio de Religador Automático, o sistema confere se as instruções de bloqueio estão na manobra.
*   **Macros:** MA52, MA14, MA28 (Bloqueios de Religamento).
*   **Exemplo ❌:** Solicitação pede RA Bloqueada, mas manobra não tem MA52.
*   **Exemplo ✅:** Presença de MA52 logo no início da intervenção.

#### Regra 23 (Uso de Gerador)
Se for usar gerador, a primeira etapa deve declarar explicitamente o código GMT: ou GBT:.
*   **Macros:** GMT:, GBT: (No cabeçalho).
*   **Exemplo ❌:** Uso de cabos de gerador sem código GMT na etapa 1.
*   **Exemplo ✅:** "EQUIPES:1 GMT:1" no cabeçalho.

#### Regra 27 (Executor Correto)
Garante que o responsável pela etapa é o adequado (ex: etapas de Religamento devem ser feitas pelo Supervisor).
*   **Macros:** Campo 'Executor'.
*   **Exemplo ❌:** Etapa de Religamento feita por 'Tecnico' (Exige Supervisor).
*   **Exemplo ✅:** Religamento executado por 'Supervisor'.

#### Regra 29 (Intervenção Extensa)
Se um alimentador estiver envolvido na manobra, o Centro de Operação (COD) deve fazer uma conferência especial (MA09).
*   **Macros:** MA09 (Verificação pelo COD).
*   **Exemplo ❌:** Manobra no alimentador sem a etapa técnica MA09.
*   **Exemplo ✅:** Inclusão da ação MA09 na etapa de verificação.

---

### 🔍 Fase 3: Identidade do Equipamento

#### Regra 1 (Presença)
Confirma se todos os equipamentos que você planejou desligar na solicitação estão realmente sendo operados na manobra.
*   **Exemplo ❌:** Solicitação pede desligar 'Chave A', mas manobra só opera 'Chave B'.

#### Regra 3 (Alimentador) e Regra 4 (Local)
Verifica se o alimentador e o local físico do equipamento na solicitação são os mesmos que constam na manobra.
*   **Exemplo ❌:** Equipamento da SE ABC planejado na manobra como SE XYZ.

---

### ⚙️ Fase 4: Restrições Técnicas (Engenharia)

#### Regra 6 (Tipo de Equipamento)
Impede ações impossíveis (ex: tentar bloquear ST de um transformador como se fosse um Religador).
*   **Exemplo ❌:** Tentar usar MA15 (Bloqueio) em um Transformador (Prefixo 01).
*   **Exemplo ✅:** Usar MA15 em um Religador (Prefixo 22).

#### Regra 7 (Modo Local) e Regra 34 (MAB9)
Equipamentos com controle remoto precisam ser colocados em "Modo Local" (MA64) se presentes na solicitação, e a macro MAB9 (Checar Tele) é restrita a tipos específicos.
*   **Macros:** MA64, MAB9.
*   **Exemplo ❌:** Usar MAB9 em uma Chave Manual (Prefixo 28).
*   **Exemplo ✅:** Usar MAB9 em um Religador Automático (Prefixo 22).

#### Regra 31 (Estado do Equipamento)
Cruza a base de dados com a manobra. Se o equipamento já é "Normal Aberto", a manobra não pode começar pedindo para "Abrir".
*   **Exemplo ❌:** Abrir (MA01) um equipamento que já possui POSOPE=A (Aberto).

#### Regra 10 (Bloqueio de RA e Chave Deslocada)
Uso de bloqueio de RA para chaves e as que exigem a observação específica "CHAVE DESLOCADA".
*   **Macros:** MA52, MA14.
*   **Exemplo ❌:** Bloquear RA de chave manual sem a Obs "CHAVE DESLOCADA".

#### Regra 12 (Segurança de Operação)
Operações manuais em equipamentos automáticos exigem que a equipe confirme o "Posicionamento" (presença no local).
*   **Exemplo ❌:** Equipe de campo operando religador remoto sem marcar "Posicionamento: Sim".

---

### ⏳ Fase 5: Balanço e Cronologia

#### Regra 22 (Ações Esquecidas / Inversas)
A regra de ouro — se você abriu, bloqueou ou aterrou algo, a manobra deve ter a etapa correspondente para fechar ao final.
*   **Macros:** MA01/MA02 (Abrir/Fechar), MA15/MA17 (Bloquear/Desbloquear).
*   **Inversão Especial (RT):** Em Reguladores de Tensão (02), a macro **MA77** (Fixar Tap) deve ser invertida pela **MA36** (Ligar Caixa de Comando). Para os demais, MA77 é invertida por MA78.
*   **Exemplo ❌:** Equipamento Aberto na Etapa 2 e nunca Fechado no final.
*   **Exemplo ✅:** Abrir (Etapa 2) -> Intervenção -> Fechar (Retorno).

#### Regra 30 (Ordem Lógica)
Garante que a sequência faz sentido (ex: você não pode desbloquear um equipamento que não foi bloqueado anteriormente).
*   **Exemplo ❌:** Desbloquear (MA17) antes de ter Bloqueado (MA15).

#### Regra 32 (Incompatibilidade de Fases)
Bloqueia abrir trifásico e fechar monofásico na mesma etapa e alimentador.
*   **Exemplo ❌:** Abrir religador Trifásico e fechar chaves Monofásicas simultaneamente.

#### Regra 33 (Chave ASTA)
Exige a indicação "COM CARGA" para abertura de chaves ASTA.
*   **Macros:** MA30.
*   **Exemplo ❌:** MA30 (Abertura em carga) sem o texto "COM CARGA".

---
© 2026 - Central de Inteligência de Planejamento - GDIS
