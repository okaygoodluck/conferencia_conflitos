# 🏢 Guia de Configuração: Servidor Central GDIS

Este guia explica como colocar a Plataforma GDIS para rodar em um servidor central, permitindo que todos na empresa (incluindo Home Office via VPN) acessem o sistema apenas pelo navegador.

## 1. Escolha da Máquina
- Use um PC ou Servidor que fique ligado 24h.
- A máquina deve ter acesso à internet (para o robô baixar o navegador e as bibliotecas) e acesso ao site do GDIS.
- Certifique-se de que a máquina tem o Python instalado (v3.9 ou superior).

## 2. Configuração do Firewall (Obrigatório)
Para que outras máquinas consigam acessar o servidor, você precisa abrir a porta **8765**:

1. No servidor, abra o **Menu Iniciar** e digite `Firewall do Windows`.
2. Clique em **Configurações Avançadas**.
3. No menu à esquerda, clique em **Regras de Entrada** (Inbound Rules).
4. No menu à direita, clique em **Nova Regra...**.
5. Selecione **Porta** e clique em Avançar.
6. Selecione **TCP** e em **Portas locais específicas** digite: `8765`.
7. Selecione **Permitir a conexão** e avance até o final.
8. Dê o nome de `GDIS Platform - Hub` e conclua.

## 3. Iniciando o Servidor
1. No servidor, vá até a pasta do projeto e execute o arquivo `SERVIDOR_CENTRAL.bat`.
2. Ele vai detectar o IP automaticamente e mostrar um link como: `http://10.X.Y.Z:8765/`.
3. **Copie este link** e envie para a equipe.

## 4. Acesso via Home Office
- O usuário deve ligar a **VPN**.
- Ele não precisa mais acessar a pasta `I:`.
- Ele só precisa abrir o navegador (Chrome ou Edge) e colar o link do servidor.

## 5. Dicas Extras
- **IP Fixo:** Peça ao TI para fixar o IP da máquina do servidor ou criar um nome de rede (ex: `http://conferidor-gdis/`).
- **Auto-Start:** Você pode colocar um atalho do `SERVIDOR_CENTRAL.bat` na pasta `Inicializar` do Windows (`shell:startup`) para que o servidor ligue sozinho se a máquina reiniciar.
