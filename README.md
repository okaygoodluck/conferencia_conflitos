# Verificador de Conflitos de Manobras (GDIS PM)

Hub Unificado para Verificação de Conflitos e Conferência de Manobras entre uma manobra base e todas as manobras **ELABORADAS (EB)** e **ENVIADAS PARA O CONDIS (EN)** em um período.

O verificador identifica conflito quando existe interseção por:
- Equipamentos
- Alimentadores/Subestações (somente códigos completos, ex.: `CMN004`; ignora `CMN`)

## Como usar (UX Web Local)

1) Execute o arquivo `start_local.bat`
2) Abra o navegador em `http://127.0.0.1:8765/` (abre automaticamente)
3) Preencha:
   - Manobra base
   - Data início / data fim
   - Usuário / senha
4) Clique em **Iniciar**
5) Acompanhe o progresso/ETA e exporte CSV ao final

## Critérios de comparação

### Equipamentos
- Comparação por string normalizada completa.
- Ex.: `22 - 55134` é diferente de `28 - 55134`.
- Padronização: espaços e hífens (`\\s*-\\s*` -> ` - `).

### Alimentadores/Subestações
- Padronização: maiúsculo e remove espaços.
- Ex.: `RPA 014` e `RPA014` viram `RPA014`.
- Apenas códigos completos `^[A-Z]{3,6}\\d{2,4}$` entram na comparação.
- Ex.: considera `CMN004`, ignora `CMN`.

## Variáveis de ambiente (opcional)

Veja o exemplo em `.env.example`.

- `GDIS_PORT` (default `8765`): porta do servidor local
- `GDIS_HTTP_TIMEOUT` (default `60`): timeout por requisição HTTP ao GDIS

## Conferidor de Manobras

Analisa o roteiro de uma manobra no GDIS e valida contra um conjunto de ~40 critérios de segurança e engenharia.

## Scripts

**Produção**
- `app_local.py`: servidor local (localhost)
- `verificador_conflitos.py`: motor do verificador de conflitos
- `conferidor_manobras.py`: motor do conferidor de manobras
- `server_conferidor_manobras.py`: servidor backend do conferidor
- `gdis_http_extrator.py`: extrator HTTP/JSF/A4J (sem UI)

**Testes/Legado**
- `gdis_pesquisas.py`
- `gdis_manobra_debug.py`
- `verificador_elaboradas.py`

## Segurança

- Não salvar senha em arquivo.
- Não versionar `.env`.
