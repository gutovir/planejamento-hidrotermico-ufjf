"""Gráficos que utilizam exclusivamente os resultados já calculados."""

import numpy as np
import plotly.graph_objects as go

from modelo_duas_uhes import CENARIOS_2U, UHES_2U, matriz_custos

CORES = {"Pessimista": "#92592D", "Otimista": "#3678B6"}
CORES_VOLUMES_COMBINADOS = {
    ("Batalha", "Pessimista"): "#245F96",
    ("Batalha", "Otimista"): "#80C7F2",
    ("Serra do Facão", "Pessimista"): "#247A52",
    ("Serra do Facão", "Otimista"): "#9CDDB4",
}


def configurar_operacao(figura, eixo_y, meses):
    figura.update_layout(
        height=500,
        hovermode="x unified",
        xaxis_title="Mês",
        yaxis_title=eixo_y,
        legend=dict(orientation="h", x=0, y=1.04, xanchor="left", yanchor="bottom"),
        margin=dict(t=150, b=110),
        title_x=0,
        title_y=0.98,
    )
    figura.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=list(meses),
        automargin=True,
        title_standoff=20,
    )
    return figura


def geracao_mensal(tabela, cenario, carga=None):
    df = tabela.loc[tabela["Cenário"] == cenario]
    fig = go.Figure()
    for coluna, nome, cor in (
        ("GH Batalha (MW)", "UHE Batalha", "#3678B6"),
        ("GH Serra (MW)", "UHE Serra do Facão", "#378678"),
        ("Candeias (MW)", "ERB Candeias", "#92592D"),
        ("Baliza (MW)", "BBF Baliza", "#BB9368"),
        ("Déficit (MW)", "Déficit", "#B33C59"),
    ):
        if coluna not in df:
            continue
        fig.add_trace(
            go.Bar(
                x=df["Mês"].tolist(),
                y=df[coluna].tolist(),
                name=nome,
                marker_color=cor,
                hovertemplate="%{x}<br>%{y:,.4f} MW médios<extra>%{fullData.name}</extra>",
            )
        )
    if carga is not None:
        demanda = np.broadcast_to(np.asarray(carga, dtype=float), (len(df),))
        fig.add_trace(
            go.Scatter(
                x=df["Mês"].tolist(),
                y=demanda.tolist(),
                name="Carga (MW médios)",
                mode="lines+markers",
                line=dict(color="#84909A", dash="dash", width=2),
                hovertemplate="%{x}<br>Carga: %{y:,.2f} MW médios<extra></extra>",
            )
        )
    fig.update_layout(
        barmode="stack", title=dict(text=f"Geração mensal — {cenario}"), separators=",."
    )
    fig.update_yaxes(rangemode="tozero")
    return configurar_operacao(fig, "Potência média mensal (MW médios)", df["Mês"])


def armazenamento(tabela, usina=None, limites=None, mostrar_limites=True):
    reservatorios = UHES_2U if limites is None else limites
    nomes = (usina,) if usina else tuple(reservatorios)
    meses = ["Inicial", *tabela["Mês"].unique().tolist()]
    fig = go.Figure()
    for nome_usina in nomes:
        fisicos = reservatorios[nome_usina]
        sufixo = "Batalha" if nome_usina == "Batalha" else "Serra"
        for cenario in CENARIOS_2U:
            cor = CORES[cenario]
            if len(nomes) > 1:
                cor = CORES_VOLUMES_COMBINADOS[(nome_usina, cenario)]
            df = tabela.loc[tabela["Cenário"] == cenario]
            volumes = np.r_[df[f"VI {sufixo} (hm³)"].iloc[0], df[f"VF {sufixo} (hm³)"]]
            percentuais = (
                100 * (volumes - fisicos["vmin"]) / (fisicos["vmax"] - fisicos["vmin"])
            )
            fig.add_trace(
                go.Scatter(
                    x=meses,
                    y=percentuais.tolist(),
                    customdata=volumes.tolist(),
                    name=f"{nome_usina} — {cenario}",
                    mode="lines+markers",
                    line=dict(
                        color=cor,
                        width=3,
                        dash="solid" if len(nomes) > 1 or sufixo == "Batalha" else "dash",
                    ),
                    marker=dict(symbol="circle" if sufixo == "Batalha" else "diamond"),
                    hovertemplate=(
                        "%{fullData.name}<br>%{x}<br>Volume útil: %{y:,.2f}%"
                        "<br>Volume físico: %{customdata:,.2f} hm³<extra></extra>"
                    ),
                )
            )
    if mostrar_limites:
        for nome, valor in (("Mínimo", 0), ("Máximo", 100)):
            fig.add_trace(
                go.Scatter(
                    x=meses,
                    y=[valor] * len(meses),
                    name=f"{nome} ({valor}%)",
                    mode="lines",
                    line=dict(dash="dot", color="#84909A"),
                )
            )
    titulo = (
        "Volume final da UHE (% útil)"
        if len(reservatorios) == 1
        else "Volume final das UHEs (% útil)"
    )
    fig.update_layout(title=dict(text=titulo), separators=",.")
    if len(nomes) > 1:
        fig.update_layout(legend=dict(itemwidth=50, itemsizing="constant"))
    fig.update_yaxes(range=[-5, 105], ticksuffix="%", tickformat=".0f")
    return configurar_operacao(fig, "Volume útil (%)", meses)


def custos_mensais(tabela):
    usar_milhoes = tabela["Custo imediato (R$)"].abs().max() >= 1_000_000
    divisor = 1_000_000 if usar_milhoes else 1
    unidade = "milhões de R$" if usar_milhoes else "R$"
    fig = go.Figure()
    for nome in CENARIOS_2U:
        df = tabela.loc[tabela["Cenário"] == nome]
        fig.add_trace(
            go.Bar(
                x=df["Mês"].tolist(),
                y=(df["Custo imediato (R$)"] / divisor).tolist(),
                customdata=df["Custo imediato (R$)"].tolist(),
                text=[
                    f"{valor:,.2f}".translate(str.maketrans(",.", ".,"))
                    for valor in df["Custo imediato (R$)"]
                ],
                name=nome,
                marker_color=CORES[nome],
                hovertemplate=(
                    "%{x} | %{fullData.name}<br>"
                    "Custo imediato: R$ %{text}<extra></extra>"
                ),
                textposition="none",
            )
        )
    fig.update_layout(
        barmode="group", separators=",.", title=dict(text="Custo imediato mensal")
    )
    fig.update_yaxes(
        rangemode="tozero",
        tickformat=",.2f",
        showexponent="none",
        exponentformat="none",
        tickprefix="" if usar_milhoes else "R$ ",
        automargin=True,
    )
    return configurar_operacao(
        fig, f"Custo imediato ({unidade})", tabela["Mês"].unique()
    )


def figuras_fcf(pontos, volumes_b, volumes_s):
    custos = matriz_custos(pontos, volumes_b, volumes_s)
    usar_milhoes = abs(custos).max() >= 1_000_000
    divisor = 1_000_000 if usar_milhoes else 1
    unidade = "milhões de R$" if usar_milhoes else "R$"
    z = custos / divisor
    escala_monetaria = dict(
        tickformat=",.2f",
        exponentformat="none",
        showexponent="none",
        tickprefix="" if usar_milhoes else "R$ ",
    )
    barra_cores = dict(title=f"Custo esperado ({unidade})", **escala_monetaria)
    hover = (
        "Batalha: %{x:,.2f} hm³<br>Serra do Facão: %{y:,.2f} hm³"
        "<br>Custo esperado: R$ %{customdata:,.2f}<extra></extra>"
    )
    batalha = UHES_2U["Batalha"]
    serra = UHES_2U["Serra do Facão"]
    percentual_b = (
        100
        * (np.asarray(volumes_b) - batalha["vmin"])
        / (batalha["vmax"] - batalha["vmin"])
    )
    percentual_s = (
        100 * (np.asarray(volumes_s) - serra["vmin"]) / (serra["vmax"] - serra["vmin"])
    )
    malha_b, malha_s = np.meshgrid(volumes_b, volumes_s)
    dados_calor = np.stack((malha_b, malha_s, custos), axis=-1)
    calor = go.Figure(
        go.Heatmap(
            x=percentual_b,
            y=percentual_s,
            z=z,
            colorscale="Viridis",
            colorbar=dict(
                barra_cores, title=f"Custo esperado ({unidade})<br>↑ Maior · ↓ Menor"
            ),
            customdata=dados_calor,
            hovertemplate=(
                "Batalha: %{x:.6~g}% do volume útil — %{customdata[0]:,.2f} hm³"
                "<br>Serra do Facão: %{y:.6~g}% do volume útil — %{customdata[1]:,.2f} hm³"
                "<br>Custo esperado: R$ %{customdata[2]:,.2f}<extra></extra>"
            ),
        )
    )
    calor.update_layout(
        height=520,
        xaxis_title="Volume útil de Batalha (%)",
        yaxis_title="Volume útil de Serra do Facão (%)",
        separators=",.",
    )
    # Cada categoria representa um estado, com as células extremas inteiramente visíveis.
    calor.update_xaxes(
        type="category",
        categoryorder="array",
        categoryarray=percentual_b,
        tickmode="array",
        tickvals=percentual_b,
        ticktext=[f"{v:g}%".replace(".", ",") for v in percentual_b],
        range=[-0.5, len(percentual_b) - 0.5],
        automargin=True,
    )
    calor.update_yaxes(
        type="category",
        categoryorder="array",
        categoryarray=percentual_s,
        tickmode="array",
        tickvals=percentual_s,
        ticktext=[f"{v:g}%".replace(".", ",") for v in percentual_s],
        range=[-0.5, len(percentual_s) - 0.5],
        automargin=True,
    )
    superficie = go.Figure(
        go.Surface(
            x=volumes_b,
            y=volumes_s,
            z=z,
            colorscale="Viridis",
            colorbar=barra_cores,
            customdata=custos,
            hovertemplate=hover,
        )
    )
    superficie.update_layout(
        height=650,
        margin=dict(l=0, r=0, b=25, t=25),
        separators=",.",
        scene=dict(
            xaxis_title="VI Batalha (hm³)",
            yaxis_title="VI Serra (hm³)",
            zaxis=dict(title=f"Custo esperado ({unidade})", **escala_monetaria),
            aspectmode="cube",
        ),
    )
    return calor, superficie
