"""Regressões numéricas dos estudos e verificações das seis telas."""
import unittest
from copy import deepcopy
from pathlib import Path
import numpy as np
from dados import perfil,construir_sistema,ler_pysddp,DECK_PADRAO
from modelos_estudo import calcular,pl_unico,despacho_pddd
import graficos as g


def sistema_padrao(amigo=False,nh=2,carga=250):
    e=perfil('Comparação com amigo' if amigo else 'Estudo padronizado',mes=9 if amigo else 10)
    utes=[dict(Nome='ERB Candeias',Capac=17.,CVU=118.93),dict(Nome='BBF Baliza',Capac=10.,CVU=882.76)]
    s=construir_sistema(e,carga,e['uhes'][:nh],utes,e['cdef']);s['Meses']=e['meses']
    return s


class TestModelos(unittest.TestCase):
    def test_pl_pddd_padronizado(self):
        s=sistema_padrao()
        for c,esperado in [(0,2165869.03367484),(1,10020271.7874301)]:
            r=calcular('PDDD',s,cenario=c)
            self.assertAlmostEqual(r['custo'],esperado,places=2)
            self.assertLess(abs(r['custo']-r['referencia']),.01)

    def test_comparacao_amigo(self):
        r=calcular('PDDD',sistema_padrao(amigo=True))
        self.assertAlmostEqual(r['custo'],22138227.6766816,places=2)

    def test_arvore_nao_antecipacao_probabilidades(self):
        s=sistema_padrao();r=calcular('Árvore',s)
        self.assertEqual(len(r['nos']),7)
        self.assertAlmostEqual(r['custo'],4887012.6199014,places=2)
        for t in range(3):
            grupo=[n for n in r['nos'] if n['estagio']==t]
            self.assertAlmostEqual(sum(n['p'] for n in grupo),1.)
        alt=calcular('Árvore',s,probabilidades=(.3,.7))
        self.assertAlmostEqual(alt['nos'][3]['p'],.09)
        self.assertAlmostEqual(alt['nos'][6]['p'],.49)
        np.testing.assert_allclose(r['resumo']['Carga (MW)'],250.)

    def test_arvore_sem_incerteza_igual_pl(self):
        s=sistema_padrao()
        for u in s['UHE']:
            for par in u['Afl']:par[0]=par[1]
        r=calcular('Árvore',s)
        self.assertAlmostEqual(r['custo'],pl_unico(s,1,False)['DGer']['CustoTotal'],places=2)

    def test_pde_duais_e_grade(self):
        for nh in (1,2):
            s=sistema_padrao(nh=nh,carga=50 if nh==1 else 150)
            for u in s['UHE']:u['VI']=u['Vmin']
            r=calcular('PDE',s,niveis=4)
            self.assertEqual(len(r['pontos'][0]),4**nh)
            # Um corte do último estágio não pode superar o custo exato fora da grade.
            t=2;vi=[u['Vmin']+.37*(u['Vmax']-u['Vmin']) for u in s['UHE']]
            exato=np.mean([despacho_pddd(s,t,vi,c,[])['total'] for c in range(2)])
            for corte in r['cortes'][t]:
                self.assertLessEqual(sum(a*x for a,x in zip(corte['a'],vi))+corte['b'],exato+.01)

    def test_incrementais_e_dados_invalidos(self):
        e=perfil();utes=[dict(Nome='ERB Candeias',Capac=17.,CVU=118.93)]
        s=construir_sistema(e,100,e['uhes'],utes,8291,natureza='Natural total')
        self.assertAlmostEqual(s['UHE'][1]['Afl'][0][0],(99.049627-62.430444)*2.592)
        e['afluencias'][1][0][0]=1.
        with self.assertRaises(ValueError):construir_sistema(e,100,e['uhes'],utes,8291,natureza='Natural total')

    def test_escalas_e_series(self):
        for valor,un in [(50,'R$'),(50000,'R$ mil'),(5e7,'R$ milhões'),(5e10,'R$ bilhões')]:
            self.assertEqual(g.escala([valor])[1],un)
        s=sistema_padrao();r=calcular('PL',s);df=r['tabela']
        for nome,grupo in df.groupby('Cenário'):
            fig=g.geracao(grupo,s)
            np.testing.assert_allclose(sum(np.asarray(t.y) for t in fig.data[:-1]),250)
        fig=g.volumes(df,s)
        self.assertEqual(fig.layout.yaxis.title.text,'Volume (hm³)')

    @unittest.skipUnless(Path(DECK_PADRAO).is_dir(),'Deck local não disponível')
    def test_pysddp_historico(self):
        e=ler_pysddp(DECK_PADRAO,2015,9,24)
        self.assertEqual((e['meses'][0],e['meses'][-1]),('Set/2015','Ago/2017'))
        self.assertEqual(e['vazoes'].iloc[0]['Local Serra (m³/s)'],17.)
        s=construir_sistema(e,100,e['uhes'],[dict(Nome='ERB Candeias',Capac=17.,CVU=118.93),dict(Nome='BBF Baliza',Capac=10.,CVU=882.76)],8291)
        s['Meses']=e['meses'];r=calcular('PDDD',s,cenario=0,max_iteracoes=100)
        self.assertAlmostEqual(r['custo'],33164208.568,places=2)


class TestInterface(unittest.TestCase):
    def test_seis_menus_e_estado_independente(self):
        from streamlit.testing.v1 import AppTest
        at=AppTest.from_file(str(Path(__file__).parent/'app.py'),default_timeout=120).run()
        self.assertEqual(len(at.exception),0)
        at.number_input(key='pde1_estudo_carga').set_value(77.).run()
        at.radio(key='laboratorio').set_value('PL Único · 2 UHEs').run()
        self.assertEqual(at.number_input(key='pl_estudo_carga').value,250.)
        at.radio(key='laboratorio').set_value('PDE Didática · 1 UHE').run()
        self.assertEqual(at.number_input(key='pde1_estudo_carga').value,77.)
        for titulo,slug in [('PDE Didática · 1 UHE','pde1'),('PDE Didática · 2 UHEs','pde2'),
                            ('PL Único · 2 UHEs','pl'),('PL Único em árvore · 2 UHEs','arvore'),
                            ('PDDD · 2 UHEs','pddd')]:
            at.radio(key='laboratorio').set_value(titulo).run()
            at.button(key=slug+'_simular').click().run()
            self.assertEqual(len(at.exception),0,str(at.exception))
            self.assertEqual(len(at.error),0,str(at.error))
            self.assertGreater(len(at.get('plotly_chart')),0)
        if Path(DECK_PADRAO).is_dir():
            at.radio(key='laboratorio').set_value('PySDDP · histórico NEWAVE').run()
            at.selectbox(key='pysddp_historico_origem').select('Pasta neste computador').run()
            at.button(key='pysddp_simular').click().run()
            self.assertEqual(len(at.exception),0,str(at.exception))
            self.assertEqual(len(at.error),0,str(at.error))
            self.assertGreater(len(at.get('plotly_chart')),0)


if __name__=='__main__':unittest.main()
