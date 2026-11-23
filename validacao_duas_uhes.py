"""Conferência contábil e dos planos de suporte do laboratório em cascata."""

import numpy as np
import pandas as pd

from modelo_duas_uhes import UHES_2U


def validar_simulacao(tabela, cfg, atol=1e-5):
    verificacoes = []

    def conferir(nome, observado, esperado):
        observado = np.asarray(observado, dtype=float)
        esperado = np.asarray(esperado, dtype=float)
        erro = float(np.max(np.abs(observado - esperado), initial=0))
        verificacoes.append(
            {"Verificação": nome, "Erro máximo": erro, "Aprovada": erro <= atol}
        )

    k = cfg["k_hm3"]
    for cenario, df in tabela.groupby("Cenário", sort=False):
        for usina, sufixo in (("Batalha", "batalha"), ("Serra", "serra")):
            limites = UHES_2U["Batalha" if usina == "Batalha" else "Serra do Facão"]
            vi = df[f"VI {usina} (hm³)"].to_numpy()
            vf = df[f"VF {usina} (hm³)"].to_numpy()
            vt = df[f"VT {usina} (m³/s)"].to_numpy()
            vv = df[f"VV {usina} (m³/s)"].to_numpy()
            entrada = df["Afl Batalha (m³/s)"].to_numpy()
            if usina == "Serra":
                entrada = (
                    df["Afl incremental Serra (m³/s)"]
                    + df["VT Batalha (m³/s)"]
                    + df["VV Batalha (m³/s)"]
                ).to_numpy()
            conferir(f"{cenario} · balanço {usina}", vf, vi + k * (entrada - vt - vv))
            conferir(f"{cenario} · continuidade {usina}", vi[1:], vf[:-1])
            conferir(
                f"{cenario} · volume inicial {usina}",
                vi[0],
                cfg[f"volume_inicial_{sufixo}"],
            )
            conferir(
                f"{cenario} · geração {usina}",
                df[f"GH {usina} (MW)"],
                limites["rho"] * vt,
            )
            conferir(
                f"{cenario} · limites VI {usina}",
                vi,
                np.clip(vi, limites["vmin"], limites["vmax"]),
            )
            conferir(
                f"{cenario} · limites VF {usina}",
                vf,
                np.clip(vf, limites["vmin"], limites["vmax"]),
            )
            conferir(
                f"{cenario} · turbinamento {usina}",
                vt,
                np.clip(vt, 0, limites["engol"]),
            )
            conferir(f"{cenario} · vertimento {usina}", vv, np.maximum(vv, 0))
        geracao = df[
            [
                "GH Batalha (MW)",
                "GH Serra (MW)",
                "Candeias (MW)",
                "Baliza (MW)",
                "Déficit (MW)",
            ]
        ].sum(axis=1)
        conferir(f"{cenario} · demanda", geracao, cfg["carga_mwmed"])
        for nome, parametro in (("Candeias", "max_candeias"), ("Baliza", "max_baliza")):
            valores = df[f"{nome} (MW)"]
            conferir(
                f"{cenario} · capacidade {nome}",
                valores,
                valores.clip(0, cfg[parametro]),
            )
        conferir(
            f"{cenario} · déficit não negativo",
            df["Déficit (MW)"],
            df["Déficit (MW)"].clip(lower=0),
        )
        conferir(
            f"{cenario} · alpha não negativo",
            df["Custo futuro alpha (R$)"],
            df["Custo futuro alpha (R$)"].clip(lower=0),
        )
        termico = cfg["horas_mes"] * (
            cfg["custo_candeias"] * df["Candeias (MW)"]
            + cfg["custo_baliza"] * df["Baliza (MW)"]
        )
        deficit = cfg["horas_mes"] * cfg["custo_deficit"] * df["Déficit (MW)"]
        vertimento = (
            cfg["custo_vertimento"]
            * k
            * (df["VV Batalha (m³/s)"] + df["VV Serra (m³/s)"])
        )
        conferir(
            f"{cenario} · custo imediato",
            df["Custo imediato (R$)"],
            termico + deficit + vertimento,
        )
        conferir(
            f"{cenario} · função objetivo",
            df["FOB (R$)"],
            df["Custo imediato (R$)"] + df["Custo futuro alpha (R$)"],
        )
        conferir(
            f"{cenario} · condição terminal", df["Custo futuro alpha (R$)"].iloc[-1], 0
        )
    return pd.DataFrame(verificacoes)


def verificar_planos(pontos, cortes):
    """Testa suporte na malha calculada, sem resolver novos despachos."""
    linhas = []
    for estagio, df in pontos.items():
        vb = df["VI Batalha (hm³)"].to_numpy()
        vs = df["VI Serra (hm³)"].to_numpy()
        custos = df["FOB esperada (R$)"].to_numpy()
        planos = np.array([c["a"] * vb + c["b"] * vs + c["c"] for c in cortes[estagio]])
        envoltoria = np.maximum(0, planos.max(axis=0))
        contato = np.diag(planos) - custos
        linhas.append(
            {
                "Estágio": estagio,
                "Maior excesso dos planos na malha (R$)": float(
                    np.max(envoltoria - custos)
                ),
                "Maior erro de contato (R$)": float(np.max(np.abs(contato))),
            }
        )
    return pd.DataFrame(linhas)
