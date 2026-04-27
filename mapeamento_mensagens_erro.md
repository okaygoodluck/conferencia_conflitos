# Mapeamento de Mensagens de Erro (FALHAS e ALERTAS)

Este documento lista os textos exatos disparados pelo sistema para cada regra. Use este guia para avaliar se as mensagens estão claras ou se precisam de ajustes de redação.

---

### 🛡️ Fase 1: Integridade e Sintaxe
| Regra | Tipo | Texto Base da Mensagem |
| :--- | :--- | :--- |
| **20** | ❌ FALHA | `Exigem preenchimento do campo Observação "Lamina ou Fusível?": [Macros MA63/MA77] em '[Equipamento]'` |
| **21** | ❌ FALHA | `Utilização do placeholder genérico 'AAA' detectada em Item '[Equipamento]'` |
| **24** | ❌ FALHA | `Codigo obrigatório '[Sigla]' não encontrado na primeira etapa.` |
| **24** | ❌ FALHA | `O Codigo '[Sigla]' está presente mas falta informar a quantidade (Ex: [Sigla]:1).` |
| **24** | ⚠️ ALERTA | `Foi escrito 'EQUIPE:' (singular). O padrão é 'EQUIPES:' no cabeçalho.` |
| **25** | ⚠️ ALERTA | `Todas as etapas possuem o mesmo horário ou horários incompatíveis: [HH:MM]'.` |
| **28** | ❌ FALHA | `Etapa '[Nome]': [Macro] duplicada no '[Equipamento]'` |

---

### 📋 Fase 2: Autorização e Planejamento
| Regra | Tipo | Texto Base da Mensagem |
| :--- | :--- | :--- |
| **5** | ❌ FALHA | `Exige RA na Solicitação, mas a Manobra NÃO possui macro MA52, MA14 ou MA28.` |
| **23** | ⚠️ ALERTA | `[Citação de gerador], mas a primeira etapa não declarou 'GMT:' ou 'GBT:'.` |
| **26** | ❌ FALHA | `Equipamento '[Eq]': Horário da Manobra diverge com o da Solicitação. Início antecipado ([HH:MM]) / Término tardio ([HH:MM]).` |
| **26** | ❌ FALHA | `Equipamento '[Eq]': Sem data autorizada na solicitação.` |
| **27** | ⚠️ ALERTA | `'[Etapa]' exige '[Supervisor/Técnico]' (encontrado: '[Executor]')` |
| **29** | ❌ FALHA | `Alimentador '[Alim]' presente na manobra, mas falta ação MA09 vinculada a ele na Verificação pelo COD.` |
| **29** | ❌ FALHA | `Detectado Alimentador em manobra sem ação MA09 na Verificação pelo COD.` |

---

### 🔍 Fase 3: Identidade do Equipamento
| Regra | Tipo | Texto Base da Mensagem |
| :--- | :--- | :--- |
| **1** | ❌ FALHA | `Equipamento da Solicitação '[Eq]' NÃO ESTÁ na Manobra.` |
| **3** | ❌ FALHA | `Equipamento '[Eq]' com Alimentador divergente. Esperado: [Alim], Encontrado: [Alims].` |
| **4** | ❌ FALHA | `Equipamento '[Eq]' com Local divergente. Esperado: [Local], Encontrado: [Locais].` |

---

### ⚙️ Fase 4: Restrições Técnicas (Engenharia)
| Regra | Tipo | Texto Base da Mensagem |
| :--- | :--- | :--- |
| **6** | ❌ FALHA | `Equipamento '[Eq]' possui ações incompatíveis: '[Macros]'.` |
| **7** | ❌ FALHA | `Equipamento '[Eq]' é telecontrolado, mas NÃO possui a macro MA64 na manobra.` |
| **8** | ❌ FALHA | `As ([Macros]) so podem ser aplicadas em RT: '[Eq]' não é RT.` |
| **9** | ❌ FALHA | `Macros ([Macros]) aplicadas para Religador/Disjuntor: '[Eq]' inválido.` |
| **10** | ❌ FALHA | `Macros ([Macros]) invalida para '[Eq]'. [Permitido apenas 01/04 / Alguns necessitam da Obs "Chave Deslocada"].` |
| **11** | ❌ FALHA | `Macros ([Macros]) aplicadas em equipamento inválido: '[Eq]'. Permitido apenas 21/22/23.` |
| **12** | ❌ FALHA | `Executor 'Região' operando equipamento telecontrolado '[Eq]' ([Macros]) está sem 'Posicionamento'.` |
| **13** | ⚠️ ALERTA | `Executor 'Região' executando MA01 sem 'CORTE DE CARGA'. A equipe está abrindo sem sinalizar!` |
| **14** | ❌ FALHA | `Equipamento '[Eq]': Executor 'COD' não pode ter 'Posicionamento'.` |
| **15** | ❌ FALHA | `Equipamento '[Eq]': COD executando ([Macros]) irregularmente. Motivo: [Motivo Técnico].` |
| **16** | ❌ FALHA | `Equipamento '[Eq]': Etapa 'VERIFICACAO PELO COD' possui executor inválido: '[Nome]'. Apenas COD é aceito.` |
| **17** | ❌ FALHA | `Macro MA09 aplicada em equipamento '[Eq]'. Só deve ser executada para o Alimentador.` |
| **18** | ❌ FALHA | `Comandos de by-pass ([Macros]) no equipamento '[Eq]'. Permitido apenas em prefixos 02, 03, 22, 23.` |
| **19** | ❌ FALHA | `Macro MAC1 aplicada em Alimentador '[Alim]'. Exige equipamento físico na rede.` |
| **31** | ❌ FALHA | `Equipamento '[Eq]': Equipamento é NA, Abrindo equipamento NA).` |
| **33** | ❌ FALHA | `Chave ASTA '[Eq]' operada sem a indicação 'COM CARGA'.` |

---

### ⏳ Fase 5: Balanço e Cronologia
| Regra | Tipo | Texto Base da Mensagem |
| :--- | :--- | :--- |
| **2** | ⚠️ ALERTA | `Equipamento '[Eq]' está na manobra, mas não detectamos ação de Abrir ou Sinalizar.` |
| **22** | ❌ FALHA | `Ações precisam de sua inversão, '[Eq]': [Grupo de Ações Ex: Rede BT (MA56/MA57)].` |
| **22** | ❌ FALHA | `Cronologia MA15/MA17 em '[Eq]': [Divergência antes/depois do Desligamento].` |
| **30** | ❌ FALHA | `Ordem cronológica invertida no equipamento '[Eq]': '[Macro]' sem '[Ação]' prévio.` |
| **32** | ❌ FALHA | `Etapa '[Etapa]' | Alim [Alim]: Abrindo Trifásico ([Eq]) e Fechando Monofásico ([Eq]) na mesma etapa.`|

---
© 2026 - Central de Mensagens de Erro - GDIS
