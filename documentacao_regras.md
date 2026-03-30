# documentacao_regras.md
# Documentação das Regras de Verificação de Manobra

## Regra 22: Inversão de Manobras
Verifica se todas as ações que possuem um estado oposto (inversão) estão devidamente documentadas na solicitação.

**Caso Especial: Reguladores de Tensão (RTs) - Prefixo 02**
- Para RTs, a macro `MA77` (FIXAR TAP DO REGULADOR E DESLIGAR CX DE COMANDO) deve ser obrigatoriamente invertida pela macro `MA36` (LIGAR CAIXA DE COMANDO E COLOCAR RT EM SERVICO).

**Para os demais equipamentos:**
- A macro `MA77` deve ser invertida pela macro `MA78` (BLOQUEAR SEGUNDO RELE DE NEUTRO E SINALIZAR).

---

## Regra 24: Cabeçalho de Recursos
Valida a presença e a quantidade dos recursos informados no cabeçalho da manobra.
Siglas obrigatórias: `CI`, `EQUIPES`, `GMT`, `GBT`, `MJ`, `LV`, `DI`.

- **Falha:** Sigla informada sem valor numérico (ex: `CI:`).
- **Alerta:** Sigla não encontrada no texto do cabeçalho.
- **Aviso:** Quantidade informada como 0.

---

## Regra 32: Integridade de Texto (Playwright)
O verificador realiza a limpeza automática de resíduos de scripts JavaServer Faces (JSF) para garantir que as mensagens de erro não contenham códigos técnicos como `SimpleTogglePanelManager`.
