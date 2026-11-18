"""Métricas del proceso: tiempos por etapa, estados y precisión del OCR.

La precisión se mide contra la capa de texto que el PDF trae incrustada: es la verdad de
referencia de la factura, pero la prueba pide extraer de las imágenes, así que la capa
solo se usa para medir, nunca para extraer.
"""

import re
from collections import Counter
from collections.abc import Sequence
from datetime import datetime

import pandas as pd

from rpa_dian.descarga import ETAPAS, Resultado
from rpa_dian.extraccion import extraer_encabezado
from rpa_dian.proceso import Factura

CAMPOS = (
    "numero_factura",
    "fecha_emision",
    "nit_emisor",
    "codigo",
    "descripcion",
    "cantidad",
    "precio_unitario",
)
Verificacion = dict[str, tuple[int, int]]  # campo -> (aciertos, verificados)

RESTRICCIONES = [
    "**La consulta exige CUFE + NIT** del emisor o receptor. La prueba solo entrega los "
    "CUFE y el NIT no se puede deducir (el CUFE es un hash), por eso esos CUFE terminan en "
    "`requiere_nit`.",
    "**Captcha Cloudflare Turnstile en el formulario y otra vez en el resultado.** En un "
    "navegador normal se valida solo; en uno controlado por un robot (Playwright) Cloudflare "
    "rechaza la verificación aunque una persona marque la casilla. No se oculta la "
    "automatización: la descarga se hace en modo asistido, con un clic de la persona por "
    "página (ver `docs/adr/0001-captcha-resuelto-por-persona.md`).",
    "**El PDF viene cifrado** con el NIT usado en la consulta; la extracción lo abre con ese NIT.",
    "**Descripciones:** el PDF parte las palabras al final de cada línea de la celda; el OCR "
    "no puede saber dónde había espacios, así que se conservan los cortes como espacios.",
    "**Letras parecidas:** secuencias como `III` pueden leerse como `II` en algunas fuentes; "
    "la precisión por campo lo refleja.",
]


def formato_colombiano(valor: float) -> str:
    """1260504.2 -> '1.260.504,20'"""
    entero, decimales = f"{valor:,.2f}".split(".")
    return f"{entero.replace(',', '.')},{decimales}"


def verificar_factura(factura: Factura, capa_de_texto: str) -> Verificacion | None:
    """Compara cada campo extraído con la capa de texto. None si el PDF no trae capa."""
    if not capa_de_texto.strip():
        return None
    referencia = extraer_encabezado(capa_de_texto)
    compacta = "".join(capa_de_texto.split()).upper()

    def esta_texto(texto: str) -> int:
        """Código o descripción (sin espacios: el PDF los parte en varias líneas). Menos de
        4 caracteres no prueba nada: aparecería en cualquier factura."""
        limpio = "".join(texto.split()).upper()
        return int(len(limpio) >= 4 and limpio in compacta)

    def esta_numero(valor: float | None) -> int:
        """El número completo, no dentro de otro: '1,00' no cuenta si solo aparece '21,00'."""
        if valor is None:
            return 0
        patron = rf"(?<![\d.,]){re.escape(formato_colombiano(valor))}(?![\d,])"
        return int(re.search(patron, capa_de_texto) is not None)

    resultado: Verificacion = {
        campo: (int(bool(valor) and valor == getattr(referencia, campo)), 1)
        for campo, valor in vars(factura.encabezado).items()
    }
    por_producto = {"codigo": [], "descripcion": [], "cantidad": [], "precio_unitario": []}
    for p in factura.productos:
        por_producto["codigo"].append(esta_texto(p.codigo))
        por_producto["descripcion"].append(esta_texto(p.descripcion))
        por_producto["cantidad"].append(esta_numero(p.cantidad))
        por_producto["precio_unitario"].append(esta_numero(p.precio_unitario))
    for campo, aciertos in por_producto.items():
        resultado[campo] = (sum(aciertos), len(aciertos))
    return resultado


def precision_por_campo(verificaciones: Sequence[Verificacion]) -> dict[str, float]:
    """Proporción de aciertos por campo y en total (solo campos verificados)."""
    aciertos, totales = Counter(), Counter()
    for verificacion in verificaciones:
        for campo, (bien, total) in verificacion.items():
            aciertos[campo] += bien
            totales[campo] += total
    precision = {c: aciertos[c] / totales[c] for c in CAMPOS if totales[c]}
    if sum(totales.values()):
        precision["total"] = sum(aciertos.values()) / sum(totales.values())
    return precision


def tabla_metricas(
    resultados: Sequence[Resultado],
    facturas: Sequence[Factura],
    capas: dict[str, str],
    fallos: dict[str, str] | None = None,
) -> pd.DataFrame:
    """Una fila por consulta: estado y tiempos de descarga + tiempos y precisión de extracción.

    `fallos` (CUFE -> motivo) son las facturas cuya extracción falló: quedan registradas
    con estado `error_extraccion` en vez de desaparecer.
    """
    fallos = fallos or {}
    por_cufe = {f.cufe: f for f in facturas}
    descargados = {r.cufe for r in resultados}
    estados = [(r.cufe, r) for r in resultados]
    estados += [(c, None) for c in [*por_cufe, *fallos] if c not in descargados]
    filas = []
    for cufe, resultado in estados:
        fila: dict = {"cufe": cufe}
        if resultado:
            fila |= {"estado": resultado.estado, "detalle": resultado.detalle}
            fila |= {f"t_{e}": resultado.tiempos.get(e) for e in ETAPAS}
        else:
            fila |= {"estado": "solo_extraccion", "detalle": ""}
        if cufe in fallos:
            fila |= {"estado": "error_extraccion", "detalle": fallos[cufe]}
        factura = por_cufe.get(cufe)
        if factura:
            verificacion = verificar_factura(factura, capas.get(cufe, ""))
            fila |= {
                "t_conversion": factura.tiempos.get("conversion"),
                "t_ocr": factura.tiempos.get("ocr"),
                "t_extraccion": factura.tiempos.get("total"),
                "productos": len(factura.productos),
                "campos_correctos": sum(b for b, _ in verificacion.values())
                if verificacion
                else None,
                "campos_verificados": sum(t for _, t in verificacion.values())
                if verificacion
                else None,
            }
        filas.append(fila)
    if not filas:  # sin consultas en esta corrida: CSV vacío pero con encabezados
        return pd.DataFrame(columns=["cufe", "estado", "detalle"])
    return pd.DataFrame(filas).rename(columns={"t_total": "t_descarga_total"})


def generar_informe(
    resultados: Sequence[Resultado],
    facturas: Sequence[Factura],
    capas: dict[str, str],
    titulo: str = "Informe de ejecución",
    fallos: dict[str, str] | None = None,
) -> str:
    """Informe en Markdown. Muestra solo los primeros 12 caracteres de cada CUFE y ningún
    dato de producto ni del comprador."""
    tabla = tabla_metricas(resultados, facturas, capas, fallos)
    verificaciones = [
        v for f in facturas if (v := verificar_factura(f, capas.get(f.cufe, ""))) is not None
    ]
    precision = precision_por_campo(verificaciones)
    lineas = [
        f"# {titulo}",
        "",
        f"Generado: {datetime.now():%Y-%m-%d %H:%M}",
        "",
        "## Resumen",
        "",
        f"- Consultas: {len(resultados)}",
        f"- Facturas extraídas: {len(facturas)}",
        f"- Facturas con error de extracción: {len(fallos or {})}",
        f"- Productos extraídos: {sum(len(f.productos) for f in facturas)}",
        "",
        "### Estados de la descarga",
        "",
        "| Estado | Consultas |",
        "|---|---|",
        *(f"| {e} | {n} |" for e, n in Counter(r.estado for r in resultados).items()),
        "",
        "## Tiempos (segundos)",
        "",
        "| Etapa | Promedio | Total | Facturas |",
        "|---|---|---|---|",
        *_filas_de_tiempo(tabla),
        "",
        "## Precisión del OCR por campo",
        "",
    ]
    if precision:
        lineas += [
            "Comparación de cada campo extraído de las imágenes contra la capa de texto del PDF.",
            "",
            "| Campo | Precisión |",
            "|---|---|",
            *(f"| {campo} | {_porcentaje(valor)} |" for campo, valor in precision.items()),
        ]
    else:
        lineas.append("No hubo facturas con capa de texto para verificar.")
    lineas += [
        "",
        "## Detalle por consulta",
        "",
        "| CUFE | Estado | Productos | Campos correctos | t humano | t extracción |",
        "|---|---|---|---|---|---|",
        *(_fila_detalle(fila) for _, fila in tabla.iterrows()),
        "",
        "## Restricciones del proceso",
        "",
        *(f"- {r}" for r in RESTRICCIONES),
        "",
    ]
    return "\n".join(lineas)


_ETIQUETAS_TIEMPO = {
    "t_persona": "Tiempo humano (captcha y clics, modo asistido)",
    "t_captcha": "Espera del captcha (modo automático)",
    "t_descarga_total": "Descarga total por consulta",
    "t_conversion": "PDF a imágenes",
    "t_ocr": "OCR (página y celdas)",
    "t_extraccion": "Extracción total por factura",
}


def _filas_de_tiempo(tabla: pd.DataFrame) -> list[str]:
    """Filas Markdown con el promedio y el total de cada etapa medida."""
    filas = []
    for columna, etiqueta in _ETIQUETAS_TIEMPO.items():
        if columna in tabla and tabla[columna].notna().any():
            valores = tabla[columna].dropna()
            filas.append(
                f"| {etiqueta} | {valores.mean():.1f} | {valores.sum():.1f} | {len(valores)} |"
            )
    return filas or ["| (sin tiempos registrados) | | | |"]


def _fila_detalle(fila: pd.Series) -> str:
    """Fila Markdown del detalle de una consulta (CUFE recortado a 12 caracteres)."""

    def valor(columna: str, formato: str = "{:.1f}") -> str:
        """Dato formateado de una columna; vacío si no se midió."""
        dato = fila.get(columna)
        return "" if dato is None or pd.isna(dato) else formato.format(dato)

    correctos = ""
    if pd.notna(fila.get("campos_verificados", None)):
        correctos = f"{valor('campos_correctos', '{:.0f}')}/{valor('campos_verificados', '{:.0f}')}"
    return (
        f"| {fila['cufe'][:12]}… | {fila['estado']} | {valor('productos', '{:.0f}')} "
        f"| {correctos} | {valor('t_persona')} | {valor('t_extraccion')} |"
    )


def _porcentaje(valor: float) -> str:
    """0.909 -> '90,9 %' (coma decimal, como en Colombia)."""
    return f"{valor * 100:.1f}".replace(".", ",") + " %"
