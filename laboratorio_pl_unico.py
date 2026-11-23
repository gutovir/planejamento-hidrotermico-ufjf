"""Laboratório determinístico independente do PL Único em cascata."""

import streamlit as st

from modelo_pl_unico import (
    CONFIG_PL,
    UHES_PL,
    AFL_NAT_BATALHA_PL,
    AFL_NAT_SERRA_PL,
    REFERENCIA_PL,
    construir_sistema,
    resolver_cenarios,
    meses_planejamento_pl,
)
from graficos_duas_uhes import geracao_mensal, armazenamento, custos_mensais


@st.cache_data(show_spinner=False)
def calcular_pl(cfg, naturais_batalha, naturais_serra):
    sistema = construir_sistema(cfg, naturais_batalha, naturais_serra)
    resultados, tabela = resolver_cenarios(sistema)
    return sistema, resultados, tabela


def restaurar_pl():
    for chave in tuple(st.session_state):
        if chave.startswith("pl_"):
            del st.session_state[chave]


def salvar_par_pl(usina, mes):
    st.session_state[f"pl_afl_{usina}_{mes}"] = st.session_state[
        f"pl_intervalo_{usina}_{mes}"
    ]


def aplicar_todos_pl(usina):
    for i in range(st.session_state["pl_meses"]):
        st.session_state[f"pl_afl_{usina}_{i}"] = st.session_state[f"pl_global_{usina}"]


def parametros_pl():
    for chave, valor in CONFIG_PL.items():
        st.session_state.setdefault(f"pl_{chave}", valor)
    for nome, valores in (("batalha", AFL_NAT_BATALHA_PL), ("serra", AFL_NAT_SERRA_PL)):
        for i in range(24):
            st.session_state.setdefault(
                f"pl_afl_{nome}_{i}", tuple(map(float, valores[i % 12]))
            )
    with st.sidebar:
        st.header("Experimento · PL Único")
        st.button(
            "Restaurar valores padrão · PL Único",
            on_click=restaurar_pl,
            key="pl_restaurar",
        )
        horizonte = st.slider("Horizonte · PL Único (meses)", 3, 24, key="pl_meses")
        st.slider("Carga · PL Único (MW médios)", 0.0, 300.0, step=1.0, key="pl_carga")
        for uhe, chave in zip(UHES_PL, ("vi_batalha", "vi_serra")):
            st.slider(
                f"Volume inicial · {uhe['Nome']} (hm³)",
                uhe["Vmin"],
                uhe["Vmax"],
                step=0.01,
                key=f"pl_{chave}",
            )
        st.subheader("Afluências naturais (m³/s)")
        modo = st.radio(
            "Ajustar afluências · PL Único",
            ("Mês a mês", "Todos os meses"),
            key="pl_modo",
        )
        if horizonte > 12:
            st.info(
                "Hipótese didática de repetição anual: os padrões de 2027 repetem os de 2026. "
                "Cada mês é editável. Essa repetição não representa previsão hidrológica."
            )
        if st.session_state.get("pl_mes_afl", 0) >= horizonte:
            st.session_state["pl_mes_afl"] = 0
        if modo == "Mês a mês":
            mes = st.selectbox(
                "Mês das afluências · PL Único",
                range(horizonte),
                format_func=lambda i: meses_planejamento_pl(horizonte)[i],
                key="pl_mes_afl",
            )
            for usina, nome in (("batalha", "Batalha"), ("serra", "Serra do Facão")):
                chave = f"pl_intervalo_{usina}_{mes}"
                st.session_state[chave] = st.session_state[f"pl_afl_{usina}_{mes}"]
                st.slider(
                    f"{nome} · Pessimista / Otimista",
                    0.0,
                    1000.0,
                    step=0.01,
                    key=chave,
                    format="%.2f",
                    on_change=salvar_par_pl,
                    args=(usina, mes),
                )
        else:
            st.caption(
                "Mover uma barra aplica o par aos meses selecionados e recalcula o PL."
            )
            for usina, nome in (("batalha", "Batalha"), ("serra", "Serra do Facão")):
                chave = f"pl_global_{usina}"
                st.session_state.setdefault(
                    chave, st.session_state[f"pl_afl_{usina}_0"]
                )
                st.slider(
                    f"{nome} · Pessimista / Otimista",
                    0.0,
                    1000.0,
                    step=0.01,
                    key=chave,
                    format="%.2f",
                    on_change=aplicar_todos_pl,
                    args=(usina,),
                )
        st.caption(
            "A incremental de Serra usa máximo(0, natural de Serra − natural de Batalha), "
            "como hipótese didática da referência."
        )
    cfg = {chave: st.session_state[f"pl_{chave}"] for chave in CONFIG_PL}
    afls = tuple(
        tuple(st.session_state[f"pl_afl_{usina}_{i}"] for i in range(horizonte))
        for usina in ("batalha", "serra")
    )
    return cfg, afls


def tabela_visual_pl(tabela):
    return tabela.rename(
        columns={
            "VI UHE Batalha (hm³)": "VI Batalha (hm³)",
            "VF UHE Batalha (hm³)": "VF Batalha (hm³)",
            "VI UHE Serra do Facão (hm³)": "VI Serra (hm³)",
            "VF UHE Serra do Facão (hm³)": "VF Serra (hm³)",
            "Geração UHE Batalha (MW)": "GH Batalha (MW)",
            "Geração UHE Serra do Facão (MW)": "GH Serra (MW)",
            "ERB Candeias (MW)": "Candeias (MW)",
            "BBF Baliza (MW)": "Baliza (MW)",
        }
    )


def renderizar_pl():
    cfg, afls = parametros_pl()
    st.subheader("PL Único — Batalha e Serra do Facão em cascata")
    st.caption(f"Referência · seção 5 de {REFERENCIA_PL}")
    st.info(
        "Cada cenário é determinístico, com suas afluências conhecidas para todo o horizonte. "
        "Todos os meses são otimizados conjuntamente em um único problema linear por cenário."
    )
    solicitado = (cfg, afls)
    if (
        st.session_state.get("pl_parametros_calculados") != solicitado
        or "pl_resultados" not in st.session_state
    ):
        try:
            with st.spinner("Otimizando os dois cenários do PL Único…"):
                resultados = calcular_pl(cfg, *afls)
        except (RuntimeError, ValueError, ArithmeticError) as erro:
            st.error(f"Não foi possível calcular o PL Único. {erro}")
            return
        st.session_state["pl_resultados"] = resultados
        st.session_state["pl_parametros_calculados"] = solicitado
    sistema, resultados, tabela = st.session_state["pl_resultados"]
    a, b, c = st.columns(3)
    a.metric(
        "Custo total · pessimista",
        f"R$ {resultados['Pessimista']['DGer']['CustoTotal']:,.2f}".translate(
            str.maketrans(",.", ".,")
        ),
    )
    b.metric(
        "Custo total · otimista",
        f"R$ {resultados['Otimista']['DGer']['CustoTotal']:,.2f}".translate(
            str.maketrans(",.", ".,")
        ),
    )
    c.metric("Problemas lineares resolvidos", 2)
    st.caption(
        f"{cfg['meses']} meses · carga de {cfg['carga']:g} MW médios · "
        "o custo total soma os custos imediatos mensais de cada cenário."
    )
    operacao, tabelas, modelo = st.tabs(
        ["📊 Operação dos cenários", "📋 Tabelas", "📖 Entenda o modelo"]
    )
    visual = tabela_visual_pl(tabela)
    with operacao:
        for nome, painel in zip(
            ("Pessimista", "Otimista"), st.tabs(["Pessimista", "Otimista"])
        ):
            with painel:
                st.plotly_chart(
                    geracao_mensal(visual, nome, sistema["DGer"]["Carga"]),
                    use_container_width=True,
                    key=f"pl_geracao_{nome}",
                )
        limites = {
            nome: {"vmin": u["Vmin"], "vmax": u["Vmax"]}
            for nome, u in zip(("Batalha", "Serra do Facão"), sistema["UHE"])
        }
        st.plotly_chart(
            armazenamento(visual, limites=limites, mostrar_limites=False),
            use_container_width=True,
            key="pl_volumes",
        )
        st.plotly_chart(
            custos_mensais(visual), use_container_width=True, key="pl_custos"
        )
    with tabelas:
        st.subheader("Resultados completos")
        st.dataframe(tabela, hide_index=True, use_container_width=True)
        st.download_button(
            "Baixar resultados · PL Único (CSV)",
            tabela.to_csv(index=False).encode("utf-8-sig"),
            "pl_unico_resultados.csv",
            "text/csv",
            key="pl_csv",
        )
    with modelo:
        st.markdown("""
        **Otimização conjunta.** O PL Único resolve todos os meses simultaneamente para cada trajetória
        de afluências. As duas trajetórias são problemas determinísticos independentes. A soma dos custos
        térmicos, do déficit e dos vertimentos em todos os meses compõe a função objetivo.

        **Cascata.** A água turbinada e vertida em Batalha chega a Serra do Facão no mesmo mês.
        A afluência incremental didática de Serra é máximo(0, natural de Serra − natural de Batalha).
        As séries naturais representam cenários mensais da referência e não são historicamente pareadas.

        **Unidades e limites.** O PL utiliza volumes e decisões hidráulicas em hm³ por estágio.
        As vazões em m³/s são convertidas por 2,592. As produtividades são divididas pelo mesmo fator,
        e os engolimentos são multiplicados por ele. Cada mês tem 720 horas. Os limites físicos e os
        custos de geração são os definidos no notebook oficial.
        """)
        st.latex(r"VF_{B,t}=VI_{B,t}+AFL_{B,t}-VT_{B,t}-VV_{B,t}")
        st.latex(
            r"VF_{S,t}=VI_{S,t}+AFL^{inc}_{S,t}+VT_{B,t}+VV_{B,t}-VT_{S,t}-VV_{S,t}"
        )
        st.latex(
            r"Prod_B VT_{B,t}+Prod_S VT_{S,t}+GT_{Baliza,t}+GT_{Candeias,t}+DEF_t=CARGA_t"
        )
        st.latex(
            r"\min\sum_t\left[720(917{,}12GT_{Baliza,t}+118{,}93GT_{Candeias,t}+8291DEF_t)+0{,}01(VV_{B,t}+VV_{S,t})\right]"
        )
        st.markdown("""
        **Acoplamento no tempo.** O volume final de um mês é o volume inicial do seguinte em ambas
        as usinas. O último volume respeita os limites operativos da referência.

        **Diferença metodológica.** A PDE aproxima custos futuros por estados e planos de suporte.
        O PL Único utiliza o conhecimento completo das afluências de cada cenário para otimizar o horizonte
        conjuntamente. O gráfico de armazenamento inclui o ponto Inicial e converte os volumes finais
        para percentual apenas na apresentação. As tabelas e o otimizador conservam os volumes em hm³.
        """)
