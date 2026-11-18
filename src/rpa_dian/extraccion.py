"""Extracción de campos a partir del texto OCR de la representación gráfica DIAN.

Todas las funciones son puras: reciben texto (o palabras con posición) y devuelven datos.
No leen archivos ni llaman al OCR, para poder probarlas sin Tesseract.
"""

import logging
import math
import re
import unicodedata
from collections.abc import Sequence
from dataclasses import dataclass

log = logging.getLogger(__name__)

# Errores típicos del OCR dentro de campos numéricos
_CORRECCION_DIGITOS = str.maketrans({"O": "0", "o": "0", "I": "1", "l": "1"})

_SEP = r"\s*[:;.]?\s*"
PATRON_NUMERO = re.compile(
    r"N[uú]mero\s+de\s+Factura" + _SEP + r"([A-Za-z0-9][A-Za-z0-9\-]*)", re.I
)
PATRON_FECHA = re.compile(
    r"Fecha\s+de\s+Emisi[oó]n"
    + _SEP
    + r"([\dOo]{1,2})\s*[/\-.]\s*([\dOo]{1,2})\s*[/\-.]\s*([\dOo]{4})",
    re.I,
)
PATRON_NIT = re.compile(r"Nit\s+del\s+Emisor" + _SEP + r"([0-9OoIl][0-9OoIl. ]*[0-9OoIl])", re.I)
PATRON_VALOR = re.compile(r"^(\d{1,3}(?:\.\d{3})+|\d+)(?:,(\d+))?$")


@dataclass(frozen=True)
class Encabezado:
    numero_factura: str
    fecha_emision: str  # ISO 8601: AAAA-MM-DD
    nit_emisor: str


def extraer_encabezado(texto: str) -> Encabezado:
    """Obtiene número de factura, fecha de emisión y NIT del emisor del texto OCR."""
    return Encabezado(
        numero_factura=_numero_factura(texto),
        fecha_emision=_fecha_emision(texto),
        nit_emisor=_nit_emisor(texto),
    )


def a_numero(texto: str) -> float | None:
    """Convierte un valor en formato colombiano ('1.234,50', '$ 45.378,15') a float."""
    limpio = texto.replace("$", "").replace(" ", "").translate(_CORRECCION_DIGITOS)
    coincidencia = PATRON_VALOR.match(limpio)
    if not coincidencia:
        return None
    entero, decimales = coincidencia.groups()
    return float(f"{entero.replace('.', '')}.{decimales or 0}")


def _numero_factura(texto: str) -> str:
    coincidencia = PATRON_NUMERO.search(texto)
    if not coincidencia:
        log.warning("No se encontró el número de factura")
        return ""
    return coincidencia.group(1)


def _fecha_emision(texto: str) -> str:
    coincidencia = PATRON_FECHA.search(texto)
    if not coincidencia:
        log.warning("No se encontró la fecha de emisión")
        return ""
    dia, mes, anio = (int(p.translate(_CORRECCION_DIGITOS)) for p in coincidencia.groups())
    return f"{anio:04d}-{mes:02d}-{dia:02d}"


def _nit_emisor(texto: str) -> str:
    coincidencia = PATRON_NIT.search(texto)
    if not coincidencia:
        log.warning("No se encontró el NIT del emisor")
        return ""
    return re.sub(r"[. ]", "", coincidencia.group(1).translate(_CORRECCION_DIGITOS))


# --- Tabla "Detalles de Productos" -------------------------------------------


@dataclass(frozen=True)
class Palabra:
    """Palabra del OCR con su caja en píxeles: (x0, y0) arriba-izquierda, (x1, y1) abajo-derecha."""

    texto: str
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def xc(self) -> float:
        return (self.x0 + self.x1) / 2

    @property
    def yc(self) -> float:
        return (self.y0 + self.y1) / 2

    @property
    def alto(self) -> float:
        return self.y1 - self.y0


@dataclass(frozen=True)
class Producto:
    codigo: str
    descripcion: str
    cantidad: float | None
    precio_unitario: float | None


_COLUMNAS = ("nro", "codigo", "descripcion", "um", "cantidad", "precio", "descuento")
_OBLIGATORIAS = ("nro", "codigo", "descripcion", "cantidad", "precio")
_FIN_DE_TABLA = ("anticipos", "notas", "hoja")


def extraer_productos(
    palabras: Sequence[Palabra],
    lineas_horizontales: Sequence[float] | None = None,
    lineas_verticales: Sequence[float] | None = None,
) -> list[Producto]:
    """Reconstruye las filas de "Detalles de Productos" a partir de palabras con posición.

    Las columnas y filas se delimitan con las líneas de la cuadrícula detectadas en la
    imagen. Sin cuadrícula se usan los encabezados (solo fiable con celdas de una línea).
    """
    tabla = _ubicar_tabla(palabras, lineas_horizontales, lineas_verticales)
    if tabla is None:
        return []
    columnas, filas, cuerpo = tabla

    productos = []
    for arriba, abajo in filas:
        en_fila = [w for w in cuerpo if arriba <= w.yc < abajo]

        def celda(columna: str, en_fila=en_fila) -> list[list[str]]:
            return _lineas([w for w in en_fila if _en(w.xc, columnas[columna])])

        productos.append(
            Producto(
                codigo="".join("".join(linea) for linea in celda("codigo")),
                descripcion=" ".join(" ".join(linea) for linea in celda("descripcion")),
                cantidad=_valor(celda("cantidad")),
                precio_unitario=_valor(celda("precio")),
            )
        )
    return productos


Caja = tuple[float, float, float, float]  # x0, y0, x1, y1 en píxeles
_CELDAS = ("codigo", "descripcion", "cantidad", "precio")


def ubicar_celdas(
    palabras: Sequence[Palabra],
    lineas_horizontales: Sequence[float],
    lineas_verticales: Sequence[float],
) -> list[dict[str, Caja]]:
    """Caja de cada celda útil (código, descripción, cantidad, precio) por fila de la tabla.

    Requiere la cuadrícula: sin ella no hay bordes fiables para recortar las celdas.
    """
    if len(lineas_horizontales) < 2 or len(lineas_verticales) < 2:
        return []
    tabla = _ubicar_tabla(palabras, lineas_horizontales, lineas_verticales)
    if tabla is None:
        return []
    columnas, filas, _ = tabla
    return [
        {c: (columnas[c][0], arriba, columnas[c][1], abajo) for c in _CELDAS}
        for arriba, abajo in filas
    ]


def zona_tabla(palabras: Sequence[Palabra]) -> tuple[float, float] | None:
    """Franja vertical (y0, y1) de la tabla de productos: del encabezado hasta "Anticipos".

    Sirve para buscar las líneas de la cuadrícula solo ahí y no confundirlas con logos.
    """
    anclas = _encabezados_tabla(palabras)
    if anclas is None:
        return None
    return min(a.y0 for a in anclas.values()), _fin_de_tabla(palabras, anclas)


def producto_desde_textos(codigo: str, descripcion: str, cantidad: str, precio: str) -> Producto:
    """Arma un producto con el texto OCR de cada celda (las celdas pueden tener varias líneas)."""

    def lineas(texto: str) -> list[str]:
        return [" ".join(linea.split()) for linea in texto.splitlines() if linea.strip()]

    return Producto(
        codigo="".join(linea.replace(" ", "") for linea in lineas(codigo)),
        descripcion=" ".join(lineas(descripcion)),
        cantidad=a_numero("".join(lineas(cantidad))),
        precio_unitario=a_numero("".join(lineas(precio))),
    )


def _ubicar_tabla(
    palabras: Sequence[Palabra],
    lineas_horizontales: Sequence[float] | None,
    lineas_verticales: Sequence[float] | None,
) -> tuple[dict[str, tuple[float, float]], list[tuple[float, float]], list[Palabra]] | None:
    """Columnas, bandas de filas y palabras del cuerpo de la tabla de productos."""
    anclas = _encabezados_tabla(palabras)
    if anclas is None:
        log.warning("No se encontró el encabezado de la tabla de productos")
        return None
    columnas = _intervalos_de_columnas(anclas, lineas_verticales)
    inicio = max(a.y1 for a in anclas.values())
    fin = _fin_de_tabla(palabras, anclas)
    cuerpo = [w for w in palabras if inicio < w.yc < fin]
    lineas = sorted(
        y for y in (lineas_horizontales or []) if inicio - anclas["codigo"].alto <= y <= fin
    )
    if len(lineas) >= 2:
        filas = _filas_por_cuadricula(lineas, cuerpo, columnas)
    else:
        filas = _filas_por_numero(cuerpo, columnas, inicio, fin)
    return columnas, filas, cuerpo


def _fin_de_tabla(palabras: Sequence[Palabra], anclas: dict[str, Palabra]) -> float:
    """y donde empieza la primera sección posterior a la tabla (Anticipos, Notas, Hoja)."""
    inicio = max(a.y1 for a in anclas.values())
    return min(
        (
            w.y0
            for w in palabras
            if w.y0 > inicio and _normalizar(w.texto).startswith(_FIN_DE_TABLA)
        ),
        default=math.inf,
    )


def _filas_por_cuadricula(
    lineas: list[float], cuerpo: list[Palabra], columnas: dict[str, tuple[float, float]]
) -> list[tuple[float, float]]:
    """Cada tramo entre dos líneas horizontales con texto en código o descripción es una fila."""
    alto_minimo = 0.8 * min((w.alto for w in cuerpo), default=0)
    filas = []
    for arriba, abajo in zip(lineas, lineas[1:], strict=False):
        con_contenido = any(
            arriba <= w.yc < abajo
            and (_en(w.xc, columnas["codigo"]) or _en(w.xc, columnas["descripcion"]))
            for w in cuerpo
        )
        if abajo - arriba > alto_minimo and con_contenido:
            filas.append((arriba, abajo))
    return filas


def _filas_por_numero(
    cuerpo: list[Palabra], columnas: dict[str, tuple[float, float]], inicio: float, fin: float
) -> list[tuple[float, float]]:
    """Sin cuadrícula: cada número de la columna Nro abre una fila (celdas de una línea)."""
    numeros = sorted(
        (w for w in cuerpo if _en(w.xc, columnas["nro"]) and w.texto.isdigit()), key=lambda w: w.yc
    )
    if not numeros:
        return []
    final = fin if math.isfinite(fin) else max(w.y1 for w in cuerpo) + 1
    cortes = [inicio] + [(a.yc + b.yc) / 2 for a, b in zip(numeros, numeros[1:], strict=False)]
    return list(zip(cortes, cortes[1:] + [final], strict=False))


def _normalizar(texto: str) -> str:
    sin_tildes = "".join(
        c for c in unicodedata.normalize("NFD", texto) if not unicodedata.combining(c)
    )
    return sin_tildes.lower().strip(".:;,")


def _encabezados_tabla(palabras: Sequence[Palabra]) -> dict[str, Palabra] | None:
    for codigo in (w for w in palabras if _normalizar(w.texto) == "codigo"):
        banda = [w for w in palabras if abs(w.yc - codigo.yc) <= 1.5 * codigo.alto]
        anclas = {"codigo": codigo}
        for w in sorted(banda, key=lambda w: w.x0):
            nombre = _normalizar(w.texto)
            if nombre.startswith("nro") and w.x1 <= codigo.x0:
                anclas.setdefault("nro", w)
            elif nombre == "descripcion":
                anclas.setdefault("descripcion", w)
            elif nombre == "u/m":
                anclas.setdefault("um", w)
            elif nombre == "cantidad":
                anclas.setdefault("cantidad", w)
            elif nombre == "precio" and "cantidad" in anclas:
                anclas.setdefault("precio", w)
            elif nombre == "descuento":
                anclas.setdefault("descuento", w)
        if all(c in anclas for c in _OBLIGATORIAS):
            return anclas
    return None


def _intervalos_de_columnas(
    anclas: dict[str, Palabra], lineas_verticales: Sequence[float] | None
) -> dict[str, tuple[float, float]]:
    lineas = sorted(lineas_verticales or [])
    if len(lineas) >= 2:
        tramos = list(zip(lineas, lineas[1:], strict=False))
        return {
            nombre: next((t for t in tramos if _en(a.xc, t)), (math.nan, math.nan))
            for nombre, a in anclas.items()
        }
    ordenadas = sorted(anclas.items(), key=lambda par: par[1].xc)
    centros = [a.xc for _, a in ordenadas]
    bordes = (
        [-math.inf] + [(i + d) / 2 for i, d in zip(centros, centros[1:], strict=False)] + [math.inf]
    )
    return {nombre: (bordes[i], bordes[i + 1]) for i, (nombre, _) in enumerate(ordenadas)}


def _en(valor: float, tramo: tuple[float, float]) -> bool:
    return tramo[0] <= valor < tramo[1]


def _lineas(palabras: list[Palabra]) -> list[list[str]]:
    """Agrupa las palabras de una celda en líneas (por altura), de izquierda a derecha."""
    lineas: list[list[Palabra]] = []
    for w in sorted(palabras, key=lambda w: w.yc):
        if lineas and abs(w.yc - lineas[-1][0].yc) < 0.5 * w.alto:
            lineas[-1].append(w)
        else:
            lineas.append([w])
    return [[w.texto for w in sorted(linea, key=lambda w: w.x0)] for linea in lineas]


def _valor(lineas: list[list[str]]) -> float | None:
    return a_numero("".join(t for linea in lineas for t in linea if t != "$"))
