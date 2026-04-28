# Verificador de Conflitos de Manobras (GDIS PM)

Hub Unificado para Verificação de Conflitos e Conferência de Manobras entre uma manobra base e todas as manobras **ELABORADAS (EB)** e **ENVIADAS PARA O CONDIS (EN)**.

---

## 📦 Downloads (Versões Prontas)

Para facilitar o acesso, utilize os links abaixo para baixar a versão compilada (não é necessário instalar Python):

[![Download Home Office](https://img.shields.io/badge/Download-Home%20Office%20(Portátil)-green?style=for-the-badge&logo=windows)](https://github.com/okaygoodluck/conferencia_conflitos/releases/latest/download/GDIS_Plataforma_HomeOffice.zip)
[![Download Servidor](https://img.shields.io/badge/Download-Pacote%20Servidor-blue?style=for-the-badge&logo=server)](https://github.com/okaygoodluck/conferencia_conflitos/releases/latest/download/PACOTE_PARA_SERVIDOR.zip)

> **Nota:** Se você baixar o arquivo ZIP direto do botão "Code" do GitHub, você baixará o código-fonte (projeto todo). Para uso normal, utilize os links acima.

---

## 🚀 Como usar

### 🏠 Versão Home Office
1. Baixe o pacote **Home Office (Portátil)** acima.
2. Extraia o ZIP em uma pasta no seu computador.
3. Execute o arquivo `INICIAR_PLATAFORMA_LOCAL.bat`.
4. O navegador abrirá automaticamente em `http://127.0.0.1:8765/`.

### 🖥️ Versão Servidor (TI)
1. Baixe o pacote **Servidor** acima.
2. Extraia no servidor de destino.
3. Certifique-se de que o Python está instalado.
4. Execute o arquivo `SERVIDOR_CENTRAL.bat`.

---

## 🔍 Critérios de Comparação

### Equipamentos
- Comparação por string normalizada completa.
- Padronização: espaços e hífens (`\\s*-\\s*` -> ` - `).

### Alimentadores/Subestações
- Padronização: maiúsculo e remove espaços.
- Apenas códigos completos (ex.: `CMN004`) entram na comparação.

---

## 🛠️ Manutenção (Desenvolvedores)
Para lançar uma nova versão no GitHub:
1. Execute o script `CRIAR_NOVA_VERSAO.bat`.
2. Informe o número da versão (ex: `1.0.5`).
3. O GitHub Actions gerará os novos ZIPs automaticamente.
