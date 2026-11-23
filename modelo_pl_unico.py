"""PL determinístico da seção 5 do Colab oficial, independente das PDEs."""

from copy import deepcopy

import numpy as np
import pandas as pd
from cvxopt.modeling import variable, solvers, op

solvers.options.setdefault("glpk", {"msg_lev": "GLP_MSG_OFF"})


def meses_planejamento_pl(horizonte):
    return tuple(f"{MESES_PL[i % 12]} · {2026 + i // 12}" for i in range(horizonte))


def construir_sistema(cfg, naturais_batalha, naturais_serra):
    horizonte = cfg["meses"]
    if not 3 <= horizonte <= 24:
        raise ValueError("O horizonte do PL Único deve ter entre 3 e 24 meses.")
    batalha = np.asarray(naturais_batalha, dtype=float)
    serra = np.asarray(naturais_serra, dtype=float)
    for nome, valores in (("Batalha", batalha), ("Serra do Facão", serra)):
        if (
            valores.shape != (horizonte, 2)
            or not np.isfinite(valores).all()
            or np.min(valores) < 0
        ):
            raise ValueError(f"Afluências inválidas para {nome}.")
    incremental = np.maximum(0.0, serra - batalha)
    uhes = deepcopy(UHES_PL)
    for uhe, serie, chave in zip(
        uhes, (batalha, incremental), ("vi_batalha", "vi_serra")
    ):
        uhe["VI"] = float(cfg[chave])
        if not uhe["Vmin"] <= uhe["VI"] <= uhe["Vmax"]:
            raise ValueError(f"Volume inicial fora dos limites de {uhe['Nome']}.")
        # Entrada da interface: pessimista/otimista. PL original: otimista/pessimista.
        uhe["Afl"] = (serie[:, [1, 0]] * K_PL).tolist()
    return {
        "DGer": {
            "Meses": list(meses_planejamento_pl(horizonte)),
            "Horas": HORAS_PL,
            "CDef": 8291.0 * HORAS_PL,
            "Carga": [float(cfg["carga"])] * horizonte,
            "Nr_Disc": 5,  # Metadado da referência, sem uso na otimização do PL.
            "Nr_Est": horizonte,
            "Nr_Cen": 2,
        },
        "UHE": uhes,
        "UTE": deepcopy(UTES_PL),
    }


def resolver_cenarios(sistema):
    """Dois PLs independentes, cada um com todos os estágios simultâneos."""
    resultados = {}
    tabelas = []
    for nome, indice in (("Pessimista", 1), ("Otimista", 0)):
        resultado = pl_unico(sistema, indice)
        verificacoes = validar_resultado(sistema, resultado)
        if not verificacoes["Aprovada"].all():
            raise RuntimeError(f"Falha na validação do PL Único no cenário {nome}.")
        resultados[nome] = resultado
        tabela = tabela_resultados(sistema, resultado)
        tabela.insert(0, "Cenário", nome)
        tabelas.append(tabela)
    return resultados, pd.concat(tabelas, ignore_index=True)


def validar_resultado(sistema, resultado, atol=1e-5):
    """Contabilidade independente do otimizador, nas unidades originais do PL."""
    linhas = []

    def conferir(nome, valor, esperado):
        erro = float(
            np.max(np.abs(np.asarray(valor) - np.asarray(esperado)), initial=0)
        )
        linhas.append(
            {"Verificação": nome, "Erro máximo": erro, "Aprovada": erro <= atol}
        )

    n = sistema["DGer"]["Nr_Est"]
    cenario = resultado["DGer"]["Cenario"]
    geracao = np.zeros(n)
    vertimento = np.zeros(n)
    for i, u in enumerate(sistema["UHE"]):
        r = resultado["UHE"][i]
        vf = np.asarray(r["vf"])
        vt = np.asarray(r["vt"])
        vv = np.asarray(r["vv"])
        vi = np.r_[u["VI"], vf[:-1]]
        recebimento = np.zeros(n)
        for j, montante in enumerate(sistema["UHE"]):
            if montante.get("Jusante") == i:
                recebimento += np.asarray(resultado["UHE"][j]["vt"]) + np.asarray(
                    resultado["UHE"][j]["vv"]
                )
        afl = np.array(u["Afl"])[:n, cenario]
        conferir(f"Balanço · {u['Nome']}", vf, vi + afl + recebimento - vt - vv)
        conferir(f"Volume · {u['Nome']}", vf, np.clip(vf, u["Vmin"], u["Vmax"]))
        conferir(f"Turbinamento · {u['Nome']}", vt, np.clip(vt, 0, u["Engol"]))
        conferir(f"Vertimento · {u['Nome']}", vv, np.maximum(vv, 0))
        if u.get("Potencia") is not None:
            conferir(
                f"Potência · {u['Nome']}",
                u["Prod"] * vt,
                np.minimum(u["Prod"] * vt, u["Potencia"]),
            )
        geracao += u["Prod"] * vt
        vertimento += vv
    termico = np.zeros(n)
    for u, r in zip(sistema["UTE"], resultado["UTE"]):
        gt = np.asarray(r["gt"])
        conferir(f"Capacidade · {u['Nome']}", gt, np.clip(gt, 0, u["Capac"]))
        geracao += gt
        termico += u["Custo"] * gt
    deficit = np.asarray(resultado["DGer"]["Deficit"])
    conferir("Déficit não negativo", deficit, np.maximum(deficit, 0))
    conferir("Atendimento à carga", geracao + deficit, sistema["DGer"]["Carga"])
    custo = termico + sistema["DGer"]["CDef"] * deficit + 0.01 * vertimento
    conferir("Custo imediato", resultado["DGer"]["CustoImediato"], custo)
    conferir("Função objetivo", resultado["DGer"]["CustoTotal"], custo.sum())
    return pd.DataFrame(linhas)


REFERENCIA_PL = "Planejamento_Energético_Códigos_OficialPLUNICO.ipynb"

HORAS_PL = 720.0

K_PL = 2.592

MESES_PL = [
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

UHES_PL = [
    {
        "Nome": "UHE Batalha",
        "Vmin": 430.05,
        "Vmax": 1781.61,
        "VI": 430.05,
        "Prod": 0.13699845679012346,
        "Engol": 381.024,
        "Potencia": None,
        "Jusante": 1,
    },
    {
        "Nome": "UHE Serra do Facão",
        "Vmin": 1752.0,
        "Vmax": 5199.0,
        "VI": 1752.0,
        "Prod": 0.23753858024691357,
        "Engol": 811.296,
        "Potencia": 212.58,
        "Jusante": None,
    },
]

UTES_PL = [
    {"Nome": "BBF Baliza", "Capac": 18.0, "Custo": 660326.4},
    {"Nome": "ERB Candeias", "Capac": 17.0, "Custo": 85629.6},
]

CONFIG_PL = {"meses": 3, "carga": 150.0, "vi_batalha": 430.05, "vi_serra": 1752.0}

AFL_NAT_BATALHA_PL = np.array(
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

AFL_NAT_SERRA_PL = np.array(
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


def pl_unico(sistema, cenario=1, imprime=False):
    """PL determinístico para UHEs em cascata, seguindo a estrutura da aula.

    cenario=0: afluências otimistas; cenario=1: pessimistas.
    Afluências das UHEs a jusante devem ser LOCAIS/INCREMENTAIS.
    """
    n = sistema["DGer"]["Nr_Est"]
    uhes, utes = (sistema["UHE"], sistema["UTE"])
    if not (isinstance(cenario, int) and 0 <= cenario < sistema["DGer"]["Nr_Cen"]):
        raise ValueError("Use cenario=0 (otimista) ou cenario=1 (pessimista).")
    if len(sistema["DGer"]["Carga"]) != n:
        raise ValueError("A carga precisa ter um valor para cada estágio.")
    vf = [variable(n, "VF " + u["Nome"]) for u in uhes]
    vt = [variable(n, "VT " + u["Nome"]) for u in uhes]
    vv = [variable(n, "VV " + u["Nome"]) for u in uhes]
    gt = [variable(n, "GT " + u["Nome"]) for u in utes]
    deficit = variable(n, "DEF")
    fob = 0
    for t in range(n):
        for j, u in enumerate(utes):
            fob += u["Custo"] * gt[j][t]
        fob += sistema["DGer"]["CDef"] * deficit[t]
        for i in range(len(uhes)):
            fob += 0.01 * vv[i][t]
    restricoes = []
    balancos = [[None for t in range(n)] for u in uhes]
    atendimento = []
    for i, u in enumerate(uhes):
        for t in range(n):
            vi = float(u["VI"]) if t == 0 else vf[i][t - 1]
            afl_local = float(u["Afl"][t][cenario])
            recebimento = 0
            for j, montante in enumerate(uhes):
                if montante.get("Jusante") == i:
                    recebimento += vt[j][t] + vv[j][t]
            restricao = vf[i][t] == vi + afl_local + recebimento - vt[i][t] - vv[i][t]
            restricoes.append(restricao)
            balancos[i][t] = restricao
    for t in range(n):
        geracao = 0
        for i, u in enumerate(uhes):
            geracao += u["Prod"] * vt[i][t]
        for j in range(len(utes)):
            geracao += gt[j][t]
        geracao += deficit[t]
        restricao = geracao == float(sistema["DGer"]["Carga"][t])
        restricoes.append(restricao)
        atendimento.append(restricao)
    for t in range(n):
        for i, u in enumerate(uhes):
            restricoes += [
                vf[i][t] >= u["Vmin"],
                vf[i][t] <= u["Vmax"],
                vt[i][t] >= 0,
                vt[i][t] <= u["Engol"],
                vv[i][t] >= 0,
            ]
            if u.get("Potencia") is not None:
                restricoes.append(u["Prod"] * vt[i][t] <= u["Potencia"])
        for j, u in enumerate(utes):
            restricoes += [gt[j][t] >= 0, gt[j][t] <= u["Capac"]]
        restricoes.append(deficit[t] >= 0)
    problema = op(fob, restricoes)
    solvers.options["show_progress"] = False
    problema.solve("dense", "glpk")
    if problema.status != "optimal":
        raise RuntimeError(f"O PL não encontrou solução ótima: {problema.status}")
    dados_uhe = []
    for i, u in enumerate(uhes):
        dados_uhe.append(
            {
                "Nome": u["Nome"],
                "vf": [float(vf[i][t].value()[0]) for t in range(n)],
                "vt": [float(vt[i][t].value()[0]) for t in range(n)],
                "vv": [float(vv[i][t].value()[0]) for t in range(n)],
                "cma": [float(balancos[i][t].multiplier.value[0]) for t in range(n)],
            }
        )
    dados_ute = []
    for j, u in enumerate(utes):
        dados_ute.append(
            {"Nome": u["Nome"], "gt": [float(gt[j][t].value()[0]) for t in range(n)]}
        )
    dados_def = [float(deficit[t].value()[0]) for t in range(n)]
    cmo = [
        -float(atendimento[t].multiplier.value[0]) / sistema["DGer"]["Horas"]
        for t in range(n)
    ]
    custo_imediato = [
        sum((utes[j]["Custo"] * dados_ute[j]["gt"][t] for j in range(len(utes))))
        + sistema["DGer"]["CDef"] * dados_def[t]
        + 0.01 * sum((dados_uhe[i]["vv"][t] for i in range(len(uhes))))
        for t in range(n)
    ]
    resultado = {
        "DGer": {
            "CustoTotal": float(fob.value()[0]),
            "CMO": cmo,
            "Deficit": dados_def,
            "CustoImediato": custo_imediato,
            "Cenario": cenario,
        },
        "UHE": dados_uhe,
        "UTE": dados_ute,
    }
    if imprime:
        print("Custo total: R$", f"{resultado['DGer']['CustoTotal']:,.2f}")
        print("CMO (R$/MWh):", np.round(cmo, 2))
        print("Déficit (MW):", np.round(dados_def, 3))
    return resultado


def tabela_resultados(sistema, resultado):
    linhas = []
    n = sistema["DGer"]["Nr_Est"]
    for t in range(n):
        linha = {
            "Mês": sistema["DGer"]["Meses"][t],
            "Carga (MW)": sistema["DGer"]["Carga"][t],
        }
        for i, u in enumerate(sistema["UHE"]):
            linha[f"VI {u['Nome']} (hm³)"] = (
                u["VI"] if t == 0 else resultado["UHE"][i]["vf"][t - 1]
            )
            linha[f"AFL local {u['Nome']} (hm³)"] = u["Afl"][t][
                resultado["DGer"]["Cenario"]
            ]
            linha[f"VT {u['Nome']} (hm³)"] = resultado["UHE"][i]["vt"][t]
            linha[f"VV {u['Nome']} (hm³)"] = resultado["UHE"][i]["vv"][t]
            linha[f"VF {u['Nome']} (hm³)"] = resultado["UHE"][i]["vf"][t]
            linha[f"Geração {u['Nome']} (MW)"] = (
                u["Prod"] * resultado["UHE"][i]["vt"][t]
            )
        for j, u in enumerate(sistema["UTE"]):
            linha[f"{u['Nome']} (MW)"] = resultado["UTE"][j]["gt"][t]
        linha["Déficit (MW)"] = resultado["DGer"]["Deficit"][t]
        linha["CMO (R$/MWh)"] = resultado["DGer"]["CMO"][t]
        linha["Custo imediato (R$)"] = resultado["DGer"]["CustoImediato"][t]
        linhas.append(linha)
    return pd.DataFrame(linhas)
