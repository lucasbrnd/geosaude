# report.py

import os
import logging
from datetime import datetime
from pathlib import Path

import contextily as ctx

import numpy as np
import matplotlib
matplotlib.use("Agg")  # backend sem interface gráfica
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
from matplotlib.patches import Patch
import matplotlib.ticker as mticker
import rasterio
from rasterio.plot import show
import geopandas as gpd
from PIL import Image as PILImage
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_JUSTIFY
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Image,
    PageBreak, Table, TableStyle, HRFlowable
)

logger = logging.getLogger("geosaude")


# ---------------------------------------------------------
# Configuração dos critérios
# ---------------------------------------------------------

CRITERIOS = [
    {
        "codigo":   "C1",
        "arquivo":  "C1_VulnSoc.tif",
        "titulo":   "C1 — Vulnerabilidade Social",
        "descricao": (
            "Identifica as áreas com maior concentração de população "
            "em situação de vulnerabilidade socioeconômica, com base "
            "no Índice de Vulnerabilidade Social (IVS) do IPEA e no "
            "Índice Paulista de Vulnerabilidade Social (IPVS) da SEADE. "
            "Scores mais altos indicam maior vulnerabilidade e, portanto, "
            "maior prioridade para implantação de novas unidades."
        ),
        "cmap":     "YlOrRd",
        "labels":   {1: "Muito Baixa", 3: "Baixa", 5: "Média",
                     8: "Alta", 10: "Muito Alta"},
    },
    {
        "codigo":   "C2",
        "arquivo":  "C2_DistDemog.tif",
        "titulo":   "C2 — Distribuição Demográfica",
        "descricao": (
            "Mapeia a concentração populacional absoluta no território, "
            "distribuída em malha hexagonal H3. Áreas mais adensadas "
            "recebem scores mais altos, indicando maior demanda potencial "
            "por serviços de saúde."
        ),
        "cmap":     "Blues",
        "labels":   {1: "Muito Baixa", 3: "Baixa", 5: "Média",
                     8: "Alta", 10: "Muito Alta"},
    },
    {
        "codigo":   "C3",
        "arquivo":  "C3_DistRenda.tif",
        "titulo":   "C3 — Distribuição de Renda",
        "descricao": (
            "Representa a renda média do responsável pelo domicílio, "
            "obtida do Censo Demográfico 2022 (IBGE). Áreas de menor renda "
            "recebem scores mais altos, pois indicam maior dependência "
            "do sistema público de saúde."
        ),
        "cmap":     "RdYlGn_r",
        "labels":   {1: "> 10 SM", 2: "5–10 SM", 5: "3–5 SM",
                     8: "2–3 SM", 10: "0–2 SM"},
    },
    {
        "codigo":   "C4",
        "arquivo":  "C4_TempoMin.tif",
        "titulo":   "C4 — Custo Mínimo de Deslocamento",
        "descricao": (
            "Representa o tempo de caminhada até a unidade de APS mais "
            "próxima. Áreas com maiores tempos de deslocamento recebem "
            "scores mais altos, indicando necessidade prioritária de "
            "novas unidades."
        ),
        "cmap":     "RdYlGn_r",
        "labels":   {1: "< 15 min", 2: "15–30 min", 6: "30–45 min",
                     8: "45–60 min", 10: "> 60 min"},
    },
    {
        "codigo":   "C5",
        "arquivo":  "C5_NivAcess.tif",
        "titulo":   "C5 — Índice de Acessibilidade (2SFCA)",
        "descricao": (
            "Mensura a acessibilidade considerando a relação entre oferta "
            "e demanda, calculada pelo método Two-Step Floating Catchment "
            "Area (2SFCA) gaussiano. Scores altos indicam baixo nível "
            "de acesso, sinalizando áreas prioritárias."
        ),
        "cmap":     "RdYlGn_r",
        "labels":   {1: "Muito Alto", 2: "Alto", 5: "Médio",
                     8: "Baixo", 10: "Muito Baixo"},
    },
    {
        "codigo":   "C6",
        "arquivo":  "C6_Cobertura.tif",
        "titulo":   "C6 — Cobertura Espacial das Unidades",
        "descricao": (
            "Analisa a sobreposição das áreas de cobertura das unidades "
            "de APS existentes (raio de 1.000 m). Áreas sem cobertura "
            "recebem score máximo; áreas com múltipla cobertura recebem "
            "scores baixos."
        ),
        "cmap":     "RdYlGn_r",
        "labels":   {1: "> 3 unidades", 2: "3 unidades", 3: "2 unidades",
                     4: "1 unidade", 10: "Sem cobertura"},
    },
    {
        "codigo":   "C7",
        "arquivo":  "C7_EventNat.tif",
        "titulo":   "C7 — Risco de Eventos Naturais",
        "descricao": (
            "Mapeia a suscetibilidade a desastres naturais (inundações e "
            "movimentos de massa), com base nos dados do Serviço Geológico "
            "Brasileiro (SGB). Scores mais altos indicam maior risco e, "
            "portanto, menor viabilidade para implantação."
        ),
        "cmap":     "YlOrRd_r",
        "labels":   {1: "Risco Alto", 5: "Risco Médio", 10: "Sem risco / N.D."},
    },
    {
        "codigo":   "C8",
        "arquivo":  "C8_EqupInd.tif",
        "titulo":   "C8 — Equipamentos Urbanos Indesejáveis",
        "descricao": (
            "Identifica a proximidade a equipamentos incompatíveis com "
            "a operação de unidades de APS (cemitérios, aeroportos, "
            "depósitos de lixo, vias de grande tráfego, entre outros), "
            "conforme Diretrizes do Ministério da Saúde (2014)."
        ),
        "cmap":     "YlOrRd_r",
        "labels":   {10: "Sem influência", 5: "Zona de influência",
                     3: "Área crítica"},
    },
    {
        "codigo":   "C9",
        "arquivo":  "C9_EqupDes.tif",
        "titulo":   "C9 — Equipamentos Urbanos Desejáveis",
        "descricao": (
            "Avalia a proximidade a equipamentos que potencializam a "
            "operação de unidades de APS (hospitais, UPAs, CRAS, CREAS "
            "e escolas). Áreas próximas a esses equipamentos recebem "
            "scores mais altos."
        ),
        "cmap":     "YlGn",
        "labels":   {1: "Sem influência", 6: "Zona de influência",
                     10: "Área próxima"},
    },
    {
        "codigo":   "VF",
        "arquivo":  "Analise_ViabilidadeFinal.tif",
        "titulo":   "Viabilidade Espacial Final",
        "descricao": (
            "Resultado da combinação ponderada dos nove critérios, "
            "com pesos definidos por 34 especialistas via análise "
            "multicritério pareada. Representa o índice composto de "
            "viabilidade para implantação de novas unidades de APS, "
            "variando de 0 (menor viabilidade) a 100 (maior viabilidade)."
        ),
        "cmap":     "RdYlGn",
        "labels":   {0: "Viabilidade muito baixa", 20: "Viabilidade baixa",
                     40: "Viabilidade média", 60: "Viabilidade alta",
                     80: "Viabilidade muito alta"},
    },
]

PESOS = {
    "C1": 1.529812,
    "C2": 1.589030,
    "C3": 0.908855,
    "C4": 1.276164,
    "C5": 1.407427,
    "C6": 0.912221,
    "C7": 0.720175,
    "C8": 0.671116,
    "C9": 0.985199,
}

def carregar_unidades_aps(mun: str, uf: str) -> gpd.GeoDataFrame | None:
    """
    Carrega as unidades de APS existentes do município a partir do GPKG do CNES.

    Retorno
    -------
    GeoDataFrame ou None
    """
    gpkg_aps = Path(f"./data/resultados/{mun}/cnes_{mun}_{uf}_02.gpkg")

    if not gpkg_aps.exists():
        logger.warning(f"GPKG de unidades APS não encontrado: {gpkg_aps}")
        return None

    try:
        gdf = gpd.read_file(str(gpkg_aps))
        if gdf.crs is None:
            gdf = gdf.set_crs("EPSG:4326")
        logger.info(f"Unidades APS carregadas: {len(gdf)} registros")
        return gdf
    except Exception as e:
        logger.warning(f"Erro ao carregar unidades APS: {e}")
        return None

# ---------------------------------------------------------
# Renderização dos mapas temáticos
# ---------------------------------------------------------

def renderizar_mapa(
    raster_path: str,
    base_dir: str,
    criterio: dict,
    limite_mun: gpd.GeoDataFrame,
    output_path: str,
    figsize: tuple = (10, 8),
    unidades_aps: gpd.GeoDataFrame = None
) -> str:

    from matplotlib.lines import Line2D

    with rasterio.open(raster_path) as src:
        data = src.read(1).astype(float)
        data[data == 0] = np.nan
        crs_raster = src.crs
        extent = [
            src.bounds.left, src.bounds.right,
            src.bounds.bottom, src.bounds.top
        ]
####
    from pyproj import Transformer

    # --- Bounding box urbana ---
    bbox_file = base_dir / "bbox_urb.txt"
    
    bbox_urb = None
    if os.path.exists(bbox_file):
        try:
            with open(bbox_file, "r") as f:
                minx, miny, maxx, maxy = map(float, f.read().strip().split(","))
    
            # bbox está em EPSG:3857 → converter para CRS do raster se necessário
            if crs_raster.to_string() != "EPSG:3857":
                transformer = Transformer.from_crs("EPSG:3857", crs_raster, always_xy=True)
                minx, miny = transformer.transform(minx, miny)
                maxx, maxy = transformer.transform(maxx, maxy)
    
            bbox_urb = (minx, miny, maxx, maxy)
    
        except Exception as e:
            logger.warning(f"Erro ao ler bbox urbana: {e}")
#####
    fig, ax = plt.subplots(figsize=figsize, dpi=120)
    
    # --- Definir limites do mapa ANTES do basemap ---
    if bbox_urb is not None:
        minx, miny, maxx, maxy = bbox_urb
        ax.set_xlim(minx, maxx)
        ax.set_ylim(miny, maxy)
    else:
        ax.set_xlim(extent[0], extent[1])
        ax.set_ylim(extent[2], extent[3])

    import contextily as ctx
    # --- Basemap ---
    try:
        ctx.add_basemap(
            ax,
            crs=crs_raster,
            source=ctx.providers.OpenStreetMap.Mapnik,  # leve e bom para fundo
            attribution_size = 2,
            #zoom = 20,
        )
    except Exception as e:
        logger.warning(f"Erro ao adicionar basemap: {e}")

    # Acumulador de handles para a legenda — construído ao longo da função
    handles_legenda = []

    # --- Raster temático ---
    if criterio["labels"] is None:

        vmin = np.nanpercentile(data, 2)
        vmax = np.nanpercentile(data, 98)
        im = ax.imshow(
            data, cmap=criterio["cmap"],
            vmin=vmin, vmax=vmax,
            extent=extent, origin="upper",
            interpolation="nearest",
            alpha = 0.75
        )
        cbar = fig.colorbar(im, ax=ax, fraction=0.035, pad=0.02)
        cbar.set_label("Índice de Viabilidade", fontsize=9)
        cbar.ax.tick_params(labelsize=8)
        # Escala contínua não usa patches na legenda

    else:

        valores   = sorted(criterio["labels"].keys())
        n         = len(valores)
        cmap_base = plt.get_cmap(criterio["cmap"], n)
        bounds    = [v - 0.5 for v in valores] + [valores[-1] + 0.5]
        norm      = mcolors.BoundaryNorm(bounds, cmap_base.N)

        ax.imshow(
            data, cmap=cmap_base, norm=norm,
            extent=extent, origin="upper",
            interpolation="nearest",
            alpha = 0.75
        )
        
        # --- Aplicar recorte pela bbox urbana ---
        if bbox_urb is not None:
            minx, miny, maxx, maxy = bbox_urb
            ax.set_xlim(minx, maxx)
            ax.set_ylim(miny, maxy)
            
        # Patches do raster adicionados ao acumulador
        for i, v in enumerate(valores):
            handles_legenda.append(
                Patch(
                    color=cmap_base(i / max(n - 1, 1)),
                    label=f"{v}  —  {criterio['labels'][v]}"
                )
            )

    # --- Limite municipal ---
    if limite_mun is not None:
        limite_mun.to_crs(crs_raster).boundary.plot(
            ax=ax, edgecolor="#1a1814",
            linewidth=1.2, zorder=5
        )

    # --- Unidades APS existentes ---
    if unidades_aps is not None and not unidades_aps.empty:
        try:
            aps_proj = unidades_aps.to_crs(crs_raster)

            # Círculo externo branco
            aps_proj.plot(
                ax=ax,
                color="white",
                edgecolor="black",
                markersize=4,
                marker="o",
                linewidth=0.8,
                zorder=6
            )
            # Ponto interno preto
            aps_proj.plot(
                ax=ax,
                color="black",
                markersize=2,
                marker="o",
                zorder=7
            )

            # Handle para a legenda — adicionado ao acumulador
            handles_legenda.append(
                Line2D(
                    [0], [0],
                    marker="o",
                    color="w",
                    markerfacecolor="black",
                    markeredgecolor="black",
                    markeredgewidth=0.6,
                    markersize=5,
                    label="Unidades APS existentes"
                )
            )

        except Exception as e:
            logger.warning(f"Erro ao plotar unidades APS: {e}")

    # --- Legenda única (raster + APS) ---
    if handles_legenda:
        ax.legend(
            handles=handles_legenda,
            loc="lower left",
            fontsize=7.5,
            framealpha=0.85,
            title="Legenda",
            title_fontsize=8,
        )

    # --- Formatação ---
    ax.set_title(criterio["titulo"], fontsize=11, fontweight="bold", pad=8)
    ax.set_axis_off()   # remove eixos, ticks e labels de coordenadas

    plt.tight_layout()
    plt.savefig(output_path, dpi=150, bbox_inches="tight")
    plt.close(fig)

    return output_path
# ---------------------------------------------------------
# Construção do PDF
# ---------------------------------------------------------

def _cabecalho_pagina(canvas_obj, doc, mun, uf, data_exec, logo_path="./data/logo_geosaude.png"):
    """Cabeçalho e rodapé aplicados a todas as páginas."""

    w, h = A4

    # Linha superior
    canvas_obj.setStrokeColorRGB(0.1, 0.1, 0.08)
    canvas_obj.setLineWidth(1.5)
    canvas_obj.line(2 * cm, h - 1.8 * cm, w - 2 * cm, h - 1.8 * cm)

    # Título do cabeçalho
    if logo_path and Path(logo_path).exists():

        # Altura da logo no cabeçalho: 0.5 cm
        logo_h = 0.5 * cm

        with PILImage.open(logo_path) as im:
            lw, lh = im.size

        logo_w = logo_h * (lw / lh)

        canvas_obj.drawImage(
            logo_path,
            2 * cm,
            h - 1.65 * cm,
            width=logo_w,
            height=logo_h,
            preserveAspectRatio=True,
            mask="auto"
        )

        canvas_obj.setFont("Helvetica-Bold", 9)
        canvas_obj.setFillColorRGB(0.1, 0.1, 0.08)
        canvas_obj.drawString(
            2 * cm + logo_w + 0.2 * cm,
            h - 1.5 * cm,
            f"|  {mun} – {uf}"
        )

    else:
        # Fallback sem logo
        canvas_obj.setFont("Helvetica-Bold", 9)
        canvas_obj.setFillColorRGB(0.1, 0.1, 0.08)
        canvas_obj.drawString(
            2 * cm, h - 1.5 * cm,
            f"GeoSaúde  |  {mun} – {uf}"
        )

    canvas_obj.setFont("Helvetica", 8)
    canvas_obj.setFillColorRGB(0.4, 0.4, 0.4)
    canvas_obj.drawRightString(
        w - 2 * cm, h - 1.5 * cm,
        f"Relatório gerado em {data_exec}"
    )

    # Rodapé
    canvas_obj.setFont("Helvetica", 7.5)
    canvas_obj.setFillColorRGB(0.5, 0.5, 0.5)
    canvas_obj.drawCentredString(
        w / 2, 1.2 * cm,
        f"Página {doc.page}"
    )

    canvas_obj.setLineWidth(0.5)
    canvas_obj.line(2 * cm, 1.6 * cm, w - 2 * cm, 1.6 * cm)

def inserir_imagem_proporcional(
    story: list,
    img_path: str,
    largura_max: float,
    altura_max: float = None
) -> None:
    """
    Insere uma imagem no story do ReportLab respeitando a proporção original.

    A imagem é redimensionada para caber dentro de largura_max.
    Se altura_max for definido, a imagem também é limitada verticalmente,
    reduzindo a largura proporcionalmente se necessário.

    Parâmetros
    ----------
    story : list
        Lista de elementos do ReportLab.
    img_path : str
        Caminho do arquivo PNG.
    largura_max : float
        Largura máxima disponível (em pontos ReportLab, ex: 14.5 * cm).
    altura_max : float, opcional
        Altura máxima disponível. Se None, não há restrição vertical.
    """

    if not Path(img_path).exists():
        return

    # Lê dimensões reais do PNG
    with PILImage.open(img_path) as im:
        largura_px, altura_px = im.size

    proporcao = altura_px / largura_px

    # Calcula dimensões respeitando largura máxima
    largura_final = largura_max
    altura_final  = largura_max * proporcao

    # Se houver limite de altura e for excedido, reduz pela altura
    if altura_max is not None and altura_final > altura_max:
        altura_final  = altura_max
        largura_final = altura_max / proporcao

    story.append(Image(img_path, width=largura_final, height=altura_final))

def gerar_imagens_locais_prioritarios(
    mun: str,
    img_dir: Path,
    buffer_m: int = 500
) -> dict:
    """
    Gera imagens de satélite (via contextily) centradas em cada
    local de maior viabilidade identificado no top_suitability.gpkg.

    Parâmetros
    ----------
    mun : str
        Nome do município.
    img_dir : Path
        Pasta onde as imagens serão salvas.
    buffer_m : int
        Raio do buffer em metros ao redor do ponto (padrão: 500m).

    Retorno
    -------
    dict
        {grupo_id: caminho_da_imagem}
    """

    top_path = Path(f"./data/resultados/{mun}/report/top_suitability.gpkg")

    if not top_path.exists():
        logger.warning("top_suitability.gpkg não encontrado.")
        return {}

    try:
        gdf = gpd.read_file(str(top_path))
    except Exception as e:
        logger.warning(f"Erro ao ler top_suitability.gpkg: {e}")
        return {}

    if gdf.crs is None:
        gdf = gdf.set_crs("EPSG:4326")

    gdf_3857 = gdf.to_crs("EPSG:3857")

    imagens = {}

    for _, row in gdf_3857.iterrows():

        grupo_id = int(row.get("grupo_id", 0))
        ponto    = row.geometry
        endereco = row.get("endereco", "")

        xmin = ponto.x - buffer_m
        xmax = ponto.x + buffer_m
        ymin = ponto.y - buffer_m
        ymax = ponto.y + buffer_m

        fig, ax = plt.subplots(figsize=(5, 5), dpi=150)

        # Marcador do ponto
        ax.plot(
            ponto.x, ponto.y,
            marker="*",
            color="#FFD700",
            markersize=18,
            markeredgecolor="#1a1814",
            markeredgewidth=0.8,
            zorder=5
        )

        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)

        # Basemap satélite
        try:
            ctx.add_basemap(
                ax,
                source=ctx.providers.Esri.WorldImagery,
                attribution=False,
                zoom=16
            )
        except Exception as e:
            logger.warning(
                f"Basemap satélite não carregado (local #{grupo_id}): {e}"
            )
            ax.set_facecolor("#cce0f0")

        # Restaura limites após basemap
        ax.set_xlim(xmin, xmax)
        ax.set_ylim(ymin, ymax)
        ax.set_axis_off()

        # Título discreto
        ax.set_title(
            f"Local #{grupo_id}",
            fontsize=8,
            fontweight="bold",
            color="#1a1814",
            pad=4
        )

        img_path = str(img_dir / f"local_{grupo_id:02d}.png")

        plt.savefig(img_path, dpi=150, bbox_inches="tight")
        plt.close(fig)

        imagens[grupo_id] = img_path
        logger.info(f"Imagem satélite gerada: local #{grupo_id} — {endereco}")

    return imagens


def gerar_relatorio(mun: str, uf: str, logo_path: str = "./data/logo_geosaude.png") -> str:
    """
    Gera o relatório PDF completo do GeoSaúde para um município.

    Conteúdo do relatório:
        - Capa com identificação e data
        - Sumário dos critérios e pesos
        - Mapa temático de cada critério (C1–C9) com legenda e descrição
        - Mapa da Viabilidade Espacial Final
        - Tabela dos locais de maior viabilidade com endereços

    Parâmetros
    ----------
    mun : str
        Nome do município.
    uf : str
        Sigla do estado.
    logo_path : str, opcional
    Caminho para a imagem da logo do projeto (PNG ou JPG).
    Se None, o título textual é utilizado como fallback.

    Retorno
    -------
    str
        Caminho do PDF gerado.
    """

    logger.info("Iniciando geração do relatório PDF...")

    data_exec = datetime.now().strftime("%d/%m/%Y %H:%M")

    # -------------------------------------------------
    # Diretórios
    # -------------------------------------------------

    base_dir    = Path(f"./data/resultados/{mun}")
    raster_dir  = base_dir / "raster" / "Critérios"
    report_dir  = base_dir / "report"
    img_dir     = report_dir / "img"

    report_dir.mkdir(parents=True, exist_ok=True)
    img_dir.mkdir(parents=True, exist_ok=True)

    pdf_path = str(report_dir / f"GeoSaude_{mun}_{uf}.pdf")

    # -------------------------------------------------
    # Limite municipal (para sobreposição nos mapas)
    # -------------------------------------------------

    limite_mun = None
    gpkg_path = base_dir / f"{mun}_{uf}_h3_grid.gpkg"

    if gpkg_path.exists():
        try:
            grade = gpd.read_file(str(gpkg_path))
            from shapely.ops import unary_union
            from geopandas import GeoDataFrame
            from shapely.geometry import mapping
            limite_geom = unary_union(grade.geometry)
            limite_mun = GeoDataFrame(
                geometry=[limite_geom], crs=grade.crs
            )
        except Exception as e:
            logger.warning(f"Limite municipal não carregado: {e}")

    
    # -------------------------------------------------
    # Unidades APS existentes
    # -------------------------------------------------

    unidades_aps = carregar_unidades_aps(mun, uf)    

    # -------------------------------------------------
    # Renderização dos mapas
    # -------------------------------------------------

    imagens_geradas = {}

    for crit in CRITERIOS:
        raster_path = raster_dir / crit["arquivo"]
        
        if not raster_path.exists():
            logger.warning(
                f"Raster não encontrado, pulando: {crit['arquivo']}"
            )
            continue

        img_path = str(img_dir / f"{crit['codigo']}.png")

        try:
            renderizar_mapa(
                str(raster_path),
                base_dir,
                crit,
                limite_mun,
                img_path,
                unidades_aps=unidades_aps    # ← novo parâmetro
            )
            imagens_geradas[crit["codigo"]] = img_path
            logger.info(f"Mapa gerado: {crit['titulo']}")

        except Exception as e:
            logger.error(f"Erro ao renderizar {crit['arquivo']}: {e}")
    
    # -------------------------------------------------
    # Imagens satélite dos locais prioritários
    # -------------------------------------------------

    imagens_locais = gerar_imagens_locais_prioritarios(mun, img_dir)

    # -------------------------------------------------
    # Leitura dos locais prioritários
    # -------------------------------------------------

    top_path = report_dir / "top_suitability.gpkg"
    top_df   = None

    if top_path.exists():
        try:
            top_gdf = gpd.read_file(str(top_path))
            top_df  = top_gdf[[
                "grupo_id",
                "Analise_ViabilidadeFinal_max",
                "pop_total",
                "renda_sm_media",
                "endereco",
                "latitude",
                "longitude"
            ]].copy()
            top_df = top_df.sort_values(
                "Analise_ViabilidadeFinal_max",
                ascending=False
            ).reset_index(drop=True)
        except Exception as e:
            logger.warning(f"Locais prioritários não carregados: {e}")

    # -------------------------------------------------
    # Estilos do documento
    # -------------------------------------------------

    styles = getSampleStyleSheet()

    estilo_titulo = ParagraphStyle(
        "titulo",
        parent=styles["Title"],
        fontSize=22,
        leading=28,
        textColor=colors.HexColor("#1a1814"),
        spaceAfter=6,
        alignment=TA_CENTER,
    )
    estilo_subtitulo = ParagraphStyle(
        "subtitulo",
        parent=styles["Normal"],
        fontSize=13,
        leading=18,
        textColor=colors.HexColor("#4a4540"),
        spaceAfter=4,
        alignment=TA_CENTER,
    )
    estilo_secao = ParagraphStyle(
        "secao",
        parent=styles["Heading1"],
        fontSize=13,
        leading=18,
        textColor=colors.HexColor("#1a1814"),
        spaceBefore=18,
        spaceAfter=8,
        borderPad=4,
    )
    estilo_criterio = ParagraphStyle(
        "criterio",
        parent=styles["Heading2"],
        fontSize=11,
        leading=15,
        textColor=colors.HexColor("#2a2420"),
        spaceBefore=12,
        spaceAfter=4,
    )
    estilo_corpo = ParagraphStyle(
        "corpo",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor("#2a2420"),
        spaceAfter=6,
        alignment=TA_JUSTIFY,
    )
    estilo_nota = ParagraphStyle(
        "nota",
        parent=styles["Normal"],
        fontSize=8,
        leading=12,
        textColor=colors.HexColor("#6b6560"),
        spaceAfter=4,
        alignment=TA_JUSTIFY,
    )

    # -------------------------------------------------
    # Montagem do documento
    # -------------------------------------------------

    doc = SimpleDocTemplate(
        pdf_path,
        pagesize=A4,
        leftMargin=2.2 * cm,
        rightMargin=2.2 * cm,
        topMargin=2.8 * cm,
        bottomMargin=2.5 * cm,
        title=f"GeoSaúde — {mun}/{uf}",
        author="GeoSaúde",
        subject="Relatório de Viabilidade Espacial para APS",
    )

    story = []

    # =====================================================
    # CAPA
    # =====================================================

    story.append(Spacer(1, 3 * cm))

    if logo_path and Path(logo_path).exists():

        # Calcula dimensões da logo preservando proporção
        # Largura máxima na capa: 8 cm
        largura_logo_capa = 8 * cm

        with PILImage.open(logo_path) as im:
            lw, lh = im.size

        altura_logo_capa = largura_logo_capa * (lh / lw)

        logo_img = Image(
            logo_path,
            width=largura_logo_capa,
            height=altura_logo_capa
        )

        # Centraliza usando uma tabela de uma célula
        tabela_logo = Table(
            [[logo_img]],
            colWidths=[A4[0] - 4.4 * cm]
        )
        tabela_logo.setStyle(TableStyle([
            ("ALIGN",   (0, 0), (-1, -1), "CENTER"),
            ("VALIGN",  (0, 0), (-1, -1), "MIDDLE"),
            ("LEFTPADDING",  (0, 0), (-1, -1), 0),
            ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ("TOPPADDING",   (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING",(0, 0), (-1, -1), 0),
        ]))

        story.append(tabela_logo)

    else:
        # Fallback textual caso a logo não seja encontrada
        story.append(Paragraph("GeoSaúde", estilo_titulo))

    story.append(Spacer(1, 0.4 * cm))
    story.append(Paragraph(
        "Análise de Viabilidade Espacial para Implantação<br/>"
        "de Novas Unidades de Atenção Primária à Saúde",
        estilo_subtitulo
    ))


    story.append(Spacer(1, 0.5 * cm))
    story.append(HRFlowable(
        width="100%", thickness=1.5,
        color=colors.HexColor("#1a1814")
    ))
    story.append(Spacer(1, 0.4 * cm))

    story.append(Paragraph(
        f"<b>Município:</b> {mun} &nbsp;|&nbsp; <b>UF:</b> {uf}",
        ParagraphStyle(
            "meta", parent=estilo_subtitulo,
            fontSize=11, textColor=colors.HexColor("#3a3530")
        )
    ))
    story.append(Paragraph(
        f"<b>Data de geração:</b> {data_exec}",
        ParagraphStyle(
            "meta2", parent=estilo_subtitulo,
            fontSize=10, textColor=colors.HexColor("#6b6560")
        )
    ))

    story.append(Spacer(1, 2 * cm))

    story.append(Paragraph(
        "Este relatório apresenta os resultados da análise multicritério "
        "realizada pelo GeoSaúde, ferramenta computacional desenvolvida "
        "para apoiar gestores públicos na identificação dos locais de maior "
        "viabilidade territorial para a implantação de novas unidades de "
        "Atenção Primária à Saúde (APS). A metodologia integra nove "
        "critérios de análise — agrupados nas dimensões demográfica, "
        "de acessibilidade e urbana — ponderados com base na consulta "
        "a 34 especialistas da área.",
        estilo_corpo
    ))

    story.append(PageBreak())

    # =====================================================
    # SUMÁRIO DOS CRITÉRIOS E PESOS
    # =====================================================

    story.append(Paragraph(
        "Critérios de Análise e Ponderação", estilo_secao
    ))
    story.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor("#d8d4cc")
    ))
    story.append(Spacer(1, 0.3 * cm))

    story.append(Paragraph(
        "A tabela a seguir apresenta os nove critérios utilizados na "
        "análise, organizados em três grupos temáticos, com os respectivos "
        "pesos derivados da consulta pareada a especialistas.",
        estilo_corpo
    ))
    story.append(Spacer(1, 0.3 * cm))

    # Tabela de critérios
    dados_tabela = [[
        Paragraph("<b>Critério</b>", estilo_nota),
        Paragraph("<b>Descrição</b>", estilo_nota),
        Paragraph("<b>Grupo</b>", estilo_nota),
        Paragraph("<b>Peso</b>", estilo_nota),
    ]]

    grupos = {
        "C1": "Demográfico",
        "C2": "Demográfico",
        "C3": "Demográfico",
        "C4": "Acessibilidade",
        "C5": "Acessibilidade",
        "C6": "Acessibilidade",
        "C7": "Urbano",
        "C8": "Urbano",
        "C9": "Urbano",
    }

    for crit in CRITERIOS:
        if crit["codigo"] == "VF":
            continue
        dados_tabela.append([
            Paragraph(f"<b>{crit['codigo']}</b>", estilo_nota),
            Paragraph(
                crit["titulo"].split("—", 1)[-1].strip(),
                estilo_nota
            ),
            Paragraph(grupos.get(crit["codigo"], "—"), estilo_nota),
            Paragraph(
                f"{PESOS.get(crit['codigo'], 0):.4f}",
                estilo_nota
            ),
        ])

    tabela_crit = Table(
        dados_tabela,
        colWidths=[1.5 * cm, 9 * cm, 3 * cm, 2 * cm],
        repeatRows=1
    )
    tabela_crit.setStyle(TableStyle([
        ("BACKGROUND",  (0, 0), (-1, 0),  colors.HexColor("#1a1814")),
        ("TEXTCOLOR",   (0, 0), (-1, 0),  colors.white),
        ("FONTNAME",    (0, 0), (-1, 0),  "Helvetica-Bold"),
        ("FONTSIZE",    (0, 0), (-1, 0),  8),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1),
         [colors.white, colors.HexColor("#f5f4f1")]),
        ("GRID",        (0, 0), (-1, -1), 0.4, colors.HexColor("#d8d4cc")),
        ("VALIGN",      (0, 0), (-1, -1), "MIDDLE"),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING",(0, 0), (-1, -1), 5),
        ("TOPPADDING",  (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING",(0, 0), (-1, -1), 4),
    ]))

    story.append(tabela_crit)
    story.append(PageBreak())

    # =====================================================
    # MAPAS TEMÁTICOS (C1–C9)
    # =====================================================

    story.append(Paragraph("Mapas Temáticos por Critério", estilo_secao))
    story.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor("#d8d4cc")
    ))
    story.append(Spacer(1, 0.2 * cm))

    # Largura útil da página descontando as margens
    largura_img = A4[0] - 2.2 * cm - 2.2 * cm

    for crit in CRITERIOS:

        if crit["codigo"] == "VF":
            continue

        img_path = imagens_geradas.get(crit["codigo"])

        story.append(Paragraph(crit["titulo"], estilo_criterio))
        story.append(Paragraph(crit["descricao"], estilo_corpo))

        if img_path and Path(img_path).exists():
            story.append(Spacer(1, 0.2 * cm))
            inserir_imagem_proporcional(
                story,
                img_path,
                largura_max=largura_img,
                altura_max=18 * cm
            )
        else:
            story.append(Paragraph(
                "<i>Mapa não disponível para este critério.</i>",
                estilo_nota
            ))

        story.append(Spacer(1, 0.3 * cm))
        story.append(HRFlowable(
            width="100%", thickness=0.3,
            color=colors.HexColor("#e8e4dc")
        ))
        story.append(PageBreak())

    # =====================================================
    # MAPA DE VIABILIDADE FINAL
    # =====================================================

    crit_vf = next(c for c in CRITERIOS if c["codigo"] == "VF")

    story.append(Paragraph(
        "Análise de Viabilidade Espacial Final", estilo_secao
    ))
    story.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor("#d8d4cc")
    ))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(crit_vf["descricao"], estilo_corpo))

    img_vf = imagens_geradas.get("VF")

    if img_vf and Path(img_vf).exists():
        story.append(Spacer(1, 0.3 * cm))
        inserir_imagem_proporcional(
            story,
            img_vf,
            largura_max=largura_img,
            altura_max=18 * cm
        )
    else:
        story.append(Paragraph(
            "<i>Mapa de viabilidade final não disponível.</i>",
            estilo_nota
        ))

    story.append(PageBreak())

    # =====================================================
    # LOCAIS PRIORITÁRIOS
    # =====================================================

    story.append(Paragraph(
        "Locais de Maior Viabilidade Espacial", estilo_secao
    ))
    story.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor("#d8d4cc")
    ))
    story.append(Spacer(1, 0.2 * cm))

    story.append(Paragraph(
        "A tabela a seguir apresenta os locais identificados como de "
        "maior viabilidade espacial para implantação de novas unidades "
        "de APS. Os endereços foram obtidos por geocodificação reversa "
        "dos centroides das células H3 com maiores índices de "
        "viabilidade. Os resultados devem ser interpretados como "
        "indicações aproximadas de área, sujeitas à validação técnica "
        "e jurídica por parte dos gestores municipais.",
        estilo_corpo
    ))

    story.append(Spacer(1, 0.4 * cm))

    if top_df is not None and not top_df.empty:

        cabecalho = [[
            Paragraph("<b>N.</b>",             estilo_nota),
            Paragraph("<b>Viabilidade</b>",    estilo_nota),
            Paragraph("<b>Pop. estimada</b>",  estilo_nota),
            Paragraph("<b>Renda média (SM)</b>", estilo_nota),
            Paragraph("<b>Endereço aproximado</b>", estilo_nota),
            Paragraph("<b>Lat / Lon</b>",      estilo_nota),
            Paragraph("<b>Imagem</b>",         estilo_nota),
        ]]

        linhas = []
        for _, row in top_df.iterrows():

            grupo_id  = int(row["grupo_id"])
            img_local = imagens_locais.get(grupo_id)

            # Célula com imagem satélite ou aviso
            if img_local and Path(img_local).exists():
                with PILImage.open(img_local) as im_pil:
                    lw, lh = im_pil.size
                largura_cel  = 3.5 * cm
                altura_cel   = largura_cel * (lh / lw)
                celula_img   = Image(
                    img_local,
                    width=largura_cel,
                    height=altura_cel
                )
            else:
                celula_img = Paragraph(
                    "<i>N/D</i>", estilo_nota
                )

            pop_fmt = f"{int(row['pop_total']):,}".replace(",", ".")

            linhas.append([
                Paragraph(str(grupo_id), estilo_nota),
                Paragraph(
                    f"{row['Analise_ViabilidadeFinal_max']:.1f}",
                    estilo_nota
                ),
                Paragraph(f"{pop_fmt} hab.", estilo_nota),
                Paragraph(
                    f"{row['renda_sm_media']:.1f}",
                    estilo_nota
                ),
                Paragraph(
                    str(row["endereco"]) if row["endereco"] else "—",
                    estilo_nota
                ),
                Paragraph(
                    f"{row['latitude']:.5f}<br/>{row['longitude']:.5f}",
                    estilo_nota
                ),
                celula_img,
            ])

        tabela_top = Table(
            cabecalho + linhas,
            colWidths=[
                0.8 * cm,   # N.
                1.6 * cm,   # Viabilidade
                1.8 * cm,   # Pop.
                1.8 * cm,   # Renda
                4.5 * cm,   # Endereço
                2.0 * cm,   # Lat/Lon
                3.5 * cm,   # Imagem
            ],
            repeatRows=1
        )
        tabela_top.setStyle(TableStyle([
            ("BACKGROUND",    (0, 0), (-1, 0),  colors.HexColor("#1a1814")),
            ("TEXTCOLOR",     (0, 0), (-1, 0),  colors.white),
            ("FONTNAME",      (0, 0), (-1, 0),  "Helvetica-Bold"),
            ("FONTSIZE",      (0, 0), (-1, 0),  8),
            ("ROWBACKGROUNDS",(0, 1), (-1, -1),
             [colors.white, colors.HexColor("#f5f4f1")]),
            ("GRID",          (0, 0), (-1, -1), 0.4, colors.HexColor("#d8d4cc")),
            ("VALIGN",        (0, 0), (-1, -1), "MIDDLE"),
            ("ALIGN",         (6, 1), (6, -1),  "CENTER"),
            ("LEFTPADDING",   (0, 0), (-1, -1), 4),
            ("RIGHTPADDING",  (0, 0), (-1, -1), 4),
            ("TOPPADDING",    (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ]))

        story.append(tabela_top)

    else:
        story.append(Paragraph(
            "<i>Dados de locais prioritários não disponíveis. "
            "Execute a etapa 'top_cells' para gerar este conteúdo.</i>",
            estilo_nota
        ))

    # Nota metodológica final
    story.append(Spacer(1, 0.8 * cm))
    story.append(HRFlowable(
        width="100%", thickness=0.5,
        color=colors.HexColor("#d8d4cc")
    ))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "<b>Nota metodológica:</b> O GeoSaúde não substitui os "
        "processos de decisão técnica e jurídica relacionados à "
        "aquisição e aprovação de terrenos. Os resultados devem ser "
        "utilizados como subsídio ao planejamento, em conjunto com "
        "vistorias de campo, análise fundiária e consulta às "
        "legislações urbanísticas municipais vigentes.",
        estilo_nota
    ))

    # -------------------------------------------------
    # Compilação do PDF
    # -------------------------------------------------

    def cabecalho_primeira(canvas_obj, doc_obj):
        # Na capa: apenas rodapé, sem cabeçalho com logo
        _cabecalho_pagina(
            canvas_obj, doc_obj, mun, uf, data_exec,
            logo_path=None          # oculta cabeçalho na capa
        )

    def cabecalho_demais(canvas_obj, doc_obj):
        _cabecalho_pagina(
            canvas_obj, doc_obj, mun, uf, data_exec,
            logo_path=logo_path     # exibe logo nas demais páginas
        )

    doc.build(
        story,
        onFirstPage=cabecalho_primeira,
        onLaterPages=cabecalho_demais
    )

    logger.info(f"Relatório PDF salvo em: {pdf_path}")
    return pdf_path