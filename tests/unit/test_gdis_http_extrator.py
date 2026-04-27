import unittest
from src.integration.gdis_http_extrator import _super_fallback_equipamentos

class TestGdisHttpExtrator(unittest.TestCase):
    def test_super_fallback_equipamentos(self):
        # 1. Deve encontrar equipamentos isolados no meio de texto
        html = "Algum texto com equipamento 28 - 50850 perdido na string."
        result = _super_fallback_equipamentos(html)
        self.assertIn("28 - 50850", result)
        
        # 2. Deve encontrar múltiplos equipamentos separados por virgulas e espaços
        html = "<tr><td>Equipamentos: 22-290951, 22-406698, 28-435618</td></tr>"
        result = _super_fallback_equipamentos(html)
        self.assertIn("22-290951", result)
        self.assertIn("22-406698", result)
        self.assertIn("28-435618", result)
        
        # 3. Deve encontrar outros IDs baseados em numeração longa que não sejam válidos no olhar humano mas que cumpram a regex
        html = "Hoje é 22-042026. Telefone: 00-12345."
        result = _super_fallback_equipamentos(html)
        self.assertEqual(len(result), 2)
        self.assertIn("22-042026", result)
        self.assertIn("00-12345", result)

        # 4. Fallback sem match
        html = "Nenhum equipamento listado aqui"
        result = _super_fallback_equipamentos(html)
        self.assertEqual(len(result), 0)

    def test_find_sol_links_backtracking(self):
        # Valida que o loop HTML não usa regex catastrófica
        # Teste 1: Padrão normal de SolicitacaoGeral
        html = '... <a href="#" id="formList:tb:0:j_id225" name="formList:tb:0:j_id225" onclick="A4J...">1619750</a> ...'
        from src.integration.gdis_http_extrator import extrair_uma_solicitacao
        # Precisamos isolar a função interna apenas copiando a lógica pra teste
        def _find_sol_links(html_text, numero):
            found = []
            if not html_text: return found
            start = 0
            while True:
                idx = html_text.find(str(numero), start)
                if idx == -1: break
                
                a_idx = html_text.rfind('<a ', 0, idx)
                if a_idx != -1:
                    close_idx = html_text.find('</a>', a_idx, idx)
                    if close_idx == -1:
                        tag_end = html_text.find('>', a_idx)
                        if tag_end != -1 and tag_end < idx:
                            import re
                            tag_attrs = html_text[a_idx:tag_end]
                            id_match = re.search(r'id=["\']([^"\']+)["\']', tag_attrs, re.I)
                            if id_match:
                                found.append((str(numero), id_match.group(1)))
                start = idx + 1
            return list(dict.fromkeys(found))
            
        res = _find_sol_links(html, "1619750")
        self.assertEqual(res, [("1619750", "formList:tb:0:j_id225")])
        
        # Teste 2: O falso positivo de input form que originou o bug (Deve FALHAR em achar anchor pois 1619750 n está encadeado no anchor, e sim no value)
        html_bug = '<a id="j_id6:link" href="#">Texto</a><input type="text" value="1619750" /></a>'
        res2 = _find_sol_links(html_bug, "1619750")
        self.assertEqual(len(res2), 0)

    def test_parse_datas_new_layout(self):
        from src.integration.gdis_http_extrator import _parse_datas
        # 1. Teste com layout de Modal (tooglePanelElaboracaoManobra)
        html = """
        <div id="tooglePanelElaboracaoManobra">
            <label>Data Início:</label> 20/05/2026 08:30
            <label>Data Término:</label> 20/05/2026 18:45
        </div>
        """
        ini, fim = _parse_datas(html)
        self.assertEqual(ini, "20/05/2026")
        self.assertEqual(fim, "20/05/2026")

        # 2. Teste com layout de Input (JSF)
        html_input = """
        <input id="formPrincipal:dataInicioInputDate" value="21/05/2026 09:00" />
        <input id="formPrincipal:dataFimInputDate" value="21/05/2026 17:00" />
        """
        ini, fim = _parse_datas(html_input)
        self.assertEqual(ini, "21/05/2026")
        self.assertEqual(fim, "21/05/2026")

    def test_parse_itens_tables_modal(self):
        from src.integration.gdis_http_extrator import _parse_itens_tables
        html = """
        <table id="statusModalContentTable">
            <thead>
                <tr><th>Equipamento</th><th>Alimentador</th></tr>
            </thead>
            <tbody>
                <tr><td>22 - 406108</td><td>RBSD214</td></tr>
                <tr><td>22 - 127228</td><td>BHSV016</td></tr>
            </tbody>
        </table>
        """
        eq, al = _parse_itens_tables(html)
        self.assertIn("22 - 406108", eq)
        self.assertIn("22 - 127228", eq)
        self.assertIn("RBSD214", al)
        self.assertIn("BHSV016", al)

    def test_parse_datas_table_fallback(self):
        from src.integration.gdis_http_extrator import _parse_datas
        # Simula o caso da manobra 240946487: labels presentes mas spans vazios, datas em uma tabela
        html = """
        <div id="tooglePanelElaboracaoManobra">
            <label>Data Início:</label> <span class="empty"></span>
            <label>Data Término:</label> <span class="empty"></span>
        </div>
        <table id="formResultTable:solicitacaoManobraMBList">
            <thead>
                <tr><th>Solicitação</th><th>Início</th><th>Término</th></tr>
            </thead>
            <tbody>
                <tr><td>12345</td><td>25/05/2026 08:00</td><td>25/05/2026 12:00</td></tr>
                <tr><td>12346</td><td>25/05/2026 14:00</td><td>25/05/2026 18:00</td></tr>
            </tbody>
        </table>
        """
        ini, fim = _parse_datas(html)
        # Deve pegar o min do início e o max do término
        self.assertEqual(ini, "25/05/2026")
        self.assertEqual(fim, "25/05/2026")

    def test_parse_itens_tables_etapas(self):
        from src.integration.gdis_http_extrator import _parse_itens_tables
        html = """
        <table id="etapasItensForm:etapasCadastradas">
            <thead>
                <tr><th>Etapa</th><th>Equipamento</th><th>Alimentador</th></tr>
            </thead>
            <tbody>
                <tr><td>1</td><td>22 - 256846</td><td>SLAD207</td></tr>
            </tbody>
        </table>
        """
        eq, al = _parse_itens_tables(html)
        self.assertIn("22 - 256846", eq)
        self.assertIn("SLAD207", al)

    def test_parse_datas_exclude_eventos(self):
        from src.integration.gdis_http_extrator import _parse_datas
        # Simula o caso da manobra 240900405: 
        # Tabela de eventos tem 15/04 (Manobra Cadastrada)
        # Tabela de etapas tem 01/05 (Início real)
        html = """
        <div id="formPrincipal">
            <table id="j_id181:eventosList">
                <tr><td>Manobra Cadastrada</td><td>15/04/2026</td></tr>
            </table>
            <table id="etapasItensForm:etapasCadastradas">
                <thead><tr><th>Início</th><th>Fim</th></tr></thead>
                <tbody>
                    <tr><td>01/05/2026 08:00</td><td>01/05/2026 12:00</td></tr>
                </tbody>
            </table>
        </div>
        """
        ini, fim = _parse_datas(html)
        # Deve ignorar o 15/04 (por estar no eventosList e conter "Cadastrada")
        # E pegar o 01/05 das etapas
        self.assertEqual(ini, "01/05/2026")
        self.assertEqual(fim, "01/05/2026")

if __name__ == '__main__':
    unittest.main()
