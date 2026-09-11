import unittest
import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src.core.rede_grafo import RedeGrafoAlimentador

class TestRegra46(unittest.TestCase):

    def setUp(self):
        dados = {
            "alimentador": "ALIM_TESTE",
            "root": {"id": "ROOT_SE", "refalm": "ALIM_TESTE"},
            "nos": [
                {"id": "ROOT_SE", "numeq": "ALIM_TESTE", "tipono": "alimentador", "posope": "F"},
                {"id": "N1", "numeq": "CH10", "tipono": "CH Faca", "tipoeq": "28", "posope": "A", "r_fases": "ABC"},
                {"id": "N2", "numeq": "RT50", "tipono": "Regulador", "tipoeq": "02", "posope": "F", "r_fases": "ABC", "pelf": "1", "pelc": "2"},
                {"id": "N3", "numeq": "CH60", "tipono": "Faca Unipolar", "tipoeq": "28", "posope": "A", "r_fases": "ABC", "alm_outro_circuito": "CIRCUITO_SOCORRO"},
            ],
            "arestas": [
                {"id": "ROOT_SE*N1"},
                {"id": "N1*N2"},
                {"id": "N2*N3"}
            ]
        }
        self.grafo = RedeGrafoAlimentador(dados)

    def test_regra_46_falha_sem_ma35_ou_ma77(self):
        """Quando o RT inverte fluxo sem ação prévia de neutro (MA35) ou fixar tap (MA77)"""
        manobra = [
            {"equipamento": "CH60", "texto_linha": "FECHAR CHAVE CH60", "etapa_nome": "10 Transferência"}
        ]
        res = self.grafo.simular_manobra(manobra)
        self.assertEqual(len(res["reguladores_invertidos"]), 1)
        self.assertEqual(res["reguladores_invertidos"][0]["regulador"], "RT50")
        self.assertEqual(len(res["rt_sem_ma35_ou_ma77"]), 1)
        self.assertEqual(res["rt_sem_ma35_ou_ma77"][0]["regulador"], "RT50")

    def test_regra_46_sucesso_com_ma35(self):
        """RT inverte fluxo, mas possui MA35 antes de fechar a chave de socorro e MA36 no retorno"""
        manobra = [
            {"equipamento": "RT50", "texto_linha": "MA35 COLOCAR REGULADOR NO NEUTRO", "etapa_nome": "10 Preparação"},
            {"equipamento": "CH60", "texto_linha": "FECHAR CHAVE CH60", "etapa_nome": "20 Transferência"},
            {"equipamento": "CH60", "texto_linha": "ABRIR CHAVE CH60", "etapa_nome": "30 Recomposição"},
            {"equipamento": "RT50", "texto_linha": "MA36 LIGAR CAIXA DE COMANDO E COLOCAR RT EM SERVICO", "etapa_nome": "30 Recomposição"}
        ]
        res = self.grafo.simular_manobra(manobra)
        self.assertEqual(len(res["reguladores_invertidos"]), 1)
        self.assertEqual(len(res["rt_sem_ma35_ou_ma77"]), 0)
        self.assertEqual(len(res["rt_sem_ma36_retorno"]), 0)

    def test_regra_46_sucesso_com_ma77(self):
        """RT inverte fluxo, mas possui MA77 (Fixar Tap) antes de fechar o socorro"""
        manobra = [
            {"equipamento": "RT50", "texto_linha": "MA77 FIXAR TAP DO REGULADOR", "etapa_nome": "10 Preparação"},
            {"equipamento": "CH60", "texto_linha": "FECHAR CHAVE CH60", "etapa_nome": "20 Transferência"},
            {"equipamento": "RT50", "texto_linha": "MA36 LIGAR CAIXA DE COMANDO E COLOCAR RT EM SERVICO", "etapa_nome": "30 Recomposição"}
        ]
        res = self.grafo.simular_manobra(manobra)
        self.assertEqual(len(res["reguladores_invertidos"]), 1)
        self.assertEqual(len(res["rt_sem_ma35_ou_ma77"]), 0)
        self.assertEqual(len(res["rt_sem_ma36_retorno"]), 0)

    def test_regra_46_falha_sem_ma36_no_retorno(self):
        """RT tratou o neutro (MA35) na transferência, mas esqueceu MA36 na recomposição"""
        manobra = [
            {"equipamento": "RT50", "texto_linha": "MA35 COLOCAR REGULADOR NO NEUTRO", "etapa_nome": "10 Preparação"},
            {"equipamento": "CH60", "texto_linha": "FECHAR CHAVE CH60", "etapa_nome": "20 Transferência"},
            {"equipamento": "CH60", "texto_linha": "ABRIR CHAVE CH60", "etapa_nome": "30 Recomposição"}
        ]
        res = self.grafo.simular_manobra(manobra)
        self.assertEqual(len(res["reguladores_invertidos"]), 1)
        self.assertEqual(len(res["rt_sem_ma35_ou_ma77"]), 0)
        self.assertEqual(len(res["rt_sem_ma36_retorno"]), 1)
        self.assertEqual(res["rt_sem_ma36_retorno"][0]["regulador"], "RT50")

    def test_regra_46_sem_reguladores_no_circuito(self):
        """Circuito sem nenhum regulador de tensão"""
        dados = {
            "alimentador": "ALIM_RADIAL",
            "root": {"id": "ROOT_SE"},
            "nos": [
                {"id": "ROOT_SE", "numeq": "ALIM_RADIAL", "posope": "F"},
                {"id": "N1", "numeq": "CH10", "tipoeq": "28", "posope": "F"},
            ],
            "arestas": [
                {"id": "ROOT_SE*N1"}
            ]
        }
        grafo = RedeGrafoAlimentador(dados)
        res = grafo.simular_manobra([{"equipamento": "CH10", "texto_linha": "ABRIR CH10"}])
        self.assertEqual(len(res["reguladores_invertidos"]), 0)
        self.assertEqual(len(res["rt_sem_ma35_ou_ma77"]), 0)

    def test_regra_46_manobra_real_uhtm30(self):
        """Valida a detecção da inversão dos reguladores 240729, 237273 e 253010 na manobra do UHTM30"""
        import json
        caminho_cad = r"C:\CEMIG\scada_dados\dados_ortogonal\REDE_UHTM30_cadastro.json"
        if not os.path.exists(caminho_cad):
            self.skipTest("Arquivo REDE_UHTM30_cadastro.json não disponível")

        with open(caminho_cad, "r", encoding="utf-8") as f:
            dados = json.load(f)

        grafo = RedeGrafoAlimentador(dados)
        manobra = [
            {"equipamento": "22 - 346798", "alim": "UHTM030", "texto_linha": "MA01 - ABRIR EQUIPAMENTO COM CARGA", "etapa_nome": "20 MANOBRA"},
            {"equipamento": "28 - 448117", "alim": "UHTM030", "texto_linha": "MA31 - ABRIR E SINALIZAR COM CARGA", "etapa_nome": "20 MANOBRA"},
            {"equipamento": "22 - 320996", "alim": "JPIQ403", "texto_linha": "MA02 - FECHAR EQUIPAMENTO COM CARGA", "etapa_nome": "20 MANOBRA"}
        ]
        res = grafo.simular_manobra(manobra)
        regs_inv = [r["regulador"] for r in res["reguladores_invertidos"]]
        self.assertIn("240729", regs_inv)
        self.assertIn("237273", regs_inv)
        self.assertIn("253010", regs_inv)

    def test_regra_46_desligamento_religamento_sem_falso_positivo(self):
        """
        Em manobras de desligamento e religamento para obras, a reabertura e fechamento
        de uma chave de tronco/ramal a jusante de um RT não deve ser interpretada como inversão.
        """
        dados = {
            "alimentador": "ALIM_TESTE",
            "root": {"id": "ROOT_SE", "refalm": "ALIM_TESTE"},
            "nos": [
                {"id": "ROOT_SE", "numeq": "ALIM_TESTE", "tipono": "alimentador", "posope": "F"},
                {"id": "N1", "numeq": "RT50", "tipono": "Regulador", "tipoeq": "02", "posope": "F", "r_fases": "ABC"},
                {"id": "N2", "numeq": "CH20", "tipono": "CH Faca", "tipoeq": "28", "posope": "F", "r_fases": "ABC"},
            ],
            "arestas": [
                {"id": "ROOT_SE*N1"},
                {"id": "N1*N2"}
            ]
        }
        grafo = RedeGrafoAlimentador(dados)
        manobra = [
            {"equipamento": "CH20", "texto_linha": "MA31 ABRIR E SINALIZAR CH20", "etapa_nome": "20 DESLIGAMENTO"},
            {"equipamento": "CH20", "texto_linha": "MA66 RETIRAR SINALIZACAO E FECHAR CH20", "etapa_nome": "30 RELIGAMENTO"}
        ]
        res = grafo.simular_manobra(manobra)
        self.assertEqual(len(res["reguladores_invertidos"]), 0)
        self.assertEqual(len(res["rt_sem_ma35_ou_ma77"]), 0)
        self.assertEqual(len(res["rt_sem_ma36_retorno"]), 0)

    def test_regra_46_manobra_real_magu105_sem_falso_positivo(self):
        """Valida que a manobra 245639735 no alimentador MAGU105 não acusa falso positivo de RT invertido"""
        import json
        caminho_cad = r"C:\CEMIG\scada_dados\dados_ortogonal\REDE_MAGU105.json"
        if not os.path.exists(caminho_cad):
            self.skipTest("Arquivo REDE_MAGU105.json não disponível")

        with open(caminho_cad, "r", encoding="utf-8") as f:
            dados = json.load(f)

        grafo = RedeGrafoAlimentador(dados)
        manobra = [
            {"equipamento": "28 - 267027", "texto_linha": "30 MA31 - ABRIR E SINALIZAR EQUIPAMENTO 28 - 267027 MAGU105", "etapa_nome": "20 DESLIGAMENTO MAGU105"},
            {"equipamento": "28 - 267027", "texto_linha": "20 MA66 - RETIRAR SINALIZACAO E FECHAR EQUIPAMENTO 28 - 267027 MAGU105", "etapa_nome": "30 RELIGAMENTO MAGU105"}
        ]
        res = grafo.simular_manobra(manobra)
        self.assertEqual(len(res["reguladores_invertidos"]), 0)
        self.assertEqual(len(res["rt_sem_ma35_ou_ma77"]), 0)
        self.assertEqual(len(res["rt_sem_ma36_retorno"]), 0)

    def test_regra_46_manobra_245764288_mzlu_e_mvdu_sem_falso_positivo(self):
        """
        Valida que a manobra 245764288 não acusa falso positivo de RT invertido
        nem no alimentador doador (MVDU105) nem no alimentador recebedor (MZLU06).
        """
        import json
        p_mvdu = r"C:\CEMIG\scada_dados\dados_ortogonal\REDE_MVDU105.json"
        p_mzlu = r"C:\CEMIG\scada_dados\dados_ortogonal\REDE_MZLU06.json"
        if not (os.path.exists(p_mvdu) and os.path.exists(p_mzlu)):
            self.skipTest("Arquivos REDE_MVDU105.json e/ou REDE_MZLU06.json não disponíveis")

        manobra = [
            {"alim": "MZLU006", "texto_linha": "10 MA09 - VERIFICAR SE HA ANORMALIDADE NO ALIMENTADOR MZLU006", "etapa_nome": "10 VERIFICACAO PELO COD MZLU006"},
            {"alim": "MVDU105", "texto_linha": "20 MA09 - VERIFICAR SE HA ANORMALIDADE NO ALIMENTADOR MVDU105", "etapa_nome": "10 VERIFICACAO PELO COD MZLU006"},
            {"equipamento": "02 - 87832", "alim": "MVDU105", "texto_linha": "30 MA18 - OUTROS 02 - 87832 MVDU105", "etapa_nome": "10 VERIFICACAO PELO COD MZLU006"},
            {"equipamento": "22 - 114168", "alim": "MVDU105", "texto_linha": "10 MAA4 - DESABILITAR TRANSFERENCIA AUTOMATICA 22 - 114168 MVDU105", "etapa_nome": "20 MANOBRA MZLU006"},
            {"equipamento": "22 - 385360", "alim": "MZLU006", "texto_linha": "20 MAA4 - DESABILITAR TRANSFERENCIA AUTOMATICA 22 - 385360 MZLU006", "etapa_nome": "20 MANOBRA MZLU006"},
            {"equipamento": "22 - 385360", "alim": "MZLU006", "texto_linha": "30 MAA2 - ALTERAR PARA AJUSTE ALTERNATIVO 2/GRUPO 3 22 - 385360 MZLU006", "etapa_nome": "20 MANOBRA MZLU006"},
            {"equipamento": "22 - 385360", "alim": "MZLU006", "texto_linha": "100 MA15 - BLOQUEAR ST DO RELIGADOR E SINALIZAR 22 - 385360 MZLU006", "etapa_nome": "20 MANOBRA MZLU006"},
            {"equipamento": "22 - 385360", "alim": "MZLU006", "texto_linha": "110 MA02 - FECHAR EQUIPAMENTO 22 - 385360 MZLU006 - RUA TIBERIO NEVES", "etapa_nome": "20 MANOBRA MZLU006"},
            {"equipamento": "02 - 379010", "alim": "MZLU006", "texto_linha": "120 MA31 - ABRIR E SINALIZAR EQUIPAMENTO 02 - 379010 MZLU006", "etapa_nome": "20 MANOBRA MZLU006"},
            {"equipamento": "22 - 385360", "alim": "MZLU006", "texto_linha": "130 MA17 - RETIRAR SINALIZACAO E NORMALIZAR ST DO RELIGADOR 22 - 385360 MZLU006", "etapa_nome": "20 MANOBRA MZLU006"},
            {"equipamento": "28 - 102997", "alim": "MZLU006", "texto_linha": "20 MA31 - ABRIR E SINALIZAR EQUIPAMENTO 28 - 102997 MZLU006", "etapa_nome": "30 DESLIGAMENTO MZLU006"},
            {"equipamento": "28 - 102997", "alim": "MZLU006", "texto_linha": "20 MA66 - RETIRAR SINALIZACAO E FECHAR EQUIPAMENTO 28 - 102997 MZLU006", "etapa_nome": "40 RELIGAMENTO MZLU006"},
            {"equipamento": "02 - 379010", "alim": "MZLU006", "texto_linha": "80 MA66 - RETIRAR SINALIZACAO E FECHAR EQUIPAMENTO 02 - 379010 MZLU006", "etapa_nome": "50 MANOBRA MZLU006"},
            {"equipamento": "22 - 385360", "alim": "MZLU006", "texto_linha": "90 MA01 - ABRIR EQUIPAMENTO 22 - 385360 MZLU006", "etapa_nome": "50 MANOBRA MZLU006"},
        ]

        with open(p_mvdu, "r", encoding="utf-8") as f:
            g_mvdu = RedeGrafoAlimentador(json.load(f))
        res_mvdu = g_mvdu.simular_manobra(manobra)
        self.assertEqual(len(res_mvdu["reguladores_invertidos"]), 0, f"Falso positivo no alimentador doador MVDU105: {res_mvdu['reguladores_invertidos']}")

        with open(p_mzlu, "r", encoding="utf-8") as f:
            g_mzlu = RedeGrafoAlimentador(json.load(f))
        res_mzlu = g_mzlu.simular_manobra(manobra)
        self.assertEqual(len(res_mzlu["reguladores_invertidos"]), 0, f"Falso positivo no alimentador recebedor MZLU06: {res_mzlu['reguladores_invertidos']}")

    def test_regra_46_sintetico_circuito_doador_e_rt_aberto(self):
        """
        Teste unitário sintético:
        1. Circuito doador (exportando para outro circuito) não inverte RT.
        2. RT que sofre abertura na manobra não é considerado invertido.
        """
        # Circuito Doador
        dados_doador = {
            "alimentador": "ALIM_A",
            "root": {"id": "ROOT_A", "refalm": "ALIM_A"},
            "nos": [
                {"id": "ROOT_A", "numeq": "ALIM_A", "posope": "F"},
                {"id": "N1", "numeq": "RT_A", "tipono": "Regulador", "tipoeq": "02", "posope": "F"},
                {"id": "N2", "numeq": "CH_SOCORRO", "tipono": "CH", "tipoeq": "22", "posope": "A", "alm_outro_circuito": "ALIM_B"},
            ],
            "arestas": [
                {"id": "ROOT_A*N1"},
                {"id": "N1*N2"}
            ]
        }
        g_doador = RedeGrafoAlimentador(dados_doador)
        # Operação executada para ALIM_B (onde ALIM_A é doador)
        res_doador = g_doador.simular_manobra([
            {"equipamento": "CH_SOCORRO", "alim": "ALIM_B", "texto_linha": "FECHAR CH_SOCORRO ALIM_B", "etapa_nome": "20 MANOBRA"}
        ])
        self.assertEqual(len(res_doador["reguladores_invertidos"]), 0)

        # Circuito com RT Aberto na manobra
        dados_rt_aberto = {
            "alimentador": "ALIM_B",
            "root": {"id": "ROOT_B", "refalm": "ALIM_B"},
            "nos": [
                {"id": "ROOT_B", "numeq": "ALIM_B", "posope": "F"},
                {"id": "NB1", "numeq": "RT_B", "tipono": "Regulador", "tipoeq": "02", "posope": "F"},
                {"id": "NB2", "numeq": "CH_SOCORRO", "tipono": "CH", "tipoeq": "22", "posope": "A", "alm_outro_circuito": "ALIM_A"},
            ],
            "arestas": [
                {"id": "ROOT_B*NB1"},
                {"id": "NB1*NB2"}
            ]
        }
        g_rt_aberto = RedeGrafoAlimentador(dados_rt_aberto)
        # Manobra onde RT_B é aberto
        res_rt_aberto = g_rt_aberto.simular_manobra([
            {"equipamento": "CH_SOCORRO", "alim": "ALIM_B", "texto_linha": "FECHAR CH_SOCORRO ALIM_B", "etapa_nome": "20 MANOBRA"},
            {"equipamento": "RT_B", "alim": "ALIM_B", "texto_linha": "MA31 ABRIR E SINALIZAR RT_B", "etapa_nome": "20 MANOBRA"},
        ])
        self.assertEqual(len(res_rt_aberto["reguladores_invertidos"]), 0)

    def test_regra_46_rt_montante_chave_assumindo_carga_sem_falso_positivo(self):
        """
        Cenário da Manobra 245818305:
        Reguladores a montante da chave que está sendo fechada (alimentados pela SE)
        estão assumindo mais carga no sentido normal (direto).
        Não devem ser apontados como fluxo invertido.
        """
        dados = {
            "alimentador": "PMSU24",
            "root": {"id": "ROOT_PMSU24", "refalm": "PMSU24"},
            "nos": [
                {"id": "ROOT_PMSU24", "numeq": "PMSU24", "tipono": "alimentador", "posope": "F"},
                {"id": "N1", "numeq": "RT_188256", "tipono": "Regulador", "tipoeq": "02", "posope": "F", "pelf": "1", "pelc": "2"},
                {"id": "N2", "numeq": "28 - 55288", "tipono": "CH Faca", "tipoeq": "28", "posope": "A", "alm_outro_circuito": "PMSU23"},
            ],
            "arestas": [
                {"id": "ROOT_PMSU24*N1"},
                {"id": "N1*N2"}
            ]
        }
        g = RedeGrafoAlimentador(dados)
        manobra = [
            {"equipamento": "28 - 55288", "alim": "PMSU24", "texto_linha": "MA02 - FECHAR EQUIPAMENTO 28 - 55288", "etapa_nome": "30 MANOBRA"}
        ]
        res = g.simular_manobra(manobra)
        self.assertEqual(len(res["reguladores_invertidos"]), 0)
        self.assertEqual(len(res["rt_sem_ma35_ou_ma77"]), 0)

    def test_regra_46_rt_lado_fonte_socorrido_mesmo_sentido_sem_inversao(self):
        """
        Cenário da Manobra 245818305 (PMSU23):
        Chave de tronco (55323) é aberta e chave de socorro (55288) é fechada no mesmo nó de junção.
        Os reguladores a jusante da junção continuam recebendo fluxo no mesmo sentido (Fonte -> Carga).
        Apenas a fonte foi alterada, sem inversão de fluxo.
        """
        dados = {
            "alimentador": "PMSU23",
            "root": {"id": "ROOT_PMSU23", "refalm": "PMSU23"},
            "nos": [
                {"id": "ROOT_PMSU23", "numeq": "PMSU23", "tipono": "alimentador", "posope": "F"},
                {"id": "CH_TRONCO", "numeq": "28 - 55323", "tipono": "CH Faca", "tipoeq": "28", "posope": "F"},
                {"id": "JUNCAO", "numeq": "PONTO_JUNCAO", "tipono": "barra", "posope": "F"},
                {"id": "CH_SOCORRO", "numeq": "28 - 55288", "tipono": "CH Faca", "tipoeq": "28", "posope": "A", "alm_outro_circuito": "PMSU24"},
                {"id": "RT_1", "numeq": "55295", "tipono": "Regulador", "tipoeq": "02", "posope": "F", "pelf": "1", "pelc": "2"},
                {"id": "RT_2", "numeq": "171172", "tipono": "Regulador", "tipoeq": "02", "posope": "F", "pelf": "1", "pelc": "2"},
            ],
            "arestas": [
                {"id": "ROOT_PMSU23*CH_TRONCO"},
                {"id": "CH_TRONCO*JUNCAO"},
                {"id": "CH_SOCORRO*JUNCAO"},
                {"id": "JUNCAO*RT_1"},
                {"id": "JUNCAO*RT_2"},
            ]
        }
        g = RedeGrafoAlimentador(dados)
        manobra = [
            {"equipamento": "28 - 55288", "alim": "PMSU24", "texto_linha": "MA02 - FECHAR EQUIPAMENTO 28 - 55288", "etapa_nome": "30 MANOBRA"},
            {"equipamento": "28 - 55323", "alim": "PMSU23", "texto_linha": "MA31 - ABRIR E SINALIZAR EQUIPAMENTO 28 - 55323", "etapa_nome": "30 MANOBRA"},
        ]
        res = g.simular_manobra(manobra)
        self.assertEqual(len(res["reguladores_invertidos"]), 0)
        self.assertEqual(len(res["rt_sem_ma35_ou_ma77"]), 0)

    def test_regra_46_rt_invertido_com_ma35_na_mesma_etapa_sucesso(self):
        """
        Cenário da Manobra 245251033 (MAGU104):
        Regulador 115127 sofre inversão após fechamento da chave 22 - 182974.
        A manobra possui MA35 para o RT listado na mesma etapa (Item 9 após Item 8)
        e MA36 na etapa de normalização.
        Deve reconhecer o tratamento e NÃO gerar falha de rt_sem_ma35_ou_ma77 nem rt_sem_ma36_retorno.
        """
        dados = {
            "alimentador": "MAGU104",
            "root": {"id": "ROOT_MAGU104", "refalm": "MAGU104"},
            "nos": [
                {"id": "ROOT", "numeq": "MAGU104", "tipono": "alimentador", "posope": "F"},
                {"id": "CH_TRONCO", "numeq": "22 - 362300", "tipono": "Religador", "tipoeq": "22", "posope": "F"},
                {"id": "RT_1", "numeq": "115127", "tipono": "Regulador", "tipoeq": "02", "posope": "F", "pelf": "1", "pelc": "2"},
                {"id": "CH_BYPASS", "numeq": "22 - 182974", "tipono": "Religador", "tipoeq": "22", "posope": "A", "alm_outro_circuito": "MAGU116"},
            ],
            "arestas": [
                {"id": "ROOT*CH_TRONCO"},
                {"id": "CH_TRONCO*RT_1"},
                {"id": "RT_1*CH_BYPASS"},
            ]
        }
        g = RedeGrafoAlimentador(dados)
        manobra = [
            {"equipamento": "22 - 182974", "alim": "MAGU104", "texto_linha": "MA02 - FECHAR EQUIPAMENTO 22 - 182974", "etapa_nome": "20 MANOBRA"},
            {"equipamento": "02 - 115127", "alim": "MAGU104", "texto_linha": "MA35 - COLOCAR RT NO NEUTRO 02 - 115127", "etapa_nome": "20 MANOBRA"},
            {"equipamento": "22 - 362300", "alim": "MAGU104", "texto_linha": "MA31 - ABRIR EQUIPAMENTO 22 - 362300", "etapa_nome": "20 MANOBRA"},
            {"equipamento": "02 - 115127", "alim": "MAGU104", "texto_linha": "MA36 - LIGAR CAIXA DE COMANDO 02 - 115127", "etapa_nome": "50 MANOBRA"},
        ]
        res = g.simular_manobra(manobra)
        self.assertEqual(len(res["reguladores_invertidos"]), 1)
        self.assertEqual(res["reguladores_invertidos"][0]["regulador"], "115127")
        self.assertEqual(len(res["rt_sem_ma35_ou_ma77"]), 0)
        self.assertEqual(len(res["rt_sem_ma36_retorno"]), 0)

if __name__ == "__main__":
    unittest.main()


