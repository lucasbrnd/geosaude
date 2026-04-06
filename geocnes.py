import requests
from requests.adapters import HTTPAdapter
from urllib3.util import Retry
import pandas as pd
import warnings
import geobr
import unicodedata
import time
import geopandas as gpd
from shapely.geometry import Point
from geopy.geocoders import HereV7  # Alterado para HERE
from geopy.geocoders import Nominatim
from geopy.extra.rate_limiter import RateLimiter
import geopy.distance
from datetime import datetime
import re
import html
import os
from io import StringIO


# ---------------------------------------------------------
# Configuração inicial
# ---------------------------------------------------------

# Suprimir avisos de SSL do requests
warnings.simplefilter(
    'ignore',
    requests.packages.urllib3.exceptions.InsecureRequestWarning
)


# ---------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------

def normalize_text(text):
    """
    Normaliza texto removendo problemas de codificação,
    acentos e diferenças de capitalização.

    Utilizado principalmente para comparação segura
    de nomes de municípios.

    Parâmetros
    ----------
    text : str
        Texto a ser normalizado

    Retorno
    -------
    str
        Texto normalizado
    """

    try:
        corrected = text.encode('latin-1').decode('utf-8')

    except (UnicodeEncodeError, UnicodeDecodeError):

        corrected = text

    return unicodedata.normalize(
        'NFKD',
        corrected
    ).lower().strip()



def obter_codigo(nome_muni, uf_sigla):
    """
    Obtém o código IBGE de um município a partir do nome e UF.

    A busca é feita utilizando a biblioteca geobr e
    comparação com texto normalizado.

    Parâmetros
    ----------

    nome_muni : str
        Nome do município

    uf_sigla : str
        Sigla da unidade federativa (ex: 'SP')

    Retorno
    -------

    int ou None
        Código IBGE do município se encontrado.
        Retorna None caso não exista correspondência.
    """

    muni_busca = geobr.lookup_muni(name_muni=nome_muni)

    if muni_busca.empty:
        return None

    muni_busca['name_muni_normalized'] = (
        muni_busca['name_muni']
        .apply(normalize_text)
    )

    nome_normalizado = normalize_text(nome_muni)

    filtro = muni_busca[

        (muni_busca['name_muni_normalized']
         == nome_normalizado)

        &

        (muni_busca['abbrev_state']
         == uf_sigla)

    ]

    return (
        filtro['code_muni'].values[0]
        if not filtro.empty
        else None
    )



def uf_sigla(code_uf):
    """
    Converte código numérico da UF
    para a sigla oficial do estado.

    Parâmetros
    ----------

    code_uf : int ou str
        Código numérico da UF (IBGE)

    Retorno
    -------

    str
        Sigla da UF.
        Retorna string vazia se não encontrado.
    """

    uf_map = {

        '12': 'AC', '27': 'AL', '13': 'AM',
        '16': 'AP', '29': 'BA', '23': 'CE',
        '53': 'DF', '32': 'ES', '52': 'GO',
        '21': 'MA', '31': 'MG', '50': 'MS',
        '51': 'MT', '15': 'PA', '25': 'PB',
        '26': 'PE', '22': 'PI', '41': 'PR',
        '33': 'RJ', '24': 'RN', '11': 'RO',
        '14': 'RR', '43': 'RS', '42': 'SC',
        '28': 'SE', '35': 'SP', '17': 'TO'

    }

    return uf_map.get(str(code_uf), '')

def busca_cnes(code_mun, code_un, data='00'):
    """
    Consulta a lista de estabelecimentos do CNES para um município.

    A consulta é realizada diretamente no portal DATASUS/CNES
    utilizando o código IBGE do município e o tipo de unidade.

    Parâmetros
    ----------

    code_mun : int ou str
        Código IBGE do município

    code_un : str
        Código do tipo de estabelecimento CNES
        (exemplo: '05' = hospital, '73' = UPA)

    data : str, opcional
        Competência CNES (formato AAMM).
        Valor padrão '00' retorna a competência mais recente.

    Retorno
    -------

    list
        Lista de tabelas HTML retornadas pela consulta.
        Cada item corresponde a um DataFrame bruto.
    """

    code_uf = str(code_mun)[:2]
    code_mun_sus = str(code_mun)[:6]

    url = (
        "https://cnes2.datasus.gov.br/"
        "Mod_Ind_Unidade_Listar.asp"
        f"?VTipo={code_un}"
        f"&VListar=1"
        f"&VEstado={code_uf}"
        f"&VMun={code_mun_sus}"
        f"&VComp={data}"
    )

    print(url)

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        r = requests.get(
            url,
            verify=False,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        return pd.read_html(StringIO(r.text))



def clean_data(data):
    """
    Limpa a tabela bruta retornada pela consulta CNES.

    Remove cabeçalhos duplicados e linhas desnecessárias,
    retornando apenas os registros válidos.

    Parâmetros
    ----------

    data : list
        Lista de DataFrames retornados pela função busca_cnes()

    Retorno
    -------

    pandas.DataFrame
        Tabela CNES limpa e estruturada.
    """

    df = data[1]

    df.columns = df.iloc[0]

    return (
        df.iloc[1:-1]
        .reset_index(drop=True)
    )



def cnes_tab(code_mun, code_un, data='00'):
    """
    Obtém a tabela CNES limpa para um município.

    Esta função combina:

    - busca_cnes()
    - clean_data()

    Parâmetros
    ----------

    code_mun : int ou str
        Código IBGE do município

    code_un : str
        Código do tipo de estabelecimento CNES

    data : str, opcional
        Competência CNES (formato AAMM).
        Padrão: '00'

    Retorno
    -------

    pandas.DataFrame
        DataFrame com os estabelecimentos CNES.

        Retorna DataFrame vazio se não houver dados.
    """

    data = busca_cnes(
        code_mun,
        code_un,
        data
    )

    return clean_data(data) if data else pd.DataFrame()



def safe_extract(df, row, col, default=""):
    """
    Extrai valores de um DataFrame com segurança.

    Evita erros quando o índice ou coluna não existem,
    retornando um valor padrão.

    Muito utilizado na leitura de tabelas HTML do CNES,
    que podem ter estrutura variável.

    Parâmetros
    ----------

    df : pandas.DataFrame
        DataFrame de origem

    row : int
        Índice da linha

    col : int
        Índice da coluna

    default : str, opcional
        Valor padrão caso o dado não exista.
        Padrão: string vazia.

    Retorno
    -------

    str
        Valor convertido para string.
        Retorna default em caso de erro.
    """

    try:

        val = df.iloc[row, col]

        return str(val).strip() if pd.notna(val) else default

    except IndexError:

        return default

import time
from requests.exceptions import Timeout

def fetch_cnes_data(cnes):
    """
    Consulta informações detalhadas de um estabelecimento CNES.

    Realiza acesso ao sistema DATASUS/CNES para obter
    dados cadastrais completos de uma unidade de saúde.

    A função inclui mecanismo de repetição automática
    (retry) para lidar com instabilidade do servidor CNES.

    Parâmetros
    ----------

    cnes : str ou int
        Código CNES do estabelecimento.

    Retorno
    -------

    dict
        Dicionário contendo:

        - CNES
        - Nome_Fantasia
        - Logradouro
        - Numero
        - Complemento
        - Bairro
        - CEP
        - Municipio
        - UF
        - prof (número de profissionais)
        - Data (data de cadastro no CNES)

        Caso ocorra erro, retorna dicionário parcial.
    """

    # Dicionário inicial com código CNES
    data = {'CNES': cnes}

    max_retries = 3
    retry_count = 0

    while retry_count < max_retries:

        # Sessão HTTP com política de retry
        session = requests.Session()

        retry = Retry(
            total=3,
            backoff_factor=1,
            status_forcelist=[
                429, 500, 502, 503, 504, 10053
            ]
        )

        adapter = HTTPAdapter(max_retries=retry)

        session.mount("https://", adapter)

        try:

            # Controle de tempo da requisição
            start_time = time.time()

            response = session.get(
                "https://cnes2.datasus.gov.br/cabecalho_reduzido.asp",
                params={'VCod_Unidade': cnes},
                headers={
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
                    'Referer': 'https://cnes2.datasus.gov.br/index.asp'
                },
                verify=False,
                timeout=10
            )

            request_time = time.time() - start_time


            # Requisições muito lentas são tratadas como falha
            if request_time > 5:

                retry_count += 1

                print(
                    f"⚠ CNES {cnes}: requisição lenta "
                    f"({request_time:.2f}s) "
                    f"- tentativa {retry_count}/{max_retries}"
                )

                if retry_count < max_retries:

                    time.sleep(1)

                    continue

                else:

                    print(
                        f"⚠ CNES {cnes}: falha após "
                        f"{max_retries} tentativas por lentidão"
                    )

                    return data


            # Configuração de codificação
            response.encoding = 'ISO-8859-1'

            response.raise_for_status()


            # Leitura das tabelas HTML
            tables = pd.read_html(
                StringIO(response.content.decode(response.encoding or "utf-8", errors="replace"))
                )

            # Caso estrutura inesperada
            if len(tables) < 3:

                return data


            # ----------------------------
            # Extração da data de cadastro
            # ----------------------------

            df_date_hc = tables[1]

            raw_text = df_date_hc.iloc[0].values[0]

            decoded_text = html.unescape(raw_text)

            pattern = (
                r"Identificação\s+CADASTRADO NO CNES EM:\s*"
                r"(\d{1,2}/\d{1,2}/\d{4})"
            )

            match = re.search(pattern, decoded_text)

            if match:

                try:

                    data['Data'] = datetime.strptime(
                        match.group(1),
                        "%d/%m/%Y"
                    )

                except ValueError:

                    data['Data'] = None

            else:

                data['Data'] = None


            # ----------------------------
            # Extração dos dados cadastrais
            # ----------------------------

            df = tables[2]

            data.update({

                'Nome_Fantasia':
                    safe_extract(df, 1, 1),

                'Logradouro':
                    safe_extract(df, 5, 1),

                'Numero':
                    safe_extract(df, 5, 3),

                'Complemento':
                    safe_extract(df, 7, 0),

                'Bairro':
                    safe_extract(df, 7, 1),

                'CEP':
                    safe_extract(df, 7, 2),

                'Municipio':
                    safe_extract(df, 7, 3),

                'UF':
                    safe_extract(df, 7, 4),

                'prof':
                    get_num_prof(cnes)
            })


            # ----------------------------
            # Ordenação do dicionário
            # ----------------------------

            from collections import OrderedDict

            ordered_keys = [
                'CNES',
                'Nome_Fantasia',
                'Logradouro',
                'Numero',
                'Complemento',
                'Bairro',
                'CEP',
                'Municipio',
                'UF',
                'prof',
                'Data'
            ]

            data = OrderedDict(
                (key, data.get(key, None))
                for key in ordered_keys
            )

            return data


        except Timeout:

            retry_count += 1

            print(
                f"⚠ CNES {cnes}: timeout "
                f"- tentativa {retry_count}/{max_retries}"
            )

            if retry_count < max_retries:

                time.sleep(1)

                continue

            else:

                print(
                    f"⚠ CNES {cnes}: falha após "
                    f"{max_retries} timeouts"
                )

                return data


        except Exception as e:

            print(
                f"⚠ CNES {cnes}: erro inesperado - {str(e)}"
            )

            return data


    return data

def fetch_cnes_data_chunks(cnes_list, chunk=50, pause=0.5):
    """
    Obtém dados detalhados de estabelecimentos CNES em lotes.

    A função realiza consultas individuais para cada código CNES,
    organizando o processamento em lotes para melhorar a estabilidade
    em grandes volumes de dados. Códigos que falharem são registrados
    em arquivos CSV para posterior reprocessamento.

    Parâmetros
    ----------
    cnes_list : list
        Lista contendo os códigos CNES a serem consultados.

    chunk : int, opcional (padrão=50)
        Quantidade de códigos CNES processados por lote.

    pause : float, opcional (padrão=0.5)
        Intervalo de espera entre requisições HTTP (em segundos).

    Retorno
    -------
    pandas.DataFrame
        DataFrame contendo os dados consolidados dos estabelecimentos
        consultados com sucesso.
    """

    from tqdm import tqdm  # Barra de progresso

    all_data = []

    # Processamento em lotes
    for i in range(0, len(cnes_list), chunk):

        chunk_vec = cnes_list[i:i+chunk]

        print(f"○ Consultando CNES: registros {i+1} a {i+len(chunk_vec)}")

        chunk_data = []
        failed = []

        # Consulta individual de cada CNES
        for cnes in tqdm(chunk_vec):

            try:
                data = fetch_cnes_data(cnes)

                # Verifica se a consulta retornou dados válidos
                # (além do próprio código CNES)
                if len(data) > 1:
                    chunk_data.append(data)
                else:
                    failed.append(cnes)
                    print(f"⚠ CNES {cnes}: dados insuficientes (marcado como falha)")

                time.sleep(pause)

            except Exception as e:

                print(f"⚠ CNES {cnes}: erro durante a consulta -> {e}")
                failed.append(cnes)

        # Salva códigos CNES com falha (opcional)
        if failed:

            df_failed = pd.DataFrame({'CNES': failed})

            df_failed.to_csv(
                f"failed_cnes_{i+1}_{i+len(chunk_vec)}.csv",
                index=False
            )

            print(
                f"⚠ {len(failed)} CNES com falha salvos em "
                f"failed_cnes_{i+1}_{i+len(chunk_vec)}.csv"
            )

        # Adiciona resultados bem-sucedidos
        all_data.extend(chunk_data)


    df = pd.DataFrame(all_data)

    return df

def build_address_string(row):
    """
    Constrói uma string de endereço completo a partir dos componentes do DataFrame.

    Os campos são concatenados na ordem:
    Nome fantasia, logradouro, número, complemento, bairro,
    CEP, município e UF.

    Valores nulos são ignorados automaticamente.

    Parâmetros
    ----------
    row : pandas.Series
        Linha do DataFrame contendo os campos de endereço.

    Retorno
    -------
    str
        String com o endereço completo formatado.
    """

    components = [
        row['Nome_Fantasia'],
        row['Logradouro'],
        row['Numero'],
        row['Complemento'],
        row['Bairro'],
        row['CEP'],
        row['Municipio'],
        row['UF']
    ]

    return ', '.join(
        filter(
            None,
            [str(c) if pd.notna(c) else '' for c in components]
        )
    )


def get_num_prof(code_url):
    """
    Obtém o número de profissionais cadastrados em um estabelecimento CNES.

    A função acessa a página de profissionais do CNES e contabiliza
    os registros de acordo com a situação cadastrada.

    Parâmetros
    ----------
    code_url : str ou int
        Código CNES do estabelecimento.

    Retorno
    -------
    int
        Número de profissionais registrados na unidade.
    """

    # Realiza requisição ignorando avisos de segurança SSL
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        r = requests.get(
            f'https://cnes2.datasus.gov.br/Mod_Profissional.asp?VCo_Unidade={code_url}',
            verify=False,
            headers={"User-Agent": "Mozilla/5.0"}
        )
        data = pd.read_html(StringIO(r.text))

        
    profissionais = data[0]

    # Remove as duas últimas linhas (rodapé da tabela)
    profissionais.drop(
        profissionais.tail(2).index,
        inplace=True
    )

    # Define nomes padronizados das colunas
    profissionais.columns = [
        'Nome',
        'Entrada',
        'CNS',
        'CNS Master/Principal',
        'Dt. Atribuição',
        'CBO',
        'CH Outros',
        'CH Amb.',
        'CH Hosp.',
        'Total',
        'SUS',
        'Vinculação',
        'Tipo',
        'Subtipo',
        'Comp. Desativação',
        'Situação',
        'Portaria 134'
    ]

    # Contagem de profissionais por situação
    counts = profissionais['Situação'].value_counts()

    counts = profissionais.groupby('Situação').size()

    num_prof = counts.iloc[0]

    return num_prof

def geocode_data(df, api_key):
    """
    Realiza o geocodificação de endereços utilizando a API HERE.

    A função constrói os endereços a partir dos campos do DataFrame,
    consulta a API HERE Geocoding e retorna um GeoDataFrame com as
    coordenadas obtidas.

    Parâmetros
    ----------
    df : pandas.DataFrame
        DataFrame contendo os campos de endereço dos estabelecimentos.

    api_key : str
        Chave de acesso à API HERE.

    Retorno
    -------
    geopandas.GeoDataFrame
        GeoDataFrame contendo os dados originais e as colunas:

        - endereco : endereço completo utilizado na consulta
        - location : objeto retornado pelo geocodificador
        - lat : latitude
        - lon : longitude
        - altitude : altitude (quando disponível)
        - geometry : geometria do ponto (EPSG:4326)
    """

    # Constrói a coluna de endereços completos
    df['endereco'] = df.apply(build_address_string, axis=1)

    # Inicializa o geocodificador HERE
    geolocator = HereV7(apikey=api_key)

    # Limitador de requisições para evitar bloqueio da API
    geocode = RateLimiter(
        geolocator.geocode,
        min_delay_seconds=0.1
    )

    # Executa o geocodificação
    df['location'] = df['endereco'].apply(
        lambda addr: geocode(addr)
        if pd.notna(addr) and addr.strip()
        else None
    )

    # Função auxiliar para extrair coordenadas
    def extract_coords(loc):

        if loc is None:
            return pd.Series([None, None, None])

        try:
            lat = loc.latitude
            lon = loc.longitude

            # Altitude pode não existir dependendo da resposta
            alt = getattr(loc.point, 'altitude', None)

            return pd.Series([lat, lon, alt])

        except Exception:
            return pd.Series([None, None, None])


    # Cria colunas de coordenadas
    df[['lat', 'lon', 'altitude']] = df['location'].apply(
        extract_coords
    )

    # Converte para GeoDataFrame (WGS84)
    return gpd.GeoDataFrame(
        df,
        geometry=gpd.points_from_xy(df.lon, df.lat),
        crs='EPSG:4326'
    )


def geocode_chunks(df, here_api, cidade, chunk=50):
    """
    Realiza o geocodificação de um DataFrame em blocos (chunks).

    O processamento em blocos reduz a chance de falhas em grandes
    volumes de dados e permite salvar partes problemáticas para
    inspeção posterior.

    Parâmetros
    ----------
    df : pandas.DataFrame
        DataFrame contendo os dados a serem geocodificados.

    here_api : str
        Chave de acesso à API HERE.

    cidade : str
        Nome do município utilizado para organização das saídas.

    chunk : int, default=50
        Número de registros processados em cada bloco.

    Retorno
    -------
    geopandas.GeoDataFrame ou None
        GeoDataFrame com os resultados geocodificados.
        Retorna None se nenhum bloco for processado com sucesso.
    """

    # Define tamanho dos blocos
    chunk_size = chunk

    # Chave da API HERE
    api_key = here_api

    # Lista de blocos geocodificados com sucesso
    geocoded_chunks = []

    # Processamento em blocos
    for i in range(0, len(df), chunk_size):

        chunk = df.iloc[i:i+chunk_size].copy()

        #print(f"Geocodificando registros {i+1} até {i+len(chunk)}...")

        try:

            geocoded_chunk = geocode_data(
                chunk,
                api_key
            )

            geocoded_chunks.append(geocoded_chunk)

        except Exception as e:

            print(f"⚠ Erro no bloco {i//chunk_size + 1}: {e}")

            # Salva bloco com erro para inspeção
            chunk.to_csv(
                f"failed_chunk_rows_{i+1}_{i+len(chunk)}.csv"
            )

            print(
                f"○ Bloco problemático salvo em "
                f"'failed_chunk_rows_{i+1}_{i+len(chunk)}.csv'"
            )

    # Combina resultados se houver blocos válidos
    if geocoded_chunks:

        final_gdf = pd.concat(
            geocoded_chunks,
            ignore_index=True
        )

        print(
            f"\n○ Geocodificação concluída: "
            f"{len(final_gdf)}/{len(df)} registros processados"
        )

        print(
            f"- Registros não processados: "
            f"{len(df) - len(final_gdf)}"
        )

        # Salva resultados finais
        os.makedirs(
            f'./data/resultados/{cidade}/temp/',
            exist_ok=True
        )

        final_gdf.to_file(
            f'./data/resultados/{cidade}/temp/final_geocoded_results.gpkg',
            driver="GPKG"
        )

        print(
            f"- Resultados salvos em "
            f"'./data/resultados/{cidade}/temp/final_geocoded_results.gpkg'"
        )

    else:

        print("\n⚠ Nenhum bloco foi geocodificado com sucesso")

        final_gdf = None

    return final_gdf


def get_municipality_center(municipio, uf, here_api):
    """
    Obtém as coordenadas do centro aproximado de um município.

    A localização é obtida por geocodificação utilizando a API HERE.

    Parâmetros
    ----------
    municipio : str
        Nome do município.

    uf : str
        Sigla da unidade federativa.

    here_api : str
        Chave de acesso à API HERE.

    Retorno
    -------
    tuple
        Tupla (longitude, latitude).

        Retorna (None, None) caso a localização não seja encontrada.
    """

    # Inicializa o geocodificador HERE
    geolocator = HereV7(apikey=here_api)

    # Consulta o centro aproximado do município
    location = geolocator.geocode(
        f"{municipio}, {uf}, Brasil"
    )

    # Retorna coordenadas ou valores nulos
    return (
        (location.longitude, location.latitude)
        if location else
        (None, None)
    )


def validate_single_location(row, here_api):
    """
    Valida a posição geográfica de um registro geocodificado.

    A validação considera:

    - Existência das coordenadas
    - Distância em relação ao centro do município
    - Possíveis erros de geocodificação

    Parâmetros
    ----------
    row : pandas.Series
        Linha do DataFrame contendo as colunas:

        - lat
        - lon
        - Municipio
        - UF

    here_api : str
        Chave de acesso à API HERE.

    Retorno
    -------
    dict
        Dicionário contendo:

        - is_valid : bool
            Indica se a localização foi considerada válida.

        - validation_issues : str ou None
            Descrição dos problemas encontrados.
    """

    valid = True
    issues = []

    # Verifica se existem coordenadas
    if pd.isna(row['lat']) or pd.isna(row['lon']):

        valid = False
        issues.append("⚠ Falha na geocodificação")

        return {
            'is_valid': valid,
            'validation_issues': '; '.join(issues)
        }

    # Obtém centro do município
    center_lon, center_lat = get_municipality_center(
        row['Municipio'],
        row['UF'],
        here_api
    )

    # Validação por distância
    if center_lon and center_lat:

        try:

            distance = geopy.distance.distance(
                (row['lat'], row['lon']),
                (center_lat, center_lon)
            ).km

            # Distância excessiva
            if distance > 50:

                valid = False

                issues.append(
                    f"Distância elevada do centro ({distance:.1f} km)"
                )

            # Mesmo ponto do centro (possível erro)
            if distance == 0:

                valid = False

                issues.append(
                    "⚠ Localização idêntica ao centro do município"
                )

        except Exception as e:

            valid = False

            issues.append(
                f"Erro no cálculo de distância: {str(e)}"
            )

    else:

        issues.append(
            "○ Centro do município não disponível"
        )

    return {
        'is_valid': valid,
        'validation_issues':
            '; '.join(issues) if issues else None
    }


def validate_locations(gdf, here_api):
    """
    Valida um conjunto de localizações geocodificadas.

    A função aplica validações individuais a cada registro e
    adiciona colunas indicando a qualidade da geocodificação.

    Parâmetros
    ----------
    gdf : geopandas.GeoDataFrame
        GeoDataFrame contendo as localizações geocodificadas.

    here_api : str
        Chave de acesso à API HERE.

    Retorno
    -------
    geopandas.GeoDataFrame
        GeoDataFrame original com as colunas adicionais:

        - is_valid : bool
            Indica se a localização foi considerada válida.

        - validation_issues : str ou None
            Lista de problemas identificados.
    """

    validation_results = []

    # Validação registro a registro
    for _, row in gdf.iterrows():

        validation_results.append(
            validate_single_location(
                row,
                here_api
            )
        )

    validation_df = pd.DataFrame(
        validation_results
    )

    # Junta resultados ao GeoDataFrame original
    return gdf.join(validation_df)

def coordenadas_manual(gdf):
    """
    Permite tratar manualmente localizações inválidas.

    A função identifica registros com geocodificação inválida e
    permite:

    - Corrigir coordenadas manualmente
    - Excluir registros
    - Manter registros como inválidos

    As coordenadas devem ser informadas no formato:

        lat, lon

    Parâmetros
    ----------
    gdf : geopandas.GeoDataFrame
        GeoDataFrame contendo as colunas:

        - lat
        - lon
        - geometry
        - is_valid
        - validation_issues

    Retorno
    -------
    geopandas.GeoDataFrame
        GeoDataFrame com correções aplicadas.
    """

    # Cria cópia de trabalho
    gdf = gdf.copy()

    # Seleciona registros inválidos
    invalid_df = gdf[~gdf['is_valid']]

    # Encerra se não houver registros inválidos
    if invalid_df.empty:
        print("○ Todas as localizações são válidas — nenhuma correção necessária")
        return gdf

    print(
        f"\nForam encontradas {len(invalid_df)} "
        "⚠ Localizações inválidas. Iniciando verificação..."
    )

    # Lista de índices a processar
    invalid_indices = invalid_df.index.tolist()

    processed_indices = []

    for idx in invalid_indices:

        if idx in processed_indices:
            continue

        row = gdf.loc[idx]

        print(
            f"\n\n--- Processando estabelecimento: "
            f"{row['Nome_Fantasia']} ---"
        )

        print(
            f"Problemas de validação: "
            f"{row['validation_issues']}"
        )

        print(
            f"Coordenadas atuais: "
            f"{row['lat']}, {row['lon']}"
        )

        while True:

            # Modo automático (sem interação)
            # action = input(...)
            action = 'S'

            # -------------------------
            # Correção manual
            # -------------------------
            if action == 'C':

                try:

                    coords = input(
                        "Informe novas coordenadas "
                        "(lat, lon): "
                    ).strip()

                    lat, lon = [
                        float(x.strip())
                        for x in coords.split(',')
                    ]

                    # Atualiza coordenadas
                    gdf.at[idx, 'lat'] = lat
                    gdf.at[idx, 'lon'] = lon

                    gdf.at[idx, 'geometry'] = Point(
                        lon,
                        lat
                    )

                    # Revalidação
                    validation = validate_single_location(
                        gdf.loc[idx]
                    )

                    gdf.at[idx, 'is_valid'] = validation['is_valid']

                    gdf.at[idx, 'validation_issues'] = \
                        validation['validation_issues']

                    status = (
                        "VÁLIDO"
                        if validation['is_valid']
                        else "INVÁLIDO"
                    )

                    print(
                        f"\nLocalização atualizada: {status}"
                    )

                    if validation['validation_issues']:

                        print(
                            "Problemas de validação: "
                            f"{validation['validation_issues']}"
                        )

                    processed_indices.append(idx)

                    break

                except Exception as e:

                    print(
                        f"Erro: {str(e)}. "
                        "Tente novamente."
                    )

            # -------------------------
            # Exclusão do registro
            # -------------------------
            elif action == 'D':

                gdf = gdf.drop(index=idx)

                print("Registro removido")

                processed_indices.append(idx)

                break

            # -------------------------
            # Manter inválido
            # -------------------------
            elif action == 'S':

                print(
                    "Registro mantido como inválido"
                )

                processed_indices.append(idx)

                break

            else:

                print(
                    "Opção inválida. "
                    "Escolha C, D ou S"
                )

    return gdf


def process_locations(gdf, here_api):
    """
    Executa o fluxo completo de processamento de localizações.

    Etapas:

    1. Validação das coordenadas geocodificadas
    2. Tratamento de registros inválidos

    Parâmetros
    ----------
    gdf : geopandas.GeoDataFrame
        GeoDataFrame com coordenadas geocodificadas.

    here_api : str
        Chave de acesso à API HERE.

    Retorno
    -------
    geopandas.GeoDataFrame
        GeoDataFrame validado e corrigido.
    """

    # Etapa 1 — validação automática
    validated_gdf = validate_locations(
        gdf,
        here_api
    )

    # Etapa 2 — tratamento de inválidos
    return coordenadas_manual(
        validated_gdf
    )

def geocnes(cidade_n, uf, here_api, code_un='02', chunk=20, ano='00'):
    """
    Executa o fluxo completo de obtenção e geocodificação de dados do CNES
    para um município.

    Etapas do processamento:

    1. Identificação do código do município (IBGE)
    2. Obtenção da lista de estabelecimentos CNES
    3. Coleta dos dados detalhados das unidades
    4. Geocodificação dos endereços (API HERE)
    5. Validação das coordenadas obtidas
    6. Geração de relatório de validação
    7. Salvamento dos resultados

    Parâmetros
    ----------
    cidade_n : str
        Nome do município.

    uf : str
        Sigla da unidade federativa.

    here_api : str
        Chave de acesso à API HERE.

    code_un : str, opcional
        Código do tipo de estabelecimento CNES.
        Exemplo:
        - '02' → Estabelecimentos de saúde

    chunk : int, opcional
        Número de registros processados por lote.

    ano : str, opcional
        Competência CNES no formato AAMM.
        Exemplo:
        - '00' → Base mais recente disponível

    Retorno
    -------
    geopandas.GeoDataFrame ou None
        GeoDataFrame com estabelecimentos geocodificados e validados.
        Retorna None caso o processamento não seja possível.
    """

    cidade = cidade_n

    print (f"• Inicializando GeoCNES • \nCidade: {cidade} - {uf}.")

    # -------------------------------------------------
    # 1. Obter código do município
    # -------------------------------------------------

    code_mun = obter_codigo(cidade, uf)

    if not code_mun:

        print(
            f"⚠ Município não encontrado: "
            f"{cidade}, {uf}"
        )

        return None

    code_mun = str(code_mun)


    # -------------------------------------------------
    # 2. Obter lista de estabelecimentos CNES
    # -------------------------------------------------

    print(
        "• Carregando a lista de estabelecimentos CNES..."
    )

    un_saude_tab = cnes_tab(
        code_mun,
        code_un,
        ano
    )

    if un_saude_tab.empty:

        print(
            f"⚠ Nenhum estabelecimento encontrado "
            f"para o tipo {code_un} em {cidade}"
        )

        return None

    # -------------------------------------------------
    # 3. Preparar lista de códigos CNES
    # -------------------------------------------------

    CNES_LIST = [
        str(code_mun)[:6] + str(cnes_code)
        for cnes_code in un_saude_tab.iloc[:, 0]
    ]

    if len(CNES_LIST) == 0:

        return None

    print(
        f"• Estabelecimentos encontrados: "
        f"{len(CNES_LIST)}"
    )

    # -------------------------------------------------
    # 4. Obter dados detalhados
    # -------------------------------------------------

    print(
        "• Obtendo dados detalhados do CNES..."
    )

    df = fetch_cnes_data_chunks(
        CNES_LIST,
        chunk,
        pause=0.5
    )

    if df.empty:

        print(
            "⚠ Não foi possível obter "
            "dados detalhados"
        )

        return None

    # -------------------------------------------------
    # 5. Geocodificação dos endereços
    # -------------------------------------------------

    print(
        "• Geocodificando endereços..."
    )

    geo_df = geocode_chunks(
        df,
        here_api,
        cidade_n,
        chunk
    )

    if geo_df is None:

        print(
            "⚠ Falha na geocodificação"
        )

        return None

    # -------------------------------------------------
    # 6. Validação das coordenadas
    # -------------------------------------------------

    print(
        "• Validando coordenadas..."
    )

    validated_df = process_locations(
        geo_df,
        here_api
    )

    # -------------------------------------------------
    # 7. Relatório de validação
    # -------------------------------------------------

    valid_count = validated_df['is_valid'].sum()

    print("\n• Relatório de validação:")

    print(
        f"Total de estabelecimentos: "
        f"{len(validated_df)}"
    )

    print(
        f"○ Localizações válidas: "
        f"{valid_count}"
    )

    print(
        f"○ Necessitam revisão: "
        f"{len(validated_df) - valid_count}"
    )

    if len(validated_df) - valid_count > 0:

        print("\n○ Registros que precisam revisão:")

        print(
            validated_df[
                ~validated_df['is_valid']
            ][
                [
                    'CNES',
                    'Nome_Fantasia',
                    'validation_issues'
                ]
            ]
        )

    # -------------------------------------------------
    # 8. Salvar resultados
    # -------------------------------------------------

    os.makedirs(
        f'./data/resultados/{cidade}/',
        exist_ok=True
    )

    output_file = (
        f"./data/resultados/{cidade}/"
        f"cnes_{cidade}_{uf}_{code_un}.gpkg"
    )

    validated_df.to_file(
        output_file,
        driver='GPKG'
    )

    print(
        f"• Resultados salvos em:\n"
        f"{output_file}\n\n"
    )
    #return validated_df