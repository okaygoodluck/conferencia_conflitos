# src/integration/gdis_http_extrator.py
import requests
import os

class GDISHttpExtrator:
    def __init__(self):
        self.base_url = "http://gdis-pm/gdispm"

    def extrair_dados(self, num_manobra):
        # Extração via requests/HTTP puras (mais rápido que Playwright)
        return {}
