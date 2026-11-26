import unittest
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile
from unittest.mock import patch
from upload_deck import ler_zip_newave


def criar_zip(arquivos):
    b=BytesIO()
    with ZipFile(b,'w') as z:
        for nome,valor in arquivos:z.writestr(nome,valor)
    return b.getvalue()


def arquivos_minimos(prefixo='caso/'):
    return [(prefixo+'caso.dat','arquivos.dat\n'),
            (prefixo+'arquivos.dat','DADOS GERAIS'.ljust(30)+'dger.dat\n'),
            (prefixo+'hidr.dat',b'cadastro'),(prefixo+'vazoes.dat',b'vazoes'),
            (prefixo+'confhd.dat','configuracao'),(prefixo+'dger.dat','gerais')]


class TestUpload(unittest.TestCase):
    def test_zip_na_raiz_e_em_pasta_com_normalizacao(self):
        for prefixo in ('','caso/nw202610/'):
            caminhos=[]
            def ler(pasta,*args):
                caminhos.append(Path(pasta))
                self.assertTrue((pasta/'HIDR.DAT').exists())
                self.assertEqual((pasta/'CASO.DAT').read_text(),'ARQUIVOS.DAT\n')
                self.assertIn('DGER.DAT',(pasta/'ARQUIVOS.DAT').read_text())
                return {'meses':['Set/2015'],'valor':123}
            with patch('upload_deck.ler_pysddp',side_effect=ler):
                r=ler_zip_newave(criar_zip(arquivos_minimos(prefixo)))
            self.assertEqual(r['valor'],123)
            self.assertFalse(caminhos[0].exists())

    def test_rejeita_caminhos_externos(self):
        for nome in ('../../fora.dat','/fora.dat','C:\\fora.dat'):
            with self.assertRaisesRegex(ValueError,'caminho inválido'):
                ler_zip_newave(criar_zip(arquivos_minimos()+[(nome,b'x')]))

    def test_rejeita_indirecao_externa(self):
        itens=arquivos_minimos();itens[0]=(itens[0][0],'../../segredo\n')
        with self.assertRaisesRegex(ValueError,'CASO.DAT'):
            ler_zip_newave(criar_zip(itens))
        itens=arquivos_minimos();itens[1]=(itens[1][0],'DADOS GERAIS'.ljust(30)+'../segredo\n')
        with self.assertRaisesRegex(ValueError,'arquivo de entradas'):
            ler_zip_newave(criar_zip(itens))

    def test_erros_de_formato_duplicidade_e_caso_ausente(self):
        for conteudo in (b'nao e zip',b''):
            with self.assertRaises(ValueError):ler_zip_newave(conteudo)
        with self.assertRaisesRegex(ValueError,'duplicados'):
            ler_zip_newave(criar_zip(arquivos_minimos()+[('caso/HIDR.DAT',b'outro')]))
        with self.assertRaisesRegex(ValueError,'único caso'):
            ler_zip_newave(criar_zip([('qualquer.txt','texto')]))


if __name__=='__main__':unittest.main()
