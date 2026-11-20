# Laboratório PDE — UHE Batalha

Aplicativo Streamlit **original e didático** com controles deslizantes para discretizações, carga, volume inicial e afluências mensais. Apresenta planejamento de janeiro a março, custos por cenário, evolução do reservatório, aproximações da FCF e download CSV.

## Como executar

1. Coloque `app.py` e `requirements.txt` na mesma pasta.
2. No terminal, execute `pip install -r requirements.txt`.
3. Execute `streamlit run app.py`.
4. Para publicar no Streamlit Community Cloud, envie ambos os arquivos a um repositório seu no GitHub e selecione `app.py` ao criar o app.

## Origem e diferenças

Baseado na formulação e nos parâmetros da PDE de três meses fornecidos na conversa. O modelo matemático de despacho é linear; nesta versão, ele é resolvido via `scipy.optimize.linprog` (HiGHS) em vez de PySCIPOpt, para simplificar a implantação. A aplicação **não foi extraída diretamente do seu Colab**, porque o link do notebook atual não foi fornecido.

Existem dois modos de planejamento: (1) secantes completas do código original e (2) cortes por duais. A linha azul dos gráficos é a interpolação por segmentos dos pontos calculados; ela não coincide necessariamente com o máximo das secantes completas usado pelo modo original. Nos dois modos, fevereiro e janeiro são calculados de acordo com a política escolhida no mês posterior.

O aplicativo considera apenas UHE Batalha e duas térmicas; não é uma réplica do painel de outras pessoas nem inclui Serra do Facão. A extensão para 12 meses exige adicionar as afluências e ajustar a configuração das etapas.
