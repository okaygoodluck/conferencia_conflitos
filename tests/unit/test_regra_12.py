import os
import sys
import unittest

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src.core.conferidor_manobras import validar_regra_12


class TestRegra12(unittest.TestCase):

    def test_regra_12_manobra_246726602_cenario(self):
        """
        Simula o cenário da manobra 246726602 para o equipamento 28 - 89080:
        Etapa 20 com MA31 e Pos=SIM.
        Etapa 90 com MA66 e Pos=NÃO.
        Deve acusar erro especificando a Etapa 90 (MA66).
        """
        manobra_items = [
            {
                'etapa_nome': '20 MANOBRA PRRU015 28/10/2026 08:00',
                'texto_linha': '50 MA31 - ABRIR E SINALIZAR EQUIPAMENTO 28 - 89080 PRRU015 - PCA BENTO DE MELO - 2112 COM TENSAO REGIAO SIM',
                'executor': 'Regiao',
                'posicionamento': 'Sim'
            },
            {
                'etapa_nome': '90 MANOBRA COM RISCO SISTEMA PRRU015 28/10/2026 15:00 NORMALIZAR ATE AS 17HS',
                'texto_linha': '40 MA66 - RETIRAR SINALIZACAO E FECHAR EQUIPAMENTO 28 - 89080 PRRU015 - PCA BENTO DE MELO - 2112 COM TENSAO REGIAO NÃO',
                'executor': 'Regiao',
                'posicionamento': 'Não'
            }
        ]

        status, msg, teve_regiao = validar_regra_12('28 - 89080', manobra_items, prefixo='28')
        self.assertEqual(status, 'ERRO')
        self.assertTrue(teve_regiao)
        self.assertIn("Etapa '90 MANOBRA COM RISCO SISTEMA PRRU015' (MA66)", msg)
        self.assertNotIn("Etapa '20", msg)

    def test_regra_12_valida_quando_todos_posicionados(self):
        """Valida que quando todas as etapas têm Posicionamento=SIM, retorna OK"""
        manobra_items = [
            {
                'etapa_nome': '20 MANOBRA',
                'texto_linha': 'MA31 - ABRIR EQUIPAMENTO 28 - 123456 REGIAO SIM',
                'executor': 'Regiao',
                'posicionamento': 'Sim'
            },
            {
                'etapa_nome': '80 MANOBRA',
                'texto_linha': 'MA66 - FECHAR EQUIPAMENTO 28 - 123456 REGIAO SIM',
                'executor': 'Regiao',
                'posicionamento': 'Sim'
            }
        ]
        status, msg, teve_regiao = validar_regra_12('28 - 123456', manobra_items, prefixo='28')
        self.assertEqual(status, 'OK')
        self.assertTrue(teve_regiao)

    def test_regra_12_isenta_etapa_pique(self):
        """Etapa de pique usa MA27 e deve ser ignorada pela Regra 12"""
        manobra_items = [
            {
                'etapa_nome': '20 MANOBRA COM PIQUE',
                'texto_linha': 'MA31 - ABRIR EQUIPAMENTO 28 - 123456 REGIAO NÃO',
                'executor': 'Regiao',
                'posicionamento': 'Não'
            }
        ]
        status, msg, teve_regiao = validar_regra_12('28 - 123456', manobra_items, prefixo='28')
        self.assertIsNone(status)


if __name__ == '__main__':
    unittest.main()
