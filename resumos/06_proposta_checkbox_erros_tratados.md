# Proposta de Melhoria: CheckBox de Divergência Tratada na Interface Web

## 1. Demanda do Usuário
Possibilitar que o técnico marque um CheckBox de "Verificado/Tratado" na frente de cada erro ou alerta apontado pelo conferidor, riscando visualmente o item como resolvido para auxílio no fluxo de trabalho.

## 2. Diagnóstico Técnico da Interface
Os relatórios de manobra são gerados dinamicamente no frontend via `src/api/static/js/app.js` (`renderConferidorResults` e `analyzeManobraBlock`).
Se o checkbox for inserido como mero elemento HTML sem controle de estado:
1. Durante o ciclo de polling (`pollConferidor`), qualquer nova chegada de logs aciona `renderConferidorResults`, recriando o DOM e desmarcando todas as caixas.
2. O contador de divergências no topo (`#cm-summary-dash`) e os badges de status continuarão indicando falha crítica, divergindo visualmente dos itens riscados.

## 3. Solução Proposta

### No Frontend (`src/api/static/js/app.js` e `src/api/static/css/style.css`):
1. **Identificador Único e Persistência**:
   - Cada linha de erro/alerta recebe uma chave única baseada no número da manobra e hash do texto da regra: `cm_chk_${manobra}_${hash}`.
   - O estado do checkbox é salvo em `localStorage`.
2. **Estilização Visual**:
   - Checkbox estilizado com `accent-color: var(--accent)`.
   - Ao marcar, aplica estilo `.rule-item-treated` com `text-decoration: line-through; opacity: 0.5;`.
   - Badge dinâmico de `Tratado` vs `Pendente`.
3. **Contador no Painel**:
   - Atualização do painel para exibir divergências pendentes vs tratadas.
4. **Preservação em Re-render**:
   - No ciclo de atualização do polling, a função `analyzeManobraBlock` consulta o `localStorage` para restaurar o estado selecionado pelo usuário sem perder o histórico.

## 4. Análise de Impacto
- **Regras do Conferidor (`src/core/conferidor_manobras.py`)**: Impacto zero. A lógica de backend e a extração do GDIS permanecem 100% inalteradas.
- **Suíte de Testes Unitários**: Impacto zero.
- **Performance Web**: Custo desprezível de leitura/escrita síncrona em `localStorage`.
