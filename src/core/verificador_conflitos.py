import os
import sys
from .verificador_regras_solicitacao import VerificadorRegrasSolicitacao

class VerificadorConflitos:
    def __init__(self):
        self.verificador = VerificadorRegrasSolicitacao(use_headless=True)

    def executar(self, solicitacao_id):
        # Ponto de entrada para a lógica de conflitos entre manobras
        pass
