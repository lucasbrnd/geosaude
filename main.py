# main.py

import logging
import sys
import time
import traceback
from pathlib import Path

import geosaude
import utils
from utils import get_bbox, calculadora_raster, agregar_resultados, top_cells
from geocnes import geocnes
from report import gerar_relatorio          # ← import no topo do arquivo


# ---------------------------------------------------------
# Configuração do logger
# ---------------------------------------------------------

def configurar_logger(mun: str, uf: str) -> logging.Logger:

    log_dir = Path(f"./data/resultados/{mun}")
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"geosaude_{mun}_{uf}.log"

    logger = logging.getLogger("geosaude")
    logger.setLevel(logging.DEBUG)

    if logger.handlers:
        logger.handlers.clear()

    fmt = logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)

    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(fmt)

    logger.addHandler(ch)
    logger.addHandler(fh)

    return logger


# ---------------------------------------------------------
# Execução controlada de cada etapa
# ---------------------------------------------------------

def executar_etapa(logger, nome, func, *args, **kwargs) -> bool:

    logger.info(f"{'='*55}")
    logger.info(f"INÍCIO: {nome}")
    logger.info(f"{'='*55}")

    t0 = time.time()

    try:
        func(*args, **kwargs)
        logger.info(f"CONCLUÍDO: {nome}  ({time.time() - t0:.1f}s)")
        return True

    except Exception:
        logger.error(f"FALHA: {nome}  ({time.time() - t0:.1f}s)")
        logger.error(traceback.format_exc())
        return False


def criterio_ja_processado(mun: str, nome_arquivo: str) -> bool:
    return Path(
        f"./data/resultados/{mun}/raster/{nome_arquivo}.tif"
    ).exists()


# ---------------------------------------------------------
# Pipeline principal
# ---------------------------------------------------------

def main(mun, uf, here_api, opentopo_api, forcar_reprocessamento=False):

    logger = configurar_logger(mun, uf)
    logger.info(f"GeoSaúde iniciado → município: {mun} / UF: {uf}")

    t_total = time.time()
    etapas_com_falha = []

    # --- Etapa 0: bbox e CNES ---
    try:
        bbox = get_bbox(mun, uf)
        logger.info(f"Bounding box: {bbox}")
    except Exception:
        logger.critical("Falha ao obter bounding box. Execução interrompida.\n"
                        + traceback.format_exc())
        sys.exit(1)

    for code_un, descricao in [
        ("02", "Unidades de APS"),
        ("05", "Hospitais"),
        ("73", "UPAs"),
    ]:
        ok = executar_etapa(logger, f"CNES — {descricao}",
                            geocnes, mun, uf, here_api, code_un=code_un)
        if not ok:
            etapas_com_falha.append(f"CNES tipo {code_un}")

    # --- Critérios C1–C9 ---
    etapas_criterios = [
        ("C1 — Vulnerabilidade Social",         "C1_VulnSoc",
         geosaude.vulnerabilidade,               (mun, uf, bbox)),
        ("C2/C3 — Demográfico e Renda",          "C2_DistDemog",
         geosaude.dados_demograficos,            (uf, mun, bbox)),
        ("C4/C5/C6 — Acessibilidade",            "C4_TempoMin",
         geosaude.travel_time_calculation,       (mun, uf, bbox, here_api, opentopo_api)),
        ("C7 — Risco de Eventos Naturais",       "C7_EventNat",
         geosaude.sgb_data,                      (uf, mun, bbox)),
        ("C8 — Equipamentos Indesejáveis",       "C8_EqupInd",
         geosaude.PUI,                           (mun, uf, bbox)),
        ("C9 — Equipamentos Desejáveis",         "C9_EqupDes",
         geosaude.equipamentos_desejaveis,       (mun, uf, bbox, here_api)),
    ]

    for nome, raster_saida, func, args in etapas_criterios:
        if not forcar_reprocessamento and criterio_ja_processado(mun, raster_saida):
            logger.info(f"PULADO (já existe em disco): {nome}")
            continue
        if not executar_etapa(logger, nome, func, *args):
            etapas_com_falha.append(nome)

    # --- Combinação ponderada ---
    if not executar_etapa(logger, "Calculadora Raster", calculadora_raster, mun, uf):
        etapas_com_falha.append("Calculadora Raster")

    # --- Agregação H3 ---
    if not executar_etapa(logger, "Agregação H3", agregar_resultados, mun, uf):
        etapas_com_falha.append("Agregação H3")

    # --- Locais prioritários ---
    if not executar_etapa(logger, "Top cells", top_cells, mun, uf, here_api):
        etapas_com_falha.append("Top cells")

    # --- Relatório PDF ---              ← aqui, ainda dentro de main()
    if not executar_etapa(logger, "Geração do relatório PDF",
                          gerar_relatorio, mun, uf,
                          logo_path="./data/logo_geosaude.png"):
        continue

    #main.py — dentro de main(), após gerar_relatorio

    from dashboard import gerar_dashboard
    
    if not executar_etapa(logger, "Geração do dashboard interativo",
                          gerar_dashboard, mun, uf,
                          logo_path="./assets/logo_geosaude.png"):
        etapas_com_falha.append("Dashboard")
        
    # --- Resumo final ---
    logger.info(f"{'='*55}")
    logger.info(f"EXECUÇÃO FINALIZADA — {time.time() - t_total:.1f}s")

    if etapas_com_falha:
        logger.warning(f"{len(etapas_com_falha)} etapa(s) com falha:")
        for etapa in etapas_com_falha:
            logger.warning(f"  • {etapa}")
    else:
        logger.info("Todas as etapas concluídas com sucesso.")

    logger.info(f"{'='*55}")


# ---------------------------------------------------------
# Ponto de entrada                ← separado e limpo
# ---------------------------------------------------------

if __name__ == "__main__":

    import argparse

    parser = argparse.ArgumentParser(
        description="GeoSaúde — Análise de viabilidade espacial para APS"
    )
    parser.add_argument("--mun",      required=True,       help="Nome do município")
    parser.add_argument("--uf",       required=True,       help="Sigla do estado")
    parser.add_argument("--here_api", required=True,       help="Chave HERE API")
    parser.add_argument("--opentopo", required=True,       help="Chave OpenTopography API")
    parser.add_argument("--forcar",   action="store_true", help="Reprocessar tudo")

    args = parser.parse_args()

    main(
        mun=args.mun,
        uf=args.uf,
        here_api=args.here_api,
        opentopo_api=args.opentopo,
        forcar_reprocessamento=args.forcar
    )