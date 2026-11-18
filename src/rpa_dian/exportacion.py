"""Un DataFrame por factura (una fila por producto) y su exportación a CSV."""

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
    """Escribe `<CUFE>.csv` por factura y `consolidado.csv` (UTF-8 con BOM para Excel)."""
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas, tablas = [], []
    for factura in facturas:
        tabla = factura_a_dataframe(factura)
        rutas.append(_guardar(tabla, carpeta / f"{factura.cufe}.csv"))
        tablas.append(tabla)
    consolidado = (
        pd.concat(tablas, ignore_index=True) if tablas else pd.DataFrame(columns=COLUMNAS_CSV)
    )
    rutas.append(_guardar(consolidado, carpeta / "consolidado.csv"))
    return rutas


def _guardar(tabla: pd.DataFrame, ruta: Path) -> Path:
    tabla.to_csv(ruta, index=False, encoding="utf-8-sig")
    return ruta
