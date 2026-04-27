# PLAN-loading-performance.md - Estratégias de Loading de Alta Performance

Este plano detalha a implementação de animações de carregamento otimizadas para o Conferidor de Conflitos e de Manobras, focando em performance (CSS-only) e experiência do usuário (Skeleton Screens).

## 1. Objetivos
- Substituir o feedback puramente textual por estados visuais de "Skeleton Screen".
- Implementar uma barra de progresso determinística baseada nos dados de processamento.
- Manuzear o console de forma discreta durante o carregamento.
- Garantir 60fps utilizando aceleração de hardware (transform/opacity).

## 2. Arquitetura e Componentes

### 2.1. CSS (style.css)
- **Animação Shimmer**: Criar um keyframe `@keyframes shimmer` para o efeito de brilho sóbrio.
- **Base do Skeleton**: Classes utilitárias para criar blocos cinzas/neutros que pulsam ou brilham.
- **Barra de Progresso**: Um componente linear no topo da área de resultados que utiliza uma variável CSS (`--progress-percent`) para controle dinâmico.
- **Transições de Fade**: Efeito de `opacity` suave na troca do esqueleto pelos dados reais.

### 2.2. JavaScript (app.js)
- **Toggle de Visibilidade**: Funções para alternar entre `skeleton-state` e `result-state`.
- **Controle de Progresso**: Atualizar a variável CSS `--progress-percent` durante o polling do backend (`pollConf` / `pollReg`).
- **Ajuste de Console**: Modificar a lógica de `startConflitos` e `startRegras` para que o console não abra automaticamente em tela cheia durante o carregamento inicial.

## 3. Detalhamento das Fases

### Fase 1: Fundamentação Visual (CSS)
- Definir tokens de cores para o esqueleto (sóbrios).
- Criar a animação de gradiente infinito para o efeito shimmer.
- Implementar a estrutura da barra de progresso linear.

### Fase 2: Templates de Esqueleto
- **Tabela de Conflitos**: Criar um mock visual da tabela com 5-10 linhas de esqueleto.
- **Relatório de Regras**: Criar um esqueleto que simule os cards de fase.

### Fase 3: Integração Lógica
- Atualizar `startConflitos` para injetar/mostrar o esqueleto.
- Atualizar `pollConf` para calcular a porcentagem e atualizar a barra de progresso.
- Garantir que `showConfResults` e `renderRegResults` removam o esqueleto com um fade suave.

### Fase 4: Polimento e UX
- Desabilitar botões com micro-animação interna (spinner CSS).
- Garantir que o console permaneça minimizado conforme solicitado.

## 4. Checklist de Verificação
- [ ] O shimmer roda sem causar picos de uso de CPU (GPU accelerated).
- [ ] A barra de progresso reflete fielmente o `processed / total`.
- [ ] O console não expande sozinho ao iniciar uma análise.
- [ ] Não ocorre "pulo" de layout (Cumulative Layout Shift) ao trocar o esqueleto pelos dados.
- [ ] O visual do shimmer é neutro e sóbrio.

## 5. Atribuições de Agentes
- **Frontend Specialist**: Implementação de CSS e templates de esqueleto.
- **Orchestrator**: Coordenação da lógica de polling e transição de estados no JS.
