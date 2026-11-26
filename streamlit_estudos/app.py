"""Aplicativo independente dos estudos padronizados de planejamento hidrotérmico."""
from copy import deepcopy
import hashlib
import json
import streamlit as st
import pandas as pd
from dados import perfil,ler_pysddp,construir_sistema,assinatura_deck,DECK_PADRAO,MESES
from modelos_estudo import calcular
from upload_deck import ler_zip_newave
import graficos as g

SECOES={
    'PDE Didática · 1 UHE':('pde1','PDE',1),
    'PDE Didática · 2 UHEs':('pde2','PDE',2),
    'PL Único · 2 UHEs':('pl','PL',2),
    'PL Único em árvore · 2 UHEs':('arvore','Árvore',2),
    'PDDD · 2 UHEs':('pddd','PDDD',2),
    'PySDDP · histórico NEWAVE':('pysddp','PDDD',2),
}


@st.cache_data(show_spinner=False)
def carregar_deck(pasta,ano,mes,horizonte,assinatura):
    return ler_pysddp(pasta,ano,mes,horizonte)


@st.cache_data(show_spinner=False,max_entries=32)
def executar(metodo,sistema,niveis,cenario,probabilidades,max_iteracoes,tolerancia):
    return calcular(metodo,sistema,niveis,cenario,probabilidades,max_iteracoes,tolerancia)


def restaurar(prefixo):
    st.session_state.setdefault('_menus',{}).pop(prefixo,None)
    for k in list(st.session_state):
        if k.startswith(prefixo):del st.session_state[k]


def guardar_menu():
    prefixo=st.session_state.get('_prefixo_ativo')
    if prefixo:
        valores={k:v for k,v in st.session_state.items()
                 if k.startswith(prefixo) and isinstance(v,(str,int,float,bool))
                 and not k.endswith(('_simular','reset'))}
        st.session_state.setdefault('_menus',{}).setdefault(prefixo,{}).update(valores)


def atualizar_upload(pk):
    if st.session_state.get(pk+'zip') is None:
        st.session_state.pop(pk+'arquivo_retido',None)
        st.session_state.pop(pk+'deck_enviado',None)


def numero(*args,**kwargs):
    chave=kwargs.get('key')
    salvo=st.session_state.get('_menus',{}).get(st.session_state.get('_prefixo_ativo'),{})
    if chave not in st.session_state and chave in salvo:kwargs['value']=salvo[chave]
    return st.number_input(*args,**kwargs)


def seletor(*args,**kwargs):
    chave=kwargs.get('key')
    salvo=st.session_state.get('_menus',{}).get(st.session_state.get('_prefixo_ativo'),{})
    if chave not in st.session_state and chave in salvo:
        opcoes=list(args[1])
        if salvo[chave] in opcoes:kwargs['index']=opcoes.index(salvo[chave])
    return st.selectbox(*args,**kwargs)


def texto(*args,**kwargs):
    chave=kwargs.get('key')
    salvo=st.session_state.get('_menus',{}).get(st.session_state.get('_prefixo_ativo'),{})
    if chave not in st.session_state and chave in salvo:kwargs['value']=salvo[chave]
    return st.text_input(*args,**kwargs)


def metrica_monetaria(painel,titulo,valor):
    divisor,unidade=g.escala([valor])
    painel.metric(titulo+' ('+unidade+')',g.moeda(valor/divisor),help='Valor completo: R$ '+g.moeda(valor))


def tabela(df,titulo,chave):
    st.subheader(titulo)
    # Apenas a apresentação arredonda e elimina resíduos próximos de zero.
    visual=df.copy()
    for c in visual.select_dtypes(include='number'):
        visual[c]=visual[c].mask(visual[c].abs()<.0000001,0)
    st.dataframe(visual.style.format(precision=3,thousands='.',decimal=','),width='stretch',hide_index=True)
    st.download_button('Baixar CSV · '+titulo,df.to_csv(index=False).encode('utf-8-sig'),
                       file_name=chave+'.csv',mime='text/csv',key=chave)


def parametros(titulo,slug,metodo,nh):
    prefixo=slug+'_'
    with st.sidebar:
        st.header('Parâmetros · '+titulo.split(' · ')[0])
        st.button('Restaurar este estudo',on_click=restaurar,args=(prefixo,),key=prefixo+'reset')
        if slug=='pysddp':
            fonte='PySDDP / NEWAVE'
        else:
            fonte=seletor('Dados de entrada',['Estudo padronizado','Comparação com amigo'],key=prefixo+'fonte',on_change=guardar_menu)
        pk=prefixo+('historico_' if slug=='pysddp' else ('amigo_' if fonte=='Comparação com amigo' else 'estudo_'))
        historico=slug=='pysddp';amigo=fonte=='Comparação com amigo'
        if historico:
            origem=seletor('Origem do deck',['Enviar ZIP','Pasta neste computador'],key=pk+'origem')
            if origem=='Enviar ZIP':
                arquivo=st.file_uploader('Deck NEWAVE (.zip)',type=['zip'],key=pk+'zip',on_change=atualizar_upload,args=(pk,),
                                         help='Compacte a pasta completa do caso, com os arquivos indicados em ARQUIVOS.DAT. Limite: 50 MB.')
            else:
                pasta=texto('Pasta do deck NEWAVE',value=DECK_PADRAO,key=pk+'pasta')
                st.caption('Disponível somente quando a pasta existe no computador que executa o aplicativo.')
        ano=numero('Ano inicial',1900,2100,value=2015 if historico else 2026,key=pk+'ano')
        mes=seletor('Mês inicial',range(1,13),index=8 if historico or amigo else 9,
                         format_func=lambda m:MESES[m-1],key=pk+'mes')
        max_meses=6 if metodo=='Árvore' else 36
        if amigo:max_meses=3
        meses=numero('Horizonte (meses)',1,max_meses,value=min(24 if historico else 3,max_meses),key=pk+'meses')
    try:
        if historico:
            if origem=='Enviar ZIP':
                if arquivo is not None:
                    st.session_state[pk+'arquivo_retido']=(arquivo.name,arquivo.getvalue())
                retido=st.session_state.get(pk+'arquivo_retido')
                if retido is None:
                    st.info('Na seção PySDDP, envie o ZIP da pasta completa do caso pelo menu lateral.');return None
                nome_arquivo,conteudo=retido
                chave=(hashlib.sha256(conteudo).hexdigest(),int(ano),mes,int(meses))
                cache=st.session_state.get(pk+'deck_enviado')
                if cache is None or cache[0]!=chave:
                    with st.spinner('Lendo o ZIP pelo PySDDP…'):
                        cache=(chave,ler_zip_newave(conteudo,int(ano),mes,int(meses)))
                    st.session_state[pk+'deck_enviado']=cache
                entrada=deepcopy(cache[1])
                st.caption('Deck enviado: '+nome_arquivo+'. A extração usa arquivos temporários, removidos após a leitura.')
            else:
                with st.spinner('Lendo o deck pelo PySDDP…'):
                    entrada=carregar_deck(pasta,int(ano),mes,int(meses),assinatura_deck(pasta))
        else:entrada=perfil(fonte,mes,int(meses),int(ano))
    except Exception as exc:
        st.error('Não foi possível preparar os dados: '+str(exc));return None
    with st.sidebar:
        carga=numero('Carga mensal (MW médios)',0.,1000.,value=100. if historico else (50. if nh==1 else 150. if metodo=='PDE' else 250.),step=1.,key=pk+'carga')
        cdef=numero('Custo de déficit (R$/MWh)',0.,100000.,value=entrada['cdef'],key=pk+'cdef')
        uhes=deepcopy(entrada['uhes'][:nh])
        for i,u in enumerate(uhes):
            with st.expander(u['Nome']):
                for campo,label in [('Vmin','Volume mínimo (hm³)'),('Vmax','Volume máximo (hm³)'),
                                     ('rho','Produtividade equivalente (MW/(m³/s))'),('qmax','Engolimento (m³/s)')]:
                    u[campo]=numero(label,min_value=0.,value=float(u[campo]),format='%.6f',key=pk+str(i)+campo)
                u['VI']=numero('Volume inicial total (hm³)',min_value=0.,value=float(u['Vmin'] if metodo=='PDE' else u['VI']),format='%.6f',key=pk+str(i)+'vi')
                percentual=100*(u['VI']-u['Vmin'])/(u['Vmax']-u['Vmin']) if u['Vmax']>u['Vmin'] else 0
                st.caption('Armazenamento útil inicial: '+g.moeda(percentual)+'%')
        utes=[]
        for i,(nome,cap,cvu) in enumerate([('ERB Candeias',17.,118.93),('BBF Baliza',10.,882.76)]):
            with st.expander(nome):
                cap=numero('Potência máxima (MW)',0.,10000.,value=cap,key=pk+'cap'+str(i))
                cvu=numero('CVU (R$/MWh)',0.,100000.,value=cvu,key=pk+'cvu'+str(i))
                utes.append(dict(Nome=nome,Capac=cap,CVU=cvu))
        niveis=numero('Níveis por reservatório',2,30,value=10 if nh==1 else 5,key=pk+'niveis') if metodo=='PDE' else 5
        cenario=0 if historico else seletor('Cenário inicial' if metodo=='Árvore' else 'Trajetória', [0,1],index=1,
                                                format_func=lambda c:['Otimista','Pessimista'][c],key=pk+'cenario') if metodo in ['PDDD','Árvore'] else 1
        probabilidades=[.5,.5]
        if metodo=='Árvore':
            prob=numero('Probabilidade otimista por abertura (%)',1.,99.,value=50.,key=pk+'prob')/100
            probabilidades=[prob,1-prob]
            st.caption(f'{2**int(meses)-1} nós. Cada ramo representa um cenário conjunto das duas UHEs.')
        max_iter=numero('Máximo de iterações',1,1000,value=100 if historico else 200,key=pk+'iter') if metodo=='PDDD' else 200
        tol=numero('Tolerância de convergência (R$)',min_value=.00001,value=.01,format='%.5f',key=pk+'tol') if metodo=='PDDD' else .01
    return dict(entrada=entrada,uhes=uhes,utes=utes,carga=carga,cdef=cdef,niveis=int(niveis),
                cenario=cenario,probabilidades=probabilidades,max_iteracoes=int(max_iter),tolerancia=tol,pk=pk)


def entradas(cfg,nh):
    entrada=deepcopy(cfg['entrada']);pk=cfg['pk']
    with st.expander('Dados de entrada e afluências',expanded=False):
        if entrada['historico']:
            st.caption(entrada['referencia']+'. O cadastro atual é aplicado à trajetória histórica; não é uma reconstrução operativa do período.')
            st.dataframe(entrada['auditoria'],hide_index=True,width='stretch')
            st.dataframe(entrada['vazoes'],hide_index=True,width='stretch')
            st.caption('VAZOES contém naturais totais. A incremental de Serra é calculada antes de somar a liberação de Batalha no balanço.')
            st.caption('Carga, UTEs, déficit e percentuais iniciais são premissas editáveis do estudo. Meses de 720 horas; sem pós-horizonte.')
            natureza='Local'
        else:
            natureza=seletor('Definição das afluências informadas',['Local','Natural total'],key=pk+'natureza')
            st.caption('Local é a contribuição própria. Natural total inclui a bacia a montante: nesse caso, o sistema calcula a diferença para Serra.')
            linhas={'Mês':entrada['meses']}
            for i,u in enumerate(cfg['uhes']):
                for c,nome in enumerate(['Otimista','Pessimista']):linhas[u['Nome']+' · '+nome]=[v[c] for v in entrada['afluencias'][i]]
            inicial=pd.DataFrame(linhas)
            salvo=st.session_state.get(pk+'afluencias_salvas')
            if salvo is not None and salvo['Mês'].tolist()==entrada['meses'] and list(salvo.columns)==list(inicial.columns):inicial=salvo
            df=st.data_editor(inicial,disabled=['Mês'],hide_index=True,width='stretch',key=pk+'afluencias')
            st.session_state[pk+'afluencias_salvas']=df.copy()
            for i,u in enumerate(cfg['uhes']):
                entrada['afluencias'][i]=df[[u['Nome']+' · '+c for c in ['Otimista','Pessimista']]].values.tolist()
            if len(entrada['meses'])>12:st.caption('Hipótese didática: o perfil mensal se repete nos anos seguintes, com edição independente na tabela.')
    sistema=construir_sistema(entrada,cfg['carga'],cfg['uhes'],cfg['utes'],cfg['cdef'],natureza=natureza)
    sistema['Meses']=entrada['meses']
    return sistema


def mostrar_resultados(resultado,sistema,metodo,slug):
    df=resultado['tabela'];meses=sistema['Meses']
    if metodo=='Árvore':
        metrica_monetaria(st,'Custo total esperado',resultado['custo'])
        arv,operacao,tabelas,modelo=st.tabs(['Árvore','Operação','Tabelas','Modelo'])
        with arv:
            st.info('Uma árvore do sistema, com uma figura por UHE. A água não se divide na bifurcação: os ramos são futuros alternativos.')
            for i in range(len(sistema['UHE'])):st.plotly_chart(g.arvore(resultado['nos'],sistema,meses,i),width='stretch')
        with operacao:
            st.plotly_chart(g.geracao(resultado['resumo'],sistema,'Atendimento à carga — valor esperado por mês'),width='stretch')
            tabela(resultado['resumo'],'Resumo mensal esperado',slug+'_resumo')
            st.plotly_chart(g.geracao(df,sistema,'Atendimento à carga por nó'),width='stretch')
            st.plotly_chart(g.custo(resultado['resumo']),width='stretch')
        with tabelas:tabela(df,'Resultados por nó',slug+'_nos')
        with modelo:st.markdown('Um único PL minimiza a soma de **probabilidade acumulada × custo imediato** dos nós. O VI de cada nó é o VF do pai. As decisões compartilhadas pelo mesmo histórico garantem a não antecipação. O primeiro mês é conhecido e não se ramifica. Não há custo terminal após o último mês.')
        return
    if metodo=='PDDD':
        col=st.columns(4)
        metrica_monetaria(col[0],'PDDD',resultado['custo'])
        metrica_monetaria(col[1],'PL Único',resultado['referencia'])
        diferenca=resultado['custo']-resultado['referencia']
        col[2].metric('Diferença (R$)',g.moeda(0. if abs(diferenca)<.0005 else diferenca))
        col[3].metric('Passagens forward',len(resultado['historico']))
        st.plotly_chart(g.convergencia(resultado['historico'],resultado['referencia']),width='stretch')
        st.success('Convergência alcançada e custo conferido com o PL Único dos mesmos dados.')
    else:
        for nome,grupo in df.groupby('Cenário',sort=False):metrica_monetaria(st,'Custo total · '+nome,grupo['Custo imediato (R$)'].sum())
    nomes=['Operação','Tabelas','Modelo']
    if metodo=='PDE':nomes.insert(1,'Função de custo futuro')
    abas=st.tabs(nomes)
    with abas[0]:
        for nome,grupo in df.groupby('Cenário',sort=False):
            st.plotly_chart(g.geracao(grupo,sistema,'Atendimento à carga — '+nome),width='stretch')
            st.plotly_chart(g.movimentacao(grupo,sistema),width='stretch')
        st.plotly_chart(g.volumes(df,sistema),width='stretch')
        st.plotly_chart(g.custo(df),width='stretch')
    if metodo=='PDE':
        with abas[1]:
            t=seletor('Estágio',range(len(meses)),format_func=lambda t:meses[t],key=slug+'_fcf')
            fig,sup=g.fcf(resultado['pontos'][t],sistema,resultado['cortes'][t])
            st.plotly_chart(fig,width='stretch')
            if sup is not None:st.plotly_chart(sup,width='stretch')
            tabela(resultado['pontos'][t],'Custos amostrados',slug+'_pontos')
    with abas[-2]:
        tabela(df,'Resultados mensais',slug+'_mensais')
        if metodo=='PDDD':
            tabela(resultado['historico'],'Histórico de convergência',slug+'_convergencia')
            linhas=[]
            for t,lista in enumerate(resultado['cortes'][:-1]):
                for corte in lista:
                    linha={'Estágio':meses[t],'Iteração':corte['iteracao'],'b (R$)':corte['b']}
                    linha.update({u['Nome']+' (R$/hm³)':corte['a'][i] for i,u in enumerate(sistema['UHE'])});linhas.append(linha)
            if linhas:tabela(pd.DataFrame(linhas),'Cortes de suporte',slug+'_cortes')
    with abas[-1]:
        st.markdown('**Balanço hídrico:** VF = VI + afluência local + liberações de montante − VT − VV. '
                    '**Carga:** soma das gerações hidráulicas, térmicas e déficit. '
                    '**Limites:** armazenamento, engolimento, capacidade térmica e não negatividade. '
                    'As produtividades são equivalentes constantes. Volumes em hm³; geração em MW médios; custos calculados em R$.')
        if metodo=='PDE':st.markdown('A PDE percorre os estágios de trás para frente em uma grade de volumes, com cenários conjuntos equiprováveis. Os duais geram planos de suporte ao custo esperado. O último estágio tem custo futuro zero.')
        elif metodo=='PDDD':st.markdown('O forward calcula uma trajetória viável; ZSUP soma seus custos imediatos. ZINF vem do objetivo do primeiro mês. O backward constrói cortes nos estados visitados. Os volumes são contínuos e a PDDD é comparada ao PL Único. Não há pós-horizonte.')
        else:st.markdown('O PL Único resolve todos os meses simultaneamente para cada trajetória conhecida. Não há uma FCF separada nem custo após o horizonte.')


def main():
    st.set_page_config(page_title='Planejamento hidrotérmico · Estudos',page_icon='💧',layout='wide')
    st.sidebar.title('Planejamento hidrotérmico')
    titulo=st.sidebar.radio('Laboratório',list(SECOES),key='laboratorio',on_change=guardar_menu)
    slug,metodo,nh=SECOES[titulo]
    prefixo=slug+'_'
    st.session_state['_prefixo_ativo']=prefixo
    st.title(titulo)
    st.caption('Estudos da disciplina · modelos lineares, entradas auditáveis e menus independentes')
    cfg=parametros(titulo,slug,metodo,nh)
    if cfg is None:return
    try:sistema=entradas(cfg,nh)
    except (ValueError,TypeError) as exc:st.error(str(exc));return
    assinatura=hashlib.sha256(json.dumps([sistema,cfg['niveis'],cfg['cenario'],cfg['probabilidades'],cfg['max_iteracoes'],cfg['tolerancia']],sort_keys=True).encode()).hexdigest()
    estado=slug+'_resultado'
    if st.button('Simular',type='primary',key=slug+'_simular'):
        try:
            if metodo=='PDE' and cfg['niveis']**nh*len(sistema['Meses'])*sistema['DGer']['Nr_Cen']>20000:
                st.error('Reduza os níveis ou o horizonte para manter este estudo interativo.');return
            with st.spinner('Resolvendo e conferindo os balanços…'):
                r=executar(metodo,sistema,cfg['niveis'],cfg['cenario'],cfg['probabilidades'],cfg['max_iteracoes'],cfg['tolerancia'])
            st.session_state[estado]=(assinatura,sistema,r)
        except Exception as exc:st.error('A simulação não foi concluída: '+str(exc));return
    if estado not in st.session_state:
        st.info('Confira os parâmetros no menu deste laboratório e clique em Simular.');return
    ass,usado,r=st.session_state[estado]
    if ass!=assinatura:st.warning('Os parâmetros foram alterados. Clique em Simular para atualizar os resultados. Abaixo está a última execução.')
    mostrar_resultados(r,usado,metodo,slug)


if __name__=='__main__':main()
