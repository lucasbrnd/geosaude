import unicodedata  # Normalização de texto (acentos e caracteres especiais)
import geobr        # Acesso a bases geográficas brasileiras


def normalize_text(text):
    """
    Normaliza texto removendo acentos, padronizando encoding e convertendo para minúsculas.

    Args:
        text (str): Texto de entrada

    Returns:
        str: Texto normalizado
    """
    try:
        corrected = text.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        corrected = text

    return unicodedata.normalize('NFKD', corrected).lower().strip()


def obter_codigo(nome_muni, uf_sigla):
    """
    Obtém o código oficial do município (IBGE) a partir do nome.

    Args:
        nome_muni (str): Nome do município
        uf_sigla (str): Sigla do estado (não utilizada diretamente, mantida por compatibilidade)

    Returns:
        int or None: Código IBGE do município ou None se não encontrado
    """

    muni_busca = geobr.lookup_muni(name_muni=nome_muni)

    if muni_busca.empty:
        return None

    # Normalização dos nomes para comparação robusta
    muni_busca['name_muni_normalized'] = muni_busca['name_muni'].apply(normalize_text)

    nome_normalizado = normalize_text(nome_muni)

    filtro = muni_busca[
        muni_busca['name_muni_normalized'] == nome_normalizado
    ]

    return filtro['code_muni'].values[0] if not filtro.empty else None

import requests
import geopandas as gpd
import os
import time
import random


def get_osmpbf(mun, uf, mail):
    """
    Solicita a extração e realiza o download da rede OpenStreetMap (formato PBF)
    para a área de estudo do município.

    A área de extração é definida a partir do arquivo de grade H3 do município,
    com aplicação de buffer de 100 metros.

    Args:
        mun (str): Nome do município
        uf (str): Sigla do estado
        mail (str): E-mail para solicitação de extração BBBike

    Returns:
        bool: True se o download foi realizado com sucesso
    """

    # Caminho do arquivo PBF
    pbf_path = f'./data/resultados/{mun}/network/{mun}_{uf}.osm.pbf'

    # Verifica se o arquivo já existe
    if os.path.exists(pbf_path):
        print("Rede OSM já disponível localmente.")
        return None

    # Leitura da área de estudo (grade H3)
    place = gpd.read_file(
        f'./data/resultados/{mun}/{mun}_{uf}_h3_grid.gpkg'
    )

    # Dissolve para formar um único polígono
    place = place.dissolve()

    # Conversão para CRS métrico
    place = place.to_crs(epsg=3857)

    # Buffer de 100 metros
    place = place.buffer(100)

    # Retorno para WGS84
    place = place.to_crs(epsg=4326)

    # Bounding box da área
    minx, miny, maxx, maxy = place.total_bounds

    # Parâmetros da solicitação BBBike
    base_url = "https://extract.bbbike.org/"

    params = {
        "lang": "en",
        "sw_lng": f'{minx}',
        "sw_lat": f'{miny}',
        "ne_lng": f'{maxx}',
        "ne_lat": f'{maxy}',
        "format": "osm.pbf",
        "city": f'{mun}',
        "email": f'{mail}',

        # Parâmetros aleatórios para evitar cache do servidor
        "as": f'{random.uniform(1, 50):.15f}',
        "pg": f'{random.uniform(1, 2):.15f}',

        "coords": "",
        "oi": "1",
        "layers": "B0000T",
        "submit": "extract",

        # Expiração da solicitação (24h)
        "expire": str(int(time.time()) + 24 * 3600)
    }

    response = requests.get(base_url, params=params)

    response.raise_for_status()

    print("Solicitação de extração enviada:")
    print(response.url)

    # Inicia tentativa de download
    return download_osmpbf(mun, uf, minx, miny, maxx, maxy)

def download_osmpbf(
        mun,
        uf,
        minx,
        miny,
        maxx,
        maxy,
        wait_seconds=20,
        max_attempts=10):
    """
    Realiza o download do arquivo PBF gerado pelo BBBike.

    O sistema tenta acessar o arquivo periodicamente até que esteja disponível.

    Args:
        mun (str): Nome do município
        uf (str): Sigla do estado
        minx (float): Longitude mínima
        miny (float): Latitude mínima
        maxx (float): Longitude máxima
        maxy (float): Latitude máxima
        wait_seconds (int): Intervalo entre tentativas
        max_attempts (int): Número máximo de tentativas

    Returns:
        bool: True se o download foi realizado com sucesso

    Raises:
        TimeoutError: Se o arquivo não ficar disponível
    """

    url = (
        f'https://download.bbbike.org/osm/extract/'
        f'planet_{minx},{miny}_{maxx},{maxy}.osm.pbf'
    )

    os.makedirs(
        f'./data/resultados/{mun}/network/',
        exist_ok=True
    )

    pbf_name = f'./data/resultados/{mun}/network/{mun}_{uf}.osm.pbf'

    for attempt in range(max_attempts):

        resp = requests.get(url, stream=True)

        if (
            resp.status_code == 200 and
            int(resp.headers.get("Content-Length", "0")) > 10000
        ):

            with open(pbf_name, "wb") as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)

            print(f"Download concluído: {pbf_name}")

            return True

        else:
            time.sleep(wait_seconds)

    raise TimeoutError(
        "Arquivo PBF não ficou disponível após todas as tentativas."
    )

def get_elevation(mun, minx, miny, maxx, maxy, apikey=None):
    """
    Realiza o download de dados de elevação (DEM) para a área definida
    pela bounding box do município.

    Os dados são obtidos por meio da biblioteca bmi_topography e armazenados
    em diretório local de cache.

    Args:
        mun (str): Nome do município
        minx (float): Longitude mínima
        miny (float): Latitude mínima
        maxx (float): Longitude máxima
        maxy (float): Latitude máxima
        apikey (str, optional): Chave de API para acesso ao serviço de elevação

    Returns:
        str: Caminho do arquivo DEM baixado
    """

    from bmi_topography import Topography
    from bmi_topography.api_key import ApiKey

    # Parâmetros padrão do Topography
    params = Topography.DEFAULT.copy()

    # Definição da área de download
    params["south"] = miny
    params["north"] = maxy
    params["west"] = minx
    params["east"] = maxx

    # API key
    params["api_key"] = apikey

    # Diretório de armazenamento
    params["cache_dir"] = f'./data/resultados/{mun}/network/'

    # Inicialização e download
    topo = Topography(**params)

    return topo.fetch()

def get_bbox(mun, uf):
    """
    Obtém a bounding box do município com aplicação de buffer de 100 metros.

    A bounding box é calculada a partir do limite municipal oficial (IBGE),
    convertido para CRS métrico para aplicação do buffer.

    Args:
        mun (str): Nome do município
        uf (str): Sigla do estado

    Returns:
        tuple:
            (minx, miny, maxx, maxy) em coordenadas WGS84
    """

    import geobr
    from utils import obter_codigo

    # Código IBGE do município
    code = obter_codigo(mun, uf)

    # Limite municipal
    place = geobr.read_census_tract(
        code_tract=code,
        year=2022,
        zone="urban",
    )

    place = place[place["code_type"]!=2]

    place.to_file(f'./data/resultados/{mun}/setores_{mun}.gpkg', driver = 'GPKG', layer = 'setores_censitarios')


    # Conversão para CRS métrico
    place = place.to_crs(epsg=3857)

    place = place.dissolve()

    # Buffer de 100 metros
    place = place.buffer(100)

    # Bounding box
    bbox = place.total_bounds

    return bbox

def criar_raster_padronizado(gdf, mun, uf, bounds_fixos, nome_arquivo,
                             crs_fixo=3857, resolution=10):
    """
    Cria um raster padronizado a partir de um GeoDataFrame.

    O raster gerado utiliza:
    - Bounding box fixa
    - Sistema de referência fixo
    - Resolução espacial constante

    Esta padronização garante compatibilidade entre os rasters
    gerados para diferentes critérios.

    Args:
        gdf (GeoDataFrame):
            Camada vetorial contendo as geometrias a serem rasterizadas.
            Deve conter a coluna 'score'.

        mun (str):
            Nome do município.

        uf (str):
            Sigla do estado.

        bounds_fixos (list ou tuple):
            Bounding box padrão no formato:
            [minx, miny, maxx, maxy]

        nome_arquivo (str):
            Nome do raster de saída (sem extensão).

        crs_fixo (int, optional):
            EPSG do raster de saída.
            Padrão = 3857.

        resolution (float, optional):
            Resolução espacial do raster em metros.
            Padrão = 10 m.

    Saídas:
        - Arquivo raster (.tif)
        - Camada vetorial armazenada em GeoPackage
    """

    import os
    import rasterio
    from rasterio.features import rasterize
    from rasterio.transform import from_bounds
    import geopandas as gpd
    import numpy as np

    # Diretório de saída do raster
    pasta_raster = f'./data/resultados/{mun}/raster/'
    os.makedirs(pasta_raster, exist_ok=True)

    # Reprojeção para o CRS padrão
    if gdf.crs != crs_fixo:
        gdf = gdf.to_crs(crs_fixo)

    # Dimensões do raster
    width = int((bounds_fixos[2] - bounds_fixos[0]) / resolution)
    height = int((bounds_fixos[3] - bounds_fixos[1]) / resolution)

    # Transformação espacial
    transform = from_bounds(*bounds_fixos,
                            width=width,
                            height=height)

    # -------------------------------------------------
    # CASO ESPECIAL: Critério C6 - Cobertura
    # Raster baseado em contagem de sobreposições
    # -------------------------------------------------

    if nome_arquivo == "C6_Cobertura":
        print ("C6 chamado!!")
        
        # Usa score pré-calculado; fill=10 cobre toda área sem isócrona
        shapes = [
            (geom, value)
            for geom, value in zip(gdf.geometry, gdf['score'])
            if geom is not None and geom.is_valid
        ]

        raster = rasterize(
            shapes,
            out_shape=(height, width),
            transform=transform,
            fill=10,        # ← áreas fora de qualquer isócrona = sem cobertura
            dtype='uint8'
        )

        with rasterio.open(
            f'{pasta_raster}/{nome_arquivo}.tif',
            'w',
            driver='GTiff',
            height=height,
            width=width,
            count=1,
            dtype='uint8',
            crs=gdf.crs,
            transform=transform,
        ) as dst:
            dst.write(raster, 1)

    # -------------------------------------------------
    # CASO GERAL
    # Rasterização baseada na coluna "score"
    # -------------------------------------------------

    else:

        # Preparação das geometrias válidas
        shapes = [
            (geom, value)
            for geom, value in zip(
                gdf.geometry,
                gdf['score']
            )
            if geom is not None and geom.is_valid
        ]

        # Rasterização
        raster = rasterize(
            shapes,
            out_shape=(height, width),
            transform=transform,
            fill=0,          # áreas fora dos polígonos
            dtype='uint8'
        )

        # Salvamento do raster
        with rasterio.open(
            f'{pasta_raster}/{nome_arquivo}.tif',
            'w',
            driver='GTiff',
            height=height,
            width=width,
            count=1,
            dtype='uint8',
            crs=crs_fixo,
            transform=transform
        ) as dst:

            dst.write(raster, 1)

    # -------------------------------------------------
    # Salvamento do vetor utilizado
    # -------------------------------------------------

    os.makedirs(f'./data/resultados/{mun}/',
                exist_ok=True)

    gdf.to_file(
        f'./data/resultados/{mun}/geosaude_{mun}.gpkg',
        layer=nome_arquivo,
        driver='GPKG'
    )

def raster_pre(mun, uf, input_folder, output_folder, reference_raster_name):
    """
    Prepara os rasters para operações matemáticas.

    Esta função realiza duas etapas:

    1) Alinhamento espacial
       Todos os rasters são reprojetados para coincidir com:
       - CRS do raster de referência
       - resolução espacial
       - bounding box
       - matriz de transformação

    2) Combinação dos rasters de eventos naturais (C7)
       Todos os rasters iniciados com "C7" são combinados
       utilizando o valor máximo pixel-a-pixel.

    Args
    ----
    mun : str
        Nome do município

    uf : str
        Sigla do estado

    input_folder : str
        Pasta contendo os rasters de entrada

    output_folder : str
        Pasta onde os rasters alinhados serão salvos

    reference_raster_name : str
        Nome do raster utilizado como referência espacial

    Saídas
    ------
    Rasters alinhados:
        ./output_folder/

    Raster combinado:
        ./data/resultados/{mun}/raster/Critérios/C7_EventNat.tif
    """

    import rasterio
    from rasterio.warp import reproject
    from rasterio.enums import Resampling
    import numpy as np
    import os
    import glob

    # -------------------------------------------------
    # Criar pasta de saída
    # -------------------------------------------------

    os.makedirs(output_folder, exist_ok=True)

    # -------------------------------------------------
    # Raster de referência
    # -------------------------------------------------

    reference_path = os.path.join(
        input_folder,
        reference_raster_name
    )

    with rasterio.open(reference_path) as ref:

        ref_profile = ref.profile.copy()
        ref_crs = ref.crs
        ref_transform = ref.transform
        ref_shape = ref.shape
        ref_bounds = ref.bounds

    # -------------------------------------------------
    # Lista de rasters de entrada
    # -------------------------------------------------

    raster_files = [
        f for f in os.listdir(input_folder)
        if f.endswith(('.tif', '.tiff'))
    ]

    # -------------------------------------------------
    # Alinhamento espacial
    # -------------------------------------------------

    for raster_file in raster_files:

        input_path = os.path.join(
            input_folder,
            raster_file
        )

        output_path = os.path.join(
            output_folder,
            raster_file
        )

        with rasterio.open(input_path) as src:

            # Verifica se já está alinhado
            if (src.crs == ref_crs and
                src.shape == ref_shape and
                np.allclose(
                    src.transform,
                    ref_transform,
                    atol=1e-6
                )):

                # Copia direto
                with rasterio.open(
                        output_path,
                        'w',
                        **ref_profile) as dst:

                    dst.write(src.read(1), 1)

                continue

            # Dados de entrada
            src_data = src.read(1)
            src_profile = src.profile

            # Array destino
            destination = np.zeros(
                ref_shape,
                dtype=src_data.dtype
            )

            # Reprojeção
            reproject(
                source=src_data,
                destination=destination,
                src_transform=src.transform,
                src_crs=src.crs,
                dst_transform=ref_transform,
                dst_crs=ref_crs,
                resampling=Resampling.nearest,
                num_threads=2
            )

            # Perfil de saída
            output_profile = ref_profile.copy()

            output_profile.update({
                'dtype': destination.dtype,
                'nodata': src_profile.get('nodata', None)
            })

            # Escrita do raster
            with rasterio.open(
                    output_path,
                    'w',
                    **output_profile) as dst:

                dst.write(destination, 1)

    # =================================================
    # COMBINAÇÃO DOS EVENTOS NATURAIS (C7)
    # =================================================

    directory = f'./data/resultados/{mun}/raster/Critérios/'

    output_file = (
        f'./data/resultados/{mun}/raster/Critérios/'
        f'C7_EventNat.tif'
    )

    # Lista rasters C7
    tif_files = sorted(
        glob.glob(
            os.path.join(directory, "C7*.tif")
        )
    )

    # Raster inicial
    with rasterio.open(tif_files[0]) as src:

        meta = src.meta.copy()
        data = src.read(1)

    # Máximo pixel-a-pixel
    for tif in tif_files[1:]:

        with rasterio.open(tif) as src:

            new_data = src.read(1)

            data = np.maximum(
                data,
                new_data
            )

    # Reclassificação do fundo

    data[data == 0] = 10

    # Escrita do raster final

    with rasterio.open(
            output_file,
            'w',
            **meta) as dst:

        dst.write(data, 1)

    print(f"Raster combinado salvo em: {output_file}")

import rasterio
import numpy as np
import os


def soma_ponderada_tif(pasta, pesos):
    """
    Calcula a soma ponderada de rasters GeoTIFF.

    Cada raster informado recebe um peso definido pelo usuário.
    O resultado corresponde à soma pixel-a-pixel dos rasters ponderados.

    Args
    ----
    pasta : str
        Caminho da pasta contendo os arquivos TIFF.

    pesos : dict
        Dicionário no formato:
        {
            "arquivo.tif": peso,
            ...
        }

    Returns
    -------
    resultado : numpy.ndarray
        Array com o resultado da soma ponderada.

    metadata : dict
        Metadados do raster de referência.

    arquivos_processados : list
        Lista de arquivos utilizados na soma ponderada.
    """

    # -------------------------------------------------
    # Verificação da pasta de entrada
    # -------------------------------------------------

    if not os.path.exists(pasta):
        raise ValueError(
            f"A pasta '{pasta}' não existe"
        )

    resultado = None
    metadata = None

    arquivos_processados = []
    arquivos_nao_encontrados = []

    # -------------------------------------------------
    # Processamento dos rasters
    # -------------------------------------------------

    for arquivo, peso in pesos.items():

        caminho_arquivo = os.path.join(
            pasta,
            arquivo
        )

        if os.path.exists(caminho_arquivo):

            print(
                f"Processando raster: "
                f"{arquivo} (peso = {peso})"
            )

            with rasterio.open(caminho_arquivo) as src:

                # Leitura da banda única
                dados = src.read(1)

                # Substitui valores NaN por zero
                dados = np.nan_to_num(dados)

                # Aplicação do peso
                dados_ponderados = dados * peso

                # Inicialização do resultado
                if resultado is None:

                    resultado = dados_ponderados
                    metadata = src.meta.copy()

                else:

                    # Verificação de compatibilidade
                    if dados_ponderados.shape != resultado.shape:

                        print(
                            f"Aviso: dimensões "
                            f"incompatíveis em {arquivo}"
                        )

                        continue

                    resultado += dados_ponderados

                arquivos_processados.append(
                    arquivo
                )

        else:

            arquivos_nao_encontrados.append(
                arquivo
            )

            print(
                f"Aviso: arquivo não encontrado "
                f"- {arquivo}"
            )

    # -------------------------------------------------
    # Verificação final
    # -------------------------------------------------

    if resultado is None:

        raise ValueError(
            "Nenhum raster válido foi encontrado "
            "para processamento"
        )

    # -------------------------------------------------
    # Relatório de execução
    # -------------------------------------------------

    print(
        f"\nRasters processados: "
        f"{len(arquivos_processados)}"
    )

    print(
        f"Rasters não encontrados: "
        f"{len(arquivos_nao_encontrados)}"
    )

    if arquivos_nao_encontrados:

        print(
            "Arquivos ausentes:",
            arquivos_nao_encontrados
        )

    return resultado, metadata, arquivos_processados


def salvar_resultado(
        resultado,
        metadata,
        pasta_saida,
        nome_arquivo="Analise_ViabilidadeFinal.tif"):
    """
    Salva o raster resultante da soma ponderada.

    Args
    ----
    resultado : numpy.ndarray
        Array contendo o resultado final.

    metadata : dict
        Metadados do raster de referência.

    pasta_saida : str
        Pasta onde o raster será salvo.

    nome_arquivo : str, opcional
        Nome do arquivo de saída.

    Returns
    -------
    str
        Caminho completo do arquivo gerado.
    """

    # -------------------------------------------------
    # Atualização dos metadados
    # -------------------------------------------------

    metadata.update({

        'dtype': resultado.dtype,
        'count': 1,
        'nodata': None

    })

    caminho_saida = os.path.join(
        pasta_saida,
        nome_arquivo
    )

    # -------------------------------------------------
    # Escrita do raster
    # -------------------------------------------------

    with rasterio.open(
            caminho_saida,
            'w',
            **metadata) as dst:

        dst.write(resultado, 1)

    print(
        f"Raster final salvo em: "
        f"{caminho_saida}"
    )

    return caminho_saida

def calculadora_raster(mun, uf):
    """
    Executa o processamento final dos rasters de critérios e
    calcula o índice composto por soma ponderada.

    Etapas realizadas:
        1. Alinhamento espacial dos rasters
        2. Organização na pasta de critérios
        3. Aplicação dos pesos
        4. Soma ponderada
        5. Geração do raster final

    Args
    ----
    mun : str
        Nome do município.

    uf : str
        Sigla do estado.

    Saída
    -----
    Raster final salvo em:

    ./data/resultados/{mun}/raster/Critérios/
    """

    # -------------------------------------------------
    # Definição de diretórios
    # -------------------------------------------------

    pasta_rasters = f'./data/resultados/{mun}/raster/'

    pasta_criterios = (
        f'./data/resultados/{mun}/raster/Critérios/'
    )

    # -------------------------------------------------
    # Etapa 1 — Alinhamento espacial dos rasters
    # -------------------------------------------------
    # Utiliza o raster C1 como referência espacial

    raster_pre(
        mun,
        uf,
        pasta_rasters,
        pasta_criterios,
        'C1_VulnSoc.tif'
    )

    import os

    os.makedirs(
        pasta_criterios,
        exist_ok=True
    )

    # -------------------------------------------------
    # Etapa 2 — Definição dos pesos
    # -------------------------------------------------

    pesos = {

        'C1_VulnSoc.tif': 1.529812,

        'C2_DistDemog.tif': 1.589030,

        'C3_DistRenda.tif': 0.908855,

        'C4_TempoMin.tif': 1.276164,

        'C5_NivAcess.tif': 1.407427,

        'C6_Cobertura.tif': 0.912221,

        'C7_EventNat.tif': 0.720175,

        'C8_EqupInd.tif': 0.671116,

        'C9_EqupDes.tif': 0.985199

    }

    # -------------------------------------------------
    # Etapa 3 — Soma ponderada
    # -------------------------------------------------

    try:

        resultado, metadata, arquivos_processados = (
            soma_ponderada_tif(
                pasta_criterios,
                pesos
            )
        )

        # -------------------------------------------------
        # Etapa 4 — Salvamento do raster final
        # -------------------------------------------------

        caminho_resultado = salvar_resultado(

            resultado,
            metadata,
            pasta_criterios

        )

        print(
            "\nProcessamento concluído com sucesso."
        )

        print(
            f"Raster final gerado em:\n"
            f"{caminho_resultado}"
        )

    except Exception as e:

        print(
            "Erro durante o processamento:"
        )

        print(e)

from geopy.geocoders import HereV7
from geopy.extra.rate_limiter import RateLimiter

import h3
import geopandas as gpd
from shapely.geometry import Point
import os

def bbox_urb (mun,setores):
    area_urb = setores[setores["CD_SIT"].isin(["1", "2"])].copy()
    area_urb = area_urb.dissolve()
    area_urb = area_urb.reset_index()
    area_urb = area_urb.explode(index_parts=False)
    area_urb = area_urb.reset_index (drop=True)
    area_urb = area_urb.to_crs(epsg=3857)
    area_urb ["area"] = area_urb.geometry.area
    area_urb = area_urb.loc[area_urb["area"].idxmax()]
    minx, miny, maxx, maxy = area_urb.geometry.bounds    
    bbox_path = f"./data/resultados/{mun}/bbox_urb.txt"
    with open(bbox_path, "w") as f:
        f.write(f"{minx},{miny},{maxx},{maxy}")
    print('bbox salva')


def top_cells(mun, uf, here_api):
    """
    Identifica as áreas com maior viabilidade territorial e gera
    pontos representativos com estatísticas agregadas.

    Etapas:
        1. Seleção das células com população > 0
        2. Seleção das 10 células com maior viabilidade
        3. Agrupamento de células vizinhas (H3)
        4. Cálculo de estatísticas por grupo
        5. Geocodificação reversa (HERE API)
        6. Geração de pontos representativos

    Args
    ----
    mun : str
        Nome do município

    uf : str
        Sigla do estado

    here_api : str
        Chave da HERE API para geocodificação reversa

    Saída
    -----
    ./data/resultados/{mun}/report/top_suitability.gpkg
    """

    # -------------------------------------------------
    # Leitura da grade H3 com resultados
    # -------------------------------------------------

    gdf = gpd.read_file(
        f'./data/resultados/{mun}/{mun}_grid_viabilidade.gpkg'
    )

    gdf_filtrado = gdf[gdf['pop_total'] > 0]

    gdf_filtrado = gdf_filtrado.to_crs(4326)

    # -------------------------------------------------
    # Seleção das células mais viáveis
    # -------------------------------------------------

    top_cells = gdf_filtrado.nlargest(
        10,
        'Analise_ViabilidadeFinal'
    ).reset_index(drop=True)

    top_cells['endereco'] = None

    # -------------------------------------------------
    # Inicialização da HERE API
    # -------------------------------------------------

    geolocator = HereV7(apikey=here_api)

    reverse_geocode = RateLimiter(

        geolocator.reverse,

        min_delay_seconds=0.1,

        return_value_on_exception=None

    )

    # -------------------------------------------------
    # Funções auxiliares H3
    # -------------------------------------------------

    def encontrar_vizinhos_h3(celula_base, todas_celulas, distancia=1):
        """
        Retorna células H3 vizinhas dentro da distância especificada
        """
        vizinhos = h3.grid_ring(celula_base, distancia)

        return [

            cel for cel in todas_celulas

            if cel in vizinhos

        ]


    def agrupar_celulas_conectadas(celulas):
        """
        Agrupa células H3 conectadas entre si
        """

        grupos = []

        visitadas = set()

        for celula in celulas:

            if celula in visitadas:

                continue

            grupo = set()

            pilha = [celula]

            while pilha:

                atual = pilha.pop()

                if atual in visitadas:

                    continue

                visitadas.add(atual)

                grupo.add(atual)

                vizinhos = encontrar_vizinhos_h3(

                    atual,

                    [

                        c for c in celulas

                        if c not in visitadas

                    ]

                )

                pilha.extend(vizinhos)

            grupos.append(list(grupo))

        return grupos

    # -------------------------------------------------
    # Agrupamento espacial das células
    # -------------------------------------------------

    celulas_h3 = top_cells['h3_polyfill'].tolist()

    grupos_celulas = agrupar_celulas_conectadas(celulas_h3)

    dados_grupos = []

    colunas_C7 = [

        col for col in top_cells.columns

        if col.startswith('C7_')

    ]

    # -------------------------------------------------
    # Processamento dos grupos
    # -------------------------------------------------

    for i, grupo in enumerate(grupos_celulas):

        celulas_grupo = top_cells[
            top_cells['h3_polyfill'].isin(grupo)
        ]

        # Centroide médio do grupo

        centroids = [

            cell.geometry.centroid

            for _, cell in celulas_grupo.iterrows()

        ]

        avg_lat = sum(c.y for c in centroids) / len(centroids)

        avg_lng = sum(c.x for c in centroids) / len(centroids)

        # Estatísticas principais

        populacao_total = celulas_grupo['pop_total'].sum()

        renda_sm_media = celulas_grupo['renda_sm'].mean()

        viabilidade_media = celulas_grupo[
            'Analise_ViabilidadeFinal'
        ].mean()

        viabilidade_max = celulas_grupo[
            'Analise_ViabilidadeFinal'
        ].max()

        # Estatísticas critérios

        C1_VulnSoc_media = celulas_grupo['C1_VulnSoc'].mean()

        C2_DistDemog_media = celulas_grupo['C2_DistDemog'].mean()

        C3_DistRenda_media = celulas_grupo['C3_DistRenda'].mean()

        C4_TempoMin_media = celulas_grupo['C4_TempoMin'].mean()

        C4_TempoMin_max = celulas_grupo['C4_TempoMin'].max()

        C5_NivAcess_media = celulas_grupo['C5_NivAcess'].mean()

        C5_NivAcess_max = celulas_grupo['C5_NivAcess'].max()

        C6_Cobertura_media = celulas_grupo['C6_Cobertura'].mean()

        C8_EqupInd_media = celulas_grupo['C8_EqupInd'].mean()

        C9_EqupDes_media = celulas_grupo['C9_EqupDes'].mean()

        # Estatísticas eventos naturais

        C7_stats = {}

        for coluna in colunas_C7:

            C7_stats[f"{coluna}_media"] = (

                celulas_grupo[coluna].mean()

            )

            C7_stats[f"{coluna}_min"] = (

                celulas_grupo[coluna].min()

            )

        # -------------------------------------------------
        # Geocodificação reversa
        # -------------------------------------------------

        endereco = None

        try:

            location = reverse_geocode(

                (avg_lat, avg_lng)

            )

            if location:

                endereco = location.address

            else:

                endereco = "Endereço não identificado"

        except Exception as e:

            endereco = f"Erro na geocodificação: {e}"

        # -------------------------------------------------
        # Registro do endereço
        # -------------------------------------------------

        for celula in grupo:

            idx = top_cells[
                top_cells['h3_polyfill'] == celula
            ].index

            if not idx.empty:

                top_cells.at[idx[0], 'endereco'] = endereco

        # -------------------------------------------------
        # Estrutura final do grupo
        # -------------------------------------------------

        grupo_data = {

            'grupo_id': i + 1,

            'num_celulas': len(grupo),

            'celulas_h3': grupo,

            'pop_total': populacao_total,

            'renda_sm_media': renda_sm_media,

            'Analise_ViabilidadeFinal_media': viabilidade_media,

            'Analise_ViabilidadeFinal_max': viabilidade_max,

            'C1_VulnSoc_media': C1_VulnSoc_media,

            'C2_DistDemog_media': C2_DistDemog_media,

            'C3_DistRenda_media': C3_DistRenda_media,

            'C4_TempoMin_media': C4_TempoMin_media,

            'C4_TempoMin_max': C4_TempoMin_max,

            'C5_NivAcess_media': C5_NivAcess_media,

            'C5_NivAcess_max': C5_NivAcess_max,

            'C6_Cobertura_media': C6_Cobertura_media,

            'C8_EqupInd_media': C8_EqupInd_media,

            'C9_EqupDes_media': C9_EqupDes_media,

            'endereco': endereco,

            'latitude': avg_lat,

            'longitude': avg_lng,

            'geometry': Point(avg_lng, avg_lat)

        }

        grupo_data.update(C7_stats)

        dados_grupos.append(grupo_data)

    # -------------------------------------------------
    # Geração do GeoDataFrame final
    # -------------------------------------------------

    gdf_grupos_pontos = gpd.GeoDataFrame(

        dados_grupos,

        crs="EPSG:4326"

    )

    os.makedirs(

        f'./data/resultados/{mun}/report/',

        exist_ok=True

    )

    caminho_saida = (

        f'./data/resultados/{mun}/report/'

        f'top_suitability.gpkg'

    )

    gdf_grupos_pontos.to_file(

        caminho_saida,

        driver='GPKG'

    )

    print("\nRelatório de áreas prioritárias gerado:")

    print(caminho_saida)

def agregar_resultados(mun, uf):
    """
    Agrega valores dos rasters de critérios para a grade H3
    utilizando estatística zonal.

    Processo:
        Raster → Estatística zonal → Grade H3

    Estatísticas utilizadas:

        C1–C6, C8, C9 → média
        C7_*          → mínimo (pior condição)
        Viabilidade   → máximo (melhor condição)

    Args
    ----

    mun : str
        Nome do município

    uf : str
        Sigla do estado

    Returns
    -------

    GeoDataFrame
        Grade H3 com valores agregados

    Saída
    -----

    ./data/resultados/{mun}/{mun}_grid_viabilidade.gpkg
    """

    import geopandas as gpd
    from rasterstats import zonal_stats
    import os

    # -------------------------------------------------
    # Leitura da grade H3
    # -------------------------------------------------

    grid = gpd.read_file(
        f'./data/resultados/{mun}/{mun}_{uf}_h3_grid.gpkg'
    )

    grid = grid.to_crs('EPSG:3857')

    # -------------------------------------------------
    # Lista de rasters de critérios
    # -------------------------------------------------

    pasta_raster = (
        f'./data/resultados/{mun}/raster/Critérios/'
    )

    arquivos_raster = [

        os.path.join(pasta_raster, f)

        for f in os.listdir(pasta_raster)

        if f.endswith('.tif')

    ]

    print("\nNúmero de rasters encontrados:")

    print(len(arquivos_raster))

    # -------------------------------------------------
    # Estatísticas zonais
    # -------------------------------------------------

    for raster_path in arquivos_raster:

        try:

            nome_arquivo = os.path.basename(raster_path)

            nome_coluna = os.path.splitext(nome_arquivo)[0]

            # Definição do tipo de estatística

            if nome_arquivo.startswith('C7'):

                stats_type = 'min'

                stats_list = ['min']

                print(f"Calculando mínimo → {nome_arquivo}")

            elif nome_arquivo == 'Analise_ViabilidadeFinal.tif':

                stats_type = 'max'

                stats_list = ['max']

                print(f"Calculando máximo → {nome_arquivo}")

            else:

                stats_type = 'mean'

                stats_list = ['mean']

                print(f"Calculando média → {nome_arquivo}")

            # Estatística zonal

            stats = zonal_stats(

                grid,

                raster_path,

                stats=stats_list,

                geojson_out=False,

                nodata=0

            )

            # Inserção dos valores no grid

            if stats_type == 'min':

                grid[nome_coluna] = [

                    s['min'] for s in stats

                ]

            elif stats_type == 'max':

                grid[nome_coluna] = [

                    s['max'] for s in stats

                ]

            else:

                grid[nome_coluna] = [

                    s['mean'] for s in stats

                ]

            print(

                f"Estatísticas concluídas: "

                f"{nome_coluna} ({stats_type})"

            )

        except Exception as e:

            print(

                f"Erro ao processar "

                f"{raster_path}: {e}"

            )

    # -------------------------------------------------
    # Limpeza de atributos auxiliares
    # -------------------------------------------------

    grid_gpd = gpd.GeoDataFrame(grid)

    colunas_remover = [

        'index',

        'renda',

        'renda/dom',

        'count',

        'renda_pond',

        'pop_class',

        'pop_class_label',

        'score'

    ]

    colunas_existentes = [

        c for c in colunas_remover

        if c in grid_gpd.columns

    ]

    grid_layers = grid_gpd.drop(

        columns=colunas_existentes

    )

    # -------------------------------------------------
    # Salvamento
    # -------------------------------------------------

    caminho_saida = (

        f'./data/resultados/{mun}/'

        f'{mun}_grid_viabilidade.gpkg'

    )

    grid_layers.to_file(

        caminho_saida,

        driver='GPKG'

    )

    print("\nGrade H3 atualizada:")

    print(caminho_saida)

    #return grid_layers