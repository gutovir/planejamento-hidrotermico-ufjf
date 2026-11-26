"""Modelos lineares dos notebooks padronizados. Valores hidráulicos em hm³."""
from copy import deepcopy
from itertools import product
import math
import numpy as np
import pandas as pd
from cvxopt.modeling import variable, op
from cvxopt import solvers

solvers.options['glpk'] = {'msg_lev': 'GLP_MSG_OFF', 'tol_bnd': 1e-9, 'tol_dj': 1e-10}
ESCALA_SOLVER = 1_000_000.0


def tabela_trajetoria(sistema, trajetoria, meses, cenario=0, nome='Trajetória'):
    linhas=[]
    for t,r in enumerate(trajetoria):
        linha={'Mês':meses[t],'Cenário':nome,'Carga (MW)':sistema['DGer']['Carga'][t]}
        for i,u in enumerate(sistema['UHE']):
            for campo,valor in [('VI',r['vi'][i]),('AFL local',u['Afl'][t][cenario]),
                                ('VT',r['vt'][i]),('VV',r['vv'][i]),('VF',r['vf'][i])]:
                linha[f'{campo} {u["Nome"]} (hm³)']=float(valor)
            linha[f'Geração {u["Nome"]} (MW)']=u['Prod']*r['vt'][i]
            if 'gradiente' in r:
                linha[f'CMA {u["Nome"]} (R$/hm³)']=-r['gradiente'][i]
        for i,u in enumerate(sistema['UTE']):linha[u['Nome']+' (MW)']=r['gt'][i]
        linha.update({'Déficit (MW)':r['deficit'],'Custo imediato (R$)':r['ci']})
        if 'futuro' in r:linha['Custo futuro (R$)']=r['futuro']
        if 'cmo' in r:linha['CMO (R$/MWh)']=r['cmo']
        linhas.append(linha)
    return pd.DataFrame(linhas)


def trajetoria_pl(sistema, resultado):
    trajetoria=[]
    for t in range(sistema['DGer']['Nr_Est']):
        trajetoria.append(dict(
            vi=[u['VI'] if t==0 else resultado['UHE'][i]['vf'][t-1] for i,u in enumerate(sistema['UHE'])],
            vf=[u['vf'][t] for u in resultado['UHE']],
            vt=[u['vt'][t] for u in resultado['UHE']],
            vv=[u['vv'][t] for u in resultado['UHE']],
            gt=[u['gt'][t] for u in resultado['UTE']],
            gradiente=[-u['cma'][t] for u in resultado['UHE']],
            deficit=resultado['DGer']['Deficit'][t],ci=resultado['DGer']['CustoImediato'][t],
            cmo=resultado['DGer']['CMO'][t]))
    return trajetoria


def validar_trajetoria(sistema,trajetoria,cenario,atol=1e-5):
    for t,r in enumerate(trajetoria):
        for i,u in enumerate(sistema['UHE']):
            vi=u['VI'] if t==0 else trajetoria[t-1]['vf'][i]
            montante=sum(r['vt'][j]+r['vv'][j] for j in u['Montante'])
            saldo=vi+u['Afl'][t][cenario]+montante-r['vt'][i]-r['vv'][i]-r['vf'][i]
            if abs(saldo)>atol or not u['Vmin']-atol<=r['vf'][i]<=u['Vmax']+atol:
                raise RuntimeError('Balanço hídrico ou armazenamento inconsistente.')
            if not -atol<=r['vt'][i]<=u['Engol']+atol or r['vv'][i]<-atol:
                raise RuntimeError('Turbinamento ou vertimento inconsistente.')
        for i,u in enumerate(sistema['UTE']):
            if not -atol<=r['gt'][i]<=u['Capac']+atol:raise RuntimeError('Geração térmica fora dos limites.')
        geracao=sum(u['Prod']*r['vt'][i] for i,u in enumerate(sistema['UHE']))+sum(r['gt'])+r['deficit']
        custo=sum(u['Custo']*r['gt'][i] for i,u in enumerate(sistema['UTE']))
        custo+=sistema['DGer']['CDef']*r['deficit']+.01*sum(r['vv'])
        if abs(geracao-sistema['DGer']['Carga'][t])>atol or r['deficit']<-atol:
            raise RuntimeError('Atendimento à carga inconsistente.')
        if abs(custo-r['ci'])>.01:raise RuntimeError('Contabilidade inconsistente.')


def resolver_pde(sistema,niveis):
    T=sistema['DGer']['Nr_Est'];nh=len(sistema['UHE'])
    volumes=[np.linspace(u['Vmin'],u['Vmax'],niveis) for u in sistema['UHE']]
    cortes=[[] for _ in range(T+1)];pontos={}
    for t in range(T-1,-1,-1):
        linhas=[]
        for estado in product(*volumes):
            rs=[despacho_pde(sistema,t,estado,c,cortes[t+1]) for c in range(sistema['DGer']['Nr_Cen'])]
            valor=float(np.mean([r['total'] for r in rs]))
            a=np.mean([r['gradiente'] for r in rs],axis=0).tolist()
            cortes[t].append({'a':a,'b':float(valor-sum(a[i]*estado[i] for i in range(nh)))})
            linha={f'VI {u["Nome"]} (hm³)':estado[i] for i,u in enumerate(sistema['UHE'])}
            linha['Custo (R$)']=valor;linhas.append(linha)
        pontos[t]=pd.DataFrame(linhas)
    tabelas=[]
    for c in range(sistema['DGer']['Nr_Cen']):
        vi=[u['VI'] for u in sistema['UHE']];traj=[]
        for t in range(T):
            r=despacho_pde(sistema,t,vi,c,cortes[t+1]);traj.append(r);vi=r['vf']
        validar_trajetoria(sistema,traj,c)
        tabelas.append(tabela_trajetoria(sistema,traj,sistema['Meses'],c,['Otimista','Pessimista'][c]))
    return dict(tabela=pd.concat(tabelas,ignore_index=True),pontos=pontos,cortes=cortes)


def despacho_pde(sistema,t,vi,cenario,cortes):
    """PySCIPOpt, como nos notebooks de PDE; duais expressos em R$/hm³."""
    from pyscipopt import Model,quicksum,SCIP_PARAMSETTING
    m=Model('PDE didática')
    try:
        m.hideOutput();m.setPresolve(SCIP_PARAMSETTING.OFF)
        m.setHeuristics(SCIP_PARAMSETTING.OFF);m.disablePropagation()
        m.setBoolParam('lp/alwaysgetduals',True)
        m.setRealParam('numerics/feastol',1e-9);m.setRealParam('numerics/dualfeastol',1e-9)
        vf=[m.addVar(lb=u['Vmin'],ub=u['Vmax']) for u in sistema['UHE']]
        vt=[m.addVar(lb=0,ub=u['Engol']) for u in sistema['UHE']]
        vv=[m.addVar(lb=0) for u in sistema['UHE']]
        gt=[m.addVar(lb=0,ub=u['Capac']) for u in sistema['UTE']]
        deficit=m.addVar(lb=0);alpha=m.addVar(lb=0,ub=0 if t==sistema['DGer']['Nr_Est']-1 else None)
        bh=[]
        for i,u in enumerate(sistema['UHE']):
            montante=quicksum(vt[j]+vv[j] for j in u['Montante'])
            bh.append(m.addCons(vf[i]+vt[i]+vv[i]-montante==float(vi[i])+u['Afl'][t][cenario]))
        demanda=m.addCons(quicksum(u['Prod']*vt[i] for i,u in enumerate(sistema['UHE']))+quicksum(gt)+deficit==sistema['DGer']['Carga'][t])
        ci=quicksum(u['Custo']*gt[i] for i,u in enumerate(sistema['UTE']))+sistema['DGer']['CDef']*deficit+.01*quicksum(vv)
        for corte in cortes:
            m.addCons(alpha >= (float(corte['b'])+quicksum(float(a)*v for a,v in zip(corte['a'],vf)))/1000.0)
        m.setObjective(ci/1000.0+alpha,'minimize');m.optimize()
        if m.getStatus()!='optimal':raise RuntimeError('PDE sem solução ótima: '+str(m.getStatus()))
        return dict(vi=list(map(float,vi)),vf=[m.getVal(v) for v in vf],vt=[m.getVal(v) for v in vt],
                    vv=[m.getVal(v) for v in vv],gt=[m.getVal(v) for v in gt],deficit=m.getVal(deficit),
                    ci=m.getVal(ci),futuro=m.getVal(alpha)*1000.0,total=m.getObjVal()*1000.0,
                    gradiente=[m.getDualsolLinear(c)*1000.0 for c in bh],
                    cmo=m.getDualsolLinear(demanda)*1000.0/sistema['DGer'].get('Horas',720))
    finally:m.freeProb()


def calcular(metodo,sistema,niveis=5,cenario=1,probabilidades=(.5,.5),max_iteracoes=200,tolerancia=.01):
    if metodo=='PDE':return resolver_pde(sistema,niveis)
    if metodo=='Árvore':
        nos,custo=pl_unico_arvore(sistema,cenario,list(probabilidades))
        linhas=[]
        for r in nos:
            t=r['estagio'];pai=r['pai']
            vi=[u['VI'] if pai is None else nos[pai]['UHE'][i]['vf'] for i,u in enumerate(sistema['UHE'])]
            traj=dict(vi=vi,vf=[u['vf'] for u in r['UHE']],vt=[u['vt'] for u in r['UHE']],
                      vv=[u['vv'] for u in r['UHE']],gt=r['gt'],deficit=r['deficit'],ci=r['ci'])
            # Valida o nó como um estágio independente com seu VI herdado.
            local=deepcopy(sistema);local['DGer']['Nr_Est']=1;local['DGer']['Carga']=[sistema['DGer']['Carga'][t]]
            for i,u in enumerate(local['UHE']):u['VI']=vi[i];u['Afl']=[u['Afl'][t]]
            validar_trajetoria(local,[traj],r['cenario'])
            linha=tabela_trajetoria(local,[traj],[sistema['Meses'][t]],r['cenario'],['Otimista','Pessimista'][r['cenario']]).iloc[0].to_dict()
            linha.update({'Nó':r['nome'],'Probabilidade':r['p'],'p × custo (R$)':r['p']*r['ci']})
            linhas.append(linha)
        tabela=pd.DataFrame(linhas)
        resumo=[]
        for mes,df in tabela.groupby('Mês',sort=False):
            linha={'Mês':mes}
            for col in tabela.select_dtypes(include='number').columns:
                if col not in ['Probabilidade','p × custo (R$)']:linha[col]=float((df[col]*df['Probabilidade']).sum())
            resumo.append(linha)
        if abs(tabela['p × custo (R$)'].sum()-custo)>.01:raise RuntimeError('Custo esperado inconsistente.')
        return dict(tabela=tabela,resumo=pd.DataFrame(resumo),nos=nos,custo=custo)
    if metodo=='PDDD':
        traj,cortes,historico=resolver_pddd(sistema,cenario,max_iteracoes,tolerancia)
        validar_trajetoria(sistema,traj,cenario)
        ref=pl_unico(sistema,cenario,False)['DGer']['CustoTotal']
        custo=sum(r['ci'] for r in traj)
        if abs(custo-ref)>max(tolerancia,.001):raise RuntimeError('PDDD e PL Único não coincidem na tolerância definida.')
        return dict(tabela=tabela_trajetoria(sistema,traj,sistema['Meses'],cenario,'Histórica' if sistema['DGer']['Nr_Cen']==1 else ['Otimista','Pessimista'][cenario]),
                    historico=pd.DataFrame(historico),cortes=cortes,custo=custo,referencia=ref)
    tabelas=[]
    for c in range(sistema['DGer']['Nr_Cen']):
        r=pl_unico(sistema,c,False);traj=trajetoria_pl(sistema,r)
        validar_trajetoria(sistema,traj,c)
        tabelas.append(tabela_trajetoria(sistema,traj,sistema['Meses'],c,'Histórica' if sistema['DGer']['Nr_Cen']==1 else ['Otimista','Pessimista'][c]))
    return dict(tabela=pd.concat(tabelas,ignore_index=True))

def despacho_pddd(sistema, estagio, vi, cenario, cortes_futuros):
    nh = len(sistema['UHE'])
    nt = len(sistema['UTE'])
    vf = variable(nh, 'Volume final')
    vt = variable(nh, 'Volume turbinado')
    vv = variable(nh, 'Volume vertido')
    gt = variable(nt, 'Geração térmica')
    deficit = variable(1, 'Déficit')
    alpha = variable(1, 'Custo futuro')
    restricoes = []
    balancos = []
    for i, u in enumerate(sistema['UHE']):
        recebimento = 0
        for j in u['Montante']:
            recebimento += vt[j] + vv[j]
        bh = vf[i] == float(vi[i]) + float(u['Afl'][estagio][cenario]) + recebimento - vt[i] - vv[i]
        balancos.append(bh)
        restricoes.append(bh)
        restricoes += [vf[i] >= u['Vmin'], vf[i] <= u['Vmax'], vt[i] >= 0, vt[i] <= u['Engol'], vv[i] >= 0]
    atendimento = 0
    ci = sistema['DGer']['CDef'] * deficit[0]
    for i, u in enumerate(sistema['UHE']):
        atendimento += u['Prod'] * vt[i]
        ci += 0.01 * vv[i]
    for i, u in enumerate(sistema['UTE']):
        atendimento += gt[i]
        ci += u['Custo'] * gt[i]
        restricoes += [gt[i] >= 0, gt[i] <= u['Capac']]
    demanda = atendimento + deficit[0] == sistema['DGer']['Carga'][estagio]
    restricoes += [demanda, deficit[0] >= 0, alpha[0] >= 0]
    for corte in cortes_futuros:
        plano = corte['b']
        for i in range(nh):
            plano += corte['a'][i] * vf[i]
        restricoes.append(alpha[0] >= plano * (1 / ESCALA_SOLVER))
    if estagio == sistema['DGer']['Nr_Est'] - 1:
        restricoes.append(alpha[0] == 0)
    fob = ci * (1 / ESCALA_SOLVER) + alpha[0]
    problema = op(fob, restricoes)
    problema.solve('dense', 'glpk')
    if problema.status != 'optimal':
        raise RuntimeError('Despacho sem solução ótima: ' + problema.status)
    gradiente = [-bh.multiplier.value[0] * ESCALA_SOLVER for bh in balancos]
    return {'vi': list(vi), 'vf': list(vf.value), 'vt': list(vt.value), 'vv': list(vv.value), 'gt': list(gt.value), 'deficit': deficit.value[0], 'ci': ci.value()[0], 'futuro': alpha.value[0] * ESCALA_SOLVER, 'total': fob.value()[0] * ESCALA_SOLVER, 'gradiente': gradiente, 'cmo': -demanda.multiplier.value[0] * ESCALA_SOLVER / sistema['DGer'].get('Horas', 720)}

def resolver_pddd(sistema, cenario, max_iteracoes, tolerancia):
    T = sistema['DGer']['Nr_Est']
    cortes = [[] for t in range(T + 1)]
    historico = []
    if cenario not in range(sistema['DGer']['Nr_Cen']):
        raise ValueError('Cenário inválido.')
    if max_iteracoes < 1 or tolerancia <= 0:
        raise ValueError('Iterações e tolerância devem ser positivas.')
    for iteracao in range(1, max_iteracoes + 1):
        vi = [u['VI'] for u in sistema['UHE']]
        trajetoria = []
        for t in range(T):
            r = despacho_pddd(sistema, t, vi, cenario, cortes[t + 1])
            trajetoria.append(r)
            vi = r['vf']
        zinf = trajetoria[0]['total']
        zsup = sum((r['ci'] for r in trajetoria))
        historico.append({'iteracao': iteracao, 'zinf': zinf, 'zsup': zsup, 'gap': zsup - zinf})
        if zinf > zsup + tolerancia:
            raise RuntimeError('ZINF maior que ZSUP; verificar os cortes.')
        if abs(zsup - zinf) <= tolerancia:
            return (trajetoria, cortes, historico)
        for t in range(T - 1, 0, -1):
            estado = trajetoria[t]['vi']
            r = despacho_pddd(sistema, t, estado, cenario, cortes[t + 1])
            a = r['gradiente']
            b = r['total'] - sum((a[i] * estado[i] for i in range(len(estado))))
            cortes[t].append({'a': a, 'b': b, 'iteracao': iteracao})
    raise RuntimeError('A PDDD não convergiu. Verifique a tolerância ou aumente max_iteracoes.')

def pl_unico_arvore(sistema, cenario_inicial, probabilidades):
    meses = sistema['DGer']['Nr_Est']
    aberturas = sistema['DGer']['Nr_Cen']
    if len(probabilidades) != aberturas or any((p <= 0 for p in probabilidades)):
        raise ValueError('Informe uma probabilidade positiva por abertura.')
    if abs(sum(probabilidades) - 1) > 1e-10:
        raise ValueError('As probabilidades devem somar 1.')
    if cenario_inicial not in range(aberturas):
        raise ValueError('Cenário inicial inválido.')
    nos = [{'nome': 'R', 'estagio': 0, 'pai': None, 'cenario': cenario_inicial, 'p': 1.0}]
    for t in range(1, meses):
        pais = [j for j, no in enumerate(nos) if no['estagio'] == t - 1]
        for pai in pais:
            for c in range(aberturas):
                nos.append({'nome': nos[pai]['nome'] + str(c + 1), 'estagio': t, 'pai': pai, 'cenario': c, 'p': nos[pai]['p'] * probabilidades[c]})
    N = len(nos)
    vf = [variable(N, 'VF ' + u['Nome']) for u in sistema['UHE']]
    vt = [variable(N, 'VT ' + u['Nome']) for u in sistema['UHE']]
    vv = [variable(N, 'VV ' + u['Nome']) for u in sistema['UHE']]
    gt = [variable(N, 'GT ' + u['Nome']) for u in sistema['UTE']]
    deficit = variable(N, 'Déficit')
    restricoes = []
    custos = []
    fob = 0
    for j, no in enumerate(nos):
        t, c, pai = (no['estagio'], no['cenario'], no['pai'])
        for i, u in enumerate(sistema['UHE']):
            vi = float(u['VI']) if pai is None else vf[i][pai]
            montante = 0
            for m in u['Montante']:
                montante += vt[m][j] + vv[m][j]
            restricoes.append(vf[i][j] == vi + float(u['Afl'][t][c]) + montante - vt[i][j] - vv[i][j])
            restricoes += [vf[i][j] >= u['Vmin'], vf[i][j] <= u['Vmax'], vt[i][j] >= 0, vt[i][j] <= u['Engol'], vv[i][j] >= 0]
        atendimento = 0
        custo = sistema['DGer']['CDef'] * deficit[j]
        for i, u in enumerate(sistema['UHE']):
            atendimento += u['Prod'] * vt[i][j]
            custo += 0.01 * vv[i][j]
        for i, u in enumerate(sistema['UTE']):
            atendimento += gt[i][j]
            custo += u['Custo'] * gt[i][j]
            restricoes += [gt[i][j] >= 0, gt[i][j] <= u['Capac']]
        restricoes += [atendimento + deficit[j] == sistema['DGer']['Carga'][t], deficit[j] >= 0]
        custos.append(custo)
        fob += no['p'] * custo
    problema = op(fob, restricoes)
    problema.solve('dense', 'glpk')
    if problema.status != 'optimal':
        raise RuntimeError('O PL não encontrou solução ótima: ' + problema.status)
    resultados = []
    for j, no in enumerate(nos):
        r = dict(no)
        r['UHE'] = []
        for i, u in enumerate(sistema['UHE']):
            vi = u['VI'] if no['pai'] is None else vf[i][no['pai']].value()[0]
            r['UHE'].append({'vi': vi, 'afl': u['Afl'][no['estagio']][no['cenario']], 'vf': vf[i][j].value()[0], 'vt': vt[i][j].value()[0], 'vv': vv[i][j].value()[0], 'geracao': u['Prod'] * vt[i][j].value()[0]})
        r['gt'] = [g[j].value()[0] for g in gt]
        r['deficit'] = deficit[j].value()[0]
        r['ci'] = custos[j].value()[0]
        resultados.append(r)
    return (resultados, fob.value()[0])

def pl_unico(sistema, cenario, imprime):
    Num_UHE = len(sistema['UHE'])
    Num_UTE = len(sistema['UTE'])
    vf = []
    vt = []
    vv = []
    for i, iusi in enumerate(sistema['UHE']):
        vf.append(variable(sistema['DGer']['Nr_Est'], 'Volume Final na Usina ' + iusi['Nome']))
        vt.append(variable(sistema['DGer']['Nr_Est'], 'Volume Turbinado na Usina ' + iusi['Nome']))
        vv.append(variable(sistema['DGer']['Nr_Est'], 'Volume Vertido na Usina ' + iusi['Nome']))
    gt = []
    for i, iusi in enumerate(sistema['UTE']):
        gt.append(variable(sistema['DGer']['Nr_Est'], 'Geração na Usina Térmica ' + iusi['Nome']))
    deficit = variable(sistema['DGer']['Nr_Est'], 'Déficit de Energia no Sistema')
    fob = 0
    for i_est in range(sistema['DGer']['Nr_Est']):
        for i, iusi in enumerate(sistema['UTE']):
            fob += iusi['Custo'] * gt[i][i_est]
        fob += sistema['DGer']['CDef'] * deficit[i_est]
        for i, iusi in enumerate(sistema['UHE']):
            fob += 0.01 * vv[i][i_est]
    restricoes = []
    for i, iusi in enumerate(sistema['UHE']):
        for i_est in range(sistema['DGer']['Nr_Est']):
            recebimento = 0
            for montante in iusi['Montante']:
                recebimento += vt[montante][i_est] + vv[montante][i_est]
            if i_est == 0:
                restricoes.append(vf[i][i_est] == float(iusi['VI']) + float(iusi['Afl'][i_est][cenario]) + recebimento - vt[i][i_est] - vv[i][i_est])
            else:
                restricoes.append(vf[i][i_est] == vf[i][i_est - 1] + float(iusi['Afl'][i_est][cenario]) + recebimento - vt[i][i_est] - vv[i][i_est])
    for i_est in range(sistema['DGer']['Nr_Est']):
        AD = 0
        for i, iusi in enumerate(sistema['UHE']):
            AD += iusi['Prod'] * vt[i][i_est]
        for i, iusi in enumerate(sistema['UTE']):
            AD += gt[i][i_est]
        AD += deficit[i_est]
        restricoes.append(AD == sistema['DGer']['Carga'][i_est])
    for i_est in range(sistema['DGer']['Nr_Est']):
        for i, iusi in enumerate(sistema['UHE']):
            restricoes.append(vf[i][i_est] >= iusi['Vmin'])
            restricoes.append(vf[i][i_est] <= iusi['Vmax'])
            restricoes.append(vt[i][i_est] >= 0)
            restricoes.append(vt[i][i_est] <= iusi['Engol'])
            restricoes.append(vv[i][i_est] >= 0)
        for i, iusi in enumerate(sistema['UTE']):
            restricoes.append(gt[i][i_est] >= 0)
            restricoes.append(gt[i][i_est] <= iusi['Capac'])
        restricoes.append(deficit[i_est] >= 0)
    problema = op(fob, restricoes)
    problema.solve('dense', 'glpk')
    lista_uhe = []
    for i, iusi in enumerate(sistema['UHE']):
        pula = i * sistema['DGer']['Nr_Est']
        cma = []
        volf = []
        volt = []
        volv = []
        for iest in range(sistema['DGer']['Nr_Est']):
            cma.append(restricoes[pula + iest].multiplier.value[0])
            volf.append(vf[i][iest].value()[0])
            volt.append(vt[i][iest].value()[0])
            volv.append(vv[i][iest].value()[0])
        elemento = {'vf': volf, 'vt': volt, 'vv': volv, 'cma': cma}
        lista_uhe.append(elemento)
    lista_ute = []
    for i, iusi in enumerate(sistema['UTE']):
        gerter = []
        for iest in range(sistema['DGer']['Nr_Est']):
            gerter.append(gt[i][iest].value()[0])
        elemento = {'gt': gerter}
        lista_ute.append(elemento)
    pula = Num_UHE * sistema['DGer']['Nr_Est']
    cmo = []
    for i_est in range(sistema['DGer']['Nr_Est']):
        cmo.append(-restricoes[pula + i_est].multiplier.value[0] / sistema['DGer'].get('Horas', 720))
    dados_deficit = []
    for i_est in range(sistema['DGer']['Nr_Est']):
        dados_deficit.append(deficit[i_est].value()[0])
    custos_imediatos = []
    for i_est in range(sistema['DGer']['Nr_Est']):
        custo_mes = sistema['DGer']['CDef'] * dados_deficit[i_est]
        for i, usina in enumerate(sistema['UTE']):
            custo_mes += usina['Custo'] * lista_ute[i]['gt'][i_est]
        for usina in lista_uhe:
            custo_mes += 0.01 * usina['vv'][i_est]
        custos_imediatos.append(custo_mes)
    Dger = {'CustoTotal': fob.value()[0], 'CMO': cmo, 'Deficit': dados_deficit, 'CustoImediato': custos_imediatos}
    resultado = {'DGer': Dger, 'UHE': lista_uhe, 'UTE': lista_ute}
    if imprime:
        print('Custo de Operação de Todos os estágios:', fob.value())
        print('Volume Final por UHE em cada Estágio em (hm^3) ')
        for i, iusi in enumerate(sistema['UHE']):
            print(vf[i])
            print(vt[i])
            print(vv[i])
        print('Geração por UTE em cada Estágio em (MWmed)')
        for i, iusi in enumerate(sistema['UTE']):
            print(gt[i])
        print('Déficit de Energia em cada Estágio em (MWMed)')
        print(deficit)
        print('----- x ----- ')
    return resultado
