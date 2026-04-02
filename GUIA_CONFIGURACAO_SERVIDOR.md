# Guia de Configuração do Servidor GDIS

Este documento descreve como configurar o servidor central para que toda a equipe possa acessar a Plataforma GDIS.

## Pré-requisitos
1.  Python instalado (versão 3.8+).
2.  Acesso à rede corporativa.
3.  Permissão para abrir a porta 8765 no firewall do servidor.

## Passo a Passo

1.  **Configuração da Pasta**:
    *   Mova a pasta do projeto para o local definitivo no servidor (ex: `C:\Transmissao\Plataforma_GDIS`).
2.  **Instalação**:
    *   Execute `Instalar_Requirements.bat` para garantir que todas as bibliotecas (incluindo `cryptography` para o HTTPS) estejam presentes.
3.  **Inicialização**:
    *   Execute `iniciar_plataforma_gdis.bat`.
    *   **Nota**: O console do servidor permanecerá visível para monitoramento. Não o feche.
4.  **Distribuição**:
    *   Edite o arquivo `Atalho_Plataforma_GDIS_TEMPLATE.url` com o IP real do servidor.
    *   Distribua o atalho gerado para os membros da equipe.

### ⚠️ Aviso Importante: Certificado Autoassinado (HTTPS)
Como a plataforma agora utiliza **HTTPS** com um certificado autoassinado para garantir a segurança dos dados na rede:
*   Ao acessar pela primeira vez, o navegador exibirá um alerta: **"Sua conexão não é particular"**.
*   **Ação**: Clique em **"Avançado"** e depois em **"Ir para [IP] (não seguro)"**.
*   Isso é esperado e ocorre porque o certificado foi gerado localmente, mas a conexão continuará sendo criptografada e segura.

## Monitoramento de Atividade
O console do servidor deve permanecer aberto. Todas as atividades (usuário, job, sucessos e erros) serão registradas em:
`./data/atividades.log`
