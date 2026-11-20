"""Laboratório didático de PDE hidrotérmica — UHE Batalha.

Aplicação independente elaborada a partir dos parâmetros e da formulação
compartilhados na conversa. Usa scipy.optimize.linprog para resolver o mesmo
modelo linear de despacho; não depende do notebook estar aberto.
"""

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from scipy.optimize import linprog
from pyecharts import options as opts
from pyecharts.charts import Line, Bar

VMIN = 430.05
VMAX = 1781.61
K = 2.592
HORAS = 720
RO = 0.3551
GTMAX1 = 17.0
GTMAX2 = 18.0
CT1 = 118.93
CT2 = 917.12
CDEF = 8291.0
ENGOL = 147.0
MESES = ("Janeiro", "Fevereiro", "Março")
CENARIOS_PADRAO = ((47., 352.), (42., 471.), (55., 502.))
COR_AZUL = "#3678B6"
COR_MARROM = "#92592D"
COR_CLARA = "#BB9368"


@st.cache_data(show_spinner=False)
def despacho(vi, afl, carga, retas_futuras):
    """Resolve um PL de 1 mês. Volume em hm³; vazão em m³/s; custo em R$."""
    # x = [vf, vt, vv, gt1, gt2, deficit, alpha]
    c = [0, 0, 0.01 * K, HORAS * CT1, HORAS * CT2, HORAS * CDEF, 1]
    a_eq = [
        [1, K, K, 0, 0, 0, 0],
        [0, RO, 0, 1, 1, 1, 0],
    ]
    b_eq = [float(vi) + K * float(afl), float(carga)]
    # alpha >= a * vf + b  ->  a * vf - alpha <= -b
    a_ub = [[float(a), 0, 0, 0, 0, 0, -1] for a, b in retas_futuras]
    b_ub = [-float(b) for a, b in retas_futuras]
    bounds = [
        (VMIN, VMAX), (0, ENGOL), (0, None),
        (0, GTMAX1), (0, GTMAX2), (0, None),
        (0, None) if retas_futuras else (0, 0),
    ]
    result = linprog(
        c,
        A_ub=np.array(a_ub) if a_ub else None,
        b_ub=np.array(b_ub) if b_ub else None,
        A_eq=np.array(a_eq), b_eq=np.array(b_eq),
        bounds=bounds, method="highs",
    )
    if not result.success:
        raise RuntimeError(f"Despacho inviável: {result.message}")
    vf, vt, vv, gt1, gt2, deficit, alpha = result.x
    # Derivada de custo em relação a VI = marginal do lado direito do balanço.
    slope = float(result.eqlin.marginals[0])
    return {
        "fob": float(result.fun), "ci": float(result.fun - alpha),
        "alpha": float(alpha), "incl": slope,
        "vf": float(vf), "vt": float(vt), "vv": float(vv),
        "gt1": float(gt1), "gt2": float(gt2), "def": float(deficit),
    }


@st.cache_data(show_spinner=False)
def planejar(discret, carga, cenarios, metodo):
    volumes = np.linspace(VMIN, VMAX, discret)
    dados = {}
    retas_proximo = ()
    for estagio in (3, 2, 1):
        custos, inclinacoes = [], []
        for vi in volumes:
            r1 = despacho(float(vi), float(cenarios[estagio-1][0]), carga, retas_proximo)
            r2 = despacho(float(vi), float(cenarios[estagio-1][1]), carga, retas_proximo)
            custos.append((r1["fob"] + r2["fob"]) / 2)
            inclinacoes.append((r1["incl"] + r2["incl"]) / 2)
        custos = np.asarray(custos)
        inclinacoes = np.asarray(inclinacoes)
        # Construção original: secantes completas entre estados consecutivos.
        a_sec = np.diff(custos) / np.diff(volumes)
        b_sec = custos[:-1] - a_sec * volumes[:-1]
        secantes = tuple((float(a), float(b)) for a, b in zip(a_sec, b_sec))
        # Cortes de suporte: um por estado, obtido pelo multiplicador dual.
        tangentes = tuple(
            (float(a), float(custo - a * vi))
            for vi, custo, a in zip(volumes, custos, inclinacoes)
        )
        dados[estagio] = {
            "custos": custos, "inclinacoes": inclinacoes,
            "secantes": secantes, "tangentes": tangentes,
        }
        retas_proximo = secantes if metodo == "Secantes (original)" else tangentes
    return volumes, dados


def simular(volumes, dados, carga, cenarios, metodo, vi_inicial):
    linhas = []
    for nome, indice in (("Pessimista", 0), ("Otimista", 1)):
        vi = vi_inicial
        for estagio, mes in enumerate(MESES, 1):
            afluencia = cenarios[estagio - 1][indice]
            proximas = ()
            if estagio < 3:
                prox = dados[estagio + 1]
                proximas = prox["secantes"] if metodo == "Secantes (original)" else prox["tangentes"]
            r = despacho(vi, afluencia, carga, proximas)
            linhas.append({
                "Cenário": nome, "Mês": mes,
                "VI (hm³)": vi, "Afluência (hm³)": afluencia * K,
                "Turbinamento (hm³)": r["vt"] * K,
                "Vertimento (hm³)": r["vv"] * K,
                "VF (hm³)": r["vf"], "Batalha (MW)": RO * r["vt"],
                "Candeias (MW)": r["gt1"], "Baliza (MW)": r["gt2"],
                "Déficit (MW)": r["def"],
                "Custo imediato (R$)": r["ci"],
                "Custo futuro (R$)": r["alpha"], "FOB (R$)": r["fob"],
            })
            vi = r["vf"]
    return pd.DataFrame(linhas)


def mostrar_grafico(grafico, altura=520):
    components.html(grafico.render_embed(), height=altura, scrolling=False)


def grafico_fcf(estagio, volumes, dados):
    d = dados[estagio]
    xx = np.unique(np.concatenate((np.linspace(VMIN, VMAX, 280), volumes)))
    azul = np.interp(xx, volumes, d["custos"])
    cortes = np.array([a * xx + b for a, b in d["tangentes"]])
    marrom = np.maximum(0, np.max(cortes, axis=0))
    max_y = max(float(max(d["custos"])) * 1.15, 1.0)
    graf = Line(init_opts=opts.InitOpts(width="100%", height="490px"))
    graf.add_xaxis([round(float(v), 2) for v in xx])
    graf.add_yaxis("Aproximação por partes", azul.tolist(), is_symbol_show=False,
                   label_opts=opts.LabelOpts(is_show=False),
                   linestyle_opts=opts.LineStyleOpts(color=COR_AZUL, width=3))
    for i in range(min(2, len(d["tangentes"]))):
        values = [float(v) if 0 <= v <= max_y else None for v in cortes[i]]
        graf.add_yaxis(f"Tangente {i+1}", values, is_symbol_show=False,
                       label_opts=opts.LabelOpts(is_show=False),
                       linestyle_opts=opts.LineStyleOpts(color=COR_CLARA, width=1, opacity=.65))
    graf.add_yaxis("Envoltória inferior", marrom.tolist(), is_symbol_show=False,
                   label_opts=opts.LabelOpts(is_show=False),
                   linestyle_opts=opts.LineStyleOpts(color=COR_MARROM, width=3))
    graf.set_global_opts(
        legend_opts=opts.LegendOpts(is_show=False),
        xaxis_opts=opts.AxisOpts(type_="value", name="Volume inicial (hm³)",
                                 min_=400, max_=1800, name_gap=30),
        yaxis_opts=opts.AxisOpts(type_="value", name="Custo (R$)", min_=0,
                                 max_=max_y, name_gap=65),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
    )
    graf.options["grid"] = {"top": "7%", "bottom": "20%", "left": "15%", "right": "6%"}
    return graf


def grafico_armazenamento(tabela):
    graf = Line(init_opts=opts.InitOpts(width="100%", height="390px"))
    graf.add_xaxis(list(MESES))
    for nome, cor in (("Pessimista", COR_MARROM), ("Otimista", COR_AZUL)):
        valores = tabela.loc[tabela["Cenário"] == nome, "VF (hm³)"].tolist()
        graf.add_yaxis(nome, [round(float(v), 2) for v in valores],
                       symbol="circle", symbol_size=8,
                       label_opts=opts.LabelOpts(is_show=False),
                       linestyle_opts=opts.LineStyleOpts(color=cor, width=3),
                       itemstyle_opts=opts.ItemStyleOpts(color=cor))
    graf.set_global_opts(
        legend_opts=opts.LegendOpts(pos_top="2%"),
        xaxis_opts=opts.AxisOpts(name="Mês"),
        yaxis_opts=opts.AxisOpts(type_="value", name="Volume final (hm³)",
                                 min_=VMIN, max_=VMAX, name_gap=55),
        tooltip_opts=opts.TooltipOpts(trigger="axis"),
    )
    graf.options["grid"] = {"top": "15%", "bottom": "18%", "left": "18%", "right": "5%"}
    return graf


st.set_page_config(page_title="Laboratório PDE | Batalha", page_icon="💧", layout="wide")
st.markdown("""
<style>
.block-container {max-width: 1230px; padding-top: 1.6rem;}
.topo {border-left:5px solid #3678B6;padding:4px 0 4px 20px;margin-bottom:18px;}
.topo h1 {font-size:2.1rem; margin:0;}
.topo p {opacity:.72; margin:6px 0 0;}
</style>
<div class="topo"><h1>💧 Laboratório de PDE — UHE Batalha</h1>
<p>Uma experiência didática de três meses, com decisões de despacho e custo futuro.</p></div>
""", unsafe_allow_html=True)

with st.sidebar:
    st.header("🎛️ Ajuste seu experimento")
    discret = st.slider("Discretizações de volume", 3, 25, 10, 1,
                        help="Quantidade de volumes avaliados em cada mês da PDE.")
    carga = st.slider("Carga mensal (MW médios)", 20, 80, 50, 1)
    vi_inicial = st.slider("Volume inicial de janeiro (hm³)",
                           min_value=VMIN, max_value=VMAX, value=VMIN, step=0.01)
    metodo = st.radio("Política usada no despacho", ["Secantes (original)", "Cortes tangentes"],
                      help="A primeira preserva a formulação das retas do notebook original; a segunda usa os duais.")
    st.divider()
    st.subheader("Afluências (m³/s)")
    cenarios = []
    for mes, (baixo, alto) in zip(MESES, CENARIOS_PADRAO):
        with st.expander(mes, expanded=(mes == "Janeiro")):
            baixo_v = st.slider(f"{mes}: pessimista", 0, 600, int(baixo), 1)
            alto_v = st.slider(f"{mes}: otimista", 0, 600, int(alto), 1)
            cenarios.append((float(baixo_v), float(alto_v)))
    st.caption("Os cenários são dois valores equiprováveis por mês no planejamento.")

try:
    with st.spinner("Resolvendo a PDE de março até janeiro..."):
        volumes, dados = planejar(discret, float(carga), tuple(cenarios), metodo)
        tabela = simular(volumes, dados, float(carga), tuple(cenarios), metodo, float(vi_inicial))
except (RuntimeError, ValueError) as erro:
    st.error(str(erro))
    st.stop()

resumo = tabela.groupby("Cenário")["Custo imediato (R$)"].sum()
col_a, col_b, col_c = st.columns(3)
col_a.metric("Custo operacional · pessimista", f"R$ {resumo['Pessimista']:,.2f}")
col_b.metric("Custo operacional · otimista", f"R$ {resumo['Otimista']:,.2f}")
col_c.metric("Despachos no planejamento", f"{discret * 3 * 2}")
st.caption("Custos totais são somas dos custos imediatos de janeiro a março — sem somar FOBs repetidamente.")

aba1, aba2, aba3, aba4 = st.tabs([
    "📊 Operação dos cenários", "📉 Função de custo futuro",
    "📋 Tabelas", "📖 Entenda o modelo",
])

with aba1:
    st.subheader("Volume armazenado ao final de cada mês")
    mostrar_grafico(grafico_armazenamento(tabela), 405)
    st.subheader("Resumo da operação")
    for nome in ("Pessimista", "Otimista"):
        st.markdown(f"**Cenário {nome.lower()}**")
        sub = tabela[tabela["Cenário"] == nome][
            ["Mês", "VI (hm³)", "VF (hm³)", "Batalha (MW)",
             "Candeias (MW)", "Baliza (MW)", "Custo imediato (R$)"]]
        st.dataframe(sub.round(2), hide_index=True, use_container_width=True)

with aba2:
    st.subheader("Como as aproximações da FCF são construídas")
    st.caption("Azul: pontos ligados por segmentos · Marrom-claro: duas tangentes visíveis · Marrom-escuro: máximo dos cortes tangentes e zero.")
    st.info("No método original, as secantes completas são prolongadas e seu máximo entra no despacho. Isso não é necessariamente a interpolação superior por segmentos mostrada em azul.")
    for estagio in (3, 2, 1):
        with st.expander(f"Estágio {estagio} — {MESES[estagio - 1]}", expanded=(estagio == 3)):
            mostrar_grafico(grafico_fcf(estagio, volumes, dados), 510)
            st.caption(f"{discret} pontos calculados; {discret-1} segmentos secantes e {discret} cortes por duais. O método selecionado determina a recursão da PDE.")

with aba3:
    st.subheader("Resultados completos")
    st.dataframe(tabela.round(2), hide_index=True, use_container_width=True)
    csv = tabela.to_csv(index=False).encode("utf-8-sig")
    st.download_button("Baixar resultados (CSV)", csv, file_name="pde_batalha_resultados.csv", mime="text/csv")
    st.subheader("Custos ótimos por estado")
    pontos = pd.DataFrame({"VI (hm³)": volumes})
    for e in (3, 2, 1):
        pontos[f"FOB estágio {e} (R$)"] = dados[e]["custos"]
    st.dataframe(pontos.round(2), hide_index=True, use_container_width=True)

with aba4:
    st.markdown("""
    **1. Planejamento (março → janeiro):** para cada um dos volumes discretizados,
    o programa resolve os dois cenários de afluência, faz a média dos custos
    e constrói aproximações da FCF para orientar os meses anteriores.

    **2. Simulação (janeiro → março):** começa no volume inicial escolhido.
    O volume final de um mês passa a ser o inicial do seguinte. São três linhas
    por cenário porque existem três meses simulados, não porque faltam discretizações.

    **3. Métodos:** no notebook original, o despacho utiliza o máximo das
    secantes completas. O modo alternativo usa cortes de suporte calculados
    pelas sensibilidades duais do balanço hídrico. Os resultados podem diferir.

    **Hipóteses:** um reservatório (Batalha), duas térmicas, carga constante
    nos três meses, 720 horas por mês, cenários equiprováveis e custo terminal zero.
    Este é um modelo didático, não um modelo operacional oficial.
    """)
