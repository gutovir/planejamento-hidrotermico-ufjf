"""Interface independente do laboratório de duas hidrelétricas em cascata."""

import streamlit as st

from modelo_duas_uhes import (
    CONFIG_2U,
    REFERENCIA_2U,
    UHES_2U,
    AFL_NAT_BATALHA_2U,
    AFL_NAT_SERRA_2U,
    MESES_2U,
    planejar_duas_uhes,
    simular_duas_uhes,
    meses_planejamento,
)
from graficos_duas_uhes import (
    geracao_mensal,
    armazenamento,
    custos_mensais,
    figuras_fcf,
)
from validacao_duas_uhes import validar_simulacao


@st.cache_data(show_spinner=False)
def calcular(cfg, naturais_batalha, naturais_serra):
    barra = st.progress(0.0, text="Calculando a PDE de duas UHEs…")
    try:
        volumes_b, volumes_s, cortes, pontos = planejar_duas_uhes(
            cfg,
            naturais_batalha,
            naturais_serra,
            progresso=barra.progress,
        )
    finally:
        barra.empty()
    tabela = simular_duas_uhes(cfg, naturais_batalha, naturais_serra, cortes)
    validacoes = validar_simulacao(tabela, cfg)
    if not validacoes["Aprovada"].all():
        falhas = validacoes.loc[~validacoes["Aprovada"], "Verificação"].tolist()
        raise RuntimeError(f"Falha na conferência dos resultados: {', '.join(falhas)}")
    return volumes_b, volumes_s, cortes, pontos, tabela, validacoes


def restaurar():
    for chave in tuple(st.session_state):
        if chave.startswith("duas_"):
            del st.session_state[chave]


def salvar_afluencia(usina, indice):
    st.session_state[f"duas_afl_{usina}_{indice}"] = st.session_state[
        f"duas_intervalo_{usina}_{indice}"
    ]


def aplicar_todos(usina):
    for i in range(st.session_state["duas_meses"]):
        st.session_state[f"duas_afl_{usina}_{i}"] = st.session_state[
            f"duas_global_{usina}"
        ]


def parametros():
    for chave in tuple(st.session_state):
        if chave.startswith("duas_global_") or chave in (
            "duas_mes_afl",
            "duas_mes_fcf",
            "duas_estagio_tabela",
        ):
            st.session_state[chave] = st.session_state[chave]
    for chave, valor in CONFIG_2U.items():
        st.session_state.setdefault(f"duas_{chave}", valor)
    # Os pares mensais persistem mesmo quando o mês fica fora do horizonte.
    for usina, valores in (
        ("batalha", AFL_NAT_BATALHA_2U),
        ("serra", AFL_NAT_SERRA_2U),
    ):
        for i in range(24):
            par = valores[i % 12]
            st.session_state.setdefault(f"duas_afl_{usina}_{i}", tuple(map(float, par)))
    with st.sidebar.expander("Experimento · 2 UHEs", expanded=True):
        st.button(
            "Restaurar valores padrão · 2 UHEs",
            key="duas_restaurar",
            on_click=restaurar,
        )
        horizonte = st.slider("Horizonte · 2 UHEs (meses)", 3, 24, key="duas_meses")
        if horizonte > 12:
            st.info(
                "Hipótese didática de repetição do perfil anual: os padrões de 2027 "
                "repetem os de 2026. Essa repetição não representa previsão hidrológica. "
                "Cada mês pode ser editado individualmente."
            )
        st.slider(
            "Carga · 2 UHEs (MW médios)", 0.0, 300.0, step=1.0, key="duas_carga_mwmed"
        )
        st.slider("Níveis de Batalha", 2, 25, key="duas_niveis_batalha")
        st.slider("Níveis de Serra do Facão", 2, 25, key="duas_niveis_serra")
        for nome, chave in (("Batalha", "batalha"), ("Serra do Facão", "serra")):
            limites = UHES_2U[nome]
            st.slider(
                f"Volume inicial · {nome} (hm³)",
                limites["vmin"],
                limites["vmax"],
                step=0.01,
                key=f"duas_volume_inicial_{chave}",
            )
        numero = (
            2
            * horizonte
            * st.session_state["duas_niveis_batalha"]
            * st.session_state["duas_niveis_serra"]
        )
        st.caption(
            f"{numero:,} despachos no planejamento e {2 * horizonte} na simulação."
        )
        if numero >= 1000:
            st.warning(
                "A malha conjunta pode levar mais tempo. As alterações recalculam automaticamente a PDE."
            )
        st.markdown("**Afluências naturais (m³/s)**")
        modo = st.radio(
            "Ajustar afluências · 2 UHEs",
            ("Mês a mês", "Todos os meses"),
            key="duas_modo",
        )
        if st.session_state.get("duas_mes_afl", 0) >= horizonte:
            st.session_state["duas_mes_afl"] = 0
        if modo == "Mês a mês":
            i = st.selectbox(
                "Mês das afluências · 2 UHEs",
                range(horizonte),
                format_func=lambda i: meses_planejamento(horizonte)[i],
                key="duas_mes_afl",
            )
            for usina, nome in (("batalha", "Batalha"), ("serra", "Serra do Facão")):
                chave = f"duas_intervalo_{usina}_{i}"
                st.session_state[chave] = st.session_state[f"duas_afl_{usina}_{i}"]
                st.slider(
                    f"{nome} · Pessimista / Otimista",
                    0.0,
                    1000.0,
                    step=0.01,
                    format="%.2f",
                    key=chave,
                    on_change=salvar_afluencia,
                    args=(usina, i),
                )
        else:
            st.caption(
                "Mover a barra aplica o par aos meses selecionados e recalcula automaticamente."
            )
            for usina in ("batalha", "serra"):
                st.session_state.setdefault(
                    f"duas_global_{usina}", st.session_state[f"duas_afl_{usina}_0"]
                )
                st.slider(
                    f"{usina.title()} · Pessimista / Otimista",
                    0.0,
                    1000.0,
                    step=0.01,
                    format="%.2f",
                    key=f"duas_global_{usina}",
                    on_change=aplicar_todos,
                    args=(usina,),
                )
        st.caption(
            "Serra incremental = máximo(0, natural de Serra − natural de Batalha). "
            "Hipótese didática com cenários de probabilidade 50%."
        )
    cfg = {chave: st.session_state[f"duas_{chave}"] for chave in CONFIG_2U}
    afls = tuple(
        tuple(st.session_state[f"duas_afl_{usina}_{i}"] for i in range(horizonte))
        for usina in ("batalha", "serra")
    )
    return cfg, afls


def renderizar():
    if st.session_state.get("duas_referencia") != REFERENCIA_2U:
        restaurar()
        st.session_state["duas_referencia"] = REFERENCIA_2U
    cfg, afls = parametros()
    st.subheader("Batalha e Serra do Facão em cascata")
    st.caption(
        f"Referência da seção 3 de {REFERENCIA_2U}. Batalha a montante e Serra do Facão a jusante."
    )
    st.info(
        "Hipótese hidrológica didática: a incremental de Serra é estimada pela diferença "
        "não negativa das vazões naturais dos dois cenários. As séries não são historicamente "
        "pareadas. A defluência de Batalha chega a Serra no mesmo mês, sem perdas ou atraso."
    )
    solicitado = (cfg, afls)
    mudou = st.session_state.get("duas_parametros_calculados") != solicitado
    if "duas_resultados" not in st.session_state or mudou:
        try:
            resultado = calcular(cfg, *afls)
        except (RuntimeError, ValueError) as erro:
            st.error(f"Não foi possível calcular o laboratório de duas UHEs. {erro}")
            return
        st.session_state["duas_resultados"] = resultado
        st.session_state["duas_parametros_calculados"] = solicitado
    volumes_b, volumes_s, cortes, pontos, tabela, _ = st.session_state[
        "duas_resultados"
    ]
    resumo = tabela.groupby("Cenário")["Custo imediato (R$)"].sum()
    a, b, c = st.columns(3)
    a.metric("Custo operacional · pessimista", f"R$ {resumo['Pessimista']:,.2f}")
    b.metric("Custo operacional · otimista", f"R$ {resumo['Otimista']:,.2f}")
    numero = 2 * cfg["meses"] * len(volumes_b) * len(volumes_s)
    c.metric("Despachos no planejamento", numero)
    st.caption(
        f"{cfg['meses']} meses · {len(volumes_b)} × {len(volumes_s)} níveis "
        f"= {len(volumes_b) * len(volumes_s)} estados por mês · {2 * cfg['meses']} despachos na simulação."
    )
    operacao, fcf, tabelas, modelo = st.tabs(
        [
            "📊 Operação dos cenários",
            "📉 Função de Custo Futuro (FCF)",
            "📋 Tabelas",
            "📖 Entenda o modelo",
        ]
    )
    with operacao:
        for nome, aba in zip(
            ("Pessimista", "Otimista"), st.tabs(["Pessimista", "Otimista"])
        ):
            with aba:
                st.plotly_chart(
                    geracao_mensal(tabela, nome, cfg["carga_mwmed"]),
                    use_container_width=True,
                    key=f"duas_geracao_{nome}",
                )
        for usina in UHES_2U:
            st.caption(f"Reservatório · {usina}")
            st.plotly_chart(
                armazenamento(tabela, usina),
                use_container_width=True,
                key=f"duas_volume_{usina}",
            )
        st.plotly_chart(
            custos_mensais(tabela), use_container_width=True, key="duas_custos"
        )
    with fcf:
        st.subheader("Função de Custo Futuro (FCF)")
        st.caption(
            "A malha apresenta a FOB esperada calculada pela PDE. A superfície conecta esses "
            "valores para visualização. Os planos de suporte utilizados no despacho são armazenados separadamente."
        )
        anos = tuple(range(2026, 2026 + (cfg["meses"] + 11) // 12))
        if st.session_state.get("duas_ano_fcf") not in anos:
            st.session_state["duas_ano_fcf"] = anos[0]
        ano = st.radio(
            "Ano da FCF · 2 UHEs",
            anos,
            horizontal=True,
            key="duas_ano_fcf",
            label_visibility="collapsed",
        )
        inicio_ano = (ano - 2026) * 12
        meses_ano = min(12, cfg["meses"] - inicio_ano)
        if st.session_state.get("duas_mes_fcf", 0) >= meses_ano:
            st.session_state["duas_mes_fcf"] = 0
        mes = st.radio(
            "Mês da FCF · 2 UHEs",
            range(meses_ano),
            format_func=lambda i: MESES_2U[i],
            horizontal=True,
            key="duas_mes_fcf",
            label_visibility="collapsed",
        )
        estagio = inicio_ano + mes + 1
        calor, superficie = figuras_fcf(pontos[estagio], volumes_b, volumes_s)
        st.subheader("FCF — Mapa de calor")
        st.plotly_chart(calor, use_container_width=True, key="duas_calor")
        st.subheader("FCF — Superfície 3D")
        st.plotly_chart(superficie, use_container_width=True, key="duas_superficie")
        with st.expander("Detalhes matemáticos dos planos de suporte", expanded=False):
            st.subheader("FCF — Planos de suporte")
            st.latex(r"\alpha \geq a\,VF_{Batalha} + b\,VF_{Serra} + c")
            st.caption(
                "Coeficientes originais dos planos do estágio selecionado. "
                "A envoltória utiliza o máximo dos planos e zero."
            )
            st.dataframe(cortes[estagio], hide_index=True, use_container_width=True)
    with tabelas:
        st.subheader("Resultados completos")
        st.dataframe(tabela, hide_index=True, use_container_width=True)
        st.download_button(
            "Baixar resultados · 2 UHEs (CSV)",
            tabela.to_csv(index=False).encode("utf-8-sig"),
            "pde_duas_uhes_resultados.csv",
            "text/csv",
            key="duas_csv",
        )
        st.subheader("Custos calculados por estado e estágio")
        if st.session_state.get("duas_estagio_tabela", 1) > cfg["meses"]:
            st.session_state["duas_estagio_tabela"] = 1
        estagio_tabela = st.selectbox(
            "Estágio · 2 UHEs",
            range(1, cfg["meses"] + 1),
            format_func=lambda e: meses_planejamento(cfg["meses"])[e - 1],
            key="duas_estagio_tabela",
        )
        st.dataframe(pontos[estagio_tabela], hide_index=True, use_container_width=True)
        st.download_button(
            "Baixar custos por estado (CSV)",
            pontos[estagio_tabela].to_csv(index=False).encode("utf-8-sig"),
            f"pde_duas_uhes_estagio_{estagio_tabela}.csv",
            "text/csv",
            key="duas_csv_fcf",
        )
    with modelo:
        explicar_modelo()


def explicar_modelo():
    st.markdown("""
    **Configuração em cascata.** A defluência de Batalha entra em Serra do Facão no mesmo mês.
    As vazões estão em m³/s e os volumes em hm³. Cada estágio tem 720 horas e fator de conversão 2,592.
    """)
    st.latex(r"VF_B = VI_B + 2{,}592(A_B - VT_B - VV_B)")
    st.latex(r"VF_S = VI_S + 2{,}592(A_{S,inc} + VT_B + VV_B - VT_S - VV_S)")
    st.latex(r"0{,}3551 VT_B + 0{,}6157 VT_S + GT_C + GT_A + DEF = CARGA")
    st.markdown("""
    **Limites operativos.** Batalha armazena de 430,05 a 1.781,61 hm³ e turbina até 147 m³/s.
    Serra armazena de 1.752 a 5.199 hm³ e turbina até 313 m³/s. Candeias gera até 17 MW
    e Baliza até 18 MW. O déficit é uma variável não negativa.

    **Função objetivo.** Os custos de Candeias e Baliza são 118,93 e 917,12 R$/MWh.
    O déficit custa 8.291 R$/MWh. O vertimento de cada usina custa 0,01 R$/hm³.
    """)
    st.latex(
        r"\min\;720(118{,}93GT_C+917{,}12GT_A+8291DEF)+0{,}01\cdot2{,}592(VV_B+VV_S)+\alpha"
    )
    st.markdown("""
    **PDE regressiva.** A malha conjunta combina os níveis dos dois volumes iniciais. Em cada estado,
    resolvemos os dois cenários com probabilidade de 50% cada. As médias do custo e dos duais dos
    balanços geram um plano por estado. A recursão segue do último mês ao primeiro.
    O último estágio usa custo futuro zero. Na simulação, ambos os volumes finais passam ao mês seguinte.
    """)
    st.latex(r"\alpha \geq a\,VF_B + b\,VF_S + c,\qquad \alpha\geq0")
    st.markdown("""
    **Mapa e superfície.** Cada ponto representa o custo esperado da função objetivo em um par
    de volumes iniciais, incluindo o custo futuro dos estágios seguintes. A envoltória dos planos
    usados pelo otimizador é uma representação distinta e depende dos dois volumes finais.

    **Custos com reservatórios cheios.** O armazenamento elevado pode exigir vertimento para
    respeitar os limites e a carga. Há penalidade de vertimento em ambas as usinas. O custo operacional
    de uma trajetória soma somente custos imediatos. A FOB também contém alpha.

    **Hipóteses hidrológicas.** As vazões naturais são cenários mensais da seção 3. A incremental
    didática usa máximo(0, natural de Serra − natural de Batalha). A construção ignora a covariância
    e a simultaneidade das séries. Para horizontes acima de 12 meses, os padrões de 2027
    repetem o perfil de 2026 por hipótese didática. Cada mês tem afluências editáveis.
    """)
