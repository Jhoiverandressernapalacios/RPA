"""Punto de entrada del RPA DIAN.

python -m rpa_dian [opciones]      proceso completo: descarga -> extracción -> métricas e informe
python -m rpa_dian descargar ...   consulta cada CUFE en la DIAN y guarda el PDF
python -m rpa_dian extraer ...     PDF -> imágenes -> OCR -> un CSV por factura + consolidado.csv,
                                   más metricas.csv e informe.md
"""

import argparse
import logging
from collections import Counter
from pathlib import Path

from rpa_dian import config
from rpa_dian.asistido import ConsultorAsistido
from rpa_dian.consultas import leer_consultas
from rpa_dian.conversion import PdfProtegidoError, capa_de_texto
from rpa_dian.descarga import (
    Resultado,
    abrir_navegador,
    descargar_todas,
    guardar_resultados,
    leer_resultados,
)
from rpa_dian.exportacion import exportar
from rpa_dian.metricas import generar_informe, tabla_metricas
from rpa_dian.proceso import Factura, procesar_pdf

log = logging.getLogger("rpa_dian")


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


def extraer(
    consultas: Path,
    entrada: Path,
    salida: Path,
    imagenes: Path,
    metricas: Path | None = None,
) -> list[Factura]:
    """Procesa cada PDF `<CUFE>.pdf` de `entrada` con el NIT de su consulta.

    Si se indica `metricas`, escribe ahí metricas.csv e informe.md; usa los resultados de
    la descarga (descargas.csv en esa carpeta) cuando existen.
    """
    facturas, capas = [], {}
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
                continue
            log.info(
                "%s… factura %s: %d productos en %.1f s",
                consulta.cufe[:12],
                factura.encabezado.numero_factura or "?",
                len(factura.productos),
                factura.tiempos["total"],
            )
            facturas.append(factura)
            capas[factura.cufe] = capa_de_texto(pdf, consulta.nit)
    rutas = exportar(facturas, salida)
    log.info("%d facturas extraídas; CSV en %s", len(facturas), rutas[-1].parent)
    if metricas is not None:
        _escribir_metricas(metricas, facturas, capas)
    return facturas


def _escribir_metricas(carpeta: Path, facturas: list[Factura], capas: dict[str, str]) -> None:
    carpeta.mkdir(parents=True, exist_ok=True)
    descargas = carpeta / "descargas.csv"
    resultados = leer_resultados(descargas) if descargas.is_file() else []
    tabla_metricas(resultados, facturas, capas).to_csv(
        carpeta / "metricas.csv", index=False, encoding="utf-8-sig"
    )
    informe = carpeta / "informe.md"
    informe.write_text(generar_informe(resultados, facturas, capas), encoding="utf-8")
    log.info("Métricas e informe en %s", carpeta)


def todo(consultas: Path, carpeta: Path, modo: str, carpeta_descargas: Path, espera: float) -> None:
    """Proceso completo con todas las salidas bajo `carpeta`."""
    metricas = carpeta / "metricas"
    descargar(
        consultas, carpeta / "pdf", metricas / "descargas.csv", modo, carpeta_descargas, espera
    )
    extraer(consultas, carpeta / "pdf", carpeta / "csv", carpeta / "img", metricas)


def _argumentos(argv: list[str] | None) -> argparse.Namespace:
    analizador = argparse.ArgumentParser(
        prog="python -m rpa_dian",
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    _opciones_de_descarga(analizador)
    analizador.add_argument("--consultas", type=Path, default=config.RUTA_CONSULTAS)
    analizador.add_argument(
        "--carpeta", type=Path, default=config.DIR_SALIDA, help="carpeta de todas las salidas"
    )
    subcomandos = analizador.add_subparsers(dest="subcomando")

    sub = subcomandos.add_parser("descargar", help="CUFE + NIT -> PDF de la DIAN")
    sub.add_argument("--consultas", type=Path, default=config.RUTA_CONSULTAS)
    sub.add_argument("--salida", type=Path, default=config.DIR_PDF)
    sub.add_argument("--resultados", type=Path, default=config.DIR_METRICAS / "descargas.csv")
    _opciones_de_descarga(sub)

    sub = subcomandos.add_parser("extraer", help="PDF -> imágenes -> OCR -> CSV + informe")
    sub.add_argument("--consultas", type=Path, default=config.RUTA_CONSULTAS)
    sub.add_argument("--entrada", type=Path, default=config.DIR_PDF)
    sub.add_argument("--salida", type=Path, default=config.DIR_CSV)
    sub.add_argument("--imagenes", type=Path, default=config.DIR_IMG)
    sub.add_argument("--metricas", type=Path, default=config.DIR_METRICAS)
    return analizador.parse_args(argv)


def _opciones_de_descarga(analizador: argparse.ArgumentParser) -> None:
    analizador.add_argument(
        "--modo",
        choices=["asistido", "automatico"],
        default="asistido",
        help="asistido: navegador normal + carpeta de Descargas (predeterminado); "
        "automatico: Playwright (Cloudflare lo rechaza)",
    )
    analizador.add_argument("--descargas", type=Path, default=config.DIR_DESCARGAS)
    analizador.add_argument("--espera", type=float, default=300, help="segundos por factura")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    a = _argumentos(argv)
    if a.subcomando == "descargar":
        descargar(a.consultas, a.salida, a.resultados, a.modo, a.descargas, a.espera)
    elif a.subcomando == "extraer":
        extraer(a.consultas, a.entrada, a.salida, a.imagenes, a.metricas)
    else:
        todo(a.consultas, a.carpeta, a.modo, a.descargas, a.espera)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
