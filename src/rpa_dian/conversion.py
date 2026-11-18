"""Apertura del PDF cifrado de la DIAN y conversión de sus páginas a imágenes PNG."""

from pathlib import Path

import pymupdf

from rpa_dian import config


class PdfProtegidoError(Exception):
    """El PDF no se pudo abrir con el NIT indicado."""


def abrir_pdf(ruta: Path, nit: str) -> pymupdf.Document:
    """Abre el PDF; si está cifrado, usa el NIT de la consulta como contraseña."""
    documento = pymupdf.open(ruta)
    if documento.needs_pass and not documento.authenticate(nit):
        documento.close()
        raise PdfProtegidoError(f"El NIT indicado no abre el PDF {ruta.name}")
    return documento


def pdf_a_imagenes(ruta: Path, nit: str, carpeta: Path, dpi: int = config.DPI_IMAGEN) -> list[Path]:
    """Guarda cada página como `<nombre>_p<N>.png` y devuelve las rutas en orden."""
    carpeta.mkdir(parents=True, exist_ok=True)
    rutas = []
    with abrir_pdf(ruta, nit) as documento:
        for numero, pagina in enumerate(documento, start=1):
            destino = carpeta / f"{ruta.stem}_p{numero}.png"
            pagina.get_pixmap(dpi=dpi).save(destino)
            rutas.append(destino)
    return rutas


def capa_de_texto(ruta: Path, nit: str) -> str:
    """Texto incrustado en el PDF, si lo trae. Solo sirve para medir la precisión del OCR."""
    with abrir_pdf(ruta, nit) as documento:
        return "\n".join(pagina.get_text() for pagina in documento)
