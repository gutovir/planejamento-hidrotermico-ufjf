# Planejamento Hidrotérmico — UFJF

Aplicativo Streamlit **original e didático** com três laboratórios independentes para planejamento hidrotérmico. As abas **PDE Didática 1 UHE**, **PDE Didática 2 UHEs** e **PL Único 2 UHEs** compartilham a identidade visual e oferecem horizontes de 3 a 24 meses, controles de carga, volumes iniciais e afluências, além de exportação em CSV. A discretização pertence aos laboratórios de PDE.

O cenário padrão de uma UHE usa janeiro a março, carga de 50 MW médios, 10 estados, volume inicial de 430,05 hm³ e o método de secantes. As afluências padrão dos 12 meses vêm do notebook de referência em `referencias_colab`. Por hipótese didática autorizada, o segundo ano repete o perfil anual original. Os sliders permitem editar cada mês individualmente. **Restaurar valores padrão** recupera o cenário inicial e limpa as edições de afluência.

A aba de operação utiliza Plotly para apresentar **Geração mensal — Pessimista**, **Geração mensal — Otimista**, volumes finais em percentual do volume útil e **Custo imediato mensal**. O armazenamento inclui o ponto **Inicial** e os tooltips conservam os volumes em hm³. A escala monetária se adapta aos custos, com tooltips em reais no formato brasileiro. Os gráficos reutilizam os resultados calculados. A FCF de uma UHE continua apresentada com Pyecharts, e a FCF de duas UHEs utiliza mapa de calor e superfície 3D.

A aba principal **PDE Didática 1 UHE** reúne operação dos cenários, FCF, tabelas e explicação do modelo. Os meses são identificados pelos anos de 2026 e 2027. Na lateral, **Mês a mês** permite selecionar e editar um mês. **Todos os meses** permite preparar um par de afluências e usar **Aplicar a todos os meses** para atualizar o horizonte selecionado. Alternar entre os modos preserva as edições mensais.

A aba **PDE Didática 2 UHEs** implementa exclusivamente a seção 3 de `Planejamento_Energético_Códigos_utlimo_versaofinaldo2UHEs.ipynb`, com PySCIPOpt. O padrão usa três meses, cinco níveis por reservatório, carga de 150 MW médios e os volumes iniciais da referência. O painel **Experimento · 2 UHEs**, na barra lateral, permite ajustar o horizonte de 3 a 24 meses, a carga de 0 a 300 MW médios e os níveis de cada reservatório de 2 a 25. Os resultados são recalculados automaticamente ao alterar parâmetros. Os padrões de 2027 repetem o perfil anual de 2026 por hipótese didática, com edição independente de cada mês. Cada laboratório tem sua própria restauração e seu próprio estado. A primeira abertura após a atualização da referência carrega os padrões da nova versão.

A aba **PL Único 2 UHEs** utiliza exclusivamente a seção 5 de `Planejamento_Energético_Códigos_OficialPLUNICO.ipynb`. O padrão tem três meses, carga de 150 MW médios e os volumes iniciais da referência. Cada trajetória é resolvida em um único PL determinístico para todo o horizonte, com CVXOPT/GLPK. A entrada mantém a convenção do notebook, com cenário 0 otimista e 1 pessimista. Os controles oferecem carga de 0 a 300 MW médios, horizonte, volumes iniciais e afluências editáveis. Os gráficos de armazenamento do PL reúnem as quatro trajetórias em uma figura. A descrição do modelo e as tabelas preservam as unidades hidráulicas de hm³ por estágio.

Ao selecionar uma das três abas principais, a barra lateral exibe os controles desse laboratório. Os parâmetros de cada um são preservados ao alternar as abas. Essa navegação utiliza as abas com estado do Streamlit 1.67 ou superior.

As vazões naturais do laboratório de duas UHEs vêm da seção 3. A incremental de Serra do Facão usa a hipótese didática `máximo(0, natural de Serra − natural de Batalha)`. A defluência de Batalha chega a Serra no mesmo mês. Cada cenário conjunto tem probabilidade de 50%. O mapa de calor e a superfície 3D exibem os custos esperados nos estados discretizados. Os planos de suporte bidimensionais utilizados na recursão podem ser consultados separadamente.

Execute `python -m unittest discover -v` para conferir a equivalência das duas UHEs com a seção 3, do PL Único com a seção 5, a contabilidade e as séries dos gráficos. Os testes leem os notebooks e executam as células de cálculo em memória.

## Como executar

1. Mantenha os arquivos Python e `requirements.txt` na raiz do projeto.
2. No terminal, execute `pip install -r requirements.txt`.
3. Execute `streamlit run app.py`.
4. O ponto de entrada do Streamlit é `app.py`.

## Origem e diferenças

O laboratório de uma UHE utiliza `scipy.optimize.linprog` com HiGHS. O laboratório de duas UHEs utiliza PySCIPOpt e a seção 3 da última versão final do Colab. O PL Único utiliza CVXOPT/GLPK e a seção 5 do notebook oficial. Cada modelo mantém seus próprios dados, funções e resultados.

Na PDE de uma UHE existem dois modos de planejamento. O primeiro usa secantes completas do código original e o segundo usa cortes por duais. A linha azul da FCF representa a interpolação por segmentos dos pontos calculados. No despacho por secantes, a FCF usa o máximo das retas prolongadas. A PDE calcula cada estágio com a política do mês seguinte e usa custo futuro zero no último estágio.

Os laboratórios utilizam Batalha, Candeias e Baliza. Os modelos de duas UHEs incluem Serra do Facão em cascata. Todos os estágios têm 720 horas. As PDEs usam dois cenários equiprováveis. No PL Único, cada trajetória determinística é resolvida separadamente.
