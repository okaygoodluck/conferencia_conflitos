"""
Módulo de Análise Topológica Elétrica usando NetworkX.
Fornece funções para construção de grafos de rede elétrica, verificação de
caminhos energizados entre equipamentos e análise de conflitos topológicos.
"""

import logging
import json
import networkx as nx

logger = logging.getLogger("analisador_topologico")


def construir_grafo_topologico(dados_json, override_status=None):
    """
    Constrói um grafo NetworkX (nx.Graph) a partir dos dados de topologia (nós e arestas).
    
    :param dados_json: Dicionário contendo as chaves 'nos' e 'arestas' (formato GDIS/Ortogonal).
    :param override_status: Dicionário opcional mapeando id ou numeq para estado 'A' ou 'F'.
    :return: Instância de nx.Graph com atributos nos nós e nas arestas.
    """
    G = nx.Graph()
    if not dados_json or not isinstance(dados_json, dict):
        return G

    nos = dados_json.get("nos", [])
    arestas = dados_json.get("arestas", [])
    
    nos_dict = {}
    open_nodes = set()

    # Processa nó raiz se presente
    if "root" in dados_json and isinstance(dados_json["root"], dict):
        root_id = str(dados_json["root"].get("id", ""))
        if root_id:
            nos_dict[root_id] = dados_json["root"]
            G.add_node(root_id, **dados_json["root"])

    # Adiciona nós
    for no in nos:
        if not isinstance(no, dict):
            continue
        no_id = str(no.get("id", ""))
        no_numeq = str(no.get("numeq", "")).strip().upper()
        
        if not no_id and not no_numeq:
            continue
            
        key_node = no_numeq if no_numeq else no_id
        nos_dict[key_node] = no
        nos_dict[no_id] = no

        # Determina estado do equipamento (A = Aberto, F = Fechado)
        base_posope = str(no.get("POSOPE", no.get("posope", no.get("estado", "F")))).strip().upper()
        
        if override_status and (no_id in override_status or no_numeq in override_status):
            posope = str(override_status.get(no_id, override_status.get(no_numeq))).strip().upper()
        else:
            posope = base_posope

        is_open = posope in ["A", "ABERTO", "ABERTA", "DESLIGADO", "OFF"]
        no_attrs = dict(no)
        no_attrs["POSOPE"] = "A" if is_open else "F"
        no_attrs["is_open"] = is_open
        
        G.add_node(key_node, **no_attrs)
        if no_id != key_node:
            G.add_node(no_id, **no_attrs)

        if is_open:
            open_nodes.add(key_node)
            open_nodes.add(no_id)

    # Adiciona arestas
    for aresta in arestas:
        if not isinstance(aresta, dict):
            continue
        aresta_id = str(aresta.get("id", ""))
        
        u, v = None, None
        if "*" in aresta_id:
            u, v = aresta_id.split("*", 1)
        elif "u" in aresta and "v" in aresta:
            u, v = str(aresta["u"]), str(aresta["v"])

        if not u or not v:
            continue

        # Mapeia para numeq se disponível
        u_node = str(nos_dict.get(u, {}).get("numeq", u)).strip().upper() or u
        v_node = str(nos_dict.get(v, {}).get("numeq", v)).strip().upper() or v

        cable_data = []
        try:
            data_str = aresta.get("data", "[]")
            if isinstance(data_str, str) and data_str:
                parsed = json.loads(data_str)
                if isinstance(parsed, list):
                    cable_data = parsed
            elif isinstance(data_str, list):
                cable_data = data_str
        except Exception as e:
            logger.debug("Erro ao parsear cabos da aresta %s: %s", aresta_id, e)

        is_edge_open = (
            u_node in open_nodes 
            or v_node in open_nodes 
            or any(str(x.get('estado', '')).upper() == 'A' for x in cable_data if isinstance(x, dict))
        )

        peso = 1000 if is_edge_open else 1
        G.add_edge(u_node, v_node, weight=peso, is_open=is_edge_open, cabos=cable_data)

    return G


def obter_subgrafo_energizado(G):
    """
    Retorna um subgrafo de G mantendo apenas arestas e nós em estado FECHADO.
    """
    if G is None or len(G) == 0:
        return nx.Graph()

    subG = nx.Graph()
    for n, data in G.nodes(data=True):
        if not data.get("is_open", False):
            subG.add_node(n, **data)

    for u, v, data in G.edges(data=True):
        if not data.get("is_open", False) and data.get("weight", 1) < 1000:
            if u in subG.nodes and v in subG.nodes:
                subG.add_edge(u, v, **data)

    return subG


def verificar_conectividade_eletrica(G, eq_set1, eq_set2):
    """
    Verifica se existe conectividade elétrica (caminho energizado) entre
    equipamentos do conjunto 1 e equipamentos do conjunto 2.

    :param G: Grafo NetworkX da topologia do alimentador/rede.
    :param eq_set1: Coleção de IDs ou nomes de equipamentos da Manobra 1.
    :param eq_set2: Coleção de IDs ou nomes de equipamentos da Manobra 2.
    :return: Tupla (tem_conflito_direto, lista_de_conexoes)
             lista_de_conexoes = [{'eq1': ..., 'eq2': ..., 'caminho': [...]}]
    """
    if G is None or len(G) == 0 or not eq_set1 or not eq_set2:
        return False, []

    conexoes = []
    
    # 1. Primeiro verifica se há coincidência direta do mesmo equipamento
    set1_clean = {str(e).strip().upper() for e in eq_set1 if e}
    set2_clean = {str(e).strip().upper() for e in eq_set2 if e}
    mesmos_eqs = set1_clean.intersection(set2_clean)

    for eq_same in mesmos_eqs:
        conexoes.append({
            "eq1": eq_same,
            "eq2": eq_same,
            "tipo": "MESMO_EQUIPAMENTO",
            "caminho": [eq_same]
        })

    # 2. Em seguida analisa conectividade no subgrafo energizado
    subG = obter_subgrafo_energizado(G)
    nodes_subg = set(subG.nodes())
    eq1_validos = [e for e in set1_clean if e in nodes_subg]
    eq2_validos = [e for e in set2_clean if e in nodes_subg]

    for eq1 in eq1_validos:
        for eq2 in eq2_validos:
            if eq1 == eq2:
                continue # Já tratado no passo 1
            if nx.has_path(subG, eq1, eq2):
                try:
                    caminho = nx.shortest_path(subG, source=eq1, target=eq2)
                    conexoes.append({
                        "eq1": eq1,
                        "eq2": eq2,
                        "tipo": "CAMINHO_ENERGIZADO_COMPARTILHADO",
                        "caminho": caminho
                    })
                except nx.NetworkXNoPath:
                    pass

    tem_conflito = len(conexoes) > 0
    return tem_conflito, conexoes


# ---------------------------------------------------------------------------
# Etapa 4: Sequência Operativa e Estado de Chaves NA (Abertas) / NF (Fechadas)
# ---------------------------------------------------------------------------
def validar_sequencia_na_nf(etapas_ou_itens, G=None):
    """
    Etapa 4: Valida a sequência operativa de chaves NA (Abertas) e NF (Fechadas).
    Garante que a manobra fecha a chave NA de socorro (fechamento em anel/paralelo)
    ANTES de abrir uma chave NF de abastecimento (evitando desabastecimento inadvertido).

    :param etapas_ou_itens: Lista de dicionários contendo os itens da manobra ordenados cronologicamente.
                            Cada item deve conter {'equipamento': ..., 'acao': ..., 'posope': ...}
    :param G: Grafo NetworkX opcional para verificar contexto topológico do equipamento.
    :return: Tupla (is_valid, lista_alertas)
    """
    alertas = []
    chaves_na_fechadas = set()

    for idx, item in enumerate(etapas_ou_itens or [], 1):
        if not isinstance(item, dict):
            continue

        eq = str(item.get("equipamento", item.get("eq", item.get("numeq", "")))).strip().upper()
        acao = str(item.get("acao", item.get("macro", item.get("operacao", "")))).strip().upper()
        posope_inicial = str(item.get("posope", item.get("POSOPE", ""))).strip().upper()

        if not eq:
            continue

        # Registra fechamento de chave NA (Normalmente Aberta)
        if ("FECHAR" in acao or "SINALIZAR FECHAMENTO" in acao or acao in ["MA02", "MA04", "MA39"]) and posope_inicial in ["A", "ABERTO", "ABERTA"]:
            chaves_na_fechadas.add(eq)

        # Verifica abertura de chave NF sem fechamento prévio de NA no circuito
        if ("ABRIR" in acao or "DESLIGAR" in acao or acao in ["MA01", "MA03", "MA49"]) and posope_inicial in ["F", "FECHADO", "FECHADA"]:
            if not chaves_na_fechadas:
                alertas.append({
                    "item_idx": idx,
                    "equipamento": eq,
                    "acao": acao,
                    "tipo_alerta": "ABERTURA_NF_SEM_FECHAMENTO_NA_PREVIO",
                    "mensagem": f"Item {idx}: Tentativa de ABRIR chave NF ({eq}) sem fechamento prévio registrado de chave NA de socorro."
                })

    is_valid = len(alertas) == 0
    return is_valid, alertas


# ---------------------------------------------------------------------------
# Etapa 5: Regra de Segurança Térmica (Ampacidade de Cabos e Sobrecarga)
# ---------------------------------------------------------------------------
TABELA_AMPACIDADE_PADRAO = {
    "CAA 1/0": 230.0,
    "CAA 4/0": 340.0,
    "CAA 336.4": 530.0,
    "CAA 477": 650.0,
    "CA 1/0": 210.0,
    "CA 4/0": 310.0,
    "CU 2": 180.0,
    "CU 1/0": 240.0,
    "CU 4/0": 380.0,
}


def obter_ampacidade_cabo(descricao_cabo, default_amp=300.0):
    """
    Retorna a ampacidade nominal em Ampères (A) de um condutor a partir da sua descrição.
    """
    if not descricao_cabo or not isinstance(descricao_cabo, str):
        return default_amp

    desc_upper = descricao_cabo.upper()
    for chave, amp in TABELA_AMPACIDADE_PADRAO.items():
        if chave in desc_upper:
            return amp

    return default_amp


def verificar_sobrecarga_termica(corrente_estimada_a, capacidade_max_a):
    """
    Etapa 5: Verifica se a corrente estimada (A) durante a manobra/transferência de carga
    excede a ampacidade nominal máxima do condutor (capacidade_max_a).

    :param corrente_estimada_a: Corrente simulada/medida em Ampères.
    :param capacidade_max_a: Limite térmico do cabo em Ampères.
    :return: Tupla (sobrecarga_detectada, percentual_carregamento, mensagem_alerta)
    """
    if capacidade_max_a <= 0:
        return False, 0.0, "Capacidade do condutor não informada."

    percentual = (corrente_estimada_a / capacidade_max_a) * 100.0
    sobrecarga = percentual > 100.0

    if sobrecarga:
        msg = f"ALERTA DE SEGURANÇA TÉRMICA: Corrente estimada de {corrente_estimada_a:.1f}A excede o limite do cabo ({capacidade_max_a:.1f}A - {percentual:.1f}% do carregamento)."
    elif percentual >= 90.0:
        msg = f"ATENÇÃO TÉRMICA: Carregamento elevado ({corrente_estimada_a:.1f}A / {capacidade_max_a:.1f}A - {percentual:.1f}%)."
    else:
        msg = f"Operação dentro dos limites térmicos ({corrente_estimada_a:.1f}A / {capacidade_max_a:.1f}A - {percentual:.1f}%)."

    return sobrecarga, percentual, msg
