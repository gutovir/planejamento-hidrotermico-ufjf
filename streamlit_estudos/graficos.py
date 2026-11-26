"""Paleta e unidades comuns aos seis laboratórios."""
import numpy as np
import plotly.graph_objects as go

CORES={'UHE Batalha':'#503722','UHE Serra do Facão':'#8B5E3C',
       'ERB Candeias':'#F59F00','BBF Baliza':'#E8590C','Déficit':'#C2255C',
       'Custo':'#0B7285','Otimista':'#66B2B2','Pessimista':'#0B7285','Carga':'#343A40'}


def moeda(v):return f'{v:,.2f}'.translate(str.maketrans(',.','.,'))


def escala(valores):
    maior=float(np.max(np.abs(np.asarray(valores,dtype=float)))) if np.size(valores) else 0.
    for limite,unidade in [(1e9,'R$ bilhões'),(1e6,'R$ milhões'),(1e3,'R$ mil')]:
        if maior>=limite:return limite,unidade
    return 1.,'R$'


def base(fig,titulo,y):
    fig.update_layout(title=titulo,yaxis_title=y,xaxis_title='Mês',height=480,
                      separators=',.',legend=dict(orientation='h',y=1.12),
                      margin=dict(t=110,b=75,l=85,r=35),hovermode='x unified',
                      paper_bgcolor='white',plot_bgcolor='white',font_color='#343A40')
    fig.update_xaxes(type='category',automargin=True)
    fig.update_yaxes(automargin=True,gridcolor='#E5E7EB',rangemode='tozero',showexponent='none')
    return fig


def geracao(df,sistema,titulo='Atendimento à carga'):
    x=df['Nó'] if 'Nó' in df else df['Mês'];fig=go.Figure()
    fontes=[(f'Geração {u["Nome"]} (MW)',u['Nome']) for u in sistema['UHE']]
    fontes += [(u['Nome']+' (MW)',u['Nome']) for u in sistema['UTE']]+[('Déficit (MW)','Déficit')]
    for col,nome in fontes:
        fig.add_bar(x=x,y=np.maximum(df[col],0),name=nome,marker_color=CORES[nome],
                    hovertemplate='%{x}<br>%{y:,.3f} MW<extra>%{fullData.name}</extra>')
    fig.add_scatter(x=x,y=df['Carga (MW)'],name='Carga',mode='lines',line=dict(color=CORES['Carga'],dash='dash'))
    fig.update_layout(barmode='stack');base(fig,titulo,'MW médios')
    if 'Nó' in df:fig.update_xaxes(title='Nó')
    return fig


def custo(df):
    div,un=escala(df['Custo imediato (R$)']);fig=go.Figure()
    grupos=df.groupby('Cenário',sort=False) if 'Cenário' in df else [('Esperado',df)]
    for nome,g in grupos:
        fig.add_bar(x=g['Mês'],y=g['Custo imediato (R$)']/div,name=nome,
                    marker_color=CORES.get(nome,CORES['Custo']),
                    customdata=[moeda(v) for v in g['Custo imediato (R$)']],
                    hovertemplate='%{x}<br>R$ %{customdata}<extra>%{fullData.name}</extra>')
    fig.update_layout(barmode='group');fig.update_yaxes(tickformat=',.2f')
    return base(fig,'Custo imediato mensal',un)


def volumes(df,sistema):
    fig=go.Figure()
    for i,u in enumerate(sistema['UHE']):
        grupos=df.groupby('Cenário',sort=False) if 'Cenário' in df else [('Esperado',df)]
        for nome,g in grupos:
            fig.add_scatter(x=['Inicial']+g['Mês'].tolist(),y=[u['VI']]+g[f'VF {u["Nome"]} (hm³)'].tolist(),
                            name=f'{u["Nome"]} — {nome}',mode='lines+markers',
                            line=dict(color=CORES[u['Nome']],dash='dash' if nome=='Pessimista' else 'solid'),
                            marker_symbol='circle' if i==0 else 'diamond',
                            hovertemplate='%{x}<br>%{y:,.3f} hm³<extra>%{fullData.name}</extra>')
    return base(fig,'Volume total armazenado','Volume (hm³)')


def movimentacao(df,sistema):
    fig=go.Figure()
    for u in sistema['UHE']:
        for campo,nome in [('VT','Turbinado'),('VV','Vertido')]:
            fig.add_bar(x=df['Mês'],y=df[f'{campo} {u["Nome"]} (hm³)'],name=nome+' — '+u['Nome'],
                        marker_color=CORES[u['Nome']],opacity=1 if campo=='VT' else .45,
                        marker_pattern_shape='' if campo=='VT' else '/')
    fig.update_layout(barmode='group')
    return base(fig,'Turbinamento e vertimento','Volume (hm³)')


def convergencia(hist,referencia):
    div,un=escala(hist[['zinf','zsup']].to_numpy());fig=go.Figure()
    for col,nome,cor in [('zinf','ZINF',CORES['Custo']),('zsup','ZSUP',CORES['Déficit'])]:
        fig.add_scatter(x=hist['iteracao'].astype(str),y=hist[col]/div,name=nome,mode='lines+markers',
                        line_color=cor,customdata=[moeda(v) for v in hist[col]],
                        hovertemplate='Iteração %{x}<br>R$ %{customdata}<extra>%{fullData.name}</extra>')
    fig.add_hline(y=referencia/div,line_dash='dot',line_color='#737373',annotation_text='PL Único')
    base(fig,'Convergência da PDDD',un);fig.update_xaxes(title='Iteração')
    fig.update_yaxes(tickformat=',.2f')
    return fig


def fcf(pontos,sistema,cortes):
    div,un=escala(pontos['Custo (R$)']);fig=go.Figure()
    x=f'VI {sistema["UHE"][0]["Nome"]} (hm³)'
    if len(sistema['UHE'])==1:
        fig.add_scatter(x=pontos[x],y=pontos['Custo (R$)']/div,name='Custos amostrados',mode='lines+markers',line_color=CORES['UHE Batalha'])
        xx=np.linspace(pontos[x].min(),pontos[x].max(),150)
        for j,c in enumerate(cortes):
            yy=np.array([c['a'][0]*v+c['b'] for v in xx])
            fig.add_scatter(x=xx,y=np.where(yy>=0,yy/div,np.nan),mode='lines',name='Retas de suporte',
                            legendgroup='retas',showlegend=j==0,line=dict(color='#B58D64',width=1),opacity=.55)
        envelope=np.maximum(0,np.max([c['a'][0]*xx+c['b'] for c in cortes],axis=0))
        fig.add_scatter(x=xx,y=envelope/div,name='Envoltória dos cortes',line_color=CORES['Custo'])
        base(fig,'Custo esperado e cortes de suporte',un);fig.update_xaxes(type='linear',title='Volume inicial (hm³)')
        return fig,None
    y=f'VI {sistema["UHE"][1]["Nome"]} (hm³)'
    matriz=pontos.pivot(index=y,columns=x,values='Custo (R$)')
    barra=dict(title=un,tickformat=',.2f')
    fig.add_trace(go.Heatmap(x=matriz.columns,y=matriz.index,z=matriz.to_numpy()/div,colorscale='Viridis',
                             colorbar=barra,customdata=matriz.to_numpy(),
                             hovertemplate='Batalha: %{x:.2f} hm³<br>Serra: %{y:.2f} hm³<br>Custo: R$ %{customdata:,.2f}<extra></extra>'))
    base(fig,'FCF — mapa de calor','VI Serra (hm³)');fig.update_xaxes(type='linear',title='VI Batalha (hm³)')
    superficie=go.Figure(go.Surface(x=matriz.columns,y=matriz.index,z=matriz.to_numpy()/div,
                                    colorscale='Viridis',colorbar=barra,customdata=matriz.to_numpy(),
                                    hovertemplate='Batalha: %{x:.2f} hm³<br>Serra: %{y:.2f} hm³<br>R$ %{customdata:,.2f}<extra></extra>'))
    superficie.update_layout(title='FCF — superfície 3D',height=600,separators=',.',
                              scene=dict(xaxis_title='VI Batalha (hm³)',yaxis_title='VI Serra (hm³)',zaxis_title=un))
    return fig,superficie


def arvore(nos,sistema,meses,i):
    folhas=[j for j,r in enumerate(nos) if r['estagio']==len(meses)-1]
    yy={j:len(folhas)-1-k for k,j in enumerate(folhas)}
    for t in range(len(meses)-2,-1,-1):
        for j,r in enumerate(nos):
            filhos=[k for k,v in enumerate(nos) if v['pai']==j]
            if r['estagio']==t:yy[j]=float(np.mean([yy[k] for k in filhos]))
    fig=go.Figure();cor=CORES[sistema['UHE'][i]['Nome']]
    for j,r in enumerate(nos):
        if r['pai'] is not None:
            pai=r['pai']
            fig.add_scatter(x=[nos[pai]['estagio'],r['estagio']],y=[yy[pai],yy[j]],mode='lines',
                            line=dict(color=cor,width=1.5),showlegend=False,hoverinfo='skip',opacity=.45)
        u=r['UHE'][i]
        fig.add_annotation(x=r['estagio'],y=yy[j],text=f"{r['nome']} · p = {r['p']:.2f}<br>AFL = {u['afl']:.2f}<br>VF = {u['vf']:.2f}",
                           showarrow=False,bgcolor='#F5EDE6',bordercolor=cor,borderwidth=1.5,borderpad=7,font=dict(size=12,color='#343A40'))
    fig.update_layout(title='Histórico e volume final — '+sistema['UHE'][i]['Nome'],height=max(480,len(folhas)*95),
                      showlegend=False,paper_bgcolor='white',plot_bgcolor='white',margin=dict(l=100,r=100,t=70,b=65),
                      xaxis=dict(tickvals=list(range(len(meses))),ticktext=meses,range=[-.3,len(meses)-.7],showgrid=False,zeroline=False,
                                 title='AFL local em hm³/mês | VF em hm³ | p acumulada'),
                      yaxis=dict(visible=False,range=[-.6,len(folhas)-.4]))
    return fig
