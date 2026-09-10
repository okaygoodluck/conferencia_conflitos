import unittest
import os
import sys

base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if base_dir not in sys.path:
    sys.path.insert(0, base_dir)

from src.core.verificador_conflitos import (
    SITUACOES_LABEL,
    _parse_situacoes_env,
    _normalize_situacoes,
    DIVISAS_MALHAS,
    obter_divisas_malha,
    expandir_malhas_com_divisas,
)


class TestVerificadorConflitosSituacoes(unittest.TestCase):

    def test_situacao_incompleta_presente(self):
        """Garante que a situação 'IN' (INCOMPLETA) está mapeada e presente por padrão."""
        self.assertIn("IN", SITUACOES_LABEL)
        self.assertEqual(SITUACOES_LABEL["IN"], "INCOMPLETA")

    def test_situacoes_padrao_todas_marcadas(self):
        """Garante que as situações padrão incluem todas as 5: EB, EN, IN, CO, EA."""
        padrao = _parse_situacoes_env()
        self.assertIn("EB", padrao)
        self.assertIn("EN", padrao)
        self.assertIn("IN", padrao)
        self.assertIn("CO", padrao)
        self.assertIn("EA", padrao)

    def test_normalize_situacoes_com_incompleta(self):
        """Valida normalização de strings com 'IN' e minúsculas."""
        norm = _normalize_situacoes(["eb", "in", "co"])
        self.assertEqual(norm, ["EB", "IN", "CO"])

    def test_divisas_malhas_geograficas(self):
        """Valida as regras de divisas solicitadas para cada uma das 6 regiões."""
        # Norte -> Triangulo, Centro, Leste
        self.assertEqual(sorted(obter_divisas_malha("NT")), sorted(["TA", "CN", "LE"]))
        # Triangulo -> Norte, Centro, Sul
        self.assertEqual(sorted(obter_divisas_malha("TA")), sorted(["NT", "CN", "SU"]))
        # Centro -> Todos
        self.assertEqual(sorted(obter_divisas_malha("CN")), sorted(["NT", "LE", "MQ", "SU", "TA"]))
        # Leste -> Centro, Norte, Mantiqueira
        self.assertEqual(sorted(obter_divisas_malha("LE")), sorted(["CN", "NT", "MQ"]))
        # Mantiqueira -> Centro, Leste, Sul
        self.assertEqual(sorted(obter_divisas_malha("MQ")), sorted(["CN", "LE", "SU"]))
        # Sul -> Triangulo, Centro, Mantiqueira
        self.assertEqual(sorted(obter_divisas_malha("SU")), sorted(["TA", "CN", "MQ"]))

    def test_expandir_malhas_com_divisas(self):
        """Valida a função de expansão de lista de malhas."""
        expandido_nt = expandir_malhas_com_divisas(["NT"])
        self.assertEqual(expandido_nt, sorted(["NT", "TA", "CN", "LE"]))

        expandido_cn = expandir_malhas_com_divisas(["CN"])
        self.assertEqual(expandido_cn, sorted(["CN", "NT", "LE", "MQ", "SU", "TA"]))


if __name__ == '__main__':
    unittest.main()
