import unittest
import os
import sys
import json

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src.core.rede_grafo import RedeGrafoAlimentador

class TestRedeGrafo(unittest.TestCase):

    def test_rede_grafo_com_rede_sintetica(self):
        """
        Testa topologia sintética:
        Raiz (SE) -> Chave 100 (F) -> Regulador 200 (F) -> Chave 300 (A, Loop com a Raiz)
        """
        dados_sinteticos = {
            "alimentador": "TEST01",
            "root": {"id": "ROOT_SE", "refalm": "TEST01"},
            "nos": [
                {"id": "ROOT_SE", "numeq": "TEST01", "tipono": "alimentador", "posope": "F"},
                {"id": "N1", "numeq": "100", "tipono": "CH Faca", "tipoeq": "28", "posope": "F", "r_fases": "ABC"},
                {"id": "N2", "numeq": "200", "tipono": "Regulador", "tipoeq": "02", "posope": "F", "r_fases": "ABC", "pelf": "1", "pelc": "2"},
                {"id": "N3", "numeq": "2201", "tipono": "Religador", "tipoeq": "22", "posope": "F", "r_fases": "ABC"},
                {"id": "N4", "numeq": "300", "tipono": "CH Faca", "tipoeq": "28", "posope": "A", "r_fases": "ABC", "alm_outro_circuito": "SOCORRO02"},
            ],
            "arestas": [
                {"id": "ROOT_SE*N1"},
                {"id": "N1*N2"},
                {"id": "N2*N3"},
                {"id": "N3*N4"},
                {"id": "N4*ROOT_SE"}
            ]
        }

        grafo = RedeGrafoAlimentador(dados_sinteticos)
        self.assertEqual(grafo.root_id, "ROOT_SE")
        self.assertEqual(len(grafo.obter_reguladores_tensao()), 1)

        # 1. Teste da zona jusante do regulador
        zona_jusante = grafo.obter_zona_jusante_regulador("200")
        self.assertIn("N2", zona_jusante)
        self.assertIn("N3", zona_jusante)

        # 2. Teste do fechamento da chave 300 gerando ciclo elétrico
        religs = grafo.obter_religadores_trifasicos_no_ciclo("300")
        self.assertEqual(len(religs), 1)
        self.assertEqual(religs[0]["numeq"], "2201")

        # 3. Teste do fechamento da chave 300 invertendo o Regulador 200
        rts_inv = grafo.detectar_reguladores_invertidos_por_fechamento("300")
        self.assertEqual(len(rts_inv), 1)
        self.assertEqual(rts_inv[0]["numeq"], "200")

    def test_simular_manobra_regra_45_e_46(self):
        dados_sinteticos = {
            "alimentador": "TEST01",
            "root": {"id": "ROOT_SE", "refalm": "TEST01"},
            "nos": [
                {"id": "ROOT_SE", "numeq": "TEST01", "tipono": "alimentador", "posope": "F"},
                {"id": "N1", "numeq": "100", "tipono": "CH Faca", "tipoeq": "28", "posope": "F", "r_fases": "ABC"},
                {"id": "N2", "numeq": "200", "tipono": "Regulador", "tipoeq": "02", "posope": "F", "r_fases": "ABC"},
                {"id": "N3", "numeq": "2201", "tipono": "Religador", "tipoeq": "22", "posope": "F", "r_fases": "ABC"},
                {"id": "N4", "numeq": "300", "tipono": "CH Faca", "tipoeq": "28", "posope": "A", "r_fases": "ABC", "alm_outro_circuito": "SOCORRO02"},
            ],
            "arestas": [
                {"id": "ROOT_SE*N1"},
                {"id": "N1*N2"},
                {"id": "N2*N3"},
                {"id": "N3*N4"},
                {"id": "N4*ROOT_SE"}
            ]
        }

        grafo = RedeGrafoAlimentador(dados_sinteticos)

        # Cenário A: Sem MA15 no religador 2201 e sem MA35 no regulador 200
        manobra_sem_macros = [
            {"equipamento": "300", "texto_linha": "FECHAR CHAVE 300", "etapa_nome": "10 Transferência"}
        ]
        res_a = grafo.simular_manobra(manobra_sem_macros)
        self.assertEqual(len(res_a["religadores_anel_sem_ma15"]), 1)
        self.assertEqual(res_a["religadores_anel_sem_ma15"][0]["religador"], "2201")
        self.assertEqual(len(res_a["rt_sem_ma35_ou_ma77"]), 1)
        self.assertEqual(res_a["rt_sem_ma35_ou_ma77"][0]["regulador"], "200")

        # Cenário B: Com MA15 e MA35 antes de fechar a chave 300, e MA36 no retorno
        manobra_com_macros = [
            {"equipamento": "2201", "texto_linha": "MA15 BLOQUEIO DO ST", "etapa_nome": "10 Preparação"},
            {"equipamento": "200", "texto_linha": "MA35 COLOCAR NO NEUTRO", "etapa_nome": "10 Preparação"},
            {"equipamento": "300", "texto_linha": "FECHAR CHAVE 300", "etapa_nome": "20 Transferência"},
            {"equipamento": "200", "texto_linha": "MA36 LIGAR CAIXA DE COMANDO E COLOCAR RT EM SERVICO", "etapa_nome": "30 Normalização"}
        ]
        res_b = grafo.simular_manobra(manobra_com_macros)
        self.assertEqual(len(res_b["religadores_anel_sem_ma15"]), 0)
        self.assertEqual(len(res_b["rt_sem_ma35_ou_ma77"]), 0)
        self.assertEqual(len(res_b["rt_sem_ma36_retorno"]), 0)

    def test_regra_45_corte_de_carga_nao_gera_loop(self):
        """Transferência com corte de carga / pique não forma anel energizado (Regra 45 não deve falhar)"""
        dados_sinteticos = {
            "alimentador": "TEST01",
            "root": {"id": "ROOT_SE", "refalm": "TEST01"},
            "nos": [
                {"id": "ROOT_SE", "numeq": "TEST01", "tipono": "alimentador", "posope": "F"},
                {"id": "N1", "numeq": "100", "tipono": "CH Faca", "tipoeq": "28", "posope": "F", "r_fases": "ABC"},
                {"id": "N2", "numeq": "2201", "tipono": "Religador", "tipoeq": "22", "posope": "F", "r_fases": "ABC"},
                {"id": "N3", "numeq": "300", "tipono": "CH Faca", "tipoeq": "28", "posope": "A", "r_fases": "ABC", "alm_outro_circuito": "SOCORRO02"},
            ],
            "arestas": [
                {"id": "ROOT_SE*N1"},
                {"id": "N1*N2"},
                {"id": "N2*N3"},
                {"id": "N3*ROOT_SE"}
            ]
        }
        grafo = RedeGrafoAlimentador(dados_sinteticos)
        manobra_com_corte = [
            {"equipamento": "100", "texto_linha": "MA01 ABRIR CHAVE 100", "observacao": "CORTE DE CARGA", "etapa_texto_header": "20 MANOBRA COM CORTE DE CARGA COM PIQUE"},
            {"equipamento": "300", "texto_linha": "FECHAR CHAVE 300", "etapa_texto_header": "20 MANOBRA COM CORTE DE CARGA COM PIQUE"}
        ]
        res = grafo.simular_manobra(manobra_com_corte)
        self.assertEqual(len(res["loops_detectados"]), 0)
        self.assertEqual(len(res["religadores_anel_sem_ma15"]), 0)

    def test_regra_46_sem_duplicacao_na_normalizacao(self):
        """Regulador invertido no socorro não deve ser reportado novamente no fechamento de retorno"""
        dados_sinteticos = {
            "alimentador": "TEST01",
            "root": {"id": "ROOT_SE", "refalm": "TEST01"},
            "nos": [
                {"id": "ROOT_SE", "numeq": "TEST01", "tipono": "alimentador", "posope": "F"},
                {"id": "N1", "numeq": "100", "tipono": "CH Faca", "tipoeq": "28", "posope": "F", "r_fases": "ABC"},
                {"id": "N2", "numeq": "200", "tipono": "Regulador", "tipoeq": "02", "posope": "F", "r_fases": "ABC"},
                {"id": "N3", "numeq": "300", "tipono": "CH Faca", "tipoeq": "28", "posope": "A", "r_fases": "ABC", "alm_outro_circuito": "SOCORRO02"},
            ],
            "arestas": [
                {"id": "ROOT_SE*N1"},
                {"id": "N1*N2"},
                {"id": "N2*N3"}
            ]
        }
        grafo = RedeGrafoAlimentador(dados_sinteticos)
        manobra = [
            {"equipamento": "300", "texto_linha": "FECHAR CHAVE 300", "etapa_texto_header": "20 TRANSFERENCIA"},
            {"equipamento": "300", "texto_linha": "ABRIR CHAVE 300", "etapa_texto_header": "50 NORMALIZACAO"},
            {"equipamento": "100", "texto_linha": "FECHAR CHAVE 100", "etapa_texto_header": "50 NORMALIZACAO"}
        ]
        res = grafo.simular_manobra(manobra)
        # O regulador 200 deve aparecer exatamente UMA vez como invertido e UMA vez pendente de MA36
        self.assertEqual(len(res["reguladores_invertidos"]), 1)
        self.assertEqual(len(res["rt_sem_ma35_ou_ma77"]), 1)
        self.assertEqual(len(res["rt_sem_ma36_retorno"]), 1)
        self.assertEqual(res["rt_sem_ma35_ou_ma77"][0]["regulador"], "200")
        self.assertEqual(res["rt_sem_ma36_retorno"][0]["regulador"], "200")


    def test_rede_real_pthd217_se_disponivel(self):
        """Valida o grafo com o dump real do PTHD217 se o arquivo existir em temp/"""
        caminho = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "temp", "topologia_PTHD217.json")
        if not os.path.exists(caminho):
            self.skipTest("Arquivo temp/topologia_PTHD217.json não presente")

        with open(caminho, "r", encoding="utf-8") as f:
            dados = json.load(f)

        grafo = RedeGrafoAlimentador(dados)
        self.assertEqual(len(grafo.G_fisico.nodes), 542)
        self.assertEqual(len(grafo.G_fisico.edges), 550)

        # Chave 79958 fecha laço com o Religador trifásico 281246
        religs = grafo.obter_religadores_trifasicos_no_ciclo("79958")
        self.assertTrue(any(str(r.get("numeq")) == "281246" for r in religs))

        # Chave 464974 inverte o Regulador 133136
        rts_inv = grafo.detectar_reguladores_invertidos_por_fechamento("464974")
        self.assertTrue(any(str(r.get("numeq")) == "133136" for r in rts_inv))

if __name__ == "__main__":
    unittest.main()
