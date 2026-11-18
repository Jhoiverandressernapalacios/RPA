"""Punto de entrada: `python -m rpa_dian <subcomando>`.

Subcomandos disponibles:
  extraer   PDF descargados -> imágenes -> OCR -> un CSV por factura + consolidado.csv
"""

import argparse
import logging
from pathlib import Path

from rpa_dian import config
from rpa_dian.consultas import leer_consultas
from rpa_dian.conversion import PdfProtegidoError
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


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    analizador = argparse.ArgumentParser(prog="python -m rpa_dian", description=__doc__)
    subcomandos = analizador.add_subparsers(dest="subcomando", required=True)

    sub = subcomandos.add_parser("extraer", help="PDF -> imágenes -> OCR -> CSV")
    sub.add_argument("--consultas", type=Path, default=config.RUTA_CONSULTAS)
    sub.add_argument("--entrada", type=Path, default=config.DIR_PDF)
    sub.add_argument("--salida", type=Path, default=config.DIR_CSV)
    sub.add_argument("--imagenes", type=Path, default=config.DIR_IMG)
    return analizador.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    argumentos = _argumentos(argv)
    if argumentos.subcomando == "extraer":
        extraer(argumentos.consultas, argumentos.entrada, argumentos.salida, argumentos.imagenes)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
