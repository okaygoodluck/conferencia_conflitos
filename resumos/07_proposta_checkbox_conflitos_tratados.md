# Proposta de Melhoria: CheckBox de Conflito Tratado na Interface Web

## 1. Demanda do Usuário
Aplicar o mecanismo de CheckBox de "Verificado/Tratado" na listagem de conflitos identificados pelo Verificador de Conflitos, permitindo riscar visualmente o conflito como resolvido/tratado pelo técnico.

## 2. Diagnóstico Técnico da Interface
Diferente do Conferidor de Manobras (que renderiza listas verticais em blocos de regras), o Verificador de Conflitos exibe os resultados em estrutura tabular (`<table>` dentro de sanfona por Manobra Base e na tabela consolidada `conf-table-real`):
- Inserir um checkbox flex inline solto como no conferidor quebraria o alinhamento das colunas.
- Os conflitos podem ser externos (Manobra Base vs Manobra GDIS) ou internos (Lote Interno: Origem vs Destino). Portanto, a chave determinística no `localStorage` deve suportar ambos os formatos: `conf_chk_${base}_${alvo}_${tipo}`.

## 3. Solução Proposta

### No Frontend (`src/api/static/js/app.js` e `src/api/templates/index.html`):
1. **Identificador Determinístico e Persistência**:
   - Criação da função `getConflictItemKey(base, alvo, tipo)` para gerar chaves únicas e estáveis no `localStorage`.
2. **Coluna Dedicada nas Tabelas de Conflito**:
   - Adição da coluna de cabeçalho `Tratar` e `Status` na tabela de conflitos por sanfona e na tabela consolidada.
   - Checkbox com `accent-color: var(--accent)`.
3. **Efeito Visual**:
   - Ao marcar, aplica estilo na linha `<tr>` (`opacity: 0.55;`) e texto tachado no número da manobra conflitante (`text-decoration: line-through;`).
   - Tag de status comutando entre `Tratado` e `Pendente`.
4. **Preservação**:
   - Ao carregar os resultados da consulta (`showConfResults`), consulta o `localStorage` para restaurar o estado marcado.

## 4. Análise de Impacto
- **Motor de Conflitos (`src/core/verificador_conflitos.py`)**: Impacto zero.
- **Backend / APIs**: Impacto zero.
- **Conferidor de Manobras**: Impacto zero (isolado).
