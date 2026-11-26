"""Entradas auditáveis: dados do estudo, comparação e histórico NEWAVE."""
from pathlib import Path
from contextlib import redirect_stdout
from io import StringIO
import numpy as np
import pandas as pd

RAIZ = Path(__file__).parent
DECK_PADRAO = r'C:\Users\Augusto\Downloads\Planejamento\Caso de Estudo\nw202610_original_20261126-0405'
MESES = ['Jan','Fev','Mar','Abr','Mai','Jun','Jul','Ago','Set','Out','Nov','Dez']


def rotulos(ano, mes, horizonte):
    return [f'{MESES[(mes-1+t)%12]}/{ano+(mes-1+t)//12}' for t in range(horizonte)]


def perfil(nome='Estudo padronizado', mes=10, horizonte=3, ano=2026):
    amigo = nome == 'Comparação com amigo'
    if amigo:
        if mes != 9 or horizonte > 3:
            raise ValueError('A comparação fornecida abrange setembro a novembro.')
        b = np.array([[30.,20.],[35.,25.],[40.,30.]])[:horizonte]
        s = np.array([[70.,24.],[93.,29.],[176.,20.]])[:horizonte]
    else:
        bdf = pd.read_csv(RAIZ/'dados_padronizados/batalha.csv')
        sdf = pd.read_csv(RAIZ/'dados_padronizados/serra.csv')
        indices = [(mes-1+t)%12 for t in range(horizonte)]
        b = bdf[['otimista_media_mais_1dp_m3_s','pessimista_media_menos_1dp_m3_s']].to_numpy()[indices]
        s = sdf[['media_mais_1dp_m3_s','media_menos_1dp_m3_s']].to_numpy()[indices]
    uhes = [
        dict(Nome='UHE Batalha', Vmin=430.049988 if amigo else 430.05,
             Vmax=1781.609985 if amigo else 1781.61, rho=.3294125 if amigo else .3323,
             qmax=147.02, percentual=39.7, Montante=[]),
        dict(Nome='UHE Serra do Facão', Vmin=1752., Vmax=5199., rho=.6157,
             qmax=313., percentual=50.2, Montante=[0]),
    ]
    uhes[0]['VI'] = (430.049988 + .397*(1781.609985-430.049988)) if amigo else 966.619306809
    uhes[1]['VI'] = 3482.394
    return dict(uhes=uhes, afluencias=[b.tolist(),s.tolist()], meses=rotulos(ano,mes,horizonte),
                cdef=4000. if amigo else 8291., origem=nome, historico=False)


def assinatura_deck(pasta):
    p = Path(pasta)
    if not p.is_dir():
        raise FileNotFoundError('Informe uma pasta de deck disponível neste computador.')
    return tuple(sorted((f.name,f.stat().st_size,f.stat().st_mtime_ns) for f in p.iterdir() if f.is_file()))


def ler_pysddp(pasta, ano=2015, mes=9, horizonte=24):
    from PySDDP.Pen import Newave
    with redirect_stdout(StringIO()):
        caso = Newave(str(pasta))
    codigos=[20,21]
    cadastro=[caso.confhd.get(c) for c in codigos]
    if cadastro[0]['jusante'] != 21:
        raise ValueError('O cadastro não confirma a cascata Batalha–Serra.')
    for cod in caso.confhd.lista_uhes():
        u=caso.confhd.get(cod)
        if u['jusante'] in codigos and cod not in codigos:
            raise ValueError('Há outra usina a montante. Revisar a redução do sistema.')
    base=int(caso.dger.anoi_hist['valor'])
    referencia=int(caso.dger.mesi_est['valor'])-1
    naturais=[]
    for u in cadastro:
        valores=[]
        for t in range(horizonte):
            a=ano+(mes-1+t)//12; m=(mes-1+t)%12
            if not int(u['ano_i']) <= a <= int(u['ano_f']):
                raise ValueError(f'{a}: fora do histórico validado no CONFHD.')
            q=float(u['vazoes'][a-base,m])
            if not np.isfinite(q) or q<0:
                raise ValueError('Vazão histórica ausente ou inválida.')
            valores.append(q)
        naturais.append(np.array(valores))
    locais=[naturais[0],naturais[1]-naturais[0]]
    if any(np.any(q<0) for q in locais):
        raise ValueError('Incremental negativa: conferir as séries; não houve truncamento.')
    uhes=[];auditoria=[]
    for i,u in enumerate(cadastro):
        rho=float(u['ro_equiv'][0,referencia]); qmax=float(u['engolimento'])
        nome=['UHE Batalha','UHE Serra do Facão'][i]
        uhes.append(dict(Nome=nome,Vmin=float(u['vol_min']),Vmax=float(u['vol_max']),
                         rho=rho,qmax=qmax,percentual=[39.7,50.2][i],Montante=[] if i==0 else [0],
                         VI=float(u['vol_min'])+[.397,.502][i]*(float(u['vol_max'])-float(u['vol_min']))))
        auditoria.append({'Usina':nome,'Código':u['codigo'],'Posto':u['posto'],
                          'Vmin (hm³)':u['vol_min'],'Vmax (hm³)':u['vol_max'],
                          'Produtividade equivalente':rho,'Engolimento (m³/s)':qmax,
                          'VI do CONFHD (% útil)':u['vol_ini']})
    meses=rotulos(ano,mes,horizonte)
    df=pd.DataFrame({'Mês':meses,'Natural Batalha (m³/s)':naturais[0],
                     'Natural Serra (m³/s)':naturais[1], 'Local Batalha (m³/s)':locais[0],
                     'Local Serra (m³/s)':locais[1]})
    return dict(uhes=uhes,afluencias=[q[:,None].tolist() for q in locais],meses=meses,
                cdef=8291.,origem='PySDDP / NEWAVE',historico=True,
                auditoria=pd.DataFrame(auditoria),vazoes=df,
                referencia=f"Cadastro {caso.dger.ano_ini['valor']} / mês {referencia+1}")


def construir_sistema(entrada, carga, uhes, utes, cdef, horas=720., natureza='Local'):
    from copy import deepcopy
    k=horas*3600/1e6
    af=np.asarray(entrada['afluencias'],dtype=float)
    if natureza=='Natural total' and len(uhes)>1:
        af=af.copy(); af[1]-=af[0]
    if not np.isfinite(af).all() or (af<0).any():
        raise ValueError('As afluências locais devem ser finitas e não negativas.')
    sistema={'DGer':{'Nr_Est':len(entrada['meses']),'Nr_Cen':af.shape[2],
                     'Carga':[float(carga)]*len(entrada['meses']), 'CDef':float(cdef)*horas,
                     'Horas':horas},'UHE':[],'UTE':[]}
    for i,u in enumerate(uhes):
        if not 0<=u['percentual']<=100 or not 0<=u['Vmin']<u['Vmax'] or u['rho']<=0 or u['qmax']<=0:
            raise ValueError('Volumes, produtividade ou engolimento inválidos.')
        item=deepcopy(u)
        vi=float(u.get('VI',u['Vmin']+u['percentual']/100*(u['Vmax']-u['Vmin'])))
        if not u['Vmin']<=vi<=u['Vmax']:raise ValueError('Volume inicial fora dos limites do reservatório.')
        item.update(VI=vi,
                    Prod=u['rho']/k,Engol=u['qmax']*k,Afl=(af[i]*k).tolist())
        sistema['UHE'].append(item)
    for u in utes:
        if u['Capac']<0 or u['CVU']<0:
            raise ValueError('Capacidade e CVU não podem ser negativos.')
        sistema['UTE'].append(dict(Nome=u['Nome'],Capac=float(u['Capac']),Custo=float(u['CVU'])*horas))
    if not np.isfinite(carga) or carga<0 or not np.isfinite(cdef) or cdef<0:
        raise ValueError('Carga e custo de déficit devem ser não negativos.')
    return sistema
