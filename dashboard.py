# dashboard.py

import json
import logging
import os
from datetime import datetime
from pathlib import Path

import folium
import geopandas as gpd
import numpy as np
import rasterio
from branca.colormap import LinearColormap, StepColormap
from folium.plugins import MeasureControl, MiniMap


logger = logging.getLogger("geosaude")


# ---------------------------------------------------------
# Configuração dos critérios (mesma do report.py)
# ---------------------------------------------------------

CRITERIOS = [
    {
        "codigo":      "C1",
        "layer":       "C1_VulnSoc",        # nome real no GPKG
        "titulo":      "C1 — Vulnerabilidade Social",
        "descricao":   (
            "Concentração de população em situação de vulnerabilidade "
            "socioeconômica (IVS/IPVS). Scores mais altos indicam maior "
            "vulnerabilidade e maior prioridade."
        ),
        "cores":       ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"],
        "discreto":    True,
        "labels":      ["Muito Baixa", "Baixa", "Média", "Alta", "Muito Alta"],
    },
    {
        "codigo":      "C2",
        "layer":       "C2_DistDemog",
        "titulo":      "C2 — Distribuição Demográfica",
        "descricao":   (
            "Concentração populacional absoluta em malha H3. "
            "Scores mais altos indicam maior densidade e maior demanda potencial."
        ),
        "cores":       ["#eff3ff", "#bdd7e7", "#6baed6", "#2171b5", "#084594"],
        "discreto":    True,
        "labels":      ["Muito Baixa", "Baixa", "Média", "Alta", "Muito Alta"],
    },
    {
        "codigo":      "C3",
        "layer":       "C3_DistRenda",
        "titulo":      "C3 — Distribuição de Renda",
        "descricao":   (
            "Renda média do responsável pelo domicílio (Censo 2022). "
            "Scores mais altos indicam menor renda e maior dependência do SUS."
        ),
        "cores":       ["#1a9641", "#a6d96a", "#ffffbf", "#fdae61", "#d7191c"],
        "discreto":    True,
        "labels":      ["> 10 SM", "5–10 SM", "3–5 SM", "2–3 SM", "0–2 SM"],
    },
    {
        "codigo":      "C4",
        "layer":       "C4_TempoMin",
        "titulo":      "C4 — Custo Mínimo de Deslocamento",
        "descricao":   (
            "Tempo de caminhada até a unidade de APS mais próxima. "
            "Scores altos indicam maior distância e maior necessidade."
        ),
        "cores":       ["#1a9641", "#a6d96a", "#ffffbf", "#fdae61", "#d7191c"],
        "discreto":    True,
        "labels":      ["< 15 min", "15–30 min", "30–45 min", "45–60 min", "> 60 min"],
    },
    {
        "codigo":      "C5",
        "layer":       "C5_NivAcess",
        "titulo":      "C5 — Índice de Acessibilidade (2SFCA)",
        "descricao":   (
            "Relação oferta/demanda calculada pelo método 2SFCA gaussiano. "
            "Scores altos indicam baixo nível de acesso."
        ),
        "cores":       ["#1a9641", "#a6d96a", "#ffffbf", "#fdae61", "#d7191c"],
        "discreto":    True,
        "labels":      ["Muito Alto", "Alto", "Médio", "Baixo", "Muito Baixo"],
    },
    {
        "codigo":      "C6",
        "layer":       "C6_Cobertura",
        "titulo":      "C6 — Cobertura Espacial das Unidades",
        "descricao":   (
            "Sobreposição das áreas de cobertura das unidades existentes (raio 1 km). "
            "Score 10 = sem cobertura; score 1 = coberto por mais de 3 unidades."
        ),
        "cores":       ["#1a9641", "#a6d96a", "#ffffbf", "#fdae61", "#d7191c"],
        "discreto":    True,
        "labels":      ["> 3 unidades", "3 unidades", "2 unidades", "1 unidade", "Sem cobertura"],
    },
    {
        # C7 tem duas camadas — tratado separadamente no loop
        "codigo":      "C7a",
        "layer":       "C7_inundacao",
        "titulo":      "C7a — Risco de Inundação",
        "descricao":   (
            "Suscetibilidade a inundações (SGB). "
            "Scores altos indicam maior risco."
        ),
        "cores":       ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"],
        "discreto":    True,
        "labels":      ["Sem risco", "Baixo", "Médio", "Alto", "Muito Alto"],
    },
    {
        "codigo":      "C7b",
        "layer":       "C7_movimentodamassa",
        "titulo":      "C7b — Risco de Movimento de Massa",
        "descricao":   (
            "Suscetibilidade a movimentos de massa (SGB). "
            "Scores altos indicam maior risco."
        ),
        "cores":       ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"],
        "discreto":    True,
        "labels":      ["Sem risco", "Baixo", "Médio", "Alto", "Muito Alto"],
    },
    {
        "codigo":      "C8",
        "layer":       "C8_EqupInd",
        "titulo":      "C8 — Equipamentos Indesejáveis",
        "descricao":   (
            "Proximidade a elementos incompatíveis com a operação de APS."
        ),
        "cores":       ["#ffffb2", "#fecc5c", "#fd8d3c", "#f03b20", "#bd0026"],
        "discreto":    True,
        "labels":      ["Sem influência", "", "Influência moderada", "", "Área crítica"],
    },
    {
        "codigo":      "C9",
        "layer":       "C9_EqupDes",
        "titulo":      "C9 — Equipamentos Desejáveis",
        "descricao":   (
            "Proximidade a hospitais, UPAs, CRAS, CREAS e escolas."
        ),
        "cores":       ["#f7fcf5", "#c7e9c0", "#74c476", "#238b45", "#00441b"],
        "discreto":    True,
        "labels":      ["Sem influência", "", "Zona de influência", "", "Área próxima"],
    },
]


# ---------------------------------------------------------
# Funções auxiliares
# ---------------------------------------------------------

# dashboard.py — remova as funções:
#   _raster_para_wgs84_array
#   _array_para_imagem_rgba
#   _adicionar_camada_raster
#
# e substitua por:

import matplotlib.colors as mcolors
import matplotlib.pyplot as plt


def _hex_para_rgba_folium(hex_cor: str, alpha: float = 0.75) -> str:
    """
    Converte cor hexadecimal para string rgba() do CSS.
    """
    r, g, b = tuple(
        int(hex_cor.lstrip("#")[i:i+2], 16) for i in (0, 2, 4)
    )
    return f"rgba({r},{g},{b},{alpha})"


def _cor_para_score(score: float, cores: list) -> str:
    """
    Mapeia um valor de score (1–10) para uma cor da rampa fornecida.
    Retorna string hexadecimal.
    """
    if score is None or np.isnan(float(score)):
        return "#cccccc"

    cmap = mcolors.LinearSegmentedColormap.from_list("custom", cores, N=256)
    norm = mcolors.Normalize(vmin=1, vmax=10)

    rgba = cmap(norm(float(score)))
    return mcolors.to_hex(rgba)

def _adicionar_camada_vetor(
    mapa: folium.Map,
    gpkg_path: str,
    criterio: dict,
    opacidade: float = 0.75,
    mostrar: bool = False
) -> bool:
    """
    Lê uma camada do GPKG, reprojetada para WGS84, e adiciona
    ao mapa como GeoJson com estilo baseado na coluna 'score'.
    """

    layer_name = criterio["layer"]

    try:
        gdf = gpd.read_file(gpkg_path, layer=layer_name)

        if gdf.empty:
            logger.warning(f"Camada vazia: {layer_name}")
            return False

        # --- Reprojeção obrigatória para WGS84 ---
        if gdf.crs is None:
            logger.warning(f"CRS não definido em {layer_name}, assumindo EPSG:3857")
            gdf = gdf.set_crs("EPSG:3857")

        gdf = gdf.to_crs("EPSG:4326")

        # --- Simplificação para reduzir tamanho do HTML ---
        gdf["geometry"] = gdf["geometry"].simplify(
            tolerance=0.0001,       # ~10m em graus decimais
            preserve_topology=True
        )

        # --- Remove geometrias nulas após simplificação ---
        gdf = gdf[gdf["geometry"].notna() & ~gdf["geometry"].is_empty]

        if gdf.empty:
            logger.warning(f"Camada sem geometrias válidas após simplificação: {layer_name}")
            return False

        cores    = criterio["cores"]
        labels   = criterio.get("labels", [])
        discreto = criterio.get("discreto", True)

        # --- Função de estilo ---
        def estilo(feature):
            score = feature["properties"].get("score", 5)
            try:
                score = float(score) if score is not None else 5.0
            except (TypeError, ValueError):
                score = 5.0

            cor = _cor_para_score(score, cores)

            return {
                "fillColor":   cor,
                "fillOpacity": opacidade,
                "color":       "transparent",
                "weight":      0,
            }

        # --- Tooltip ---
        def label_do_score(score_f):
            if not labels:
                return f"{score_f:.0f}"
            idx = int(round((score_f - 1) / 9 * (len(labels) - 1)))
            idx = max(0, min(idx, len(labels) - 1))
            lbl = labels[idx]
            return f"{score_f:.0f} — {lbl}" if lbl else f"{score_f:.0f}"

        folium.GeoJson(
            data=gdf.__geo_interface__,
            name=criterio["titulo"],
            style_function=estilo,
            tooltip=folium.GeoJsonTooltip(
                fields=["score"],
                aliases=[f"{criterio['titulo']}:"],
                localize=True,
                sticky=False,
                style=(
                    "font-family: Georgia, serif;"
                    "font-size: 12px;"
                    "padding: 6px 10px;"
                )
            ),
            show=mostrar,
            smooth_factor=1.5,
        ).add_to(mapa)

        logger.info(f"Camada adicionada: {criterio['titulo']} ({len(gdf)} feições)")
        return True

    except Exception as e:
        logger.error(f"Erro ao adicionar {layer_name}: {e}")
        import traceback
        logger.error(traceback.format_exc())
        return False

def _adicionar_pontos_prioritarios(
    mapa: folium.Map,
    top_path: str
) -> None:
    """
    Adiciona marcadores dos locais prioritários com popups informativos.
    """
    if not Path(top_path).exists():
        return

    gdf = gpd.read_file(top_path).to_crs("EPSG:4326")

    grupo = folium.FeatureGroup(
        name="📍 Locais Prioritários",
        show=True
    )

    for _, row in gdf.iterrows():

        lat = row.geometry.y
        lon = row.geometry.x

        viab  = row.get("Analise_ViabilidadeFinal_max", 0)
        pop   = row.get("pop_total", 0)
        renda = row.get("renda_sm_media", 0)
        end   = row.get("endereco", "Não identificado")
        gid   = row.get("grupo_id", "—")

        popup_html = f"""
        <div style="
            font-family: Georgia, serif;
            font-size: 13px;
            min-width: 260px;
            max-width: 320px;
            line-height: 1.6;
        ">
            <div style="
                background: #1a1814;
                color: white;
                padding: 8px 12px;
                font-weight: bold;
                font-size: 14px;
                border-radius: 4px 4px 0 0;
                margin: -1px -1px 10px -1px;
            ">
                Local #{int(gid)}
            </div>
            <table style="width:100%; border-collapse:collapse;">
                <tr>
                    <td style="color:#6b6560; padding:2px 0;">Viabilidade</td>
                    <td style="font-weight:bold; color:#1a6a2a;">
                        {viab:.1f} / 100
                    </td>
                </tr>
                <tr>
                    <td style="color:#6b6560; padding:2px 0;">Pop. estimada</td>
                    <td>{int(pop):,}" hab.</td>
                </tr>
                <tr>
                    <td style="color:#6b6560; padding:2px 0;">Renda média</td>
                    <td>{renda:.1f} SM</td>
                </tr>
                <tr>
                    <td style="color:#6b6560; padding:2px 0; vertical-align:top;">
                        Endereço aprox.
                    </td>
                    <td style="font-size:12px;">{end}</td>
                </tr>
                <tr>
                    <td style="color:#6b6560; padding:2px 0;">Coordenadas</td>
                    <td style="font-size:11px;">{lat:.5f}, {lon:.5f}</td>
                </tr>
            </table>
        </div>
        """

        folium.Marker(
            location=[lat, lon],
            popup=folium.Popup(popup_html, max_width=340),
            tooltip=f"Local #{int(gid)} — Viabilidade: {viab:.1f}",
            icon=folium.Icon(
                color="darkgreen",
                icon="plus-sign",
                prefix="glyphicon"
            )
        ).add_to(grupo)

    grupo.add_to(mapa)


# ---------------------------------------------------------
# Geração do dashboard HTML
# ---------------------------------------------------------

def gerar_dashboard(
    mun: str,
    uf: str,
    logo_path: str = None
) -> str:
    """
    Gera dashboard HTML interativo do GeoSaúde para um município.

    Conteúdo:
        - Mapa interativo com todas as camadas de critérios
        - Controle de camadas para ativar/desativar critérios
        - Marcadores clicáveis dos locais prioritários com popup
        - Painel lateral com descrição dos critérios
        - Minimap de localização
        - Ferramenta de medição de distâncias

    Parâmetros
    ----------
    mun : str
        Nome do município.
    uf : str
        Sigla do estado.
    logo_path : str, opcional
        Caminho para a logo do projeto (PNG).

    Retorno
    -------
    str
        Caminho do arquivo HTML gerado.
    """

    logger.info("Iniciando geração do dashboard interativo...")

    data_exec = datetime.now().strftime("%d/%m/%Y %H:%M")

    base_dir   = Path(f"./data/resultados/{mun}")
    raster_dir = base_dir / "raster" / "Criterios"
    report_dir = base_dir / "report"
    report_dir.mkdir(parents=True, exist_ok=True)

    html_path = str(report_dir / f"GeoSaude_{mun}_{uf}_dashboard.html")

    # -------------------------------------------------
    # Centro do mapa (a partir da grade H3)
    # -------------------------------------------------

    centro = [-15.8, -47.9]   # fallback: centro do Brasil

    gpkg_path = base_dir / f"{mun}_{uf}_h3_grid.gpkg"
    if gpkg_path.exists():
        try:
            grade  = gpd.read_file(str(gpkg_path)).to_crs("EPSG:4326")
            bounds = grade.total_bounds
            centro = [
                (bounds[1] + bounds[3]) / 2,
                (bounds[0] + bounds[2]) / 2
            ]
        except Exception as e:
            logger.warning(f"Centro do mapa não calculado: {e}")

    # -------------------------------------------------
    # Mapa base
    # -------------------------------------------------

    mapa = folium.Map(
        location=centro,
        zoom_start=12,
        tiles=None,               # tiles adicionados manualmente abaixo
        control_scale=True
    )

    # Camadas base alternativas
    folium.TileLayer(
        "CartoDB positron",
        name="Base — Claro",
        show=True
    ).add_to(mapa)

    folium.TileLayer(
        "CartoDB dark_matter",
        name="Base — Escuro",
        show=False
    ).add_to(mapa)

    folium.TileLayer(
        "OpenStreetMap",
        name="Base — OpenStreetMap",
        show=False
    ).add_to(mapa)

    # -------------------------------------------------
    # Camadas de critérios
    # -------------------------------------------------

    gpkg_mun = str(base_dir / f"geosaude_{mun}.gpkg")

    if not Path(gpkg_mun).exists():
        logger.warning(f"GeoPackage não encontrado: {gpkg_mun}")
    else:
        import fiona
        camadas_disponiveis = fiona.listlayers(gpkg_mun)
        logger.info(f"Camadas no GPKG: {camadas_disponiveis}")

        for crit in CRITERIOS:

            if crit["layer"] not in camadas_disponiveis:
                logger.warning(f"Camada ausente: {crit['layer']}")
                continue

            # Apenas VF ativa por padrão — aqui nenhum critério
            # isolado começa ativo; o usuário ativa pelo painel
            _adicionar_camada_vetor(
                mapa,
                gpkg_mun,
                crit,
                opacidade=0.75,
                mostrar=False
            )
    
    grid_path = str(base_dir / f"{mun}_grid_viabilidade.gpkg")

    if Path(grid_path).exists():

        try:
            gdf_vf = gpd.read_file(grid_path)
            gdf_vf = gdf_vf.to_crs("EPSG:4326")

            # Coluna da viabilidade final
            col_vf = "Analise_ViabilidadeFinal"

            if col_vf not in gdf_vf.columns:
                # Tenta variações de nome
                candidatos = [
                    c for c in gdf_vf.columns
                    if "viabilidade" in c.lower() or "final" in c.lower()
                ]
                if candidatos:
                    col_vf = candidatos[0]
                    logger.info(f"Coluna VF encontrada como: {col_vf}")

            if col_vf in gdf_vf.columns:

                gdf_vf = gdf_vf[
                    gdf_vf[col_vf].notna() & (gdf_vf[col_vf] > 0)
                ].copy()

                gdf_vf["geometry"] = gdf_vf["geometry"].simplify(
                    tolerance=0.0001, preserve_topology=True
                )

                cores_vf = ["#d7191c", "#fdae61", "#ffffbf", "#a6d96a", "#1a9641"]

                vmin = gdf_vf[col_vf].quantile(0.02)
                vmax = gdf_vf[col_vf].quantile(0.98)

                def estilo_vf(feature):
                    val = feature["properties"].get(col_vf, 0)
                    try:
                        val = float(val) if val is not None else 0.0
                    except (TypeError, ValueError):
                        val = 0.0

                    norm  = mcolors.Normalize(vmin=vmin, vmax=vmax)
                    cmap  = mcolors.LinearSegmentedColormap.from_list(
                        "vf", cores_vf, N=256
                    )
                    cor = mcolors.to_hex(cmap(norm(val)))

                    return {
                        "fillColor":   cor,
                        "fillOpacity": 0.80,
                        "color":       "transparent",
                        "weight":      0,
                    }

                folium.GeoJson(
                    data=gdf_vf.__geo_interface__,
                    name="Viabilidade Espacial Final",
                    style_function=estilo_vf,
                    tooltip=folium.GeoJsonTooltip(
                        fields=[col_vf],
                        aliases=["Viabilidade:"],
                        localize=True,
                        sticky=False,
                        style=(
                            "font-family: Georgia, serif;"
                            "font-size: 12px;"
                            "padding: 6px 10px;"
                        )
                    ),
                    show=True,       # única camada ativa por padrão
                    smooth_factor=1.5,
                ).add_to(mapa)

                logger.info(
                    f"Viabilidade Final adicionada "
                    f"({len(gdf_vf)} células H3)"
                )

        except Exception as e:
            logger.error(f"Erro ao adicionar Viabilidade Final: {e}")
            import traceback
            logger.error(traceback.format_exc())

    # -------------------------------------------------
    # Locais prioritários
    # -------------------------------------------------

    _adicionar_pontos_prioritarios(
        mapa,
        str(report_dir / "top_suitability.gpkg")
    )

    # -------------------------------------------------
    # Plugins
    # -------------------------------------------------

    MiniMap(toggle_display=True, position="bottomleft").add_to(mapa)
    MeasureControl(position="topleft", primary_length_unit="meters").add_to(mapa)
    folium.LayerControl(collapsed=False, position="topright").add_to(mapa)

    # -------------------------------------------------
    # Logo em base64 (para embed no HTML)
    # -------------------------------------------------

    logo_b64 = ""
    if logo_path and Path(logo_path).exists():
        import base64
        with open(logo_path, "rb") as f:
            logo_b64 = base64.b64encode(f.read()).decode("utf-8")

    # -------------------------------------------------
    # Painel lateral HTML (injetado no mapa)
    # -------------------------------------------------

    criterios_html = ""
    for crit in CRITERIOS:
        swatches = "".join(
            f'<span style="'
            f'display:inline-block;width:14px;height:14px;'
            f'background:{c};border-radius:2px;margin-right:2px;'
            f'vertical-align:middle;"></span>'
            for c in crit["cores"]
        )
        criterios_html += f"""
        <div class="crit-item" onclick="toggleLayer('{crit['titulo']}')">
            <div class="crit-titulo">{crit['titulo']}</div>
            <div class="crit-cores">{swatches}</div>
            <div class="crit-desc">{crit['descricao']}</div>
        </div>
        """

    logo_html = (
        f'<img src="data:image/png;base64,{logo_b64}" '
        f'style="height:40px; margin-bottom:8px;" alt="GeoSaúde">'
        if logo_b64
        else '<span style="font-size:20px;font-weight:bold;">GeoSaúde</span>'
    )

    painel_css = """
    <style>
      @import url('https://fonts.googleapis.com/css2?family=Source+Serif+4:wght@300;400;600&display=swap');

      #painel {
        position: fixed;
        top: 0; left: 0;
        width: 300px;
        height: 100vh;
        background: #faf9f6;
        border-right: 1px solid #d8d4cc;
        z-index: 1000;
        display: flex;
        flex-direction: column;
        font-family: 'Source Serif 4', Georgia, serif;
        box-shadow: 2px 0 12px rgba(26,24,20,0.1);
        overflow: hidden;
      }

      #painel-header {
        background: #faf9f6;
        color: white;
        padding: 16px 18px 12px;
        flex-shrink: 0;
      }

      #painel-header .mun {
        font-size: 13px;
        color: #c0bbb5;
        margin-top: 4px;
      }

      #painel-header .data {
        font-size: 11px;
        color: #807a74;
        margin-top: 2px;
      }

      #painel-body {
        flex: 1;
        overflow-y: auto;
        padding: 10px 14px;
      }

      #painel-body::-webkit-scrollbar { width: 5px; }
      #painel-body::-webkit-scrollbar-thumb {
        background: #d8d4cc;
        border-radius: 3px;
      }

      .secao-titulo {
        font-size: 10px;
        font-weight: 600;
        letter-spacing: 0.12em;
        text-transform: uppercase;
        color: #6b6560;
        margin: 14px 0 6px;
      }

      .crit-item {
        padding: 8px 10px;
        margin-bottom: 4px;
        border: 1px solid #e8e4dc;
        border-radius: 4px;
        cursor: pointer;
        transition: background 0.15s;
        background: white;
      }

      .crit-item:hover { background: #f0ede8; }

      .crit-titulo {
        font-size: 11.5px;
        font-weight: 600;
        color: #1a1814;
        margin-bottom: 3px;
      }

      .crit-cores { margin-bottom: 4px; }

      .crit-desc {
        font-size: 10.5px;
        color: #6b6560;
        line-height: 1.45;
      }

      #painel-footer {
        padding: 10px 14px;
        font-size: 10px;
        color: #a8a39c;
        border-top: 1px solid #e8e4dc;
        flex-shrink: 0;
      }

      /* Desloca o mapa para a direita */
      .folium-map {
        margin-left: 300px !important;
        width: calc(100vw - 300px) !important;
      }
    </style>
    """

    painel_html = f"""
    {painel_css}
    <div id="painel">
      <div id="painel-header">
        {logo_html}
        <div class="mun">{mun} — {uf}</div>
        <div class="data">Gerado em {data_exec}</div>
      </div>
      <div id="painel-body">
        <div class="secao-titulo">Viabilidade Final</div>
        <div class="crit-item" onclick="toggleLayer('Viabilidade Espacial Final')"
             style="border-left: 3px solid #1a9641;">
          <div class="crit-titulo">Viabilidade Espacial Final</div>
          <div class="crit-cores">
            <span style="display:inline-block;width:100%;height:10px;
              background:linear-gradient(to right,#d7191c,#fdae61,#ffffbf,#a6d96a,#1a9641);
              border-radius:2px;"></span>
          </div>
          <div class="crit-desc">
            Combinação ponderada dos nove critérios.
            Índice de 0 a 100.
          </div>
        </div>

        <div class="secao-titulo">Critérios de Análise</div>
        {criterios_html}

        <div class="secao-titulo">Locais Prioritários</div>
        <div class="crit-item" onclick="toggleLayer('📍 Locais Prioritários')"
             style="border-left: 3px solid #2171b5;">
          <div class="crit-titulo">📍 Locais Prioritários</div>
          <div class="crit-desc">
            Clique nos marcadores para ver viabilidade,
            população estimada, renda e endereço aproximado.
          </div>
        </div>
      </div>

      <div id="painel-footer">
        GeoSaúde · Análise de Viabilidade Espacial para APS<br>
        Os resultados são subsídios ao planejamento e não substituem
        validação técnica e jurídica.
      </div>
    </div>
    """

    # Script para toggle de camadas via painel
    toggle_script = """
    <script>
    function toggleLayer(layerName) {
        var map = Object.values(window).find(
            v => v && v._leaflet_id && v.eachLayer
        );
        if (!map) return;
        map.eachLayer(function(layer) {
            if (layer.options && layer.options.name === layerName) {
                if (map.hasLayer(layer)) {
                    map.removeLayer(layer);
                } else {
                    map.addLayer(layer);
                }
            }
        });
    }
    </script>
    """

    mapa.get_root().html.add_child(folium.Element(painel_html))
    mapa.get_root().html.add_child(folium.Element(toggle_script))

    mapa.save(html_path)

    logger.info(f"Dashboard salvo em: {html_path}")
    return html_path