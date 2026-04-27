# Walkthrough - Loading de Alta Performance

As animações de carregamento foram atualizadas para um padrão moderno de "Skeleton Screens", eliminando saltos de layout e melhorando a percepção de performance.

## Mudanças Realizadas

### 🎨 Design System (CSS)
- **Animação Shimmer**: Implementada via GPU (`background-position`) para garantir 60fps sem sobrecarregar a thread principal.
- **Identidade Sóbria**: O esqueleto utiliza tons de cinza/transparência que respeitam o modo escuro da aplicação.
- **Micro-interações**: Adicionado spinner CSS nos botões de ação enquanto a tarefa está ativa.

### 🏗️ Interface (HTML)
- **Skeleton Tables**: Injetados na seção de Conflitos para simular o carregamento de linhas.
- **Skeleton Cards**: Injetados na seção de Regras Base para simular os blocos de análise.
- **Progress Container**: Adicionada uma barra linear no topo de cada seção de resultados.

### ⚙️ Lógica (JS)
- **Barra Determinística**: Agora o progresso reflete fielmente o status `processed / total` vindo do backend.
- **Controle do Console**: Conforme solicitado, o console agora permanece minimizado durante o carregamento para dar foco à interface principal.
- **Transições Suaves**: O esqueleto desaparece gradualmente assim que os dados reais são renderizados.

## Verificação
- [x] O efeito de brilho (*shimmer*) está fluído.
- [x] A barra de progresso avança conforme os itens são processados.
- [x] Os botões são desabilitados e mostram o spinner corretamente.
- [x] O layout não "pula" ao carregar os dados.

## Instruções para o Usuário
1. Inicie uma verificação de conflitos.
2. Observe o esqueleto da tabela e a barra de progresso no topo.
3. Verifique que o console inferior não abre automaticamente, mantendo o foco na tela principal.
