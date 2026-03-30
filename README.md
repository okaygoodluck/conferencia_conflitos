# Verificador de Conflitos de Manobras (GDIS PM)

Aplicação local para verificar conflitos entre uma manobra base e todas as manobras **ELABORADAS (EB)** e **ENVIADAS PARA O CONDIS (EN)** em um período.

O verificador identifica conflito quando existe interseção por:
- Equipamentos
- Alimentadores/Subestações (somente códigos completos, ex.: `CMN004`; ignora `CMN`)

## Novidades (Março 2026)
- **Regra 22 (Inversão MA77/MA36):** Lógica específica para Reguladores de Tensão (RTs).
- **Cache Local:** Fallback automático para a pasta `%TEMP%` em caso de falha de permissão na rede.
- **Limpeza Deep:** Limpeza automática de resíduos de scripts JSF no scraper.
- **Regra 24:** Validação rigorosa de recursos (CI, EQUIPES, GMT, GBT, MJ, LV, DI).

## Como usar
1) Execute `iniciar_verificador_regras.bat`
2) O sistema abrirá em `http://127.0.0.1:8766/`
3) Informe a manobra e as credenciais.

## Estrutura do Projeto
- `src/core`: Lógica de verificação e regras.
- `src/api`: APIs locais (Flask).
- `src/integration`: Extratores de dados (HTTP/Playwright).
