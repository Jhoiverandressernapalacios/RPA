"""Listado de consultas: un CUFE por fila, el NIT con que se consulta y su Estado.

Acepta dos formatos:
- Excel (.xlsx), p. ej. LISTADO_CUFE.xlsx, con las columnas CUFE, NIT y Estado. La
  columna Estado es la memoria del proceso: el robot escribe ahí cómo terminó cada
  consulta y, en la siguiente corrida, salta las filas que ya dicen "Validado".
- CSV con columnas cufe,nit (sin Estado), como data/consultas.csv.

El archivo puede venir de un tercero, así que se valida: el CUFE se usa en rutas, en la
URL de la consulta y para reconocer el PDF descargado.
"""

import csv
import logging
import re
import unicodedata
from dataclasses import dataclass, field
from pathlib import Path

import openpyxl

log = logging.getLogger(__name__)

PATRON_CUFE = re.compile(r"[0-9a-f]{96}")  # SHA-384 en hexadecimal
EXTENSIONES_EXCEL = (".xlsx", ".xlsm")
VALIDADO = "Validado"  # texto que marca una fila como terminada


@dataclass(frozen=True)
class Consulta:
    """Una factura por consultar.

    `estado` y `fila` vienen del archivo de origen y no cuentan al comparar consultas.
    """

    cufe: str
    nit: str  # sin puntos ni dígito de verificación; vacío si no se conoce
    estado: str = field(default="", compare=False)  # columna Estado del Excel
    fila: int = field(default=0, compare=False)  # número de fila en el archivo

    @property
    def validada(self) -> bool:
        """True si una corrida anterior ya la dejó en "Validado"."""
        return _normalizar(self.estado) == _normalizar(VALIDADO)


def leer_consultas(ruta: Path) -> list[Consulta]:
    """Lee y valida el listado (Excel o CSV), en el orden del archivo.

    Salta las filas sin CUFE. Lanza ValueError, indicando la fila, si un CUFE no tiene
    96 hexadecimales o está repetido.
    """
    if ruta.suffix.lower() in EXTENSIONES_EXCEL:
        filas = _filas_de_excel(ruta)
    else:
        filas = _filas_de_csv(ruta)
    consultas: list[Consulta] = []
    for numero, cufe, nit, estado in filas:
        cufe = cufe.strip().lower()
        if not cufe:
            continue
        if not PATRON_CUFE.fullmatch(cufe):
            raise ValueError(f"{ruta.name}, fila {numero}: el CUFE debe tener 96 hexadecimales")
        if any(c.cufe == cufe for c in consultas):
            raise ValueError(f"{ruta.name}, fila {numero}: CUFE repetido")
        consultas.append(Consulta(cufe, _limpiar_nit(nit), estado.strip(), numero))
    return consultas


def marcar_estado(ruta: Path, cufe: str, estado: str) -> bool:
    """Escribe `estado` en la columna Estado de la fila de ese CUFE (solo en Excel).

    Si la columna no existe, la crea con el encabezado "Estado". Devuelve False sin
    detener el proceso si el archivo es CSV, si el CUFE no está o si el Excel está
    abierto en otro programa (Windows bloquea el archivo).
    """
    if ruta.suffix.lower() not in EXTENSIONES_EXCEL:
        return False
    libro = openpyxl.load_workbook(ruta)
    hoja = libro.active
    columnas = _columnas(hoja)
    if "estado" not in columnas:
        columnas["estado"] = hoja.max_column + 1
        hoja.cell(1, columnas["estado"]).value = "Estado"
    for numero in range(2, hoja.max_row + 1):
        valor = hoja.cell(numero, columnas["cufe"]).value
        if valor is not None and str(valor).strip().lower() == cufe:
            hoja.cell(numero, columnas["estado"]).value = estado
            break
    else:
        log.warning("El CUFE %s… no está en %s", cufe[:12], ruta.name)
        return False
    try:
        libro.save(ruta)
    except PermissionError:
        log.warning("No se pudo escribir el Estado: cierra %s en Excel", ruta.name)
        return False
    return True


# --- Detalles de lectura ------------------------------------------------------------


def _filas_de_excel(ruta: Path) -> list[tuple[int, str, str, str]]:
    """(número de fila, CUFE, NIT, Estado) de la primera hoja, desde la fila 2."""
    hoja = openpyxl.load_workbook(ruta, read_only=True, data_only=True).active
    filas = list(hoja.iter_rows(values_only=True))
    if not filas:
        return []
    columnas = _columnas_de_encabezado(filas[0])
    if "cufe" not in columnas:
        raise ValueError(f"{ruta.name}: la primera fila debe tener la columna 'CUFE'")

    def celda(valores: tuple, nombre: str) -> str:
        """Texto de una columna (CUFE, NIT o Estado) en la fila; vacío si no hay dato."""
        indice = columnas.get(nombre)
        if indice is None or indice - 1 >= len(valores) or valores[indice - 1] is None:
            return ""
        return str(valores[indice - 1])

    return [
        (numero, celda(valores, "cufe"), celda(valores, "nit"), celda(valores, "estado"))
        for numero, valores in enumerate(filas[1:], start=2)
    ]


def _filas_de_csv(ruta: Path) -> list[tuple[int, str, str, str]]:
    """(número de fila, CUFE, NIT, "") de un CSV con columnas cufe,nit."""
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        lector = csv.DictReader(archivo)
        if not {"cufe", "nit"} <= set(lector.fieldnames or []):
            raise ValueError(f"{ruta} debe tener las columnas 'cufe' y 'nit'")
        return [
            (numero, fila["cufe"] or "", fila["nit"] or "", "")
            for numero, fila in enumerate(lector, start=2)  # la fila 1 es el encabezado
        ]


def _columnas(hoja) -> dict[str, int]:
    """Columnas (1, 2, 3…) de CUFE, NIT y Estado según el encabezado de la hoja."""
    encabezado = next(hoja.iter_rows(min_row=1, max_row=1, values_only=True), ())
    return _columnas_de_encabezado(encabezado)


def _columnas_de_encabezado(encabezado: tuple) -> dict[str, int]:
    """Ubica las columnas por nombre, sin importar mayúsculas, tildes ni espacios."""
    return {
        nombre: indice
        for indice, valor in enumerate(encabezado, start=1)
        if (nombre := _normalizar(str(valor or ""))) in ("cufe", "nit", "estado")
    }


def _normalizar(texto: str) -> str:
    """'  Éstado ' -> 'estado': minúsculas, sin tildes y sin espacios a los lados."""
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)
    )
    return sin_tildes.strip().lower()


def _limpiar_nit(nit: str) -> str:
    """'900.123.456-7' -> '900123456': sin puntos ni dígito de verificación."""
    if nit.endswith(".0"):  # Excel puede guardar el NIT como número decimal
        nit = nit[:-2]
    return "".join(c for c in nit.split("-")[0] if c.isdigit())
