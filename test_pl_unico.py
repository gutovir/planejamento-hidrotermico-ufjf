"""Equivalência do PL determinístico com a seção 5 do notebook oficial."""

import ast
import contextlib
import copy
import io
import json
from pathlib import Path
import unittest

from cvxopt.modeling import variable, solvers, op
import numpy as np
import pandas as pd

import modelo_pl_unico as modelo
from laboratorio_pl_unico import tabela_visual_pl
from graficos_duas_uhes import geracao_mensal, armazenamento, custos_mensais


class TestPlUnico(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.notebook = json.loads(
            (Path("referencias_colab") / modelo.REFERENCIA_PL).read_text(
                encoding="utf-8"
            )
        )
        cls.referencia = {
            "display": lambda *args: None,
            "variable": variable,
            "solvers": solvers,
            "op": op,
        }
        with contextlib.redirect_stdout(io.StringIO()):
            exec("".join(cls.notebook["cells"][66]["source"]), cls.referencia)
            for indice in (68, 70):
                funcoes = [
                    n
                    for n in ast.parse(
                        "".join(cls.notebook["cells"][indice]["source"])
                    ).body
                    if isinstance(n, ast.FunctionDef)
                ]
                exec(
                    compile(
                        ast.Module(body=funcoes, type_ignores=[]),
                        "<Colab oficial PL>",
                        "exec",
                    ),
                    cls.referencia,
                )
        cls.cfg = dict(modelo.CONFIG_PL)
        cls.sistema = modelo.construir_sistema(
            cls.cfg, modelo.AFL_NAT_BATALHA_PL[:3], modelo.AFL_NAT_SERRA_PL[:3]
        )
        cls.resultados, cls.tabela = modelo.resolver_cenarios(cls.sistema)

    def test_equivalencia_colab(self):
        for nome, indice in (("Pessimista", 1), ("Otimista", 0)):
            esperado = self.referencia["pl_unico"](self.referencia["sistema"], indice)
            observado = self.resultados[nome]
            for chave in ("CustoTotal", "CustoImediato", "CMO", "Deficit"):
                np.testing.assert_allclose(
                    observado["DGer"][chave], esperado["DGer"][chave], rtol=0, atol=1e-8
                )
            for obtido, original in zip(observado["UHE"], esperado["UHE"]):
                for chave in ("vf", "vt", "vv", "cma"):
                    np.testing.assert_allclose(
                        obtido[chave], original[chave], rtol=0, atol=1e-8
                    )
            for obtido, original in zip(observado["UTE"], esperado["UTE"]):
                np.testing.assert_allclose(
                    obtido["gt"], original["gt"], rtol=0, atol=1e-8
                )
            tabela_ref = self.referencia["tabela_resultados"](
                self.referencia["sistema"], esperado
            )
            tabela_app = self.tabela.loc[
                self.tabela["Cenário"] == nome, tabela_ref.columns
            ].reset_index(drop=True)
            tabela_app["Mês"] = tabela_ref["Mês"]
            pd.testing.assert_frame_equal(tabela_app, tabela_ref, check_exact=True)

    def test_unidades_e_ordem_dos_cenarios(self):
        for i, (serie, chave) in enumerate(
            (
                (modelo.AFL_NAT_BATALHA_PL, "vi_batalha"),
                (
                    np.maximum(0, modelo.AFL_NAT_SERRA_PL - modelo.AFL_NAT_BATALHA_PL),
                    "vi_serra",
                ),
            )
        ):
            u = self.sistema["UHE"][i]
            np.testing.assert_array_equal(u["Afl"], serie[:3, [1, 0]] * 2.592)
            self.assertEqual(u["VI"], self.cfg[chave])
        self.assertEqual(self.sistema["UHE"][0]["Jusante"], 1)
        self.assertAlmostEqual(self.sistema["UHE"][0]["Prod"] * modelo.K_PL, 0.3551)
        self.assertAlmostEqual(self.sistema["UHE"][1]["Engol"] / modelo.K_PL, 313.0)
        antes = copy.deepcopy(modelo.UHES_PL)
        cfg = dict(self.cfg, vi_batalha=700.0)
        sistema = modelo.construir_sistema(
            cfg, modelo.AFL_NAT_BATALHA_PL[:3], modelo.AFL_NAT_SERRA_PL[:3]
        )
        self.assertEqual(sistema["UHE"][0]["VI"], 700.0)
        self.assertEqual(modelo.UHES_PL, antes)

    def test_horizontes_e_cargas(self):
        for meses, carga in ((3, 0.0), (3, 50.0), (3, 200.0), (12, 150.0), (24, 300.0)):
            with self.subTest(meses=meses, carga=carga):
                cfg = dict(self.cfg, meses=meses, carga=carga)
                batalha = np.tile(modelo.AFL_NAT_BATALHA_PL, (2, 1))[:meses]
                serra = np.tile(modelo.AFL_NAT_SERRA_PL, (2, 1))[:meses]
                sistema = modelo.construir_sistema(cfg, batalha, serra)
                resultados, tabela = modelo.resolver_cenarios(sistema)
                self.assertEqual(len(tabela), meses * 2)
                for resultado in resultados.values():
                    self.assertTrue(
                        modelo.validar_resultado(sistema, resultado)["Aprovada"].all()
                    )
                    self.assertEqual(len(resultado["UHE"][0]["vf"]), meses)
                if meses == 24:
                    self.assertEqual(tabela.iloc[12]["Mês"], "Jan · 2027")

    def test_graficos_padronizados(self):
        visual = tabela_visual_pl(self.tabela)
        for nome in self.resultados:
            figura = geracao_mensal(visual, nome, self.sistema["DGer"]["Carga"])
            self.assertEqual(figura.layout.title.text, f"Geração mensal — {nome}")
            barras = [s for s in figura.data if s.type == "bar"]
            self.assertEqual(len(barras), 5)
            np.testing.assert_allclose(
                np.array([s.y for s in barras]).sum(axis=0), 150.0, rtol=0, atol=1e-5
            )
            np.testing.assert_array_equal(figura.data[-1].y, [150.0] * 3)
        limites = {
            nome: {"vmin": u["Vmin"], "vmax": u["Vmax"]}
            for nome, u in zip(("Batalha", "Serra do Facão"), self.sistema["UHE"])
        }
        volume = armazenamento(visual, limites=limites, mostrar_limites=False)
        self.assertEqual(volume.layout.title.text, "Volume final das UHEs (% útil)")
        self.assertEqual(len(volume.data), 4)
        for serie in volume.data:
            self.assertEqual(serie.x[0], "Inicial")
            self.assertEqual(serie.y[0], 0.0)
            self.assertEqual(len(serie.y), 4)
        custo = custos_mensais(visual)
        self.assertEqual(custo.layout.title.text, "Custo imediato mensal")
        for serie in custo.data:
            valores = self.tabela.loc[
                self.tabela["Cenário"] == serie.name, "Custo imediato (R$)"
            ]
            np.testing.assert_array_equal(serie.customdata, valores)


if __name__ == "__main__":
    unittest.main()
