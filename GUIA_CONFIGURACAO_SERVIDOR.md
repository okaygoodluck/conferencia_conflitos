# Guia de Configuração do Servidor GDIS

Este guia orienta a migração da Plataforma GDIS para uma máquina dedicada (Servidor Local).

---

## 1. Requisitos da Máquina (Servidor)
- **Sistema Operacional:** Windows 10/11 ou Server.
- **Python:** Versão 3.10 ou superior instalada e no PATH.
- **Rede:** IP fixo na rede interna ou um nome de rede (hostname) estável.
- **Acesso:** Permissão para abrir a porta **8765** no Firewall.

## 2. Passo a Passo da Instalação

### Passo A: Copiar o Projeto
Copie toda a pasta `conferidor_conflitos` para o servidor (ex: `C:\GDIS_Platform\`).

### Passo B: Instalar Dependências
No servidor, abra o terminal na pasta do projeto e execute:
```powershell
.\Instalar_Requirements.bat
```
*(Isso vai instalar o Python localmente na pasta `python_portable` e as bibliotecas necessárias).*

### Passo C: Instalar o Navegador Robô
No mesmo terminal, execute:
```powershell
.\python_portable\python.exe -m playwright install chromium
```

### Passo D: Abrir o Firewall
É necessário permitir que outras máquinas acessem a porta 8765.
1. Vá em **Firewall do Windows** -> **Configurações Avançadas**.
2. **Regras de Entrada** -> **Nova Regra**.
3. Escolha **Porta** -> **TCP** -> **Portas locais específicas: 8765**.
4. **Permitir a conexão**.
5. Dê o nome: `GDIS_Plataforma_8765`.

## 3. Iniciando o Servidor
Basta executar o arquivo:
```powershell
.\iniciar_plataforma_gdis.bat
```
A tela do prompt **ficará aberta e visível** no servidor, exibindo os logs de acesso e o status da plataforma. **Não feche esta janela**, pois ela é o motor do sistema.

---

## 4. Como os usuários vão acessar?

Agora, em qualquer outra máquina da rede, basta abrir o navegador e digitar:
`http://[IP-DO-SERVIDOR]:8765/`

> [!TIP]
> Me informe o **IP do Servidor** (ou o nome da máquina) para que eu possa gerar um arquivo de atalho (.url) pronto para você distribuir para a equipe.
