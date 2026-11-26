# Estudos de planejamento hidrotérmico

Aplicativo novo, independente do Streamlit anterior. Possui seis laboratórios com menus, parâmetros e resultados próprios:

1. PDE Didática com uma UHE.
2. PDE Didática com duas UHEs em cascata.
3. PL Único com duas UHEs.
4. PL Único em árvore completa.
5. PDDD com duas UHEs.
6. Histórico NEWAVE lido pelo PySDDP, resolvido por PDDD e conferido com o PL Único.

## Executar

Na raiz deste repositório:

```powershell
cd streamlit_estudos
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8503
```

O aplicativo anterior e os notebooks não são alterados.

## Dados e unidades

Os CSVs em `dados_padronizados` preservam as médias mais e menos um desvio padrão enviadas para o estudo. As entradas locais não sofrem subtração. Se a entrada for explicitamente natural total, Serra usa a diferença em relação a Batalha; incrementais negativas geram uma mensagem, sem truncamento silencioso.

Na seção PySDDP, a opção principal é **Enviar ZIP**. Compacte a pasta completa do caso NEWAVE (arquivos na raiz ou dentro de uma pasta) e envie pelo menu lateral. O limite é 50 MB compactados e 250 MB extraídos. A leitura aceita nomes de arquivos em maiúsculas ou minúsculas, inclusive em servidores Linux. Os dados enviados são mantidos na memória da sessão; a extração ocorre em uma pasta temporária removida após a leitura. Os dados do deck não são incorporados ao repositório. A opção de pasta local continua disponível para uso no computador onde o aplicativo é executado.

A leitura usa `PySDDP.Pen.Newave` na versão 0.0.90. São exibidos os parâmetros processados e as séries naturais e incrementais. O cadastro atual é mantido constante durante a trajetória histórica. Carga, térmicas, déficit e volumes iniciais permanecem premissas editáveis; não se reproduzem todas as restrições do NEWAVE.

Os estágios têm 720 horas. Volumes são exibidos em hm³. Os custos usam automaticamente R$, R$ mil, R$ milhões ou R$ bilhões nos gráficos, mantendo os valores em reais nos cálculos e CSVs. As UHEs usam marrom escuro e médio; térmicas dourado e laranja; déficit vinho; custos verde-petróleo; FCF bidimensional e superfície 3D Viridis.

A árvore tem primeiro estágio conhecido e duas aberturas conjuntas por mês. Os gráficos mensais representam expectativas ponderadas; as restrições valem em cada nó. Não há custo terminal ou estágio pós-horizonte.

## Validação

```powershell
python -m unittest discover -p "test_*.py" -v
```

Modelos e dados foram incorporados aos arquivos Python; a execução não depende de abrir ou executar notebooks.

## Hospedagem

O aplicativo requer um servidor Python com CVXOPT/GLPK e PySCIPOpt. Não é uma página HTML estática.

No Streamlit Community Cloud, selecione o repositório, a branch de publicação e o arquivo `streamlit_estudos/app.py`. Use Python 3.12. As dependências próprias estão ao lado do arquivo de entrada. A aplicação antiga pode continuar usando sua branch e entrada anteriores.

Como alternativa, o Dockerfile permite hospedar a pasta em um serviço que execute contêineres:

```sh
docker build -t planejamento-estudos .
docker run --rm -p 8503:8501 planejamento-estudos
```

Depois de hospedado, use a opção ZIP para carregar os dados a partir de qualquer computador. Os decks não precisam estar no GitHub.
