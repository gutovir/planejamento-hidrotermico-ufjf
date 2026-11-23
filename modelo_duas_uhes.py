"""Modelo da seção 3 da última versão final do notebook de duas UHEs."""

from itertools import product

import numpy as np
import pandas as pd
from pyscipopt import Model, SCIP_PARAMSETTING

REFERENCIA_2U = "Planejamento_Energético_Códigos_utlimo_versaofinaldo2UHEs.ipynb"

CONFIG_2U = {
    "meses": 3,
    "niveis_batalha": 5,
    "niveis_serra": 5,
    "carga_mwmed": 150.0,
    "volume_inicial_batalha": 430.05,
    "volume_inicial_serra": 1752.0,
    "horas_mes": 720.0,
    "k_hm3": 2.592,
    "custo_vertimento": 0.01,
    "custo_deficit": 8291.0,
    "custo_candeias": 118.93,
    "custo_baliza": 917.12,
    "max_candeias": 17.0,
    "max_baliza": 18.0,
}

UHES_2U = {
    "Batalha": {"vmin": 430.05, "vmax": 1781.61, "rho": 0.3551, "engol": 147.0},
    "Serra do Facão": {
        "vmin": 1752.0,
        "vmax": 5199.0,
        "rho": 0.6157,
        "engol": 313.0,
        "potencia_nominal": 212.58,
    },
}

MESES_2U = [
    "Jan",
    "Fev",
    "Mar",
    "Abr",
    "Mai",
    "Jun",
    "Jul",
    "Ago",
    "Set",
    "Out",
    "Nov",
    "Dez",
]

AFL_NAT_BATALHA_2U = np.array(
    [
        [109.39, 261.01],
        [97.88, 277.97],
        [108.8, 270.99],
        [89.59, 198.6],
        [60.91, 122.33],
        [47.01, 91.64],
        [36.62, 72.28],
        [28.47, 57.15],
        [23.09, 50.3],
        [23.78, 62.43],
        [37.72, 112.72],
        [68.42, 209.66],
    ],
    dtype=float,
)

AFL_NAT_SERRA_2U = np.array(
    [
        [179.45, 436.8],
        [161.44, 455.13],
        [174.79, 441.38],
        [144.15, 320.63],
        [96.82, 194.82],
        [74.6, 145.02],
        [58.21, 114.11],
        [45.44, 89.89],
        [37.4, 78.24],
        [39.01, 99.05],
        [63.67, 180.47],
        [111.85, 348.71],
    ],
    dtype=float,
)

AFL_INC_SERRA_2U = np.maximum(0.0, AFL_NAT_SERRA_2U - AFL_NAT_BATALHA_2U)

CENARIOS_2U = ("Pessimista", "Otimista")


def meses_planejamento(horizonte):
    return tuple(f"{MESES_2U[i % 12]} · {2026 + i // 12}" for i in range(horizonte))


def planejar_duas_uhes(cfg, naturais_batalha, naturais_serra, progresso=None):
    """Backward da seção 3 com dois cenários conjuntos equiprováveis."""
    horizonte = cfg["meses"]
    if not 3 <= horizonte <= 24:
        raise ValueError(
            "O horizonte deve ter entre 3 e 24 meses com afluências informadas."
        )
    if min(cfg["niveis_batalha"], cfg["niveis_serra"]) < 2:
        raise ValueError("Cada reservatório precisa de pelo menos dois níveis.")
    for nome, valores in (("Batalha", naturais_batalha), ("Serra", naturais_serra)):
        if (
            np.asarray(valores).shape != (horizonte, 2)
            or not np.isfinite(valores).all()
            or np.min(valores) < 0
        ):
            raise ValueError(f"Afluências inválidas para {nome}.")
    incremental = np.maximum(
        0, np.asarray(naturais_serra) - np.asarray(naturais_batalha)
    )
    volumes_b = np.linspace(
        UHES_2U["Batalha"]["vmin"], UHES_2U["Batalha"]["vmax"], cfg["niveis_batalha"]
    )
    volumes_s = np.linspace(
        UHES_2U["Serra do Facão"]["vmin"],
        UHES_2U["Serra do Facão"]["vmax"],
        cfg["niveis_serra"],
    )
    estados = list(product(volumes_b, volumes_s))
    cortes = {horizonte + 1: []}
    custos = {}
    for estagio in range(horizonte, 0, -1):
        pontos = []
        planos = []
        for vi_b, vi_s in estados:
            resultados = [
                despacho_hidrotermico_2uhes(
                    vi_b,
                    vi_s,
                    naturais_batalha[estagio - 1][c],
                    incremental[estagio - 1, c],
                    cortes[estagio + 1],
                    cfg=cfg,
                )
                for c in range(2)
            ]
            custo = float(np.mean([r["fob"] for r in resultados]))
            a = float(np.mean([r["dual_b"] for r in resultados]))
            b = float(np.mean([r["dual_s"] for r in resultados]))
            planos.append({"a": a, "b": b, "c": custo - a * vi_b - b * vi_s})
            pontos.append(
                {
                    "VI Batalha (hm³)": float(vi_b),
                    "VI Serra (hm³)": float(vi_s),
                    "FOB esperada (R$)": custo,
                }
            )
        cortes[estagio] = planos
        custos[estagio] = pd.DataFrame(pontos)
        if progresso:
            progresso((horizonte - estagio + 1) / horizonte)
    return volumes_b, volumes_s, cortes, custos


def simular_duas_uhes(cfg, naturais_batalha, naturais_serra, cortes):
    incremental = np.maximum(
        0, np.asarray(naturais_serra) - np.asarray(naturais_batalha)
    )
    linhas = []
    for c, nome in enumerate(CENARIOS_2U):
        vi_b = float(cfg["volume_inicial_batalha"])
        vi_s = float(cfg["volume_inicial_serra"])
        for estagio, mes in enumerate(meses_planejamento(cfg["meses"]), 1):
            abl = float(naturais_batalha[estagio - 1][c])
            ain = float(incremental[estagio - 1, c])
            r = despacho_hidrotermico_2uhes(
                vi_b, vi_s, abl, ain, cortes[estagio + 1], cfg=cfg
            )
            linhas.append(
                {
                    "Cenário": nome,
                    "Mês": mes,
                    "VI Batalha (hm³)": vi_b,
                    "VF Batalha (hm³)": r["vf_b"],
                    "VI Serra (hm³)": vi_s,
                    "VF Serra (hm³)": r["vf_s"],
                    "Afl Batalha (m³/s)": abl,
                    "Afl natural Serra (m³/s)": float(naturais_serra[estagio - 1][c]),
                    "Afl incremental Serra (m³/s)": ain,
                    "VT Batalha (m³/s)": r["vt_b"],
                    "VV Batalha (m³/s)": r["vv_b"],
                    "VT Serra (m³/s)": r["vt_s"],
                    "VV Serra (m³/s)": r["vv_s"],
                    "GH Batalha (MW)": r["gh_b"],
                    "GH Serra (MW)": r["gh_s"],
                    "Candeias (MW)": r["gt_c"],
                    "Baliza (MW)": r["gt_a"],
                    "Déficit (MW)": r["def"],
                    "Custo imediato (R$)": r["custo_imediato"],
                    "Custo futuro alpha (R$)": r["alpha"],
                    "FOB (R$)": r["fob"],
                }
            )
            vi_b, vi_s = r["vf_b"], r["vf_s"]
    return pd.DataFrame(linhas)


def matriz_custos(pontos, volumes_b, volumes_s):
    matriz = pontos.pivot(
        index="VI Serra (hm³)", columns="VI Batalha (hm³)", values="FOB esperada (R$)"
    )
    matriz = matriz.reindex(index=volumes_s, columns=volumes_b)
    if matriz.isna().any().any():
        raise ValueError("Há estados sem custo calculado na malha da FCF.")
    return matriz.to_numpy(dtype=float)


def despacho_hidrotermico_2uhes(
    vi_b, vi_s, afl_b, afl_s_inc, cortes_futuros=(), cfg=None
):
    cfg = CONFIG_2U if cfg is None else cfg
    bat = UHES_2U["Batalha"]
    ser = UHES_2U["Serra do Facão"]
    k = cfg["k_hm3"]
    h = cfg["horas_mes"]
    m = Model("despacho_2uhes_cascata")
    m.hideOutput()
    m.setPresolve(SCIP_PARAMSETTING.OFF)
    m.setHeuristics(SCIP_PARAMSETTING.OFF)
    m.disablePropagation()
    vf_b = m.addVar("vf_b", lb=bat["vmin"], ub=bat["vmax"])
    vf_s = m.addVar("vf_s", lb=ser["vmin"], ub=ser["vmax"])
    vt_b = m.addVar("vt_b", lb=0.0, ub=bat["engol"])
    vv_b = m.addVar("vv_b", lb=0.0)
    vt_s = m.addVar("vt_s", lb=0.0, ub=ser["engol"])
    vv_s = m.addVar("vv_s", lb=0.0)
    gt_c = m.addVar("gt_candeias", lb=0.0, ub=cfg["max_candeias"])
    gt_a = m.addVar("gt_baliza", lb=0.0, ub=cfg["max_baliza"])
    deficit = m.addVar("deficit", lb=0.0)
    alpha = m.addVar("alpha", lb=0.0)
    bal_b = m.addCons(vf_b + k * vt_b + k * vv_b == float(vi_b) + k * float(afl_b))
    bal_s = m.addCons(
        vf_s + k * vt_s + k * vv_s - k * vt_b - k * vv_b
        == float(vi_s) + k * float(afl_s_inc)
    )
    m.addCons(
        bat["rho"] * vt_b + ser["rho"] * vt_s + gt_c + gt_a + deficit
        == cfg["carga_mwmed"]
    )
    for corte in cortes_futuros:
        m.addCons(alpha >= corte["a"] * vf_b + corte["b"] * vf_s + corte["c"])
    if not cortes_futuros:
        m.addCons(alpha == 0.0)
    custo_imediato = h * (
        cfg["custo_candeias"] * gt_c
        + cfg["custo_baliza"] * gt_a
        + cfg["custo_deficit"] * deficit
    ) + cfg["custo_vertimento"] * k * (vv_b + vv_s)
    m.setObjective(custo_imediato + alpha, sense="minimize")
    m.optimize()
    if m.getStatus() != "optimal":
        raise RuntimeError(
            f"Despacho 2 UHEs não ótimo: {m.getStatus()}; vi=({vi_b},{vi_s})"
        )
    vb = float(m.getVal(vf_b))
    vs = float(m.getVal(vf_s))
    tb = float(m.getVal(vt_b))
    ts = float(m.getVal(vt_s))
    sb = float(m.getVal(vv_b))
    ss = float(m.getVal(vv_s))
    gc = float(m.getVal(gt_c))
    ga = float(m.getVal(gt_a))
    de = float(m.getVal(deficit))
    al = float(m.getVal(alpha))
    ci = h * (
        cfg["custo_candeias"] * gc
        + cfg["custo_baliza"] * ga
        + cfg["custo_deficit"] * de
    ) + cfg["custo_vertimento"] * k * (sb + ss)
    return {
        "vf_b": vb,
        "vf_s": vs,
        "vt_b": tb,
        "vv_b": sb,
        "vt_s": ts,
        "vv_s": ss,
        "gh_b": bat["rho"] * tb,
        "gh_s": ser["rho"] * ts,
        "gt_c": gc,
        "gt_a": ga,
        "def": de,
        "custo_imediato": ci,
        "alpha": al,
        "fob": float(m.getObjVal()),
        "dual_b": float(m.getDualsolLinear(bal_b)),
        "dual_s": float(m.getDualsolLinear(bal_s)),
    }
