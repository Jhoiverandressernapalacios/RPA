"""Valida el archivo de entrada con los CUFE de la prueba."""

import re
from pathlib import Path

RUTA_CUFES = Path(__file__).resolve().parents[1] / "data" / "cufes.txt"
PATRON_CUFE = re.compile(r"^[0-9a-f]{96}$")


def leer_lineas() -> list[str]:
    return RUTA_CUFES.read_text(encoding="utf-8").splitlines()


def test_existe_el_archivo_de_cufes():
    assert RUTA_CUFES.is_file()


def test_tiene_exactamente_diez_cufes():
    assert len(leer_lineas()) == 10


def test_cada_cufe_tiene_96_caracteres_hexadecimales():
    invalidos = [linea for linea in leer_lineas() if not PATRON_CUFE.match(linea)]
    assert invalidos == []


def test_no_hay_cufes_repetidos():
    lineas = leer_lineas()
    assert len(set(lineas)) == len(lineas)
