"""Laboratórios de planejamento hidrotérmico — UFJF.

PDE de uma UHE, PDE de duas UHEs em cascata e PL Único determinístico.
Os modelos utilizam as referências locais e mantêm estados independentes.
"""

import numpy as np
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from scipy.optimize import linprog
from pyecharts import options as opts
from pyecharts.charts import Line
from graficos_duas_uhes import geracao_mensal, armazenamento, custos_mensais

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
MESES = (
    "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
    "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
)
# Perfil original do Colab, incluindo os meses que estavam comentados.
# O segundo ano repete este perfil por hipótese didática autorizada.
CENARIOS_PADRAO = (
    (47., 352.), (42., 471.), (55., 502.), (38., 203.),
    (26., 170.), (24., 125.), (17., 95.), (14., 76.),
    (11., 74.), (8., 115.), (13., 266.), (19., 385.),
)
CARGA_MAXIMA = 150
METODOS = ("Secantes (original)", "Cortes tangentes")
CONTROLES_PADRAO = {
    "horizonte": 3, "discret": 10, "carga": 50,
    "vi_inicial": VMIN, "metodo": METODOS[0],
}
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
    for estagio in range(len(cenarios), 0, -1):
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


def meses_do_horizonte(horizonte):
    return tuple(f"{MESES[i % 12]} · {2026 + i // 12}" for i in range(horizonte))


def simular(dados, carga, cenarios, metodo, vi_inicial):
    linhas = []
    meses = meses_do_horizonte(len(cenarios))
    for nome, indice in (("Pessimista", 0), ("Otimista", 1)):
        vi = vi_inicial
        for estagio, mes in enumerate(meses, 1):
            afluencia = cenarios[estagio - 1][indice]
            proximas = ()
            if estagio < len(cenarios):
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
    visual = tabela.rename(columns={"VI (hm³)": "VI Batalha (hm³)", "VF (hm³)": "VF Batalha (hm³)"})
    return armazenamento(visual, "Batalha", limites={"Batalha": {"vmin": VMIN, "vmax": VMAX}})


def grafico_geracao(tabela, cenario, carga):
    visual = tabela.rename(columns={"Batalha (MW)": "GH Batalha (MW)"})
    return geracao_mensal(visual, cenario, carga)


def grafico_custo_imediato(tabela):
    return custos_mensais(tabela)


def restaurar_padrao():
    st.session_state.update(CONTROLES_PADRAO)
    for chave in tuple(st.session_state):
        if chave.startswith(("afluencia_", "fcf_")) or chave == "mes_fcf":
            del st.session_state[chave]


def aplicar_afluencias_em_todos_meses():
    for i in range(st.session_state["horizonte"]):
        for j in range(2):
            st.session_state[f"afluencia_{i}_{j}"] = st.session_state[f"afluencia_global_{j}"]


def atualizar_par_afluencias(chave_intervalo, chave_pessimista, chave_otimista):
    pessimista, otimista = st.session_state[chave_intervalo]
    st.session_state[chave_pessimista] = pessimista
    st.session_state[chave_otimista] = otimista


def slider_afluencias(chave_intervalo, chave_pessimista, chave_otimista):
    par_atual = (st.session_state[chave_pessimista], st.session_state[chave_otimista])
    st.session_state[chave_intervalo] = tuple(sorted(par_atual))
    if par_atual[0] > par_atual[1]:
        st.warning(f"Par atual: pessimista {par_atual[0]:.1f} e otimista {par_atual[1]:.1f} m³/s. "
                   "Ajuste o intervalo para definir o pessimista como o menor valor.")
    st.slider("Batalha · Pessimista / Otimista (m³/s)", 0., 600., step=0.1,
              key=chave_intervalo, format="%.1f", on_change=atualizar_par_afluencias,
              args=(chave_intervalo, chave_pessimista, chave_otimista),
              help="Alça da esquerda: cenário pessimista. Alça da direita: cenário otimista.")


st.set_page_config(page_title="Planejamento Hidrotérmico | UFJF", page_icon="💧", layout="wide")
st.markdown("""
<style>
.block-container {max-width: 1230px; padding-top: 1.6rem;}
.topo {border-left:5px solid #3678B6;padding:4px 0 4px 20px;margin-bottom:18px;}
.topo h1 {font-size:2.1rem; margin:0;}
.topo p {opacity:.72; margin:6px 0 0;}
</style>
<div class="topo"><h1>💧 Planejamento Hidrotérmico — UFJF</h1>
<p>Explore como afluência, demanda e armazenamento orientam as decisões de despacho.</p></div>
""", unsafe_allow_html=True)

def renderizar_uma_uhe():
    for chave, valor in CONTROLES_PADRAO.items():
        st.session_state.setdefault(chave, valor)

    # Mantém as edições quando um mês fica temporariamente fora do horizonte.
    for chave in tuple(st.session_state):
        if chave.startswith("afluencia_"):
            st.session_state[chave] = st.session_state[chave]

    with st.sidebar:
        st.header("Experimento")
        st.button("Restaurar valores padrão", on_click=restaurar_padrao)
        horizonte = st.slider("Horizonte (meses)", 3, 24, step=1, key="horizonte")
        meses = meses_do_horizonte(horizonte)
        discret = st.slider("Discretizações de volume", 2, 25, step=1, key="discret",
                            help="Quantidade de volumes avaliados em cada mês da PDE.")
        carga = st.slider("Carga mensal (MW médios)", 0, CARGA_MAXIMA, step=1, key="carga")
        vi_inicial = st.slider("Volume inicial de janeiro (hm³)",
                               min_value=VMIN, max_value=VMAX, step=0.01, key="vi_inicial")
        metodo = st.radio("Política usada no despacho", METODOS, key="metodo",
                          help="As secantes seguem o método original. Os cortes são calculados pelos duais.")
        total_despachos = 2 * horizonte * discret
        if total_despachos >= 400 or discret >= 20:
            st.warning(f"O planejamento avalia {total_despachos} despachos. O cálculo pode demorar mais.")
        st.divider()
        st.subheader("Afluências (m³/s)")
        st.caption("Os dois cenários têm probabilidade de 50% em cada mês no planejamento.")
        st.caption("Padrões de janeiro a dezembro extraídos do notebook original.")
        if horizonte > 12:
            st.info("Hipótese didática de repetição do perfil anual: os padrões do segundo ano "
                    "repetem as afluências originais do primeiro ano. Essa repetição não representa "
                    "uma previsão hidrológica. Cada mês dos dois anos pode ser editado individualmente.")
        for i in range(24):
            for j in range(2):
                st.session_state.setdefault(f"afluencia_{i}_{j}", CENARIOS_PADRAO[i % 12][j])
        modo_afluencias = st.radio("Ajustar afluências", ("Todos os meses", "Mês a mês"),
                                   index=1, key="afluencia_modo")
        if modo_afluencias == "Todos os meses":
            st.caption(f"Escolha um par para aplicar aos {horizonte} meses selecionados.")
            for j in range(2):
                chave = f"afluencia_global_{j}"
                st.session_state.setdefault(chave, CENARIOS_PADRAO[0][j])
            slider_afluencias("afluencia_intervalo_global", "afluencia_global_0", "afluencia_global_1")
            st.button("Aplicar a todos os meses", on_click=aplicar_afluencias_em_todos_meses)
        else:
            if st.session_state.get("afluencia_mes", 0) >= horizonte:
                st.session_state["afluencia_mes"] = 0
            i = st.selectbox("Mês das afluências", range(horizonte),
                             format_func=lambda indice: meses[indice], key="afluencia_mes")
            slider_afluencias(f"afluencia_intervalo_{i}", f"afluencia_{i}_0", f"afluencia_{i}_1")
        st.caption("As edições mensais são preservadas ao alternar o modo ou o horizonte.")
        cenarios = tuple(
            tuple(st.session_state[f"afluencia_{i}_{j}"] for j in range(2))
            for i in range(horizonte)
        )

    with st.container():
        cenarios = tuple(cenarios)
        try:
            with st.spinner(f"Resolvendo {horizonte} estágios, do último mês ao primeiro..."):
                volumes, dados = planejar(discret, float(carga), cenarios, metodo)
                tabela = simular(dados, float(carga), cenarios, metodo, vi_inicial)
        except RuntimeError as erro:
            st.error("O solver não encontrou uma solução para esta configuração.")
            with st.expander("Detalhes do solver"):
                st.write(str(erro))
            return
        except ValueError as erro:
            st.error(str(erro))
            return

        resumo = tabela.groupby("Cenário")["Custo imediato (R$)"].sum()
        col_a, col_b, col_c = st.columns(3)
        col_a.metric("Custo operacional · pessimista", f"R$ {resumo['Pessimista']:,.2f}")
        col_b.metric("Custo operacional · otimista", f"R$ {resumo['Otimista']:,.2f}")
        col_c.metric("Despachos no planejamento", total_despachos)
        st.caption("O custo operacional de cada cenário soma os custos imediatos dos meses simulados.")

        aba1, aba2, aba3, aba4 = st.tabs([
            "📊 Operação dos cenários", "📉 Função de Custo Futuro (FCF)",
            "📋 Tabelas", "📖 Entenda o modelo",
        ])

        with aba1:
            cenarios_operacao = ("Pessimista", "Otimista")
            for nome, painel in zip(cenarios_operacao, st.tabs(cenarios_operacao)):
                with painel:
                    st.plotly_chart(grafico_geracao(tabela, nome, carga), use_container_width=True,
                                    key=f"geracao_{nome}")
            st.plotly_chart(grafico_armazenamento(tabela), use_container_width=True)
            st.plotly_chart(grafico_custo_imediato(tabela), use_container_width=True)
            st.subheader("Resultados mensais por cenário")
            for nome, painel in zip(cenarios_operacao, st.tabs(cenarios_operacao)):
                with painel:
                    sub = tabela[tabela["Cenário"] == nome][
                        ["Mês", "VI (hm³)", "VF (hm³)", "Batalha (MW)", "Candeias (MW)",
                         "Baliza (MW)", "Déficit (MW)", "Custo imediato (R$)"]
                    ]
                    st.dataframe(sub.round(2), hide_index=True, use_container_width=True)

        with aba2:
            st.subheader("Função de Custo Futuro (FCF)")
            st.caption("Azul: pontos ligados por segmentos · Marrom-claro: duas tangentes visíveis · Marrom-escuro: máximo dos cortes tangentes e zero.")
            st.info("No método original, as secantes completas são prolongadas e seu máximo entra no despacho. Isso não é necessariamente a interpolação superior por segmentos mostrada em azul.")
            anos_fcf = tuple(range(2026, 2026 + (horizonte + 11) // 12))
            if st.session_state.get("fcf_ano") not in anos_fcf:
                st.session_state["fcf_ano"] = anos_fcf[-1]
            ano_fcf = st.radio("Ano da FCF", anos_fcf, key="fcf_ano",
                                horizontal=True, label_visibility="collapsed")
            inicio_ano = (ano_fcf - 2026) * 12
            meses_fcf = tuple(range(min(12, horizonte - inicio_ano)))
            if st.session_state.get("fcf_mes") not in meses_fcf:
                st.session_state["fcf_mes"] = meses_fcf[-1]
            abreviacoes = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
                           "Jul", "Ago", "Set", "Out", "Nov", "Dez")
            mes_fcf = st.radio("Mês da FCF", meses_fcf, format_func=lambda i: abreviacoes[i],
                               key="fcf_mes", horizontal=True, label_visibility="collapsed")
            estagio = inicio_ano + mes_fcf + 1
            mostrar_grafico(grafico_fcf(estagio, volumes, dados), 510)
            st.caption(f"{discret} estados, {discret - 1} secantes e {discret} cortes por duais. "
                       "O método selecionado determina a recursão da PDE.")

        with aba3:
            st.subheader("Resultados completos")
            st.dataframe(tabela.round(2), hide_index=True, use_container_width=True)
            csv = tabela.to_csv(index=False).encode("utf-8-sig")
            st.download_button("Baixar resultados (CSV)", csv, file_name="pde_batalha_resultados.csv", mime="text/csv")
            st.subheader("Custos ótimos por estado")
            pontos = pd.DataFrame({"VI (hm³)": volumes})
            for e, mes in enumerate(meses, 1):
                pontos[f"FOB {mes} (R$)"] = dados[e]["custos"]
            st.dataframe(pontos.round(2), hide_index=True, use_container_width=True)

        with aba4:
            st.markdown("""
            **1. Planejamento (do último mês ao primeiro).** Para cada volume discretizado,
            o programa resolve os dois cenários de afluência, faz a média dos custos
            e constrói aproximações da FCF para orientar os meses anteriores.

            **2. Simulação (do primeiro mês ao último).** Começa no volume inicial escolhido.
            O volume final de um mês passa a ser o inicial do seguinte. A tabela de operação
            tem uma linha por mês para cada trajetória de afluências.

            **3. Métodos.** No notebook original, o despacho utiliza o máximo das
            secantes completas. O modo alternativo usa cortes de suporte calculados
            pelas sensibilidades duais do balanço hídrico. Os resultados podem diferir.

            **Hipóteses.** Um reservatório (Batalha), duas térmicas, carga constante
            ao longo do horizonte, 720 horas por mês, cenários equiprováveis e custo terminal zero.
            Este é um modelo didático, não um modelo operacional oficial.
            """)


# Preserva os controles do laboratório oculto durante a limpeza de widgets do Streamlit.
botoes_acao = {"duas_restaurar", "duas_aplicar", "duas_calcular", "duas_csv", "duas_csv_fcf", "pl_restaurar", "pl_csv"}
for chave in tuple(st.session_state):
    parametro = chave in CONTROLES_PADRAO or chave.startswith(("afluencia_", "fcf_", "duas_", "pl_"))
    if parametro and chave not in botoes_acao:
        st.session_state[chave] = st.session_state[chave]

aba_uma_uhe, aba_duas_uhes, aba_pl_unico = st.tabs(
    ["PDE Didática 1 UHE", "PDE Didática 2 UHEs", "PL Único 2 UHEs"],
    key="laboratorio_ativo", on_change="rerun",
)
if aba_uma_uhe.open:
    with aba_uma_uhe:
        renderizar_uma_uhe()
if aba_duas_uhes.open:
    with aba_duas_uhes:
        from laboratorio_duas_uhes import renderizar

        renderizar()

if aba_pl_unico.open:
    with aba_pl_unico:
        from laboratorio_pl_unico import renderizar_pl

        renderizar_pl()
