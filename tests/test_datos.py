"""Valida el archivo de entrada con las consultas (CUFE + NIT) de la prueba."""

import csv
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
RUTA_CONSULTAS = RAIZ / "data" / "consultas.csv"
PATRON_CUFE = re.compile(r"^[0-9a-f]{96}$")
PATRON_NIT = re.compile(r"^\d*$")


def leer_filas() -> list[dict[str, str]]:
    with RUTA_CONSULTAS.open(encoding="utf-8", newline="") as archivo:
        return list(csv.DictReader(archivo))


def test_existe_el_archivo_de_consultas():
    assert RUTA_CONSULTAS.is_file()


def test_el_archivo_viejo_de_cufes_ya_no_existe():
    assert not (RAIZ / "data" / "cufes.txt").exists()


def test_tiene_las_columnas_cufe_y_nit():
    with RUTA_CONSULTAS.open(encoding="utf-8", newline="") as archivo:
        assert csv.DictReader(archivo).fieldnames == ["cufe", "nit"]


def test_tiene_exactamente_diez_consultas():
    assert len(leer_filas()) == 10


def test_cada_cufe_tiene_96_caracteres_hexadecimales():
    invalidos = [fila["cufe"] for fila in leer_filas() if not PATRON_CUFE.match(fila["cufe"])]
    assert invalidos == []


def test_el_nit_esta_vacio_o_solo_tiene_digitos():
    invalidos = [fila["nit"] for fila in leer_filas() if not PATRON_NIT.match(fila["nit"])]
    assert invalidos == []


def test_no_hay_cufes_repetidos():
    cufes = [fila["cufe"] for fila in leer_filas()]
    assert len(set(cufes)) == len(cufes)
