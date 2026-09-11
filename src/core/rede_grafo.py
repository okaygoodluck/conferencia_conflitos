"""
Motor de Análise Topológica em Grafos para Redes de Distribuição (GDIS)
Mapeia nós, trechos, conectividade radial, loops/anéis elétricos e sentido de fluxo
para suporte às validações de manobras (Regra 45: Bloqueio de ST e Regra 46: RT Invertido).
"""

import re
import json
import logging
from typing import Dict, List, Set, Tuple, Optional, Any
import networkx as nx

logger = logging.getLogger(__name__)

def _extrair_id_puro(cod: str) -> str:
    """Extrai o número puro do equipamento removendo prefixos como '22 - ' ou '28 - '."""
    if not cod or cod == '-':
        return ""
    parts = [p.strip() for p in str(cod).split('-')]
    if len(parts) > 1 and parts[-1].isdigit():
        return parts[-1].lstrip("0")
    m = re.findall(r'\d+', str(cod))
    if m:
        # Pega a parte numérica mais longa (número real do equipamento, evitando prefixos curtos de 2 dígitos)
        return max(m, key=len).lstrip("0")
    return str(cod).strip()


def _obter_nome_etapa(mi: dict) -> str:
    """Extrai o nome ou identificador limpo e legível da etapa."""
    et = str(mi.get("etapa_nome") or mi.get("etapa_texto_header") or mi.get("etapa") or "").strip()
    et = re.sub(r'^(?:etapa\s*:\s*)+', '', et, flags=re.IGNORECASE).strip()
    if not et:
        return "Manobra"
    # Se contiver a data ex: 09/09/2026, pega a parte descritiva antes da data para ficar conciso e legível
    m = re.search(r'^(.*?)\s+\d{2}/\d{2}/\d{4}', et)
    if m:
        return m.group(1).strip()
    return et


def _norm_alim(s: str) -> str:
    """Normaliza o código do alimentador removendo espaços, hífens e zeros à esquerda dos dígitos (ex: 'MZLU 006' -> 'MZLU6')."""
    if not s:
        return ""
    s_clean = re.sub(r'[\s\-_]+', '', str(s)).upper()
    m = re.match(r'^([A-Z]+)0*(\d+)$', s_clean)
    if m:
        return f"{m.group(1)}{m.group(2)}"
    return s_clean


def _alim_compativel(a1: str, a2: str) -> bool:
    """Verifica se dois códigos de alimentador são equivalentes."""
    if not a1 or not a2:
        return False
    return _norm_alim(a1) == _norm_alim(a2)


class RedeGrafoAlimentador:
    """
    Representa a topologia física e operacional de um alimentador elétrico
    obtida dinamicamente do GDIS (getRedeAlimentador).
    """

    def __init__(self, dados_json: dict):
        self.dados_json = dados_json or {}
        self.nos_raw = self.dados_json.get("nos", [])
        self.arestas_raw = self.dados_json.get("arestas", [])
        self.root_raw = self.dados_json.get("root", {})
        
        # Identificação da raiz da SE
        self.root_id = str(self.root_raw.get("id") or self.dados_json.get("alimentador", "")).strip()
        self.cod_alim = str(self.root_raw.get("refalm") or self.dados_json.get("alimentador", "")).strip().upper()

        # Grafo físico completo (todas as conexões físicas)
        self.G_fisico = nx.Graph()

        # Indexadores rápidos
        self.id_to_no: Dict[str, dict] = {}
        self.numeq_to_ids: Dict[str, List[str]] = {}
        self.nos_abertos: Set[str] = set()

        self._construir_grafo()

    def _construir_grafo(self):
        """Monta o grafo físico no NetworkX e preenche os indexadores de nós e estado."""
        # 1. Adiciona os nós
        for no in self.nos_raw:
            if not isinstance(no, dict):
                continue
            nid = str(no.get("id", "")).strip()
            if not nid:
                continue

            numeq = str(no.get("numeq", "")).strip()
            posope = str(
                no.get("posope") or no.get("POSOPE") or no.get("r_posope") or 
                no.get("estado") or no.get("r_estado") or ""
            ).strip().upper()

            # Normaliza posope
            if posope in ["A", "ABERTO", "ABERTA", "DESLIGADO", "NA", "N.A.", "0"]:
                pos_norm = "A"
                self.nos_abertos.add(nid)
            elif posope in ["F", "FECHADO", "FECHADA", "LIGADO", "NF", "N.F.", "1"]:
                pos_norm = "F"
            else:
                pos_norm = ""

            no_attr = dict(no)
            no_attr["posope_norm"] = pos_norm
            self.id_to_no[nid] = no_attr

            if numeq and numeq != "-":
                self.numeq_to_ids.setdefault(numeq, []).append(nid)
                puro = _extrair_id_puro(numeq)
                if puro and puro != numeq:
                    self.numeq_to_ids.setdefault(puro, []).append(nid)
                if numeq.lstrip("0") and numeq.lstrip("0") != numeq:
                    self.numeq_to_ids.setdefault(numeq.lstrip("0"), []).append(nid)

            self.G_fisico.add_node(nid, **no_attr)

        # Se o nó raiz não estiver explicitamente em 'nos', adiciona com base no root_raw
        if self.root_id and self.root_id not in self.G_fisico:
            self.G_fisico.add_node(self.root_id, **self.root_raw)
            self.id_to_no[self.root_id] = self.root_raw

        # 2. Adiciona as arestas físicas
        for aresta in self.arestas_raw:
            if not isinstance(aresta, dict):
                continue
            aid = str(aresta.get("id", ""))
            if "*" in aid:
                u, v = aid.split("*", 1)
                u = u.strip()
                v = v.strip()
                if u and v:
                    self.G_fisico.add_edge(u, v, **aresta)

    def obter_grafo_condutor(self, chaves_abertas_adicionais: Optional[Set[str]] = None,
                              chaves_fechadas_adicionais: Optional[Set[str]] = None) -> nx.Graph:
        """
        Retorna uma cópia do grafo elétrico condutor ativo.
        Equipamentos abertos (posope=='A') são removidos para impedir condução através deles.
        Permite simular aberturas e fechamentos temporários via sets adicionais.
        """
        G = self.G_fisico.copy()
        abertos = set(self.nos_abertos)

        if chaves_abertas_adicionais:
            for c in chaves_abertas_adicionais:
                abertos.update(self.obter_ids_por_numeq(c))

        if chaves_fechadas_adicionais:
            for c in chaves_fechadas_adicionais:
                for nid in self.obter_ids_por_numeq(c):
                    abertos.discard(nid)

        for nid in abertos:
            if G.has_node(nid):
                G.remove_node(nid)

        return G

    def obter_ids_por_numeq(self, numeq: str) -> List[str]:
        """Retorna os IDs de nó do GDIS para um dado número de equipamento."""
        if not numeq:
            return []
        cod_clean = str(numeq).strip()
        # 1. Busca exata
        if cod_clean in self.numeq_to_ids:
            return list(self.numeq_to_ids[cod_clean])
        # 2. Busca pelo ID puro (sem prefixos como '22 - ' ou '28 - ')
        puro = _extrair_id_puro(cod_clean)
        if puro and puro in self.numeq_to_ids:
            return list(self.numeq_to_ids[puro])
        # 3. Varredura por equivalência normalizada
        for k, v in self.numeq_to_ids.items():
            if _extrair_id_puro(k) == puro:
                return list(v)
        return []

    def obter_no_por_numeq(self, numeq: str) -> Optional[dict]:
        """Retorna o dicionário do primeiro nó correspondente ao equipamento."""
        ids = self.obter_ids_por_numeq(numeq)
        if ids:
            return self.id_to_no.get(ids[0])
        return None

    def obter_reguladores_tensao(self) -> List[dict]:
        """Retorna todos os nós cadastrados como Regulador de Tensão (RT)."""
        reguladores = []
        for nid, no in self.id_to_no.items():
            tipoeq = str(no.get("tipoeq", "")).strip()
            tipono = str(no.get("tipono", "")).strip().lower()
            rtipo = str(no.get("r_tipoeq", "")).strip().lower()

            if tipoeq in ["02", "2"] or "regulador" in tipono or "regulador" in rtipo:
                reguladores.append(no)
        return reguladores

    def obter_zona_jusante_regulador(self, reg_numeq_ou_id: str) -> Set[str]:
        """
        Calcula o componente/zona a jusante (lado de carga) de um Regulador de Tensão
        no fluxo radial normal a partir da subestação (root) usando a topologia física.
        Utiliza árvore radial com penalidade em chaves abertas (posope=='A') para evitar
        fugas através de malhas/anéis e garantir determinação correta do sentido fonte -> carga.
        """
        ids = self.obter_ids_por_numeq(reg_numeq_ou_id)
        if not ids and reg_numeq_ou_id in self.id_to_no:
            ids = [reg_numeq_ou_id]
        if not ids:
            return set()

        reg_id = ids[0]
        if not self.root_id or not self.G_fisico.has_node(self.root_id) or not self.G_fisico.has_node(reg_id):
            return set()

        try:
            G_w = self.G_fisico.copy()
            for u, v in G_w.edges():
                no_u = self.id_to_no.get(u, {})
                no_v = self.id_to_no.get(v, {})
                is_na = (str(no_u.get("posope") or "").upper() in ["A", "ABERTO", "NA"] or
                         str(no_u.get("posope_norm") or "").upper() == "A" or
                         str(no_v.get("posope") or "").upper() in ["A", "ABERTO", "NA"] or
                         str(no_v.get("posope_norm") or "").upper() == "A")
                G_w[u][v]["weight"] = 10000 if is_na else 1

            paths = nx.single_source_dijkstra_path(G_w, self.root_id, weight="weight")
            comp_jusante = {x for x, path in paths.items() if reg_id in path}
            comp_jusante.add(reg_id)
            return comp_jusante
        except Exception:
            return {reg_id}

    def obter_religadores_trifasicos_no_ciclo(self, chave_numeq_ou_id: str,
                                              abertas_adicionais: Optional[Set[str]] = None,
                                              fechadas_adicionais: Optional[Set[str]] = None) -> List[dict]:
        """
        Ao simular o fechamento de uma chave, detecta se ela fecha um loop/anel elétrico
        e retorna todos os RELIGADORES TRIFÁSICOS presentes no laço formado (Regra 45).
        """
        ids = self.obter_ids_por_numeq(chave_numeq_ou_id)
        if not ids and chave_numeq_ou_id in self.id_to_no:
            ids = [chave_numeq_ou_id]
        if not ids:
            return []

        nid_chave = ids[0]
        if not self.G_fisico.has_node(nid_chave):
            return []

        vizinhos = list(self.G_fisico.neighbors(nid_chave))
        if len(vizinhos) < 2:
            return []

        # Obtém o grafo condutor antes de fechar esta chave
        G_cond = self.obter_grafo_condutor(abertas_adicionais, fechadas_adicionais)

        u, v = vizinhos[0], vizinhos[1]
        if not G_cond.has_node(u) or not G_cond.has_node(v):
            return []

        if not nx.has_path(G_cond, u, v):
            return []

        caminho_ciclo = nx.shortest_path(G_cond, u, v)
        nos_no_ciclo = set(caminho_ciclo)
        nos_no_ciclo.add(nid_chave)

        religadores_trifasicos = []
        for nid in nos_no_ciclo:
            no = self.id_to_no.get(nid, {})
            tipoeq = str(no.get("tipoeq", "")).strip()
            tipono = str(no.get("tipono", "")).strip().lower()
            rtipo = str(no.get("r_tipoeq", "")).strip().lower()
            fases = str(no.get("r_fases") or no.get("fases") or "").strip().upper()

            is_religador = (tipoeq in ["22", 22] or "religador" in tipono or "religador" in rtipo)
            is_mono = fases in ["A", "B", "C"]

            if is_religador and not is_mono:
                religadores_trifasicos.append(no)

        return religadores_trifasicos

    def detectar_reguladores_invertidos_por_fechamento(self, chave_numeq_ou_id: str,
                                                       chaves_abertas_simuladas: Optional[Set[str]] = None,
                                                       etapa_nome: str = "",
                                                       equipamentos_abertos_manobra: Optional[Set[str]] = None,
                                                       alim_item: str = "") -> List[dict]:
        """
        Verifica se o fechamento de uma chave (especialmente socorro ou interligação)
        provoca alimentação reversa em algum Regulador de Tensão do circuito (Regra 46).
        """
        ids = self.obter_ids_por_numeq(chave_numeq_ou_id)
        if not ids and chave_numeq_ou_id in self.id_to_no:
            ids = [chave_numeq_ou_id]
        if not ids:
            return []

        nid_chave = ids[0]
        no_chave = self.id_to_no.get(nid_chave, {})
        vizinhos_chave = list(self.G_fisico.neighbors(nid_chave))

        posope_orig = str(no_chave.get("posope_norm") or "").upper()
        alm_outro = str(no_chave.get("alm_outro_circuito") or no_chave.get("alm_outro_circuito_cod") or "").strip()
        outro_circuito = bool(alm_outro)

        # 1. Chaves que retornam ao seu estado normal (Religamento / Recomposição / Normalização):
        # Se a chave era normalmente fechada (posope_orig == 'F') e não conecta a outro circuito,
        # o seu fechamento apenas recompõe/restaura o fluxo radial normal vindo da subestação.
        if posope_orig == "F" and not outro_circuito:
            return []

        # 2. Se a chave foi aberta durante a própria manobra e está sendo refechada (sem ser socorro externo):
        if chaves_abertas_simuladas and not outro_circuito:
            puro_chave = _extrair_id_puro(chave_numeq_ou_id)
            for c_aberta in chaves_abertas_simuladas:
                if c_aberta == chave_numeq_ou_id or _extrair_id_puro(c_aberta) == puro_chave:
                    return []

        # 3. Se a etapa for de religamento/recomposição/normalização, não há novas inversões de socorro
        if etapa_nome and not outro_circuito:
            etapa_up = etapa_nome.upper()
            if any(k in etapa_up for k in ["RELIGAMENTO", "RECOMPOSICAO", "RECOMPOSIÇÃO", "NORMALIZACAO", "NORMALIZAÇÃO"]):
                return []

        # Conjunto de equipamentos abertos conhecidos na manobra
        abertas_total = set(chaves_abertas_simuladas or [])
        if equipamentos_abertos_manobra:
            abertas_total.update(equipamentos_abertos_manobra)

        abertas_puro = {_extrair_id_puro(c) for c in abertas_total if _extrair_id_puro(c)}

        # Grafo condutor elétrico considerando equipamentos abertos (sem a chave que está sendo fechada)
        G_cond_sem_chave = self.obter_grafo_condutor(chaves_abertas_adicionais=abertas_total)

        # Grafo condutor elétrico COM a chave que está sendo fechada
        G_cond = G_cond_sem_chave.copy()
        for v in vizinhos_chave:
            G_cond.add_edge(nid_chave, v)

        reguladores = self.obter_reguladores_tensao()
        reguladores_invertidos = []

        for reg in reguladores:
            reg_id = str(reg.get("id"))
            reg_num = str(reg.get("numeq") or "")
            reg_puro = _extrair_id_puro(reg_num)

            # Se o próprio regulador está aberto/desconectado na manobra, não há circulação de corrente nem reversão
            if reg_id in abertas_total or reg_num in abertas_total or (reg_puro and reg_puro in abertas_puro):
                continue

            comp_jusante = self.obter_zona_jusante_regulador(reg_id)
            if not comp_jusante:
                continue

            # Se a chave que está sendo fechada conecta na zona a jusante do regulador:
            conecta_jusante = (nid_chave in comp_jusante) or any(v in comp_jusante for v in vizinhos_chave)
            if not conecta_jusante:
                continue

            # Só há fluxo reverso se houver continuidade elétrica ativa (caminho condutor) entre a chave e o regulador
            tem_caminho_eletrico = False
            if G_cond.has_node(nid_chave) and G_cond.has_node(reg_id):
                try:
                    tem_caminho_eletrico = nx.has_path(G_cond, nid_chave, reg_id)
                except Exception:
                    tem_caminho_eletrico = False

            if not tem_caminho_eletrico:
                continue

            # 1. Obter vizinho a montante do regulador no caminho radial normal a partir da SE
            vizinho_montante = None
            if self.root_id and self.G_fisico.has_node(self.root_id) and self.G_fisico.has_node(reg_id):
                try:
                    caminho_normal = nx.shortest_path(self.G_fisico, self.root_id, reg_id)
                    if len(caminho_normal) >= 2:
                        vizinho_montante = caminho_normal[-2]
                except Exception:
                    pass

            # REGRA FUNDAMENTAL DE FLUXO DIRETO vs INVERSO:
            # Se o regulador está conectado à subestação (root) no grafo condutor antes do fechamento:
            tem_caminho_se = False
            if self.root_id and G_cond_sem_chave.has_node(self.root_id) and G_cond_sem_chave.has_node(reg_id):
                try:
                    tem_caminho_se = nx.has_path(G_cond_sem_chave, self.root_id, reg_id)
                except Exception:
                    tem_caminho_se = False

            if tem_caminho_se:
                # O regulador está energizado por sua própria SE.
                # Para haver alimentação reversa atingindo o lado de carga (jusante) do RT vinda da SE,
                # deve haver um anel/loop condutor (com a chave fechada) ligando a SE até o RT SEM
                # passar pelo seu lado fonte (vizinho_montante).
                loop_atinge_jusante = False
                if vizinho_montante and self.root_id:
                    G_sem_fonte_rt = G_cond.copy()
                    if G_sem_fonte_rt.has_edge(vizinho_montante, reg_id):
                        G_sem_fonte_rt.remove_edge(vizinho_montante, reg_id)
                    try:
                        loop_atinge_jusante = nx.has_path(G_sem_fonte_rt, self.root_id, reg_id)
                    except Exception:
                        loop_atinge_jusante = False

                if not loop_atinge_jusante:
                    # Rede puramente radial ou chave de socorro sem retorno para a carga:
                    # A potência flui da SE em direção à chave fechada (fluxo direto normal SE -> RT -> Chave).
                    # O regulador está a montante da chave fechada, assumindo mais carga (não há inversão).
                    continue

            if outro_circuito:
                # Chave de socorro externo injetando tensão na jusante do regulador isolado de sua SE
                reguladores_invertidos.append(reg)
            elif posope_orig == "A":
                # Chave NA interna estabelecendo alimentação reversa:
                conecta_fora = (nid_chave not in comp_jusante) or any(v not in comp_jusante for v in vizinhos_chave)
                if conecta_fora:
                    reguladores_invertidos.append(reg)

        return reguladores_invertidos

    def simular_manobra(self, manobra_dados: List[dict]) -> dict:
        """
        Executa a simulação completa da folha de manobras contra o grafo:
        1. Rastreia fechamentos que criam anéis elétricos com tensão (Regra 45) e extrai religadores trifásicos.
           (Descarta etapas com corte de carga/pique/desenergizadas, pois são abertas).
        2. Rastreia fechamentos que invertem fluxo em Reguladores de Tensão (Regra 46).
           (Evita duplicatas para o mesmo regulador em operações subsequentes de normalização).
        3. Verifica a presença das macros obrigatórias (MA15 para religadores; MA35/MA77 para RT invertido; MA36 na recomposição).
        """
        resultado = {
            "loops_detectados": [],
            "religadores_anel_sem_ma15": [],
            "reguladores_invertidos": [],
            "rt_sem_ma35_ou_ma77": [],
            "rt_sem_ma36_retorno": []
        }

        chaves_fechadas_simuladas = set()
        chaves_abertas_simuladas = set()
        equipamentos_abertos_manobra = set()

        macros_por_equipamento: Dict[str, List[Tuple[int, str, str]]] = {}
        rts_invertidos_ja_detectados = set()

        # 1. Primeiro passo: coleta macros e equipamentos que sofrem abertura na manobra
        for idx, mi in enumerate(manobra_dados):
            eq = str(mi.get("equipamento") or mi.get("numeq") or "").strip()
            txt = str(mi.get("texto_linha", "")).upper()
            etapa = _obter_nome_etapa(mi)

            if eq:
                eq_puro = _extrair_id_puro(eq)
                for k_eq in set([eq, eq_puro]):
                    if not k_eq:
                        continue
                    if k_eq not in macros_por_equipamento:
                        macros_por_equipamento[k_eq] = []
                    for m_cod in re.findall(r'\b\d*(MA[A-Z0-9]{2})\b', txt):
                        macros_por_equipamento[k_eq].append((idx, m_cod, etapa))

                is_abrir_scan = bool(re.search(r'\b\d*(MA01|MA31|MA39)\b', txt) or "ABRIR" in txt)
                if is_abrir_scan:
                    equipamentos_abertos_manobra.add(eq)
                    if eq_puro:
                        equipamentos_abertos_manobra.add(eq_puro)

        # 2. Segundo passo: simula a execução sequencial da manobra
        for idx, mi in enumerate(manobra_dados):
            eq = str(mi.get("equipamento") or mi.get("numeq") or "").strip()
            txt = str(mi.get("texto_linha", "")).upper()
            obs = str(mi.get("observacao", "")).upper()
            etapa = _obter_nome_etapa(mi)
            alim_item = str(mi.get("alim") or mi.get("alimentador") or mi.get("cod_alim") or "").strip()
            if not alim_item:
                m_alim = re.search(r'\b([A-Z]{4}\s*\d{2,4})\b', txt)
                if m_alim:
                    alim_item = m_alim.group(1).strip()

            etapa_full = (str(mi.get("etapa_nome", "")) + " " + str(mi.get("etapa_texto_header", ""))).upper()
            txt_full = (txt + " " + obs).upper()

            is_corte_ou_pique = any(k in (etapa_full + " " + txt_full) for k in [
                "CORTE DE CARGA", "COM PIQUE", "MANOBRA COM PIQUE", "SEM TENSÃO", "SEM TENSAO",
                "DESENERGIZADO", "DESLIGAMENTO", "RELIGAMENTO"
            ])

            if not eq:
                continue

            is_fechar = bool(re.search(r'\b\d*(MA02|MA66)\b', txt) or "FECHAR" in txt)
            is_abrir = bool(re.search(r'\b\d*(MA01|MA31|MA39)\b', txt) or "ABRIR" in txt)

            if is_fechar:
                # 1. Regra 45: Verifica se fecha anel elétrico COM TENSÃO
                # Se a etapa ou item for transferência com corte de carga ou pique, não há paralelo energizado
                if not is_corte_ou_pique:
                    religs_loop = self.obter_religadores_trifasicos_no_ciclo(
                        eq, chaves_abertas_simuladas, chaves_fechadas_simuladas
                    )
                    if religs_loop:
                        resultado["loops_detectados"].append({
                            "chave": eq,
                            "etapa": etapa,
                            "religadores": [r.get("numeq") for r in religs_loop]
                        })
                        for r_no in religs_loop:
                            r_num = str(r_no.get("numeq"))
                            r_puro = _extrair_id_puro(r_num)
                            macros_r = macros_por_equipamento.get(r_num, []) + macros_por_equipamento.get(r_puro, [])
                            tem_ma15 = any(
                                m[1] == "MA15" and (m[0] <= idx or m[2].strip().upper() == etapa.strip().upper())
                                for m in macros_r
                            )
                            if not tem_ma15:
                                # Fallback textual no conjunto de itens da manobra
                                for idx_m, mi_m in enumerate(manobra_dados):
                                    et_m = _obter_nome_etapa(mi_m).strip().upper()
                                    txt_m = str(mi_m.get("texto_linha", "")).upper()
                                    if (r_num in txt_m or (r_puro and r_puro in txt_m)) and "MA15" in txt_m:
                                        if idx_m <= idx or et_m == etapa.strip().upper():
                                            tem_ma15 = True
                                            break

                            if not tem_ma15:
                                resultado["religadores_anel_sem_ma15"].append({
                                    "religador": r_num,
                                    "chave_fechada": eq,
                                    "etapa": etapa
                                })

                # 2. Regra 46: Verifica se inverte fluxo em Regulador de Tensão
                rts_invertidos = self.detectar_reguladores_invertidos_por_fechamento(
                    eq,
                    chaves_abertas_simuladas=chaves_abertas_simuladas,
                    etapa_nome=etapa,
                    equipamentos_abertos_manobra=equipamentos_abertos_manobra,
                    alim_item=alim_item
                )
                for rt in rts_invertidos:
                    rt_num = str(rt.get("numeq"))
                    if rt_num in rts_invertidos_ja_detectados:
                        # Já registrado na etapa de transferência; evita redundâncias em normalizações
                        continue
                    rts_invertidos_ja_detectados.add(rt_num)

                    rt_puro = _extrair_id_puro(rt_num)
                    resultado["reguladores_invertidos"].append({
                        "regulador": rt_num,
                        "chave_fechada": eq,
                        "etapa": etapa,
                        "item_idx": idx
                    })

                    macros_rt = macros_por_equipamento.get(rt_num, []) + macros_por_equipamento.get(rt_puro, [])
                    tem_ma35_ou_ma77 = any(
                        m[1] in ["MA35", "MA77"] and (m[0] <= idx or m[2].strip().upper() == etapa.strip().upper())
                        for m in macros_rt
                    )
                    if not tem_ma35_ou_ma77:
                        # Fallback textual adicional para MA35/MA77 executado na etapa ou anterior
                        for idx_m, mi_m in enumerate(manobra_dados):
                            et_m = _obter_nome_etapa(mi_m).strip().upper()
                            txt_m = str(mi_m.get("texto_linha", "")).upper()
                            if (rt_num in txt_m or (rt_puro and rt_puro in txt_m)) and any(k in txt_m for k in ["MA35", "MA77", "NEUTRO", "FIXAR TAP"]):
                                if idx_m <= idx or et_m == etapa.strip().upper():
                                    tem_ma35_ou_ma77 = True
                                    break

                    if not tem_ma35_ou_ma77:
                        resultado["rt_sem_ma35_ou_ma77"].append({
                            "regulador": rt_num,
                            "chave_fechada": eq,
                            "etapa": etapa
                        })

                chaves_fechadas_simuladas.add(eq)
                chaves_abertas_simuladas.discard(eq)

            elif is_abrir:
                chaves_abertas_simuladas.add(eq)
                chaves_fechadas_simuladas.discard(eq)

        # 3. Regra 46: Valida MA36 na recomposição para RTs invertidos (garante 1 por RT)
        rts_com_falha_ma36 = set()
        for item_inv in resultado["reguladores_invertidos"]:
            rt_num = item_inv["regulador"]
            if rt_num in rts_com_falha_ma36:
                continue
            rt_puro = _extrair_id_puro(rt_num)
            idx_inv = item_inv["item_idx"]
            macros_rt = macros_por_equipamento.get(rt_num, []) + macros_por_equipamento.get(rt_puro, [])
            tem_ma36 = any(m[1] == "MA36" and m[0] >= idx_inv for m in macros_rt)
            if not tem_ma36:
                # Fallback textual para MA36 na etapa de recomposição/normalização
                for idx_m, mi_m in enumerate(manobra_dados):
                    if idx_m >= idx_inv:
                        txt_m = str(mi_m.get("texto_linha", "")).upper()
                        if (rt_num in txt_m or (rt_puro and rt_puro in txt_m)) and ("MA36" in txt_m or "SERVIÇO" in txt_m or "SERVICO" in txt_m):
                            tem_ma36 = True
                            break

            if not tem_ma36:
                rts_com_falha_ma36.add(rt_num)
                resultado["rt_sem_ma36_retorno"].append({
                    "regulador": rt_num,
                    "etapa_inversao": item_inv["etapa"]
                })

        return resultado

