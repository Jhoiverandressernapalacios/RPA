"""Archivo de consultas: un CUFE por fila y el NIT con que se consulta (puede ir vacío)."""

import csv
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Consulta:
    cufe: str
    nit: str  # sin puntos ni dígito de verificación; vacío si no se conoce


def leer_consultas(ruta: Path) -> list[Consulta]:
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        if not {"cufe", "nit"} <= set(lector.fieldnames or []):
            raise ValueError(f"{ruta} debe tener las columnas 'cufe' y 'nit'")
        return [
            Consulta(
                cufe=fila["cufe"].strip().lower(),
                nit="".join(c for c in (fila["nit"] or "") if c.isdigit()),
            )
            for fila in lector
            if (fila["cufe"] or "").strip()
        ]
