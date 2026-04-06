##########################################################
############ CARACTERÍSTICAS DEMOGRÁFICAS ################
##########################################################

######################## FUNÇÕES UTILITÁRIAS ########################

import unicodedata   # Normalização de texto (acentos e caracteres especiais)
import geobr         # Acesso a dados geográficos oficiais do Brasil


def normalize_text(text):
    """
    Normaliza textos tratando problemas de codificação e removendo acentos.

    Parâmetros
    ----------
    text : str
        Texto de entrada.

    Retorno
    -------
    str
        Texto normalizado (sem acentos, em minúsculas e sem espaços extras).
    """
    try:
        corrected = text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        corrected = text

    return unicodedata.normalize('NFKD', corrected).lower().strip()


def obter_codigo(nome_muni, uf_sigla):
    """
    Obtém o código IBGE do município a partir do nome e da UF.

    Parâmetros
    ----------
    nome_muni : str
        Nome do município.
    uf_sigla : str
        Sigla da unidade federativa (ex: 'SP').

    Retorno
    -------
    int ou None
        Código do município (IBGE) ou None caso não encontrado.
    """

    muni_busca = geobr.lookup_muni(name_muni=nome_muni)

    if muni_busca.empty:
        return None

    muni_busca['name_muni_normalized'] = muni_busca['name_muni'].apply(normalize_text)

    nome_normalizado = normalize_text(nome_muni)

    filtro = muni_busca[
        muni_busca['name_muni_normalized'] == nome_normalizado
    ]

    return filtro['code_muni'].values[0] if not filtro.empty else None


##########################################################
################ C1 - VULNERABILIDADE SOCIAL #############
##########################################################

import pandas as pd
import geopandas as gpd


def check_ivs(mun, uf):
    """
    Verifica a disponibilidade de dados de vulnerabilidade social
    para um município.

    A função busca dados nas seguintes bases:

    - IVS (Atlas de Vulnerabilidade Social - IPEA)
    - IPVS (Índice Paulista de Vulnerabilidade Social - SEADE)

    Parâmetros
    ----------
    mun : str
        Nome do município.
    uf : str
        Sigla da unidade federativa.

    Retorno
    -------
    tuple
        (GeoDataFrame, tipo_indice)

        tipo_indice pode ser:
        - 'ivs'
        - 'ipvs'
        - None (dados não encontrados)
    """

    # Carregar tabelas de referência
    ivs = pd.read_csv('./data/ivs_mun.csv')
    ipvs = pd.read_csv('./data/ipvs_mun.csv')

    # Verificação na base IVS
    match_ivs = ivs[
        (ivs['Municipality'] == mun) &
        (ivs['UF'] == uf)
    ]

    if not match_ivs.empty:

        ivs_data = gpd.read_file('./data/ivs.gpkg')

        ivs_data = ivs_data[
            ivs_data['nome_municipio_uf'] == f'{mun} ({uf})'
        ]

        print(
            f'✔ Dados de vulnerabilidade para {mun} disponíveis no '
            f'Atlas de Vulnerabilidade Social (IPEA).'
        )

        return ivs_data, 'ivs'

    # Verificação na base IPVS (somente para SP)
    if uf == 'SP':

        match_ipvs = ipvs[
            ipvs['Municipality'] == mun
        ]

        if not match_ipvs.empty:

            ipvs_data = gpd.read_file('./data/ipvs.gpkg')

            ipvs_data = ipvs_data[
                ipvs_data['V2'] == mun
            ]

            print(
                f'✔ Dados de vulnerabilidade para {mun} disponíveis no '
                f'Índice Paulista de Vulnerabilidade Social (SEADE).'
            )

            return ipvs_data, 'ipvs'

    # Caso não haja dados
    print(
        f'⚠ Dados de vulnerabilidade para {mun} não encontrados '
        f'nas bases consideradas. Verifique a grafia do município.'
    )

    return None, None


def vulnerabilidade(mun, uf, bbox):
    """
    Processa dados de vulnerabilidade social e gera raster padronizado.

    Dependendo da disponibilidade, a função utiliza:

    - IVS (IPEA)
    - IPVS (SEADE - apenas SP)

    O resultado final é um raster com pontuação padronizada.

    Parâmetros
    ----------
    mun : str
        Nome do município.

    uf : str
        Sigla da unidade federativa.

    bbox : tuple
        Bounding box da área de estudo.

    Retorno
    -------
    None
    """

    vs, indice = check_ivs(mun, uf)

    # -----------------------------
    # Processamento com base IVS
    # -----------------------------
    if (indice == 'ivs'):

        vs = vs[vs['ano'] == 2010]

        # Intervalos de classificação do IVS
        bins = [0, 0.2, 0.3, 0.4, 0.5, float('inf')]

        labels = [
            'Muito baixa',
            'Baixa',
            'Média',
            'Alta',
            'Muito alta'
        ]

        # Classificação das áreas
        vs['ivs_classe'] = pd.cut(
            vs['ivs'],
            bins=bins,
            labels=labels,
            include_lowest=True
        )

        # Conversão de classes em pontuação
        score_map = {
            'Muito alta': 10,
            'Alta': 8,
            'Média': 5,
            'Baixa': 3,
            'Muito baixa': 1
        }

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            vs['score'] = (
                vs['ivs_classe']
                .replace(score_map)
                .infer_objects(copy=False)
            )

        from utils import criar_raster_padronizado

        criar_raster_padronizado(
            vs,
            mun,
            uf,
            bbox,
            nome_arquivo='C1_VulnSoc'
        )

    # -----------------------------
    # Processamento com base IPVS
    # -----------------------------
    elif (indice == 'ipvs'):

        v10_score_map = {
            'Não classificado': 0,
            'Baixíssima vulnerabilidade': 1,
            'Vulnerabilidade muito baixa': 2,
            'Vulnerabilidade baixa': 3,
            'Vulnerabilidade média': 5,
            'Vulnerabilidade alta (Urbanos)': 8,
            'Vulnerabilidade alta (Rurais)': 8,
            'Vulnerabilidade muito alta (aglomerados subnormais urbanos)': 10
        }

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            vs['score'] = (
                vs['V10']
                .replace(v10_score_map)
                .infer_objects(copy=False)
            )

        from utils import criar_raster_padronizado

        criar_raster_padronizado(
            vs,
            mun,
            uf,
            bbox,
            nome_arquivo='C1_VulnSoc'
        )

    else:

        return None

##########################################################
# C2 - DISTRIBUIÇÃO DEMOGRÁFICA
# C3 - DISTRIBUIÇÃO DE RENDA
##########################################################

import os
import pandas as pd
import geopandas as gpd
import numpy as np
import requests
from pathlib import Path
import h3
import h3pandas
import warnings
import unicodedata   # Normalização de texto
import geobr         # Dados geográficos oficiais do Brasil
from utils import bbox_urb

##########################################################
############ DOWNLOAD E PREPARAÇÃO DE DADOS ##############
##########################################################

def download_file(url: str, filename: str, folder: str = './data/censo') -> None:
    """
    Faz o download de um arquivo caso ele ainda não exista.

    Parâmetros
    ----------
    url : str
        Endereço do arquivo.

    filename : str
        Nome do arquivo.

    folder : str
        Pasta de destino (padrão: ./data/censo)
    """

    save_folder = Path(folder)
    save_folder.mkdir(parents=True, exist_ok=True)

    file_path = save_folder / filename

    if file_path.exists():

        print(f"⚠ Arquivo já existente: {file_path}")
        return

    try:

        response = requests.get(url)
        response.raise_for_status()

        with open(file_path, 'wb') as f:
            f.write(response.content)

        print(f"✔ Download concluído: {file_path}")

    except requests.exceptions.RequestException as e:

        print(f"⚠  Falha no download: {e}")


def unzip_file(zip_filename: str, folder: str = './data/censo') -> None:
    """
    Extrai um arquivo ZIP.

    Parâmetros
    ----------
    zip_filename : str
        Nome do arquivo ZIP

    folder : str
        Pasta destino
    """

    import zipfile

    zip_path = Path(f'{folder}/{zip_filename}')
    extract_to = Path(folder)

    extract_to.mkdir(parents=True, exist_ok=True)

    if not zip_path.exists() or zip_path.suffix != '.zip':

        print(f"⚠ Arquivo inexistente ou inválido: {zip_path}")
        return

    try:

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)

        print(f"✔ Arquivo extraído em: {extract_to.resolve()}")

    except zipfile.BadZipFile:

        print(f"⚠ Arquivo ZIP inválido: {zip_path}")


##########################################################
############ FUNÇÃO PRINCIPAL DEMOGRAFIA #################
##########################################################

def dados_demograficos(uf_code, mun, bbox):
    """
    Processa dados do Censo 2022 para:

    - C2 Distribuição demográfica
    - C3 Distribuição de renda

    Dados utilizados:
    - Setores censitários
    - CNEFE (endereços)
    - Demografia
    - Renda

    Parâmetros
    ----------
    uf_code : str
        Sigla da UF

    mun : str
        Nome do município

    bbox : tuple
        Bounding box da área de estudo

    Retorno
    -------
    None
    """

    code_ibge = obter_codigo(mun, uf_code).astype('str')


    ###################################################
    # DOWNLOAD DOS DADOS IBGE
    ###################################################

    # Setores censitários
    url = f'https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/malha_com_atributos/setores/gpkg/UF/{uf_code}/{uf_code}_setores_CD2022.gpkg'
    filename = f'{uf_code}_setores_CD2022.gpkg'
    download_file(url, filename)


    # CNEFE
    url = f'https://ftp.ibge.gov.br/Cadastro_Nacional_de_Enderecos_para_Fins_Estatisticos/Censo_Demografico_2022/Arquivos_CNEFE/GeoJSON/Municipio_20240910/qg_810_endereco_Munic{code_ibge}.json.zip'
    filename = f'qg_810_endereco_Munic{code_ibge}.json.zip'
    download_file(url, filename)
    unzip_file(filename)


    # Dados de renda
    url = f'https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios_Rendimento_do_Responsavel/Agregados_por_setores_renda_responsavel_BR_csv.zip'
    filename = f'Agregados_por_setores_renda_BR.zip'
    download_file(url, filename)
    unzip_file(filename)


    # Dados demográficos
    url = f'https://ftp.ibge.gov.br/Censos/Censo_Demografico_2022/Agregados_por_Setores_Censitarios/Agregados_por_Setor_csv/Agregados_por_setores_demografia_BR.zip'
    filename = f'Agregados_por_setores_demografia_BR.zip'
    download_file(url, filename)
    unzip_file(filename)


    ###################################################
    # LEITURA E PREPARAÇÃO DOS DADOS
    ###################################################

    setores = gpd.read_file(
        f'./data/censo/{uf_code}_setores_CD2022.gpkg'
    )

    setores = setores[setores['CD_MUN'] == code_ibge]
    
    setores = setores[setores['CD_TIPO']!=2]

    setores['CD_SETOR'] = setores['CD_SETOR'].astype('int64')

    bbox_urb(mun,setores)


    ###################################################
    # DADOS DEMOGRÁFICOS
    ###################################################

    dados = pd.read_csv(
        './data/censo/Agregados_por_setores_demografia_BR.csv',
        sep=';',
        decimal=',',
        encoding='ISO-8859-1',
        low_memory=False
    )

    dados.replace('X', np.nan, inplace=True)

    for col in dados.columns[1:]:
        dados[col] = pd.to_numeric(dados[col], errors='coerce')

    dados = dados[['CD_setor', 'V01006']]


    ###################################################
    # DADOS DE RENDA
    ###################################################

    dados_renda = pd.read_csv(
        './data/censo/Agregados_por_setores_renda_responsavel_BR.csv',
        sep=';',
        decimal=',',
        encoding='utf-8'
    )

    for col in dados_renda.columns[1:]:

        dados_renda[col] = (
            dados_renda[col]
            .str.replace(',', '.', regex=False)
        )

        dados_renda[col] = pd.to_numeric(
            dados_renda[col],
            errors='coerce'
        )

    dados_renda = dados_renda[
        ['CD_SETOR', 'V06001', 'V06004']
    ]


    ###################################################
    # INTEGRAÇÃO DOS DADOS
    ###################################################

    setores = pd.merge(
        setores,
        dados,
        left_on='CD_SETOR',
        right_on='CD_setor',
        how='left'
    )

    setores = pd.merge(
        setores,
        dados_renda,
        on='CD_SETOR',
        how='left'
    )


    ###################################################
    # PROCESSAMENTO CNEFE
    ###################################################

    pontos_cnefe = gpd.read_file(
        f'./data/censo/qg_810_endereco_Munic{code_ibge}.json'
    )

    pontos_cnefe['COD_ESPECIE'] = pontos_cnefe['COD_ESPECIE'].astype('int64')


    # Apenas domicílios particulares
    pontos_cnefe = pontos_cnefe[
        ((pontos_cnefe['COD_ESPECIE'] == 1)) &
        ((pontos_cnefe['NV_GEO_COORD'] != 5) |
         (pontos_cnefe['NV_GEO_COORD'] != 6))
    ]


    ###################################################
    # POPULAÇÃO POR DOMICÍLIO
    ###################################################

    join_gdf = pontos_cnefe.sjoin(
        setores[['geometry', 'CD_SETOR']],
        how='left'
    )

    group = (
        join_gdf[['CD_SETOR', 'geometry']]
        .groupby('CD_SETOR')
        .count()
        .reset_index()
        .rename(columns={'geometry': 'count'})
    )

    setores = pd.merge(
        setores,
        group,
        on='CD_SETOR',
        how='left'
    )

    setores['pop/dom'] = setores['V01006'] / setores['count']

    setores['renda'] = setores['V06004']

    setores['renda/dom'] = setores['V06004'] / setores['count']


    ###################################################
    # ATRIBUIÇÃO PARA OS PONTOS
    ###################################################

    join_gdf = pontos_cnefe.sjoin(
        setores[['geometry', 'pop/dom', 'renda', 'renda/dom']],
        how='left'
    )


    ###################################################
    # GERAÇÃO DA GRADE H3
    ###################################################

    area = setores.dissolve()

    area = area.to_crs('4326')

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        area = area.buffer(0.0001)

    area = gpd.GeoDataFrame(geometry=area)

    bounds_hex = area[['geometry']].h3.polyfill_resample(9)

    bounds_hex.to_crs(epsg=4674, inplace=True)


    ###################################################
    # AGREGAÇÃO POR HEXÁGONO
    ###################################################

    join_gdf = join_gdf.sjoin(bounds_hex, how='left')

    group = join_gdf.groupby('h3_polyfill').agg({

        'pop/dom': 'sum',
        'renda': 'sum',
        'renda/dom': 'sum',
        'geometry': 'count'

    }).rename(columns={
        'geometry': 'count',
        'pop/dom': 'pop_total'
    })

    bounds_hex = pd.merge(
        bounds_hex,
        group,
        on='h3_polyfill',
        how='left'
    )


    ###################################################
    # C2 — DISTRIBUIÇÃO DEMOGRÁFICA
    ###################################################

    import mapclassify

    valid = bounds_hex['pop_total'].notna()

    with warnings.catch_warnings():

        warnings.simplefilter("ignore")

        nb = mapclassify.NaturalBreaks(
            bounds_hex.loc[valid, 'pop_total'],
            k=5
        )

    bounds_hex.loc[valid, 'pop_class'] = nb.yb

    labels = {

        None: 'Sem dados',
        0: 'Muito baixa',
        1: 'Baixa',
        2: 'Média',
        3: 'Alta',
        4: 'Muito alta'
    }

    bounds_hex['pop_class_label'] = (
        bounds_hex['pop_class']
        .map(labels)
    )

    label_to_value = {

        'Sem dados': None,
        'Muito baixa': 1,
        'Baixa': 3,
        'Média': 5,
        'Alta': 8,
        'Muito alta': 10
    }

    bounds_hex['score'] = (
        bounds_hex['pop_class_label']
        .map(label_to_value)
    )

    from utils import criar_raster_padronizado

    criar_raster_padronizado(
        bounds_hex,
        mun,
        uf_code,
        bbox,
        nome_arquivo='C2_DistDemog'
    )


    ###################################################
    # C3 — DISTRIBUIÇÃO DE RENDA
    ###################################################

    
    bounds_hex['renda_pond'] = bounds_hex['renda']/bounds_hex['count']
    bounds_hex['renda_sm'] = bounds_hex['renda_pond']/ 1212


    def classify_income(sm):

        if pd.isna(sm):
            return 0

        elif sm <= 2:
            return 10

        elif sm <= 3:
            return 8

        elif sm <= 5:
            return 5

        elif sm <= 10:
            return 2

        else:
            return 1


    bounds_hex['score'] = (
        bounds_hex['renda_sm']
        .apply(classify_income)
        .astype('uint8')
    )


    criar_raster_padronizado(
        bounds_hex,
        mun,
        uf_code,
        bbox,
        nome_arquivo='C3_DistRenda'
    )


    ###################################################
    # EXPORTAÇÃO FINAL
    ###################################################

    bounds_hex.to_file(
        f'./data/resultados/{mun}/{mun}_{uf_code}_h3_grid.gpkg',
        driver='GPKG'
    )

##########################################################
########### CARACTERÍSTICAS DE ACESSIBILIDADE ############
##########################################################

# C4 – Tempo mínimo de deslocamento
# C5 – Nível de acesso (FCA)
# C6 – Cobertura das unidades


def travel_time_calculation(mun, uf, bbox, google_api, opentopo_api):
    """
    Calcula os indicadores de acessibilidade baseados em tempo de deslocamento.

    Gera automaticamente:
        C4 – Tempo mínimo de deslocamento
        C5 – Nível de acesso (FCA)
        C6 – Cobertura das unidades (isócronas)

    Parâmetros
    ----------
    mun : str
        Nome do município
    uf : str
        Sigla do estado
    bbox : tuple
        Bounding box para geração do raster final
    google_api : str
        Chave de API (não utilizada nesta versão)
    opentopo_api : str
        Chave da API OpenTopoData para modelo de elevação
    """

    import geopandas as gpd
    import shapely
    import datetime
    import pandas as pd
    import geocnes
    import os
    import inspect

    from utils import get_osmpbf
    from utils import get_elevation

    # Carregar grade hexagonal (origens)
    origins = gpd.read_file(
        f'./data/resultados/{mun}/{mun}_{uf}_h3_grid.gpkg'
    )

    # Carregar ou gerar destinos (CNES)
    if os.path.exists(f'./data/resultados/{mun}/cnes_{mun}_{uf}_02.gpkg'):
        destinations = gpd.read_file(
            f'./data/resultados/{mun}/cnes_{mun}_{uf}_02.gpkg'
        )
    else:
        destinations = geocnes.geocnes(mun, uf, here_api)

    # Obter rede OSM
    get_osmpbf(mun, uf, mail='nobody')

    # Converter para WGS84
    origins_wgs = origins.to_crs(4326)

    minx, miny, maxx, maxy = origins_wgs.dissolve().total_bounds

    # Modelo de elevação
    elev = get_elevation(
        mun,
        minx,
        miny,
        maxx,
        maxy,
        opentopo_api
    )

    import r5py

    # Criar rede de transporte
    transport_network = r5py.TransportNetwork(
        osm_pbf=f'./data/resultados/{mun}/network/{mun}_{uf}.osm.pbf',
        elevation_model=elev
    )

    # Pontos de origem (centroides dos hexágonos)
    origins_pt = origins.copy()

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        origins_pt.geometry = origins.geometry.centroid

    origins_pt['id'] = origins['h3_polyfill']
    destinations['id'] = destinations['CNES']

    # -------------------------------------------------
    # Limpeza de geometrias inválidas antes do r5py
    # -------------------------------------------------

    # Origens: remove pontos nulos, vazios ou com coordenadas inválidas
    n_antes = len(origins_pt)
    origins_pt = origins_pt[
        origins_pt.geometry.notna() &
        ~origins_pt.geometry.is_empty &
        origins_pt.geometry.is_valid
    ].reset_index(drop=True)
    n_removidos = n_antes - len(origins_pt)

    if n_removidos > 0:
        print(f"Origens removidas por geometria inválida: {n_removidos}")

    # Destinos: mesma limpeza
    n_antes = len(destinations)
    destinations = destinations[
        destinations.geometry.notna() &
        ~destinations.geometry.is_empty &
        destinations.geometry.is_valid
    ].reset_index(drop=True)
    n_removidos = n_antes - len(destinations)

    if n_removidos > 0:
        print(f"Destinos removidos por geometria inválida: {n_removidos}")

    # Verificação de segurança
    if origins_pt.empty:
        raise ValueError("Nenhuma origem válida após limpeza de geometrias.")

    if destinations.empty:
        raise ValueError("Nenhum destino válido após limpeza de geometrias.")

    # Garante WGS84 (r5py exige internamente)
    if origins_pt.crs.to_epsg() != 4326:
        origins_pt = origins_pt.to_crs(4326)

    if destinations.crs is None:
        destinations = destinations.set_crs(4326)
    elif destinations.crs.to_epsg() != 4326:
        destinations = destinations.to_crs(4326)

    # Matriz de tempos de deslocamento
    travel_times = r5py.TravelTimeMatrix(
        transport_network,
        origins=origins_pt,
        destinations=destinations,
        transport_modes=[r5py.TransportMode.WALK],
        max_time=datetime.timedelta(seconds=7200),
        snap_to_network=True
    )

    print('Executando análise de tempo mínimo...')
    min_travel_time(mun, uf, bbox, origins, travel_times)
    print('Concluído.')

    print('Executando análise do nível de acesso...')
    fca(mun, uf, bbox, origins, travel_times)
    print('Concluído.')

    print('Executando análise de cobertura...')
    get_isochrones(destinations, bbox, transport_network, mun, uf)
    print('Concluído.')


##########################################################
# C4 – Tempo mínimo de deslocamento
##########################################################

def min_travel_time(mun, uf, bbox, origins, travel_time):
    """
    Calcula o tempo mínimo de deslocamento até a unidade mais próxima.

    O resultado é classificado em faixas de tempo e convertido
    para pontuações padronizadas.
    """

    min_travel_times = (
        travel_time
        .groupby("from_id", as_index=False)["travel_time"]
        .min()
    )

    min_travel_times = origins.merge(
        min_travel_times,
        left_on='h3_polyfill',
        right_on='from_id',
        how='left'
    )

    min_travel_times = min_travel_times[
        min_travel_times['pop_total'] > 0
    ]

    import numpy as np

    # Classes de tempo (minutos)
    conditions = [
        min_travel_times['travel_time'] < 15,
        min_travel_times['travel_time'].between(15, 30, inclusive='left'),
        min_travel_times['travel_time'].between(30, 45, inclusive='left'),
        min_travel_times['travel_time'].between(45, 60, inclusive='left'),
        min_travel_times['travel_time'] > 60
    ]

    categories = [1, 2, 6, 8, 10]

    min_travel_times['score'] = np.select(
        conditions,
        categories,
        default=np.nan
    )

    from utils import criar_raster_padronizado

    criar_raster_padronizado(
        min_travel_times,
        mun,
        uf,
        bbox,
        nome_arquivo='C4_TempoMin'
    )


##########################################################
# C6 – Cobertura das unidades (isócronas)
##########################################################

def get_isochrones(destinations, bbox, transport_network, mun, uf):
    """
    Calcula isócronas de caminhada (30 min) individualmente por destino.
    Regiões com sobreposição de múltiplas isócronas recebem pontuação maior.
    """

    import geopandas as gpd
    import pandas as pd
    import r5py
    import inspect
    from shapely.ops import polygonize, unary_union

    all_isochrones = []

    # -------------------------------------------------
    # Pré-validação dos destinos
    # -------------------------------------------------

    if destinations.crs is None:
        destinations = destinations.set_crs("EPSG:4326")
    else:
        destinations = destinations.to_crs("EPSG:4326")

    destinations = destinations[
        destinations.geometry.notna() &
        ~destinations.geometry.is_empty &
        destinations.geometry.is_valid
    ].reset_index(drop=True)

    if destinations.empty:
        print("get_isochrones: nenhum destino válido após filtragem.")
        return

    # -------------------------------------------------
    # Isócrona individual por destino
    # -------------------------------------------------

    sig = inspect.signature(r5py.Isochrones.__init__)

    for idx, row in destinations.iterrows():

        geom = row.geometry

        if geom is None or geom.is_empty or not geom.is_valid:
            print(f"Destino {row.get('id', idx)}: geometria inválida, ignorado.")
            continue

        if geom.geom_type == "MultiPoint":
            geom = geom.geoms[0]

        origin_gdf = gpd.GeoDataFrame(
            [{"id": row["id"], "geometry": geom}],
            crs="EPSG:4326"
        )

        try:
            iso_kwargs = dict(
                transport_modes=[r5py.TransportMode.WALK],
                isochrones=[30],
                speed_walking=4.5,
                point_grid_resolution=200,
            )

            if "point_grid_sample_ratio" in sig.parameters:
                iso_kwargs["point_grid_sample_ratio"] = 1

            iso = r5py.Isochrones(
                transport_network,
                origins=origin_gdf,
                **iso_kwargs
            )

        except Exception as e:
            print(f"Destino {row.get('id', idx)}: erro ao calcular isócrona — {e}")
            continue

        if iso is None or len(iso) == 0:
            print(f"Destino {row.get('id', idx)}: sem resultado.")
            continue

        # -------------------------------------------------
        # Conversão linhas → polígono
        # iso já contém apenas este destino — sem necessidade de filtrar por id
        # -------------------------------------------------

        try:
            iso["geometry"] = iso.geometry.make_valid()

            polys = list(polygonize(iso.geometry))

            if polys:
                merged_poly = unary_union(polys)
            else:
                # Fallback: dissolve direto
                merged_poly = unary_union(iso.geometry).buffer(0)

            if merged_poly is None or merged_poly.is_empty:
                print(f"Destino {row.get('id', idx)}: polígono vazio.")
                continue

            iso_poly = gpd.GeoDataFrame(
                geometry=[merged_poly],
                crs="EPSG:4326"
            )
            iso_poly["geometry"] = iso_poly.geometry.make_valid()
            iso_poly["destination_id"] = row["id"]
            iso_poly["score"] = 1

            all_isochrones.append(iso_poly)

        except Exception as e:
            print(f"Destino {row.get('id', idx)}: erro na conversão — {e}")
            continue

    # -------------------------------------------------
    # Sobreposição: pontuação proporcional ao nº de coberturas
    # -------------------------------------------------

    if not all_isochrones:
        print("Nenhuma isócrona gerada. Critério C6 não será calculado.")
        return

    # -------------------------------------------------
    # Sobreposição: pontuação proporcional ao nº de coberturas
    # -------------------------------------------------

    if not all_isochrones:
        print("Nenhuma isócrona gerada. Critério C6 não será calculado.")
        return

    all_gdf = pd.concat(all_isochrones, ignore_index=True)
    all_gdf = all_gdf.to_crs(epsg=3857)

    all_polys = all_gdf.geometry.tolist()

    # -------------------------------------------------
    # Cria regiões únicas a partir das fronteiras de todas as isócronas
    # Cada região única receberá uma contagem de cobertura independente
    # -------------------------------------------------

    from shapely.ops import unary_union, polygonize

    all_boundaries = unary_union([p.boundary for p in all_polys])
    unique_faces = list(polygonize(all_boundaries))

    if not unique_faces:
        print("Erro: não foi possível gerar regiões únicas de sobreposição.")
        return

    print(f"Regiões únicas geradas: {len(unique_faces)}")

    # -------------------------------------------------
    # Conta quantas isócronas cobrem cada região única
    # -------------------------------------------------

    records = []

    for face in unique_faces:

        centroid = face.centroid

        count = sum(
            1 for poly in all_polys
            if poly.contains(centroid) or poly.covers(centroid)
        )

        records.append({
            "geometry": face,
            "overlap_count": count
        })

    result = gpd.GeoDataFrame(records, crs=all_gdf.crs)
    result = result[result["overlap_count"] > 0]

    # -------------------------------------------------
    # Atribuição do score por número de sobreposições
    # -------------------------------------------------

    import numpy as np

    conditions = [
        result["overlap_count"] == 0,
        result["overlap_count"] == 1,
        result["overlap_count"] == 2,
        result["overlap_count"] == 3,
        result["overlap_count"] > 3,
    ]

    scores = [10, 4, 3, 2, 1]

    result["score"] = np.select(conditions, scores, default=1).astype(int)

    print(f"Distribuição de scores:\n{result['score'].value_counts().sort_index()}")

    result = result.to_crs(epsg=4326)
    result["geometry"] = result.geometry.make_valid()

    from utils import criar_raster_padronizado

    criar_raster_padronizado(
        result,
        mun,
        uf,
        bbox,
        nome_arquivo="C6_Cobertura"
    )

    print(
        f"C6 gerado: {len(all_isochrones)} isócronas, "
        f"{result['score'].nunique()} classes de cobertura."
    )
'''
def get_isochrones(destinations, bbox, transport_network, mun, uf):
    """
    Calcula isócronas de caminhada (30 min) e gera polígonos
    individuais para cada destino.
    """

    import geopandas as gpd
    import pandas as pd
    import r5py
    from shapely.ops import polygonize, unary_union
    from shapely.geometry import box
    import inspect

    all_isochrones = []

    # -------------------------------------------------
    # Pré-validação dos destinos
    # -------------------------------------------------

    # Garante WGS84 (exigido pelo r5py internamente)
    if destinations.crs is None:
        destinations = destinations.set_crs("EPSG:4326")
    else:
        destinations = destinations.to_crs("EPSG:4326")

    # Remove registros com geometria nula ou inválida
    destinations_iso = destinations[
        destinations.geometry.notna() &
        ~destinations.geometry.is_empty &
        destinations.geometry.is_valid
    ].reset_index(drop=True)

    if destinations_iso.empty:
        logger.warning("get_isochrones: nenhum destino válido após filtragem.")
        return

    for idx, row in destinations_iso.iterrows():

        geom = row.geometry

        # Validação individual antes de passar ao r5py
        if geom is None or geom.is_empty or not geom.is_valid:
            print(f"Destino {row.get('id', idx)} ignorado: geometria inválida.")
            continue

        # Garante que é um ponto simples (não MultiPoint)
        if geom.geom_type == "MultiPoint":
            geom = geom.geoms[0]

        origin_gdf = gpd.GeoDataFrame(
            [{"id": row["id"], "geometry": geom}],
            crs="EPSG:4326"
        )

        try:
            # -------------------------------------------------
            # Parâmetros compatíveis com versões recentes do r5py
            # point_grid_sample_ratio foi removido em versões > 1.x
            # -------------------------------------------------

            iso_kwargs = dict(
                transport_modes=[r5py.TransportMode.WALK],
                isochrones=[30],
                speed_walking=4.5,
                point_grid_resolution=200,
            )
            
            sig = inspect.signature(r5py.Isochrones.__init__)
            if "point_grid_sample_ratio" in sig.parameters:
                iso_kwargs["point_grid_sample_ratio"] = 1
            
            iso = r5py.Isochrones(
                transport_network,
                origins = origin_gdf,
                **iso_kwargs
            )

        except Exception as e:
            print(f"Destino {row.get('id', idx)}: erro ao calcular isócrona — {e}")
            continue

        if iso is None or len(iso) == 0:
            print(f"Destino {row.get('id', idx)}: sem resultado na isócrona.")
            continue

        print(iso)

        # -------------------------------------------------
        # Dissolve e conversão linhas → polígonos
        # -------------------------------------------------

        try:
            iso_lines = iso.dissolve().reset_index(drop=True)
            iso_lines["geometry"] = iso_lines.geometry.make_valid()

            polys = list(polygonize(iso_lines.geometry))

            if not polys:
                print(f"Destino {row.get('id', idx)}: sem polígono gerado.")
                continue

            merged_poly = unary_union(polys)

            if merged_poly is None or merged_poly.is_empty:
                continue

            iso_poly = gpd.GeoDataFrame(
                geometry=[merged_poly],
                crs="EPSG:4326"
            )

            iso_poly["geometry"] = iso_poly.geometry.make_valid()
            iso_poly["destination_id"] = row["id"]
            iso_poly["score"] = 1

            all_isochrones.append(iso_poly)

        except Exception as e:
            print(f"Destino {row.get('id', idx)}: erro na conversão — {e}")
            continue

    # -------------------------------------------------
    # Concatenação e rasterização
    # -------------------------------------------------

    if not all_isochrones:
        print("Nenhuma isócrona gerada. Critério C6 não será calculado.")
        return

    poly_gdf = pd.concat(all_isochrones, ignore_index=True)
    poly_gdf["geometry"] = poly_gdf.geometry.make_valid()

    from utils import criar_raster_padronizado

    criar_raster_padronizado(
        poly_gdf,
        mun,
        uf,
        bbox,
        nome_arquivo="C6_Cobertura"
    )

   # print(f"C6 gerado com {len(poly_gdf)} isócronas.")'''
'''
def get_isochrones(destinations, bbox, transport_network, mun, uf):
    """
    Calcula isócronas de caminhada (30 min) para todos os destinos.
    """

    import geopandas as gpd
    import pandas as pd
    import r5py
    from shapely.ops import polygonize, unary_union

    # -------------------------------------------------
    # Pré-validação dos destinos
    # -------------------------------------------------

    if destinations.crs is None:
        destinations = destinations.set_crs("EPSG:4326")
    else:
        destinations = destinations.to_crs("EPSG:4326")

    destinations = destinations[
        destinations.geometry.notna() &
        ~destinations.geometry.is_empty &
        destinations.geometry.is_valid
    ].reset_index(drop=True)

    print (destinations.head)

    # Garante que não há MultiPoint
    def extrair_ponto(geom):
        if geom.geom_type == "MultiPoint":
            return geom.geoms[0]
        return geom

    destinations["geometry"] = destinations["geometry"].apply(extrair_ponto)

    if destinations.empty:
        print("get_isochrones: nenhum destino válido após filtragem.")
        return

    # -------------------------------------------------
    # Cálculo das isócronas — todos os destinos de uma vez
    # -------------------------------------------------

    origins_iso = destinations[["id", "geometry"]].copy()

    print(origins_iso.head())

    try:
        iso = r5py.Isochrones(
            transport_network,
            origins=origins_iso,
            transport_modes=[r5py.TransportMode.WALK],
            isochrones=[30],
            speed_walking=4.5,
            point_grid_resolution=200,
        )
    except Exception as e:
        print(f"Erro ao calcular isócronas: {e}")
        return
   
    print(iso.columns.tolist())
    print(iso.head(2))

    if iso is None or len(iso) == 0:
        print("Nenhuma isócrona gerada pelo r5py.")
        return

    # -------------------------------------------------
    # Conversão linhas → polígonos — união de todas as isócronas
    # -------------------------------------------------

    try:
        iso["geometry"] = iso.geometry.make_valid()

        # Tenta converter linhas em polígonos
        polys = list(polygonize(iso.geometry))

        if polys:
            merged_poly = unary_union(polys)
        else:
            # Fallback: dissolve direto das geometrias retornadas
            merged_poly = unary_union(iso.geometry).buffer(0)

        if merged_poly is None or merged_poly.is_empty:
            print("Nenhuma isócrona gerada. Critério C6 não será calculado.")
            return

        poly_gdf = gpd.GeoDataFrame(
            geometry=[merged_poly],
            crs="EPSG:4326"
        )
        poly_gdf["geometry"] = poly_gdf.geometry.make_valid()
        poly_gdf["score"] = 1

    except Exception as e:
        print(f"Erro na conversão das isócronas — {e}")
        return

    # -------------------------------------------------
    # Rasterização
    # -------------------------------------------------

    from utils import criar_raster_padronizado

    criar_raster_padronizado(
        poly_gdf,
        mun,
        uf,
        bbox,
        nome_arquivo="C6_Cobertura"
    )

    print(f"C6 gerado: {len(poly_gdf)} polígono(s) de cobertura.")
'''
    
##########################################################
# Função de decaimento gaussiano
##########################################################

def decay(t, t_prime):
    """
    Função de decaimento gaussiano utilizada no método FCA.

    Baseada em Liu et al. (2024).

    Parâmetros
    ----------
    t : float
        Tempo de deslocamento
    t_prime : float
        Tempo máximo considerado

    Retorna
    -------
    float
        Peso de decaimento
    """

    numerator = np.exp(-0.5 * (t / t_prime)**2) - np.exp(-0.5)
    denominator = 1 - np.exp(-0.5)

    return numerator / denominator


##########################################################
# C5 – Nível de acesso (FCA)
##########################################################

def fca(mun, uf, bbox, origins, travel_time, max_ttm=30):
    """
    Calcula o nível de acesso utilizando o método FCA
    (Floating Catchment Area com decaimento exponencial).

    O indicador considera:
        - população
        - oferta de profissionais
        - tempo de deslocamento
    """

    hex_grid = origins
    ttm = travel_time

    travel_times_agg = ttm.merge(
        hex_grid[['h3_polyfill', 'pop_total']],
        left_on='from_id',
        right_on='h3_polyfill',
        how='left'
    )

    cnes = gpd.read_file(
        f"./data/resultados/{mun}/cnes_{mun}_{uf}_02.gpkg"
    )

    travel_times_agg = travel_times_agg.merge(
        cnes[['CNES', 'prof']],
        left_on='to_id',
        right_on='CNES',
        how='left'
    )

    ttm_filtered = travel_times_agg[
        travel_times_agg['travel_time'] <= max_ttm
    ]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        ttm_filtered['decay'] = decay(
            ttm_filtered['travel_time'],
            max_ttm
        )

        ttm_filtered['pop_decay'] = (
            ttm_filtered['pop_total']
            * ttm_filtered['decay']
        )

    aux = (
        ttm_filtered
        .groupby('CNES')['pop_decay']
        .sum()
        .reset_index()
    )

    aux = aux[
        aux['pop_decay'].notna()
        & (aux['pop_decay'] > 0)
    ]

    PPR = cnes[['CNES', 'prof']]

    PPR = pd.merge(PPR, aux, how='left')

    PPR['Rj'] = PPR['prof'] / PPR['pop_decay']

    travel_times_agg = travel_times_agg.merge(
        PPR[['CNES', 'Rj']],
        how='left'
    )

    filtered = travel_times_agg[
        travel_times_agg['travel_time'] <= max_ttm
    ]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")

        filtered['decay'] = decay(
            filtered['travel_time'],
            max_ttm
        )

        filtered['Rj_decay'] = (
            filtered['Rj']
            * filtered['decay']
        )

    aux = (
        filtered
        .groupby('h3_polyfill')['Rj_decay']
        .sum()
        .reset_index()
    )

    aux.rename(columns={'Rj_decay': 'Ai'}, inplace=True)

    acess = pd.merge(
        hex_grid,
        aux,
        how='left'
    )

    acess = acess[
        acess['pop_total'] > 0
    ]

    quintis = pd.qcut(
        acess['Ai'],
        q=5,
        labels=[1, 2, 3, 4, 5]
    )

    quintis = quintis.astype('category')
    quintis = quintis.cat.add_categories([0])

    acess['Ai_quintil'] = (
        quintis.fillna(0)
        .astype(int)
    )

    reclass_map = {
        0: 10,
        1: 10,
        2: 8,
        3: 5,
        4: 2,
        5: 1
    }

    acess['score'] = (
        acess['Ai_quintil']
        .map(reclass_map)
        .fillna(0)
        .astype(np.uint8)
    )

    acess.to_file(
        f'niv_acess_{mun}.gpkg',
        driver='GPKG'
    )

    from utils import criar_raster_padronizado

    criar_raster_padronizado(
        acess,
        mun,
        uf,
        bbox,
        nome_arquivo='C5_NivAcess'
    )

##########################################################
############## CARACTERÍSTICAS DO ENTORNO ################
##########################################################

# C7 – Risco de eventos naturais (Base SGB)

def sgb_data(uf, mun, bbox):
    """
    Obtém e processa dados de suscetibilidade a eventos naturais do SGB
    (Serviço Geológico do Brasil) para um município específico.

    O procedimento inclui:
    - Verificação de dados locais previamente baixados
    - Download automático (se necessário)
    - Extração dos arquivos
    - Leitura de camadas espaciais (Shapefile ou GPKG)
    - Reclassificação em pontuações padronizadas
    - Geração de rasters padronizados

    Parâmetros
    ----------
    uf : str
        Sigla do estado (ex: 'SP').

    mun : str
        Nome do município.

    bbox : tuple
        Bounding box no formato (xmin, ymin, xmax, ymax).

    Retorno
    -------
    dict
        Dicionário contendo os GeoDataFrames processados
        para cada tipo de evento natural.

    Retorna None caso os dados não estejam disponíveis.
    """

    import pandas as pd
    import os
    import requests
    import zipfile
    import shutil
    from tqdm import tqdm
    import re
    import geopandas as gpd
    import time


    #######################################################
    # 1 - Localizar link de dados do município
    #######################################################

    df_mun = pd.read_csv(
        "./data/sgb_mun1.csv",
        encoding='utf-8',
        sep=";"
    )

    match = df_mun[
        (df_mun['uf_abbr'] == uf) &
        (df_mun['municipality'] == mun)
    ]

    if not match.empty:
        mun_url = match.iloc[0]['SIG_link']
    else:
        mun_url = None
        print(
            f"⚠ Município '{mun}' ({uf}) não encontrado na base SGB.\n"
            f"Verifique o nome informado."
        )


    #######################################################
    # 2 - Verificação de dados existentes
    #######################################################

    base_susc_path = f'./temp/{uf}_{mun}_Suscetibilidade/'
    susc_path = None


    def encontrar_suscetibilidade(pasta_base):
        """
        Busca recursivamente por pasta ou arquivo contendo
        'suscetibilidade' no nome.
        """

        for root, dirs, files in os.walk(pasta_base):

            # Verificar pastas
            for dir_name in dirs:
                if 'suscetibilidade' in dir_name.lower():
                    return os.path.join(root, dir_name)

            # Verificar arquivos
            for file_name in files:
                if 'suscetibilidade' in file_name.lower():

                    if file_name.lower().endswith(
                        ('.gpkg', '.shp')
                    ):
                        print(
                            os.path.join(root, file_name)
                        )

                        return os.path.dirname(
                            os.path.join(root, file_name)
                        )

        return None


    #######################################################
    # 3 - Verificar pasta local existente
    #######################################################

    if os.path.isdir(base_susc_path):

        print(f"Pasta encontrada: {base_susc_path}")

        susc_path = encontrar_suscetibilidade(
            base_susc_path
        )

        if susc_path and os.path.exists(susc_path):

            shapefiles = [
                f for f in os.listdir(susc_path)
                if f.lower().endswith('.shp')
                and not f.lower().endswith('_l.shp')
                and 'bacia' not in f.lower()
            ]

            gpkg_files = [
                f for f in os.listdir(susc_path)
                if f.lower() == 'suscetibilidade.gpkg'
            ]

            if shapefiles or gpkg_files:

                print(
                    f"✔ Dados de suscetibilidade encontrados:\n"
                    f"   Pasta: {susc_path}\n"
                    f"   Shapefiles: {len(shapefiles)}\n"
                    f"   GPKG: {len(gpkg_files)}"
                )

            else:

                print(
                    "⚠ Pasta encontrada, mas sem dados válidos."
                )

                susc_path = None

        else:

            print(
                "⚠ Pasta base encontrada, "
                "mas dados de suscetibilidade ausentes."
            )

            susc_path = None

    else:

        print(
            f"⚠ Pasta não encontrada: {base_susc_path}"
        )

        susc_path = None


    #######################################################
    # 4 - Download e extração (se necessário)
    #######################################################

    if susc_path is None:

        print(
            "Iniciando download dos dados SGB..."
        )

        if mun_url is None:

            print(
                "⚠ URL do município não encontrada."
            )

            return None


        temp_dir = 'temp'

        os.makedirs(temp_dir, exist_ok=True)

        zip_path = os.path.join(
            temp_dir,
            f'arquivo_{mun}.zip'
        )


        if os.path.exists(zip_path):

            print(
                f"✔ Arquivo ZIP já existente:\n{zip_path}"
            )

        else:

            os.makedirs(
                base_susc_path,
                exist_ok=True
            )

            try:

                print(
                    f"Baixando dados:\n{mun_url}"
                )

                session = requests.Session()

                headers = {
                    'Accept-Encoding': 'identity',
                    'User-Agent':
                    'Mozilla/5.0'
                }

                response = session.get(
                    mun_url,
                    headers=headers,
                    stream=True,
                    timeout=60
                )

                response.raise_for_status()

                total_size = int(
                    response.headers.get(
                        'content-length', 0
                    )
                )

                with open(zip_path, 'wb') as file, tqdm(
                        total=total_size,
                        unit='B',
                        unit_scale=True,
                        unit_divisor=1024,
                        desc="Download",
                        miniters=1
                ) as pbar:

                    for chunk in response.iter_content(
                            chunk_size=262144
                    ):

                        if chunk:

                            file.write(chunk)

                            pbar.update(
                                len(chunk)
                            )

                print("✔ Download concluído.")

            except Exception as e:

                print(
                    f"⚠ Erro no download:\n{e}"
                )

                if not os.path.exists(zip_path):

                    return None


        ###################################################
        # Extração do ZIP
        ###################################################

        try:

            print(
                f"Extraindo arquivos para:\n"
                f"{base_susc_path}"
            )

            with zipfile.ZipFile(
                    zip_path, 'r'
            ) as zip_ref:

                zip_ref.extractall(
                    base_susc_path
                )

            time.sleep(2)

            susc_path = encontrar_suscetibilidade(
                base_susc_path
            )


            if not susc_path:

                print(
                    "⚠ Dados de suscetibilidade "
                    "não encontrados após extração."
                )

                return None

            print(
                f"✔ Dados localizados:\n"
                f"{susc_path}"
            )


            # Limpeza de pastas extras

            for item in os.listdir(
                    base_susc_path
            ):

                item_path = os.path.join(
                    base_susc_path,
                    item
                )

                if (
                        os.path.isdir(item_path)
                        and item_path != susc_path
                ):

                    try:

                        shutil.rmtree(
                            item_path
                        )

                        print(
                            f"Pasta removida: {item}"
                        )

                    except Exception as e:

                        print(
                            f"⚠ Erro ao remover {item}: {e}"
                        )


        except zipfile.BadZipFile:

            print(
                "⚠ Arquivo ZIP inválido."
            )

            return None

        except Exception as e:

            print(
                f"⚠ Erro na extração:\n{e}"
            )

            return None


    #######################################################
    # 5 - Leitura dos dados espaciais
    #######################################################

    if not os.path.exists(susc_path):

        print(
            "⚠ Caminho de suscetibilidade inválido."
        )

        return None


    shapefiles = [
        f for f in os.listdir(susc_path)
        if f.lower().endswith('.shp')
        and not f.lower().endswith('_l.shp')
        and 'bacia' not in f.lower()
    ]

    gpkg_files = [
        f for f in os.listdir(susc_path)
        if f.lower() == 'suscetibilidade.gpkg'
    ]


    #######################################################
    # 5.1 Prioridade: arquivo GPKG
    #######################################################

    if gpkg_files:

        gpkg_path = os.path.join(
            susc_path,
            gpkg_files[0]
        )

        print(
            f"Arquivo GPKG encontrado:\n"
            f"{gpkg_path}"
        )

        try:

            camadas = gpd.list_layers(
                gpkg_path
            )

            camadas_filtradas = camadas[
                camadas['name'].str.endswith('_A')
            ]

            eventos = {}

            for camada in camadas_filtradas['name']:

                nome_evento = (
                    camada.replace('A', '')
                    .replace(' ', '')
                    .replace('_', '')
                    .lower()
                    .replace('ç', 'c')
                    .replace('ã', 'a')
                    .replace('á', 'a')
                    .replace('é', 'e')
                    .replace('í', 'i')
                    .replace('ó', 'o')
                    .replace('ú', 'u')
                )

                eventos[nome_evento] = gpd.read_file(
                    gpkg_path,
                    layer=camada
                )

                print(
                    f"Camada carregada: "
                    f"{nome_evento}"
                )

            if not eventos:

                print(
                    "⚠ Nenhuma camada válida encontrada."
                )

                return None

        except Exception as e:

            print(
                f"⚠ Erro ao processar GPKG:\n{e}"
            )

            return None


    #######################################################
    # 5.2 Alternativa: shapefiles
    #######################################################

    elif shapefiles:

        print(
            f"Processando "
            f"{len(shapefiles)} shapefiles"
        )

        eventos = {}

        for filename in shapefiles:

            nome_base = os.path.splitext(
                filename
            )[0]

            nome_evento = (
                nome_base.replace('A', '')
                .replace(' ', '')
                .replace('_', '')
                .lower()
                .replace('ç', 'c')
                .replace('ã', 'a')
                .replace('á', 'a')
                .replace('é', 'e')
                .replace('í', 'i')
                .replace('ó', 'o')
                .replace('ú', 'u')
            )

            shp_path = os.path.join(
                susc_path,
                filename
            )

            eventos[nome_evento] = gpd.read_file(
                shp_path
            )

            print(
                f"Shapefile carregado: "
                f"{nome_evento}"
            )

    else:

        print(
            "⚠ Nenhum dado espacial encontrado."
        )

        return None

    ############################################################
    # CONTINUA COM O PROCESSAMENTO NORMAL (reclassificação e rasterização)
    ############################################################

    # Mapeamento padrão
    reclass_map_default = {
        None: 10,
        'Inexistente': 10,
        'inexistente': 10,
        'Muito baixa': 10,
        'muito baixa': 10,
        'muito baixo': 10,
        'Baixa': 5,
        'baixa': 5,
        'baixo': 5,
        'Média': 3,
        'média': 3,
        'Media': 3,
        'media': 3,
        'Médio': 3,
        'médio': 3,
        'Medio': 3,
        'medio': 3,
        'Alta': 1,
        'Alto': 1,
        'alta': 1,
        'alto': 1,
    }

    # Mapeamento especial para movimento de massa
    reclass_map_movimentomassa = {
        'Inexistente': 10,
        'inexistente': 10,
        'Muito baixa': 10,
        'Muito baixo': 10,
        'muito baixa': 10,
        'muito baixo': 10,
        'Baixa': 0,
        'Baixo': 0,
        'baixa': 0,
        'baixo': 0,
        'Média': 3,
        'Médio': 3,
        'media': 3,
        'medio': 3,
        'Alta': 1,
        'Alto': 1,
        'alta': 1,
        'alto': 1
    }


    def encontrar_coluna_classe(gdf):
        """Encontra a coluna CLASSE independente do case"""
        for coluna in gdf.columns:
            if coluna.upper() == 'CLASSE':
                return coluna
        return None


    ############################################################
    # Reclassificação
    ############################################################

    for nome_evento, gdf in eventos.items():

        coluna_classe = encontrar_coluna_classe(gdf)

        if coluna_classe:

            if (
                nome_evento == 'movimentodamassa'
                or nome_evento == 'movimentodemassa'
                or nome_evento == 'suscetibilidademovimentodemassa'
                or 'movimento' in nome_evento
            ):

                gdf['score'] = gdf[coluna_classe].map(
                    reclass_map_movimentomassa
                )

            else:

                gdf['score'] = gdf[coluna_classe].map(
                    reclass_map_default
                )

            print(
                f"✔ Evento '{nome_evento}' reclassificado usando coluna '{coluna_classe}'."
            )

        else:

            print(
                f"⚠ Evento '{nome_evento}' não possui coluna 'CLASSE'."
            )


    ############################################################
    # Rasterização
    ############################################################

    for nome_evento, gdf in eventos.items():

        if 'score' in gdf.columns:

            from utils import criar_raster_padronizado

            criar_raster_padronizado(
                gdf,
                mun,
                uf,
                bbox,
                nome_arquivo=f'C7_{nome_evento}'
            )

            print(
                f"✔ Raster '{nome_evento}.tif' gerado com sucesso."
            )

        else:

            print(
                f"⚠ Evento '{nome_evento}' não possui 'score'. Raster não gerado."
            )


# C8 - PROXIMIDADE A EQUIPAMENTOS URBANOS INDESEJÁVEIS (PUI)

import osmnx as ox
import geopandas as gpd
import pandas as pd
from shapely.geometry import box


def PUI(mun, uf, bbox):
    """
    Calcula o critério C8 - Proximidade a Equipamentos Urbanos Indesejáveis (PUI).

    O método identifica equipamentos urbanos potencialmente indesejáveis a partir
    do OpenStreetMap e classifica o território municipal conforme a distância:

        0 – 50 m   → score = 3
        50 – 100 m → score = 5
        > 100 m    → score = 10

    Parâmetros
    ----------
    mun : str
        Nome do município.

    uf : str
        Sigla do estado.

    bbox : tuple
        Bounding box utilizada na rasterização final.

    Saída
    -----
    Raster:
        C8_EqupInd.tif
    """

    from utils import obter_codigo

    # ------------------------------------------------------------------
    # Definição da área de estudo (limite municipal)
    # ------------------------------------------------------------------

    code = obter_codigo(mun, uf)

    # Aumenta o tempo limite das requisições ao OSM
    ox.settings.use_cache = True
    ox.settings.log_console = True
    ox.settings.requests_timeout = 120
    ox.settings.overpass_rate_limit = True

    # Carrega o limite municipal a partir do shapefile
    place = gpd.read_file(
        f'./data/resultados/{mun}/setores_{mun}.gpkg',
        layer='setores_censitarios'
    )

    # garantir CRS correto (OSM usa WGS84)
    place = place.to_crs(4326)

    # dissolver tudo em um único polígono
    place = place.dissolve()

    # Extrai apenas a geometria
    place = place.geometry.iloc[0]

    # ------------------------------------------------------------------
    # Definição das tags OSM para equipamentos indesejáveis
    # ------------------------------------------------------------------

    # Vias de grande fluxo
    vias_tags = {
        "highway": [
            "motorway", "trunk", "primary",
            "motorway_link", "trunk_link", "primary_link"
        ]
    }

    # Redes de energia elétrica de alta voltagem
    redes_tags = {
        "power": ["line", "tower", "substation"]
    }

    # Áreas industriais
    industrias_tags = {
        "landuse": "industrial"
    }

    # Matadouros e processamento de carne
    matadouro_tags = {
        "industrial": ["meat_processing", "slaughterhouse"]
    }

    # Postos de combustível
    posto_tags = {
        "amenity": "fuel"
    }

    # Aeroportos e estruturas associadas
    aero_tags = {
        "aeroway": ["aerodrome", "runway", "terminal"]
    }

    # Cemitérios
    cemiterio_tags = {
        "landuse": ["cemetery"],
        "amenity": ["grave_yard"]
    }

    # Áreas de resíduos sólidos
    lixo_tags = {
        "landuse": ["landfill"],
        "amenity": ["recycling", "waste_transfer_station"]
    }


    # ------------------------------------------------------------------
    # Download das feições do OpenStreetMap
    # ------------------------------------------------------------------

    vias_grande_fluxo = ox.features_from_polygon(place, vias_tags)

    redes_alta_voltagem = safe_features_from_place(place, redes_tags)
    redes_alta_voltagem = redes_alta_voltagem[
        redes_alta_voltagem.geometry.geom_type.isin(
            ['Polygon', 'MultiPolygon', 'Point']
        )
    ]

    industrias = safe_features_from_place(place, industrias_tags)
    industrias = industrias[
        industrias.geometry.geom_type.isin(
            ['Polygon', 'MultiPolygon']
        )
    ]

    matadouros = safe_features_from_place(place, matadouro_tags)
    postos_gasolina = safe_features_from_place(place, posto_tags)
    aeroportos = safe_features_from_place(place, aero_tags)
    cemiterios = safe_features_from_place(place, cemiterio_tags)
    depositos_lixo = safe_features_from_place(place, lixo_tags)


    # ------------------------------------------------------------------
    # Padronização do sistema de coordenadas
    # ------------------------------------------------------------------

    crs = vias_grande_fluxo.crs


    # ------------------------------------------------------------------
    # Identificação das categorias
    # ------------------------------------------------------------------

    vias_grande_fluxo['categoria'] = 'vias_grande_fluxo'
    redes_alta_voltagem['categoria'] = 'redes_alta_voltagem'
    industrias['categoria'] = 'industrias'
    matadouros['categoria'] = 'matadouros'
    postos_gasolina['categoria'] = 'postos_gasolina'
    aeroportos['categoria'] = 'aeroportos'
    cemiterios['categoria'] = 'cemiterios'
    depositos_lixo['categoria'] = 'depositos_lixo'


    # ------------------------------------------------------------------
    # Ajuste de CRS antes da união das camadas
    # ------------------------------------------------------------------

    for gdf in [
        redes_alta_voltagem,
        industrias,
        matadouros,
        postos_gasolina,
        aeroportos,
        cemiterios,
        depositos_lixo
    ]:

        if not gdf.empty:
            gdf.to_crs(crs, inplace=True)


    # ------------------------------------------------------------------
    # União de todos os equipamentos em uma única camada
    # ------------------------------------------------------------------

    todos = gpd.GeoDataFrame(
        pd.concat([
            vias_grande_fluxo,
            redes_alta_voltagem,
            industrias,
            matadouros,
            postos_gasolina,
            aeroportos,
            cemiterios,
            depositos_lixo
        ], ignore_index=True),
        crs=crs
    )


    # ------------------------------------------------------------------
    # Conversão para CRS métrico (necessário para buffers)
    # ------------------------------------------------------------------

    todos = todos.to_crs(3857)


    # Salva camada intermediária (depuração)
    todos.to_file(f'./data/resultados/{mun}/geosaude_{mun}.gpkg', driver='GPKG', layer = 'Eqpuipamentos Indesejáveis.gpkg')


    # ------------------------------------------------------------------
    # Geração das zonas de proximidade
    # ------------------------------------------------------------------

    buffer_50m = todos.copy()
    buffer_50m['geometry'] = buffer_50m.buffer(50)

    buffer_100m = todos.copy()
    buffer_100m['geometry'] = buffer_100m.buffer(100)

    buffer_50m_dissolved = buffer_50m.dissolve()
    buffer_100m_dissolved = buffer_100m.dissolve()


    # ------------------------------------------------------------------
    # Classificação das áreas por distância
    # ------------------------------------------------------------------

    import geobr

    #code = obter_codigo(mun, uf)
    place = gpd.read_file(f'./data/resultados/{mun}/setores_{mun}.gpkg', layer='setores_censitarios')

    #place = geobr.read_municipality(
    #    code_muni=code,
    #    year=2010
    #)

    place['score'] = 10

    place = place.to_crs(buffer_100m_dissolved.crs)

    # Áreas fora de influência (>100 m)
    non_affected_area = gpd.overlay(
        place,
        buffer_100m_dissolved,
        how='difference'
    )


    # Áreas até 50 m
    buffer = buffer_50m_dissolved.copy()
    buffer['score'] = 3


    # Áreas entre 50 m e 100 m
    difference = gpd.overlay(
        buffer_100m_dissolved,
        buffer_50m_dissolved,
        how='difference'
    )

    difference['score'] = 5


    # União das classes
    buffer = gpd.GeoDataFrame(
        pd.concat(
            [buffer, difference, non_affected_area],
            ignore_index=True
        )
    )

    buffer = buffer[['geometry', 'score']]


    # ------------------------------------------------------------------
    # Rasterização final
    # ------------------------------------------------------------------

    from utils import criar_raster_padronizado

    criar_raster_padronizado(
        buffer,
        mun,
        uf,
        bbox,
        nome_arquivo=f'C8_EqupInd'
    )
    


# ----------------------------------------------------------------------
# Função auxiliar para download seguro do OSM
# ----------------------------------------------------------------------

import osmnx as ox
import geopandas as gpd


def safe_features_from_place(place, tags, crs='EPSG:4326'):
    """
    Baixa feições do OpenStreetMap usando um polígono e um conjunto de tags.

    Caso nenhuma feição seja encontrada, retorna um GeoDataFrame vazio,
    evitando falhas no processamento.

    Parâmetros
    ----------
    place : shapely.geometry
        Polígono da área de interesse.

    tags : dict
        Tags OSM utilizadas na consulta.

    crs : str
        Sistema de coordenadas do resultado vazio.

    Retorno
    -------
    GeoDataFrame
    """

    try:
        gdf = ox.features_from_polygon(place, tags)

    except ox._errors.InsufficientResponseError:

        print(f"⚠ Nenhuma feição encontrada para tags: {tags}")

        gdf = gpd.GeoDataFrame(
            columns=['geometry'],
            geometry='geometry',
            crs=crs
        )

    return gdf

# C9 - PROXIMIDADE A EQUIPAMENTOS URBANOS DESEJÁVEIS (PUD)

import requests
import pandas as pd
import geopandas as gpd
from shapely.geometry import Point
from utils import obter_codigo


# ---------------------------------------------------------------------
# Centro aproximado do município
# ---------------------------------------------------------------------

from geopy.geocoders import HereV7


def get_municipality_center(municipio, uf, here_api):
    """
    Obtém as coordenadas aproximadas do centro do município
    utilizando a API HERE.

    Parâmetros
    ----------
    municipio : str
    uf : str
    here_api : str

    Retorno
    -------
    tuple (longitude, latitude)
    """

    geolocator = HereV7(apikey=here_api)

    location = geolocator.geocode(
        f"{municipio}, {uf}, Brasil"
    )

    return (
        (location.longitude, location.latitude)
        if location else
        (None, None)
    )


# ---------------------------------------------------------------------
# Critério C9
# ---------------------------------------------------------------------

def equipamentos_desejaveis(mun, uf, bbox, here_api):
    """
    Calcula o critério C9 - Proximidade a Equipamentos Urbanos Desejáveis.

    Equipamentos considerados:

    • UPAs
    • Hospitais
    • CRAS/CREAS
    • Escolas

    Classificação por distância:

        0 – 250 m → score = 10
        250 – 500 m → score = 6

    Parâmetros
    ----------
    mun : str
        Município

    uf : str
        Estado

    bbox : tuple
        Bounding box usada na rasterização

    here_api : str
        Chave da API HERE

    Saída
    -----
    Raster:
        C9_EqupDes.tif
    """

    # ------------------------------------------------------------------
    # Carregamento da grade H3 (não usada diretamente, mas mantida)
    # ------------------------------------------------------------------

    cidade = gpd.read_file(
        f'./data/resultados/{mun}/{mun}_{uf}_h3_grid.gpkg'
    )


    # ------------------------------------------------------------------
    # Centro municipal
    # ------------------------------------------------------------------

    pontos = get_municipality_center(
        mun,
        uf,
        here_api
    )

    code = obter_codigo(mun, uf)


    # ------------------------------------------------------------------
    # Importação do módulo CNES
    # ------------------------------------------------------------------

    from geocnes import geocnes

    execfile('./geocnes.py')


    # ------------------------------------------------------------------
    # UPAs
    # ------------------------------------------------------------------

    if os.path.exists(
        f'./data/resultados/{mun}/cnes_{mun}_{uf}_73.gpkg'
    ):

        upas = gpd.read_file(
            f'./data/resultados/{mun}/cnes_{mun}_{uf}_73.gpkg'
        )

    else:

        upas = geocnes.geocnes(
            mun,
            uf,
            here_api,
            code_un='73'
        )

    if upas is not None and not upas.empty:

        upas['origem'] = 'UPA'

        upas_clean = upas[
            ['CNES', 'Nome_Fantasia', 'geometry']
        ].copy()

        upas_clean.columns = [
            'id_equipamento',
            'nome',
            'geometry'
        ]

        upas_clean['tipo'] = 'UPA'

    else:

        upas_clean = gpd.GeoDataFrame(
            columns=[
                'id_equipamento',
                'nome',
                'geometry',
                'tipo'
            ],
            crs="EPSG:4326"
        )


    # ------------------------------------------------------------------
    # Hospitais
    # ------------------------------------------------------------------

    if os.path.exists(
        f'./data/resultados/{mun}/cnes_{mun}_{uf}_05.gpkg'
    ):

        hospitais = gpd.read_file(
            f'./data/resultados/{mun}/cnes_{mun}_{uf}_05.gpkg'
        )

    else:

        hospitais = geocnes.geocnes(
            mun,
            uf,
            here_api,
            code_un='05'
        )


    if hospitais is not None and not hospitais.empty:

        hospitais['origem'] = 'Hospital'

        hospitais_clean = hospitais[
            ['CNES', 'Nome_Fantasia', 'geometry']
        ].copy()

        hospitais_clean.columns = [
            'id_equipamento',
            'nome',
            'geometry'
        ]

        hospitais_clean['tipo'] = 'Hospital'

    else:

        hospitais_clean = gpd.GeoDataFrame(
            columns=[
                'id_equipamento',
                'nome',
                'geometry',
                'tipo'
            ],
            crs="EPSG:4326"
        )


    # ------------------------------------------------------------------
    # CRAS, CREAS e Escolas
    # ------------------------------------------------------------------

    cras = dados_cras(
        mun,
        uf,
        here_api
    )

    if cras is None or cras.empty:

        cras = gpd.GeoDataFrame(
            columns=[
                'id_equipamento',
                'nome',
                'geometry',
                'tipo'
            ],
            crs=hospitais_clean.crs
        )

    else:

        cras = cras.to_crs(
            hospitais_clean.crs
        )


    # ------------------------------------------------------------------
    # União dos equipamentos
    # ------------------------------------------------------------------

    todos = pd.concat(
        [upas_clean, hospitais_clean, cras],
        ignore_index=True
    )

    todos_simplificado = todos[
        ['nome', 'tipo', 'geometry']
    ]


    # ------------------------------------------------------------------
    # Conversão para CRS métrico
    # ------------------------------------------------------------------

    df = todos_simplificado.to_crs(31983)

    # Camada intermediária (depuração)
    df.to_file(
        'EqpDes.gpkg',
        driver='GPKG'
    )


    # ------------------------------------------------------------------
    # Buffers de proximidade
    # ------------------------------------------------------------------

    buffer_50m = df.copy()
    buffer_50m['geometry'] = buffer_50m.buffer(250)

    buffer_100m = df.copy()
    buffer_100m['geometry'] = buffer_100m.buffer(500)

    buffer_50m_dissolved = buffer_50m.dissolve()
    buffer_100m_dissolved = buffer_100m.dissolve()


    # ------------------------------------------------------------------
    # Classificação por distância
    # ------------------------------------------------------------------

    buffer = buffer_50m_dissolved.copy()
    buffer['score'] = 10

    difference = gpd.overlay(
        buffer_100m_dissolved,
        buffer_50m_dissolved,
        how='difference'
    )

    difference['score'] = 6


    buffer = gpd.GeoDataFrame(
        pd.concat(
            [buffer, difference],
            ignore_index=True
        )
    )


    # ------------------------------------------------------------------
    # Rasterização
    # ------------------------------------------------------------------

    from utils import criar_raster_padronizado

    criar_raster_padronizado(
        buffer,
        mun,
        uf,
        bbox,
        nome_arquivo=f'C9_EqupDes'
    )

    # ---------------------------------------------------------------------
    # Consulta à API do Mapa Social
    # ---------------------------------------------------------------------

import json
from urllib.request import Request, urlopen


def consulta_cras(lat, lon, raio):
    """
    Consulta equipamentos sociais na API do Mapa Social.

    Retorna dados brutos em formato JSON.
    """

    url = (
        'https://mapa-social-api.mds.gov.br/api/v1/minha-localizacao'
        f'?tipos=cras,creas,escolas'
        f'&ponto={lon},{lat}'
        f'&raio={raio}'
    )

    req = Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0",
            "Accept": "application/json",
        },
    )

    with urlopen(req, timeout=15) as resp:

        data = json.load(resp)

        return data

def json_para_df(dados):
    """
    Converte o JSON da API do Mapa Social em DataFrame pandas.
    """

    equipamentos = []

    for tipo in dados.get('equipments', {}).get('docs', []):

        tipo_nome = tipo.get('tipo')

        for item in tipo.get('dados', []):

            equipamentos.append({

                "id_equipamento":
                    item.get("id_equipamento"),

                "nome":
                    item.get("nome"),

                "tipo":
                    tipo_nome,

                "georef_location_p":
                    item.get("georef_location_p"),

                "distancia":
                    item.get("distancia"),

                "municipio":
                    item.get("municipio"),

                "codigo_ibge":
                    item.get("codigo_ibge")
            })

    return pd.DataFrame(equipamentos)

def dados_cras(mun, uf, here_api):
    """
    Obtém CRAS, CREAS e escolas a partir da API do Mapa Social.
    """

    pontos = get_municipality_center(
        mun,
        uf,
        here_api
    )

    lat = pontos[0]
    lon = pontos[1]

    dados = consulta_cras(
        lat,
        lon,
        raio=50
    )

    df = json_para_df(dados)


    # Conversão para geometria
    df['geometry'] = df['georef_location_p'].apply(

        lambda coord:

        Point(
            float(coord.split(',')[1]),
            float(coord.split(',')[0])
        )
    )


    df = gpd.GeoDataFrame(
        df,
        geometry='geometry'
    )

    df = df.set_crs(4326)


    # Filtragem por município
    code = f'{obter_codigo(mun, uf)}'

    df = df[
        df['codigo_ibge'] == code[:-1]
    ]


    escolas = df[
        df['tipo'] == 'ESCOLAS'
    ]

    cras = df[
        (df['tipo'] == 'CRAS')
        | (df['tipo'] == 'CREAS')
    ]


    cras_clean = cras[
        ['id_equipamento', 'nome', 'geometry']
    ].copy()

    cras_clean['tipo'] = cras['tipo']


    escolas_clean = escolas[
        ['id_equipamento', 'nome', 'geometry']
    ].copy()

    escolas_clean['tipo'] = escolas['tipo']


    todos_cras = pd.concat(
        [cras_clean, escolas_clean],
        ignore_index=True
    )


    todos_simplificado = todos_cras[
        ['nome', 'tipo', 'geometry']
    ]


    return todos_simplificado.to_crs(31983)