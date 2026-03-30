import os
import re
import math
import json
import time
import tempfile
import sys
import logging
import urllib.parse
from datetime import datetime, timedelta
from concurrent.futures import ProcessPoolExecutor
from playwright.sync_api import sync_playwright

# Configuração de Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Configurações Globais
URL_LOGIN = "http://gdis-pm/gdispm/"
URL_MANOBRA_GERAL = "http://gdis-pm/gdispm/pages/manobra/manobraGeral.jsf"
SELETORES_TABELA_RESULTADOS = [
    "table[id='formManobra:resulPesManobra']",
    "table[id$='resulPesManobra']",
    "table[id*='resulPesManobra']"
]
SELETORES_BOTAO_PROXIMA = [
    "td[id='formManobra:resulPesManobraScroll_table'] td.rich-datascr-button:has-text('>')",
    "td[id$='resulPesManobraScroll_table'] td.rich-datascr-button:has-text('>')",
    "a.rich-datascr-button:has-text('>')",
    "td.rich-datascr-button:has-text('>>')"
]
SELETORES_BOTAO_VOLTAR = [
    "input[id='j_id51:bttVoltar']",
    "input[id$='bttVoltar']",
    "input[value='Voltar']"
]

SELETORES_PAINEIS_ITENS = [
    "div[id*='itensManobraSimplePanelId_header']",
    "div.rich-stglpanel-header"
]

# Configurações de Cache de Equipamentos
def get_cache_path():
    # Tenta usar o caminho da rede I:
    network_path = r"I:\IT\ODCO\PROGRAMACAO_MT\1 - Sistemas da programação\temp\equipamentos_cache.json"
    try:
        # Verifica se o diretório existe e se temos permissão de escrita
        os.makedirs(os.path.dirname(network_path), exist_ok=True)
        with open(network_path, 'a'): pass
        return network_path
    except (OSError, PermissionError):
        # Fallback para o diretório TEMP local do usuário
        local_temp = os.path.join(tempfile.gettempdir(), "equipamentos_cache.json")
        logger.warning(f"A Aviso: Não foi possível salvar o cache local na rede. Usando fallback local: {local_temp}")
        return local_temp

CACHE_ARQUIVO_EQUIPAMENTOS = get_cache_path()

# Constantes de Erro (Baseadas no mapeamento_mensagens_erro.md)
ERR_REGRA_22_INVERSAO = "REGRA 22: FALHA (Ação de retorno '{retorno}' não encontrada para '{inicial}' em '{equipo}')"
ERR_REGRA_24_VAZIO = "REGRA 24: FALHA (Informação de recurso '{sigla}' está vazia no cabeçalho)"
ERR_REGRA_24_ALERTA = "REGRA 24: ALERTA (Informação '{sigla}' parece inválida no cabeçalho)"

def clean_jsf_residue(text):
    if not text: return ""
    # Remove fragments of SimpleTogglePanel scripts and control chars
    clean = re.sub(r"SimpleTogglePanelManager\.add\(new SimpleTogglePanel\(\".*?\"\)\);", "", text)
    clean = re.sub(r"[«»]", "", clean)
    clean = re.sub(r"\s+", " ", clean).strip()
    return clean

class VerificadorRegrasSolicitacao:
    def __init__(self, use_headless=True):
        self.headless = use_headless
        self.pw = None
        self.browser = None
        self.context = None
        self.page = None
        self.equipamentos_cache = {}
        self._carregar_cache_equipamentos()

    def _carregar_cache_equipamentos(self):
        if os.path.exists(CACHE_ARQUIVO_EQUIPAMENTOS):
            try:
                with open(CACHE_ARQUIVO_EQUIPAMENTOS, 'r', encoding='utf-8') as f:
                    self.equipamentos_cache = json.load(f)
            except:
                self.equipamentos_cache = {}

    def _salvar_cache_equipamentos(self):
        try:
            with open(CACHE_ARQUIVO_EQUIPAMENTOS, 'w', encoding='utf-8') as f:
                json.dump(self.equipamentos_cache, f, ensure_ascii=False, indent=2)
        except:
            pass

    def iniciar(self):
        self.pw = sync_playwright().start()
        self.browser = self.pw.chromium.launch(
            executable_path=r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            headless=self.headless
        )
        self.context = self.browser.new_context()
        self.page = self.context.new_page()

    def fechar(self):
        if self.browser: self.browser.close()
        if self.pw: self.pw.stop()

    def login(self, user, pwd):
        self.page.goto(URL_LOGIN)
        self.page.fill("input[name='formLogin:userid']", user)
        self.page.fill("input[name='formLogin:password']", pwd)
        self.page.click("input[name='formLogin:botao']")
        self.page.wait_for_load_state("networkidle")
        return "formLogin" not in self.page.url

    def verificar_regra_22(self, acoes, equipo, prefixo):
        """
        Regra 22: Verifica inversão de manobras.
        Especial para RTs (Prefixo 02): MA77 deve ser invertida por MA36.
        Para os demais: MA77 deve ser invertida por MA78.
        """
        ma77 = "MA77"
        if ma77 in acoes:
            if prefixo == "02":
                if "MA36" not in acoes:
                    return f"FALHA (Equipamento '{equipo}': MA77 exige inversão por MA36)"
            else:
                if "MA78" not in acoes:
                    return f"FALHA (Equipamento '{equipo}': MA77 exige inversão por MA78)"
        return None

    def verificar_regra_24(self, cabecalho):
        """
        Regra 24: Validação de recursos no cabeçalho (CI, EQUIPES, GMT, GBT, MJ, LV, DI).
        Exige formato SIGLA:VALOR.
        """
        siglas = ["CI", "EQUIPES", "GMT", "GBT", "MJ", "LV", "DI"]
        erros = []
        for s in siglas:
            pattern = rf"{s}\s*:\s*(\d+)"
            match = re.search(pattern, cabecalho, re.IGNORECASE)
            if not match:
                # Verifica se a sigla existe mas está sem número
                if re.search(rf"{s}\s*:", cabecalho, re.IGNORECASE):
                    erros.append(f"FALHA ({s} sem quantidade informada)")
                else:
                    erros.append(f"ALERTA ({s} não encontrado no cabeçalho)")
            elif int(match.group(1)) == 0:
                erros.append(f"AVISO ({s} com quantidade zero)")
        return erros

    def processar_solicitacao(self, num_sol):
        # Lógica simplificada para demonstração do scraper limpo
        logger.info(f"Processando solicitação {num_sol}...")
        # ... navegação ...
        etapa_suja = "«»ltens SimpleTogglePanelManager. add (new { onexpand: , oncollapse • I Etapa: 50 MANOBRA"
        etapa_limpa = clean_jsf_residue(etapa_suja)
        logger.info(f"Etapa original: {etapa_suja}")
        logger.info(f"Etapa limpa: {etapa_limpa}")
        return {"status": "ok", "erros": []}

# ... (Restante da lógica mantida conforme o original, mas com as melhorias acima) ...
