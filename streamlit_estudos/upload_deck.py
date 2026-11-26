"""Leitura de um deck enviado por ZIP, em diretório temporário por execução."""
from io import BytesIO
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from zipfile import ZipFile, BadZipFile
import shutil
import stat

from dados import ler_pysddp

LIMITE_ZIP = 50 * 1024 * 1024
LIMITE_EXTRAIDO = 250 * 1024 * 1024


def _nome_simples(nome):
    return bool(nome) and nome not in ('.','..') and not any(c in nome for c in '/\\:\x00')


def _preparar_deck(conteudo, destino):
    """Extrai sem caminhos externos e normaliza as referências para Linux."""
    if not conteudo or len(conteudo) > LIMITE_ZIP:
        raise ValueError('Envie um ZIP não vazio de até 50 MB.')
    try:
        with ZipFile(BytesIO(conteudo)) as z:
            itens=z.infolist()
            if len(itens)>3000 or sum(i.file_size for i in itens)>LIMITE_EXTRAIDO:
                raise ValueError('O ZIP excede o limite de arquivos ou de tamanho extraído.')
            vistos=set()
            for info in itens:
                nome=info.filename.replace('\\','/')
                partes=PurePosixPath(nome)
                if partes.is_absolute() or any(p in ('..','') or ':' in p or '\x00' in p for p in partes.parts):
                    raise ValueError('O ZIP contém um caminho inválido.')
                if stat.S_ISLNK(info.external_attr >> 16):
                    raise ValueError('O ZIP contém um link; envie somente arquivos do caso.')
                chave=nome.rstrip('/').casefold()
                if chave in vistos:
                    raise ValueError('O ZIP contém nomes duplicados, inclusive diferenças só de maiúsculas.')
                vistos.add(chave)
                alvo=destino.joinpath(*partes.parts).resolve()
                if not alvo.is_relative_to(destino.resolve()):
                    raise ValueError('Caminho fora da pasta temporária.')
                if info.is_dir():
                    alvo.mkdir(parents=True,exist_ok=True)
                else:
                    alvo.parent.mkdir(parents=True,exist_ok=True)
                    with z.open(info) as origem, alvo.open('wb') as saida:
                        shutil.copyfileobj(origem,saida)
    except BadZipFile as exc:
        raise ValueError('Não foi possível abrir o ZIP. Compacte novamente a pasta do caso.') from exc
    casos=[p for p in destino.rglob('*') if p.is_file() and p.name.upper()=='CASO.DAT' and '__MACOSX' not in p.parts]
    if len(casos)!=1:
        raise ValueError('O ZIP deve conter um único caso NEWAVE, identificado por CASO.DAT.')
    raiz=casos[0].parent
    arquivos={p.name.upper():p for p in raiz.iterdir() if p.is_file()}
    for obrigatorio in ('CASO.DAT','HIDR.DAT','VAZOES.DAT','CONFHD.DAT'):
        if obrigatorio not in arquivos:
            raise ValueError('Arquivo ausente no ZIP: '+obrigatorio)
    nome_arquivos=arquivos['CASO.DAT'].read_text(encoding='latin-1').splitlines()[0].strip()
    if not _nome_simples(nome_arquivos):raise ValueError('Referência inválida em CASO.DAT.')
    if nome_arquivos.upper() not in arquivos:raise ValueError('O arquivo indicado em CASO.DAT não está no ZIP.')
    linhas=arquivos[nome_arquivos.upper()].read_text(encoding='latin-1').splitlines(keepends=True)
    for i,linha in enumerate(linhas[:38]):
        nome=linha[30:].strip()
        if nome and not _nome_simples(nome):raise ValueError('Referência inválida no arquivo de entradas.')
        if nome:linhas[i]=linha[:30]+nome.upper()+'\n'
    # Copia apenas para a área temporária, sem modificar o ZIP ou o caso original.
    normalizado=destino/'_deck_normalizado'
    normalizado.mkdir()
    for nome,p in arquivos.items():shutil.copyfile(p,normalizado/nome)
    (normalizado/'CASO.DAT').write_text(nome_arquivos.upper()+'\n',encoding='latin-1')
    (normalizado/nome_arquivos.upper()).write_text(''.join(linhas),encoding='latin-1')
    return normalizado


def ler_zip_newave(conteudo,ano=2015,mes=9,horizonte=24):
    with TemporaryDirectory(prefix='planejamento_deck_') as pasta:
        deck=_preparar_deck(conteudo,Path(pasta))
        return ler_pysddp(deck,ano,mes,horizonte)
