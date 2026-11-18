"""Punto de entrada: `python -m rpa_dian <subcomando>`.

Subcomandos disponibles:
  descargar  consulta cada CUFE en la DIAN y guarda el PDF (modo asistido o automático)
  extraer    PDF descargados -> imágenes -> OCR -> un CSV por factura + consolidado.csv
"""

import argparse
import logging
from collections import Counter
from pathlib import Path

from rpa_dian import config
from rpa_dian.asistido import ConsultorAsistido
from rpa_dian.consultas import leer_consultas
from rpa_dian.conversion import PdfProtegidoError
from rpa_dian.descarga import Resultado, abrir_navegador, descargar_todas, guardar_resultados
from rpa_dian.exportacion import exportar
from rpa_dian.proceso import Factura, procesar_pdf

log = logging.getLogger("rpa_dian")


def extraer(consultas: Path, entrada: Path, salida: Path, imagenes: Path) -> list[Factura]:
    """Procesa cada PDF `<CUFE>.pdf` de `entrada` con el NIT de su consulta."""
    facturas = []
    for consulta in leer_consultas(consultas):
        pdf = entrada / f"{consulta.cufe}.pdf"
        if not consulta.nit:
            log.info("%s… sin NIT: no se puede abrir el PDF", consulta.cufe[:12])
        elif not pdf.is_file():
            log.info("%s… sin PDF en %s", consulta.cufe[:12], entrada)
        else:
            try:
                factura = procesar_pdf(pdf, consulta.nit, imagenes)
            except PdfProtegidoError as error:
                log.warning("%s… %s", consulta.cufe[:12], error)
            else:
                log.info(
                    "%s… factura %s: %d productos",
                    consulta.cufe[:12],
                    factura.encabezado.numero_factura or "?",
                    len(factura.productos),
                )
                facturas.append(factura)
    rutas = exportar(facturas, salida)
    log.info("%d facturas extraídas; CSV en %s", len(facturas), rutas[-1].parent)
    return facturas


def descargar(
    consultas: Path,
    salida: Path,
    resultados: Path,
    modo: str = "asistido",
    carpeta_descargas: Path = config.DIR_DESCARGAS,
    espera: float = 300,
) -> list[Resultado]:
    """Descarga los PDF; solo se usa el navegador si alguna consulta tiene NIT.

    - asistido: abre la consulta en el navegador normal y vigila la carpeta de Descargas.
    - automatico: Playwright (Cloudflare lo rechaza; se conserva como evidencia).
    """
    lista = leer_consultas(consultas)
    if not any(c.nit for c in lista):
        obtenidos = descargar_todas(lista, None, salida)
    elif modo == "automatico":
        with abrir_navegador() as consultor:
            obtenidos = descargar_todas(lista, consultor, salida)
    else:
        consultor = ConsultorAsistido(carpeta_descargas=carpeta_descargas, espera_s=espera)
        obtenidos = descargar_todas(lista, consultor, salida)
    guardar_resultados(obtenidos, resultados)
    resumen = Counter(r.estado for r in obtenidos)
    log.info("Descarga terminada: %s; detalle en %s", dict(resumen), resultados)
    return obtenidos


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    analizador = argparse.ArgumentParser(prog="python -m rpa_dian", description=__doc__)
    subcomandos = analizador.add_subparsers(dest="subcomando", required=True)

    sub = subcomandos.add_parser("descargar", help="CUFE + NIT -> PDF de la DIAN")
    sub.add_argument("--consultas", type=Path, default=config.RUTA_CONSULTAS)
    sub.add_argument("--salida", type=Path, default=config.DIR_PDF)
    sub.add_argument("--resultados", type=Path, default=config.DIR_METRICAS / "descargas.csv")
    sub.add_argument(
        "--modo",
        choices=["asistido", "automatico"],
        default="asistido",
        help="asistido: navegador normal + carpeta de Descargas (predeterminado); "
        "automatico: Playwright (Cloudflare lo rechaza)",
    )
    sub.add_argument("--descargas", type=Path, default=config.DIR_DESCARGAS)
    sub.add_argument("--espera", type=float, default=300, help="segundos por factura")

    sub = subcomandos.add_parser("extraer", help="PDF -> imágenes -> OCR -> CSV")
    sub.add_argument("--consultas", type=Path, default=config.RUTA_CONSULTAS)
    sub.add_argument("--entrada", type=Path, default=config.DIR_PDF)
    sub.add_argument("--salida", type=Path, default=config.DIR_CSV)
    sub.add_argument("--imagenes", type=Path, default=config.DIR_IMG)
    return analizador.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    argumentos = _argumentos(argv)
    if argumentos.subcomando == "descargar":
        descargar(
            argumentos.consultas,
            argumentos.salida,
            argumentos.resultados,
            argumentos.modo,
            argumentos.descargas,
            argumentos.espera,
        )
    elif argumentos.subcomando == "extraer":
        extraer(argumentos.consultas, argumentos.entrada, argumentos.salida, argumentos.imagenes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
