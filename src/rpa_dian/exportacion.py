"""Un DataFrame por factura (una fila por producto) y su exportación a CSV."""

import re
from collections.abc import Iterable
from pathlib import Path

import pandas as pd

from rpa_dian.proceso import Factura

COLUMNAS_CSV = [
    "cufe",
    "numero_factura",
    "fecha_emision",
    "nit_emisor",
    "codigo",
    "descripcion",
    "cantidad",
    "precio_unitario",
]
_COLUMNAS_NUMERICAS = ["cantidad", "precio_unitario"]


def factura_a_dataframe(factura: Factura) -> pd.DataFrame:
    """Una fila por producto con los datos del encabezado repetidos.

    Si la factura no tiene productos legibles, queda una fila con el encabezado para no perderla.
    """
    encabezado = {
        "cufe": factura.cufe,
        "numero_factura": factura.encabezado.numero_factura,
        "fecha_emision": factura.encabezado.fecha_emision,
        "nit_emisor": factura.encabezado.nit_emisor,
    }
    filas = [
        encabezado
        | {
            "codigo": p.codigo,
            "descripcion": p.descripcion,
            "cantidad": p.cantidad,
            "precio_unitario": p.precio_unitario,
        }
        for p in factura.productos
    ] or [encabezado]
    tabla = pd.DataFrame(filas).reindex(columns=COLUMNAS_CSV)
    tabla[_COLUMNAS_NUMERICAS] = tabla[_COLUMNAS_NUMERICAS].astype(float)
    return tabla


def exportar(facturas: Iterable[Factura], carpeta: Path) -> list[Path]:
    """Escribe `<CUFE>.csv` por factura y `consolidado.csv` (UTF-8 con BOM para Excel).

    El consolidado reúne todos los `<CUFE>.csv` de la carpeta, también los de corridas
    anteriores: las filas ya validadas no se vuelven a procesar pero siguen en la base.
    """
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    for factura in facturas:
        rutas.append(_guardar(factura_a_dataframe(factura), carpeta / f"{factura.cufe}.csv"))
    por_factura = sorted(r for r in carpeta.glob("*.csv") if _PATRON_CSV.fullmatch(r.name))
    tablas = [pd.read_csv(r, encoding="utf-8-sig", dtype=str) for r in por_factura]
    consolidado = (
        pd.concat(tablas, ignore_index=True) if tablas else pd.DataFrame(columns=COLUMNAS_CSV)
    )
    rutas.append(_guardar(consolidado, carpeta / "consolidado.csv"))
    return rutas


_PATRON_CSV = re.compile(r"[0-9a-f]{96}\.csv")  # solo los CSV por factura


def _guardar(tabla: pd.DataFrame, ruta: Path) -> Path:
    """Guarda la tabla como CSV seguro y devuelve su ruta."""
    guardar_csv_seguro(tabla, ruta)
    return ruta


def guardar_csv_seguro(tabla: pd.DataFrame, ruta: Path) -> None:
    """CSV en UTF-8 con BOM (Excel) y sin fórmulas: los textos vienen del OCR de documentos
    de terceros, y un valor que empieza por = + - @ se ejecutaría como fórmula en Excel."""
    segura = tabla.copy()
    for columna in segura.columns:
        if not pd.api.types.is_numeric_dtype(segura[columna]):
            segura[columna] = segura[columna].map(neutralizar_formula)
    segura.to_csv(ruta, index=False, encoding="utf-8-sig")


def neutralizar_formula(valor):
    """Antepone un apóstrofo a los textos que Excel interpretaría como fórmula (empiezan por = + -
    @).
    """
    if isinstance(valor, str) and valor[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + valor
    return valor
