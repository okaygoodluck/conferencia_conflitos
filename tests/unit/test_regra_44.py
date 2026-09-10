import unittest
import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src.core.conferidor_manobras import validar_regra_44


class TestRegra44(unittest.TestCase):

    def test_manobra_245242049_sem_falsos_positivos(self):
        """
        Garante que a manobra 245242049 (Etapas 20 e 50 com CP:1576 - SATELITAL e Manobra com Pique)
        não gere nenhum falso positivo na Regra 44.
        """
        manobra_dados = [
            # Etapa 20
            {
                'etapa_texto_header': '20 MANOBRA COM CORTE DE CARGA CP:1576 - SATELITAL UHTM030 09/09/2026 10:00 MANOBRA COM PIQUE',
                'equipamento': '22 - 346798', 'alimentador': 'UHTM030', 'executor': 'COD',
                'acao_bruta': '10 MA01 - ABRIR EQUIPAMENTO',
                'texto_linha': '10 MA01 - ABRIR EQUIPAMENTO 22 - 346798 UHTM030 - ENDERECO RURAL - 5252 COM CARGA 09/09/2026 10:00 COD NÃO CORTE DE CARGA',
                'observacao': 'CORTE DE CARGA'
            },
            {
                'etapa_texto_header': '20 MANOBRA COM CORTE DE CARGA CP:1576 - SATELITAL UHTM030 09/09/2026 10:00 MANOBRA COM PIQUE',
                'equipamento': '22 - 320996', 'alimentador': 'JPIQ403', 'executor': 'COD',
                'acao_bruta': '20 MA79 - CONFIRMAR EQUIPAMENTO COMUNICANDO',
                'texto_linha': '20 MA79 - CONFIRMAR EQUIPAMENTO COMUNICANDO 22 - 320996 JPIQ403 - ENDERECO RURAL - 8202 COM TENSAO COD NÃO'
            },
            {
                'etapa_texto_header': '20 MANOBRA COM CORTE DE CARGA CP:1576 - SATELITAL UHTM030 09/09/2026 10:00 MANOBRA COM PIQUE',
                'equipamento': '28 - 448117', 'alimentador': 'UHTM030', 'executor': 'REGIAO',
                'acao_bruta': '30 MA27 - POSICIONAR PARA MANOBRAR',
                'texto_linha': '30 MA27 - POSICIONAR PARA MANOBRAR 28 - 448117 UHTM030 - ENDERECO RURAL - 5239 COM CARGA 09/09/2026 10:00 REGIAO NÃO'
            },
            {
                'etapa_texto_header': '20 MANOBRA COM CORTE DE CARGA CP:1576 - SATELITAL UHTM030 09/09/2026 10:00 MANOBRA COM PIQUE',
                'equipamento': '22 - 320996', 'alimentador': 'JPIQ403', 'executor': 'REGIAO',
                'acao_bruta': '40 MA27 - POSICIONAR PARA MANOBRAR',
                'texto_linha': '40 MA27 - POSICIONAR PARA MANOBRAR 22 - 320996 JPIQ403 - ENDERECO RURAL - 8202 COM CARGA 09/09/2026 10:00 REGIAO NÃO'
            },
            {
                'etapa_texto_header': '20 MANOBRA COM CORTE DE CARGA CP:1576 - SATELITAL UHTM030 09/09/2026 10:00 MANOBRA COM PIQUE',
                'equipamento': '28 - 448117', 'alimentador': 'UHTM030', 'executor': 'COD',
                'acao_bruta': '50 MA31 - ABRIR E SINALIZAR EQUIPAMENTO',
                'texto_linha': '50 MA31 - ABRIR E SINALIZAR EQUIPAMENTO 28 - 448117 UHTM030 - ENDERECO RURAL - 5239 COM CARGA 09/09/2026 10:00 COD NÃO'
            },
            {
                'etapa_texto_header': '20 MANOBRA COM CORTE DE CARGA CP:1576 - SATELITAL UHTM030 09/09/2026 10:00 MANOBRA COM PIQUE',
                'equipamento': '22 - 320996', 'alimentador': 'JPIQ403', 'executor': 'COD',
                'acao_bruta': '60 MA02 - FECHAR EQUIPAMENTO',
                'texto_linha': '60 MA02 - FECHAR EQUIPAMENTO 22 - 320996 JPIQ403 - ENDERECO RURAL - 8202 COM CARGA 09/09/2026 10:00 COD NÃO'
            },
            # Etapa 50
            {
                'etapa_texto_header': '50 MANOBRA COM CORTE DE CARGA CP:1576 - SATELITAL UHTM030 09/09/2026 10:00 MANOBRA COM PIQUE',
                'equipamento': '22 - 320996', 'alimentador': 'JPIQ403', 'executor': 'COD',
                'acao_bruta': '10 MA79 - CONFIRMAR EQUIPAMENTO COMUNICANDO',
                'texto_linha': '10 MA79 - CONFIRMAR EQUIPAMENTO COMUNICANDO 22 - 320996 JPIQ403 - ENDERECO RURAL - 8202 COM TENSAO COD NÃO'
            },
            {
                'etapa_texto_header': '50 MANOBRA COM CORTE DE CARGA CP:1576 - SATELITAL UHTM030 09/09/2026 10:00 MANOBRA COM PIQUE',
                'equipamento': '22 - 320996', 'alimentador': 'JPIQ403', 'executor': 'REGIAO',
                'acao_bruta': '20 MA27 - POSICIONAR PARA MANOBRAR',
                'texto_linha': '20 MA27 - POSICIONAR PARA MANOBRAR 22 - 320996 JPIQ403 - ENDERECO RURAL - 8202 COM CARGA 09/09/2026 10:00 REGIAO NÃO'
            },
            {
                'etapa_texto_header': '50 MANOBRA COM CORTE DE CARGA CP:1576 - SATELITAL UHTM030 09/09/2026 10:00 MANOBRA COM PIQUE',
                'equipamento': '28 - 448117', 'alimentador': 'UHTM030', 'executor': 'REGIAO',
                'acao_bruta': '30 MA27 - POSICIONAR PARA MANOBRAR',
                'texto_linha': '30 MA27 - POSICIONAR PARA MANOBRAR 28 - 448117 UHTM030 - ENDERECO RURAL - 5239 COM CARGA 09/09/2026 10:00 REGIAO NÃO'
            },
            {
                'etapa_texto_header': '50 MANOBRA COM CORTE DE CARGA CP:1576 - SATELITAL UHTM030 09/09/2026 10:00 MANOBRA COM PIQUE',
                'equipamento': '22 - 320996', 'alimentador': 'JPIQ403', 'executor': 'COD',
                'acao_bruta': '40 MA01 - ABRIR EQUIPAMENTO',
                'texto_linha': '40 MA01 - ABRIR EQUIPAMENTO 22 - 320996 JPIQ403 - ENDERECO RURAL - 8202 COM CARGA 09/09/2026 10:00 COD NÃO'
            },
            {
                'etapa_texto_header': '50 MANOBRA COM CORTE DE CARGA CP:1576 - SATELITAL UHTM030 09/09/2026 10:00 MANOBRA COM PIQUE',
                'equipamento': '28 - 448117', 'alimentador': 'UHTM030', 'executor': 'COD',
                'acao_bruta': '50 MA66 - RETIRAR SINALIZACAO E FECHAR EQUIPAMENTO',
                'texto_linha': '50 MA66 - RETIRAR SINALIZACAO E FECHAR EQUIPAMENTO 28 - 448117 UHTM030 - ENDERECO RURAL - 5239 COM CARGA 09/09/2026 10:00 COD NÃO'
            },
            {
                'etapa_texto_header': '50 MANOBRA COM CORTE DE CARGA CP:1576 - SATELITAL UHTM030 09/09/2026 10:00 MANOBRA COM PIQUE',
                'equipamento': '22 - 346798', 'alimentador': 'UHTM030', 'executor': 'COD',
                'acao_bruta': '60 MA02 - FECHAR EQUIPAMENTO',
                'texto_linha': '60 MA02 - FECHAR EQUIPAMENTO 22 - 346798 UHTM030 - ENDERECO RURAL - 5252 COM CARGA 09/09/2026 10:00 COD NÃO CORTE DE CARGA',
                'observacao': 'CORTE DE CARGA'
            }
        ]
        falhas = validar_regra_44(manobra_dados)
        self.assertEqual(falhas, [], f"Não deveria haver falhas na Regra 44 para manobra válida: {falhas}")

    def test_regra_44_sequencia_fechar_antes_de_abrir(self):
        """Detecta erro se houver fechamento antes de abertura na etapa de pique"""
        manobra_dados = [
            {
                'etapa_texto_header': '20 MANOBRA COM PIQUE CP:100 - DADOS',
                'equipamento': '22 - 111111', 'executor': 'COD',
                'acao_bruta': '10 MA02 - FECHAR EQUIPAMENTO',
                'texto_linha': '10 MA02 - FECHAR EQUIPAMENTO 22 - 111111'
            },
            {
                'etapa_texto_header': '20 MANOBRA COM PIQUE CP:100 - DADOS',
                'equipamento': '22 - 222222', 'executor': 'COD',
                'acao_bruta': '20 MA01 - ABRIR EQUIPAMENTO',
                'texto_linha': '20 MA01 - ABRIR EQUIPAMENTO 22 - 222222'
            },
            {
                'etapa_texto_header': '20 MANOBRA COM PIQUE CP:100 - DADOS',
                'equipamento': '22 - 111111', 'executor': 'COD',
                'acao_bruta': '05 MA79 - CONFIRMAR EQUIPAMENTO COMUNICANDO',
                'texto_linha': '05 MA79 - CONFIRMAR EQUIPAMENTO COMUNICANDO 22 - 111111'
            }
        ]
        falhas = validar_regra_44(manobra_dados)
        self.assertTrue(any("Sequência irregular" in f for f in falhas), f"Deveria acusar sequência irregular: {falhas}")

    def test_regra_44_sem_ma79(self):
        """Detecta falta de MA79 quando há equipamento telecontrolado na etapa de pique"""
        manobra_dados = [
            {
                'etapa_texto_header': '20 MANOBRA COM PIQUE CP:100 - DADOS',
                'equipamento': '22 - 111111', 'executor': 'COD',
                'acao_bruta': '10 MA01 - ABRIR EQUIPAMENTO',
                'texto_linha': '10 MA01 - ABRIR EQUIPAMENTO 22 - 111111'
            },
            {
                'etapa_texto_header': '20 MANOBRA COM PIQUE CP:100 - DADOS',
                'equipamento': '22 - 222222', 'executor': 'COD',
                'acao_bruta': '20 MA02 - FECHAR EQUIPAMENTO',
                'texto_linha': '20 MA02 - FECHAR EQUIPAMENTO 22 - 222222'
            }
        ]
        falhas = validar_regra_44(manobra_dados)
        self.assertTrue(any("MA79" in f for f in falhas), f"Deveria acusar falta de MA79: {falhas}")

    def test_regra_44_sem_ma27_manual(self):
        """Detecta falta de MA27 para equipamento manual (ex: chave 28) operado na etapa de pique"""
        manobra_dados = [
            {
                'etapa_texto_header': '20 MANOBRA COM PIQUE CP:100 - DADOS',
                'equipamento': '28 - 999999', 'executor': 'REGIAO',
                'acao_bruta': '10 MA31 - ABRIR E SINALIZAR',
                'texto_linha': '10 MA31 - ABRIR E SINALIZAR 28 - 999999'
            },
            {
                'etapa_texto_header': '20 MANOBRA COM PIQUE CP:100 - DADOS',
                'equipamento': '22 - 222222', 'executor': 'COD',
                'acao_bruta': '20 MA02 - FECHAR EQUIPAMENTO',
                'texto_linha': '20 MA02 - FECHAR EQUIPAMENTO 22 - 222222'
            },
            {
                'etapa_texto_header': '20 MANOBRA COM PIQUE CP:100 - DADOS',
                'equipamento': '22 - 222222', 'executor': 'COD',
                'acao_bruta': '05 MA79 - CONFIRMAR EQUIPAMENTO COMUNICANDO',
                'texto_linha': '05 MA79 - CONFIRMAR EQUIPAMENTO COMUNICANDO 22 - 222222'
            }
        ]
        falhas = validar_regra_44(manobra_dados)
        self.assertTrue(any("Equipamento manual '28 - 999999' exige a macro MA27" in f for f in falhas), f"Deveria acusar falta de MA27: {falhas}")

    def test_regra_44_cp_invalido(self):
        """Valida exigências de formato do CP no cabeçalho"""
        # CP < 500 com VOZ (esperado DADOS)
        m1 = [{
            'etapa_texto_header': '20 MANOBRA COM PIQUE CP:200 - VOZ',
            'equipamento': '22 - 111111', 'executor': 'COD',
            'acao_bruta': '10 MA01 - ABRIR EQUIPAMENTO', 'texto_linha': '10 MA01'
        }]
        f1 = validar_regra_44(m1)
        self.assertTrue(any("CP:200 < 500 exige canal 'DADOS'" in f for f in f1))

        # CP >= 500 com DADOS (esperado VOZ ou SATELITAL)
        m2 = [{
            'etapa_texto_header': '20 MANOBRA COM PIQUE CP:1200 - DADOS',
            'equipamento': '22 - 111111', 'executor': 'COD',
            'acao_bruta': '10 MA01 - ABRIR EQUIPAMENTO', 'texto_linha': '10 MA01'
        }]
        f2 = validar_regra_44(m2)
        self.assertTrue(any("CP:1200 >= 500 exige canal 'VOZ' ou 'SATELITAL'" in f for f in f2))


if __name__ == '__main__':
    unittest.main()
