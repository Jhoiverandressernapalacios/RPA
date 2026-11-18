"""Archivo de consultas: un CUFE por fila y el NIT con que se consulta (puede ir vacío).

El archivo puede venir de un tercero, así que se valida: el CUFE se usa en rutas, en la
URL de la consulta y para reconocer el PDF descargado.
"""

import csv
import re
from dataclasses import dataclass
from pathlib import Path

PATRON_CUFE = re.compile(r"[0-9a-f]{96}")  # SHA-384 en hexadecimal


@dataclass(frozen=True)
class Consulta:
    cufe: str
    nit: str  # sin puntos ni dígito de verificación; vacío si no se conoce


def leer_consultas(ruta: Path) -> list[Consulta]:
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        if not {"cufe", "nit"} <= set(lector.fieldnames or []):
            raise ValueError(f"{ruta} debe tener las columnas 'cufe' y 'nit'")
        consultas: list[Consulta] = []
        for numero, fila in enumerate(lector, start=2):  # la fila 1 es el encabezado
            cufe = (fila["cufe"] or "").strip().lower()
            if not cufe:
                continue
            if not PATRON_CUFE.fullmatch(cufe):
                raise ValueError(f"{ruta.name}, fila {numero}: el CUFE debe tener 96 hexadecimales")
            if any(c.cufe == cufe for c in consultas):
                raise ValueError(f"{ruta.name}, fila {numero}: CUFE repetido")
            consultas.append(Consulta(cufe, _limpiar_nit(fila["nit"] or "")))
        return consultas


def _limpiar_nit(nit: str) -> str:
    """'900.123.456-7' -> '900123456': sin puntos ni dígito de verificación."""
    return "".join(c for c in nit.split("-")[0] if c.isdigit())
