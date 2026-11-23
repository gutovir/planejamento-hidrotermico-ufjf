"""Regressão contra a seção 3 do Colab e verificações físicas e econômicas."""

import contextlib
import copy
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
import pandas as pd

import modelo_duas_uhes as modelo
from graficos_duas_uhes import figuras_fcf, geracao_mensal, custos_mensais, CORES
from validacao_duas_uhes import validar_simulacao, verificar_planos


class TestDuasUhes(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        caminho = Path("referencias_colab") / modelo.REFERENCIA_2U
        notebook = json.loads(caminho.read_text(encoding="utf-8"))
        cls.referencia = {"display": lambda *args: None}
        with contextlib.redirect_stdout(io.StringIO()):
            for indice in (37, 39, 41, 43):
                exec("".join(notebook["cells"][indice]["source"]), cls.referencia)
        cls.cfg = copy.deepcopy(modelo.CONFIG_2U)
        cls.batalha = modelo.AFL_NAT_BATALHA_2U[:3]
        cls.serra = modelo.AFL_NAT_SERRA_2U[:3]
        cls.vb, cls.vs, cls.cortes, cls.pontos = modelo.planejar_duas_uhes(
            cls.cfg, cls.batalha, cls.serra
        )
        cls.tabela = modelo.simular_duas_uhes(
            cls.cfg, cls.batalha, cls.serra, cls.cortes
        )

    def test_equivalencia_colab(self):
        self.assertEqual(modelo.CONFIG_2U, self.referencia["CONFIG_2U"])
        np.testing.assert_array_equal(
            modelo.AFL_NAT_BATALHA_2U, self.referencia["AFL_NAT_BATALHA_2U"]
        )
        np.testing.assert_array_equal(
            modelo.AFL_NAT_SERRA_2U, self.referencia["AFL_NAT_SERRA_2U"]
        )
        for estagio, pontos in self.pontos.items():
            pd.testing.assert_frame_equal(
                pontos, self.referencia["CUSTOS_2U"][estagio], check_exact=True
            )
            self.assertEqual(
                self.cortes[estagio], self.referencia["CORTES_2U"][estagio]
            )
        for nome, df in self.referencia["SIMULACAO_2U"].items():
            observado = self.tabela.loc[
                self.tabela["Cenário"] == nome, df.columns
            ].reset_index(drop=True)
            observado["Mês"] = df["Mês"]
            pd.testing.assert_frame_equal(observado, df, check_exact=True)

    def test_contabilidade_e_planos(self):
        self.assertTrue(validar_simulacao(self.tabela, self.cfg)["Aprovada"].all())
        auditoria = verificar_planos(self.pontos, self.cortes)
        self.assertLessEqual(auditoria.iloc[:, 1:].to_numpy().max(), 1e-5)

    def test_suporte_fora_da_malha(self):
        for estagio in range(1, 4):
            for fracao in (0.07, 0.19, 0.31, 0.43, 0.57, 0.69, 0.83):
                vb = self.vb[0] + fracao * (self.vb[-1] - self.vb[0])
                vs = self.vs[-1] - fracao * (self.vs[-1] - self.vs[0])
                resultados = [
                    modelo.despacho_hidrotermico_2uhes(
                        vb,
                        vs,
                        self.batalha[estagio - 1, c],
                        max(
                            0.0,
                            self.serra[estagio - 1, c] - self.batalha[estagio - 1, c],
                        ),
                        self.cortes[estagio + 1],
                        cfg=self.cfg,
                    )
                    for c in range(2)
                ]
                esperado = np.mean([r["fob"] for r in resultados])
                aproximado = max(
                    0,
                    max(
                        p["a"] * vb + p["b"] * vs + p["c"] for p in self.cortes[estagio]
                    ),
                )
                self.assertLessEqual(aproximado - esperado, 1e-5)

    def test_figuras_usam_mesmos_custos(self):
        for pontos in self.pontos.values():
            calor, superficie = figuras_fcf(pontos, self.vb, self.vs)
            custos = modelo.matriz_custos(pontos, self.vb, self.vs)
            divisor = 1_000_000 if abs(custos).max() >= 1_000_000 else 1
            z = custos / divisor
            np.testing.assert_array_equal(calor.data[0].z, z)
            np.testing.assert_array_equal(superficie.data[0].z, z)
        for nome in modelo.CENARIOS_2U:
            grafico = geracao_mensal(self.tabela, nome)
            soma = np.array([serie.y for serie in grafico.data]).sum(axis=0)
            np.testing.assert_allclose(soma, self.cfg["carga_mwmed"], rtol=0, atol=1e-5)

    def test_graficos_da_ultima_versao_colab(self):
        from pyecharts import options as opts
        from plotly.graph_objects import Figure

        notebook = json.loads(
            (Path("referencias_colab") / modelo.REFERENCIA_2U).read_text(
                encoding="utf-8"
            )
        )
        referencia = dict(self.referencia, opts=opts, HTML=lambda html: html)
        with contextlib.redirect_stdout(io.StringIO()), patch.object(Figure, "show"):
            for indice in (47, 49):
                exec("".join(notebook["cells"][indice]["source"]), referencia)
        estagio = referencia["ESTAGIO_FCF_3D"]
        calor, superficie = figuras_fcf(self.pontos[estagio], self.vb, self.vs)
        np.testing.assert_array_equal(
            superficie.data[0].z, referencia["fig_3d"].data[0].z
        )
        np.testing.assert_array_equal(
            superficie.data[0].customdata, referencia["custos_reais"]
        )
        np.testing.assert_array_equal(calor.data[0].z, superficie.data[0].z)
        for ib, js, custo in referencia["g"].options["series"][0]["data"]:
            self.assertEqual(calor.data[0].z[js, ib], custo)

    def test_formatacao_monetaria_fcf(self):
        for custos, divisor, unidade in (
            (np.array([[0.0, 10.0], [40.0, 50.0]]), 1, "R$"),
            (np.zeros((2, 2)), 1, "R$"),
            (
                np.array([[0.0, 1_000_000.0], [1_234_567.89, 2_000_000.0]]),
                1_000_000,
                "milhões de R$",
            ),
        ):
            vb = np.array([430.05, 1781.61])
            vs = np.array([1752.0, 5199.0])
            pontos = pd.DataFrame(
                [
                    {
                        "VI Batalha (hm³)": b,
                        "VI Serra (hm³)": s,
                        "FOB esperada (R$)": custos[j, i],
                    }
                    for j, s in enumerate(vs)
                    for i, b in enumerate(vb)
                ]
            )
            original = pontos.copy(deep=True)
            calor, superficie = figuras_fcf(pontos, vb, vs)
            for fig in (calor, superficie):
                serie = fig.data[0]
                np.testing.assert_array_equal(serie.z, custos / divisor)
                self.assertTrue(
                    serie.colorbar.title.text.startswith(f"Custo esperado ({unidade})")
                )
                self.assertEqual(serie.colorbar.tickformat, ",.2f")
                self.assertEqual(serie.colorbar.exponentformat, "none")
                self.assertEqual(serie.colorbar.showexponent, "none")
                self.assertEqual(fig.layout.separators, ",.")
                if serie.type == "heatmap":
                    self.assertIn("R$ %{customdata[2]:,.2f}", serie.hovertemplate)
                    np.testing.assert_array_equal(
                        np.asarray(serie.customdata)[:, :, 2], custos
                    )
                else:
                    self.assertIn("R$ %{customdata:,.2f}", serie.hovertemplate)
                    np.testing.assert_array_equal(serie.customdata, custos)
            self.assertEqual(
                superficie.layout.scene.zaxis.title.text, f"Custo esperado ({unidade})"
            )
            self.assertEqual(superficie.layout.scene.zaxis.tickformat, ",.2f")
            np.testing.assert_array_equal(
                np.asarray(calor.data[0].customdata)[:, :, 2],
                superficie.data[0].customdata,
            )
            pd.testing.assert_frame_equal(pontos, original, check_exact=True)
            np.testing.assert_array_equal(modelo.matriz_custos(pontos, vb, vs), custos)

    def test_mapa_percentual_volume_util(self):
        for niveis in (5, 9):
            cfg = dict(self.cfg, niveis_batalha=niveis, niveis_serra=niveis)
            vb, vs, _, pontos = modelo.planejar_duas_uhes(cfg, self.batalha, self.serra)
            original = pontos[1].copy(deep=True)
            calor, superficie = figuras_fcf(pontos[1], vb, vs)
            percentual = np.linspace(0, 100, niveis)
            np.testing.assert_allclose(calor.data[0].x, percentual, rtol=0, atol=1e-10)
            np.testing.assert_allclose(calor.data[0].y, percentual, rtol=0, atol=1e-10)
            rotulos = [f"{p:g}%".replace(".", ",") for p in percentual]
            self.assertEqual(list(calor.layout.xaxis.ticktext), rotulos)
            self.assertEqual(list(calor.layout.yaxis.ticktext), rotulos)
            self.assertEqual(calor.layout.xaxis.type, "category")
            self.assertEqual(calor.layout.yaxis.type, "category")
            self.assertEqual(list(calor.layout.xaxis.range), [-0.5, niveis - 0.5])
            self.assertEqual(list(calor.layout.yaxis.range), [-0.5, niveis - 0.5])
            dados = np.asarray(calor.data[0].customdata)
            malha_b, malha_s = np.meshgrid(vb, vs)
            np.testing.assert_array_equal(dados[:, :, 0], malha_b)
            np.testing.assert_array_equal(dados[:, :, 1], malha_s)
            np.testing.assert_array_equal(
                dados[:, :, 2], modelo.matriz_custos(pontos[1], vb, vs)
            )
            np.testing.assert_array_equal(calor.data[0].z, superficie.data[0].z)
            np.testing.assert_array_equal(superficie.data[0].x, vb)
            np.testing.assert_array_equal(superficie.data[0].y, vs)
            pd.testing.assert_frame_equal(pontos[1], original, check_exact=True)

    def test_cargas_horizontes_discretizacoes(self):
        for meses, carga, nb, ns in (
            (3, 0.0, 2, 2),
            (3, 100.0, 3, 4),
            (3, 150.0, 5, 5),
            (6, 200.0, 3, 3),
            (12, 50.0, 5, 5),
            (3, 300.0, 2, 2),
        ):
            with self.subTest(meses=meses, carga=carga):
                cfg = dict(
                    self.cfg,
                    meses=meses,
                    carga_mwmed=carga,
                    niveis_batalha=nb,
                    niveis_serra=ns,
                )
                b = modelo.AFL_NAT_BATALHA_2U[:meses]
                s = modelo.AFL_NAT_SERRA_2U[:meses]
                vb, vs, cortes, pontos = modelo.planejar_duas_uhes(cfg, b, s)
                tabela = modelo.simular_duas_uhes(cfg, b, s, cortes)
                self.assertEqual(len(pontos), meses)
                self.assertTrue(all(len(df) == nb * ns for df in pontos.values()))
                self.assertEqual(len(tabela), meses * 2)
                self.assertTrue(validar_simulacao(tabela, cfg)["Aprovada"].all())
                grafico = custos_mensais(tabela)
                divisor = (
                    1_000_000
                    if tabela["Custo imediato (R$)"].abs().max() >= 1_000_000
                    else 1
                )
                for serie in grafico.data:
                    custos = tabela.loc[
                        tabela["Cenário"] == serie.name, "Custo imediato (R$)"
                    ]
                    np.testing.assert_array_equal(serie.y, custos / divisor)
                    np.testing.assert_array_equal(serie.customdata, custos)
                if meses == 12 and carga == 50.0:
                    self.assertLess(tabela["Custo imediato (R$)"].sum(), 100.0)
                    self.assertEqual(
                        grafico.layout.yaxis.title.text, "Custo imediato (R$)"
                    )
                if carga == 300.0:
                    self.assertTrue((tabela["Déficit (MW)"] > 0).all())

    def test_formatacao_monetaria_custo_imediato(self):
        for valores, divisor, unidade in (
            ([0.0, 0.0, 13.33, 8.52], 1, "R$"),
            ([0.0, 0.0, 0.0, 0.0], 1, "R$"),
            ([0.01, 999_999.99, 0.0, 1.0], 1, "R$"),
            (
                [0.0, 1_000_000.0, 1_234_567.89, 2_000_000.01],
                1_000_000,
                "milhões de R$",
            ),
        ):
            tabela = pd.DataFrame(
                {
                    "Cenário": ["Pessimista", "Pessimista", "Otimista", "Otimista"],
                    "Mês": ["Nov · 2026", "Dez · 2026"] * 2,
                    "Custo imediato (R$)": valores,
                    "Custo futuro alpha (R$)": [99_000_000.0] * 4,
                }
            )
            original = tabela.copy(deep=True)
            grafico = custos_mensais(tabela)
            self.assertEqual(
                grafico.layout.yaxis.title.text, f"Custo imediato ({unidade})"
            )
            self.assertEqual(grafico.layout.yaxis.tickformat, ",.2f")
            self.assertEqual(grafico.layout.yaxis.exponentformat, "none")
            self.assertEqual(grafico.layout.separators, ",.")
            self.assertEqual(grafico.layout.barmode, "group")
            for serie in grafico.data:
                custos = tabela.loc[
                    tabela["Cenário"] == serie.name, "Custo imediato (R$)"
                ]
                np.testing.assert_array_equal(serie.y, custos / divisor)
                np.testing.assert_array_equal(serie.customdata, custos)
                self.assertEqual(serie.marker.color, CORES[serie.name])
            if valores[-1] == 8.52:
                self.assertEqual(grafico.data[1].text[-1], "8,52")
            if divisor == 1_000_000:
                self.assertEqual(grafico.data[1].text[0], "1.234.567,89")
            pd.testing.assert_frame_equal(tabela, original, check_exact=True)

    def test_horizonte_de_dois_anos(self):
        for meses in (18, 24):
            cfg = dict(self.cfg, meses=meses)
            batalha = np.tile(modelo.AFL_NAT_BATALHA_2U, (2, 1))[:meses]
            serra = np.tile(modelo.AFL_NAT_SERRA_2U, (2, 1))[:meses]
            vb, vs, cortes, pontos = modelo.planejar_duas_uhes(cfg, batalha, serra)
            tabela = modelo.simular_duas_uhes(cfg, batalha, serra, cortes)
            self.assertEqual(len(pontos), meses)
            self.assertEqual(len(tabela), meses * 2)
            self.assertTrue(validar_simulacao(tabela, cfg)["Aprovada"].all())
            self.assertEqual(tabela.iloc[12]["Mês"], "Jan · 2027")
            for estagio in range(1, meses + 1):
                calor, superficie = figuras_fcf(pontos[estagio], vb, vs)
                np.testing.assert_array_equal(calor.data[0].z, superficie.data[0].z)

    def test_incremental_negativa_e_custos_reservatorios_cheios(self):
        cfg = dict(self.cfg, meses=3, niveis_batalha=2, niveis_serra=2)
        b = np.full((3, 2), 100.0)
        s = np.full((3, 2), 50.0)
        _, _, cortes, _ = modelo.planejar_duas_uhes(cfg, b, s)
        tabela = modelo.simular_duas_uhes(cfg, b, s, cortes)
        self.assertTrue((tabela["Afl incremental Serra (m³/s)"] == 0).all())
        self.assertTrue(validar_simulacao(tabela, cfg)["Aprovada"].all())
        for c in range(2):
            r = modelo.despacho_hidrotermico_2uhes(
                self.vb[-1],
                self.vs[-1],
                self.batalha[2, c],
                self.serra[2, c] - self.batalha[2, c],
                cfg=self.cfg,
            )
            self.assertAlmostEqual(
                r["fob"], 0.01 * 2.592 * (r["vv_b"] + r["vv_s"]), places=6
            )
            self.assertAlmostEqual(
                r["gt_c"] + r["gt_a"] + r["def"] + r["alpha"], 0, places=6
            )


if __name__ == "__main__":
    unittest.main()
