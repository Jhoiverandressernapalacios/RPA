"""Modo asistido de descarga (automatización asistida).

El robot no controla el navegador: abre la consulta en el navegador normal de la persona
con el enlace oficial que ya trae el CUFE (Cloudflare valida solo), pone el NIT en el
portapapeles y vigila la carpeta de Descargas hasta que llega el PDF. La persona pega el
NIT y pulsa "Buscar", "Descargar PDF" y "Aceptar".
Así se respeta el captcha: nadie engaña a Cloudflare, simplemente no hay automatización
dentro del navegador.
"""

import os
import subprocess
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path

from rpa_dian import config
from rpa_dian.consultas import Consulta
from rpa_dian.descarga import TiempoAgotado, validar_pdf


def buscar_pdf(carpeta: Path, cufe: str, desde: float) -> Path | None:
    """El PDF más reciente de ese CUFE en `carpeta` modificado después de `desde`.

    Acepta `<CUFE>.pdf` y `<CUFE> (1).pdf` (nombre que pone el navegador si ya existía).
    Las descargas en curso (`.crdownload`, `.tmp`) no terminan en `.pdf` y se ignoran.
    """
    candidatos = [
        ruta
        for ruta in carpeta.glob(f"{cufe}*.pdf")
        if ruta.is_file() and ruta.stat().st_mtime >= desde
    ]
    return max(candidatos, key=lambda r: r.stat().st_mtime, default=None)


def copiar_al_portapapeles(texto: str) -> None:
    """Portapapeles de Windows con `clip.exe` (sin dependencias extra)."""
    subprocess.run(["clip"], input=texto, text=True, check=True)


class ConsultorAsistido:
    """Cumple el mismo contrato que el bot automático: `consultar(...) -> Path`."""

    def __init__(
        self,
        carpeta_descargas: Path = config.DIR_DESCARGAS,
        espera_s: float = 300,
        abrir_url: Callable[[str], object] = webbrowser.open,
        copiar: Callable[[str], None] = copiar_al_portapapeles,
        avisar: Callable[[str], None] = print,
        dormir: Callable[[float], None] = time.sleep,
    ):
        self.carpeta_descargas = carpeta_descargas
        self.espera_s = espera_s
        self.abrir_url = abrir_url
        self.copiar = copiar
        self.avisar = avisar
        self.dormir = dormir

    def consultar(self, consulta: Consulta, carpeta: Path, tiempos: dict[str, float]) -> Path:
        inicio = time.time()
        desde = inicio - 1  # margen por la resolución de la hora de los archivos
        # Enlace oficial (el mismo del QR de las facturas): abre el formulario con el CUFE
        # escrito. El NIT va en el fragmento (#nit=…), que el navegador no envía a la DIAN;
        # lo usa el botón de favoritos (docs/marcador-dian.html) cuando la persona lo pulsa.
        # También queda en el portapapeles por si se prefiere pegarlo.
        self.abrir_url(f"{config.URL_DIAN}?DocumentKey={consulta.cufe}#nit={consulta.nit}")
        self.copiar(consulta.nit)
        self.avisar(
            f"\nCUFE {consulta.cufe[:12]}…: se abrió la consulta en tu navegador.\n"
            "  1. Pulsa el favorito 'RPA DIAN': escribe el NIT, espera el visto verde y busca.\n"
            "  2. En el resultado, pulsa otra vez 'RPA DIAN': espera el visto verde y descarga.\n"
            f"  Esperando el PDF en {self.carpeta_descargas} (máximo {self.espera_s:.0f} s)…"
        )
        while time.time() - inicio < self.espera_s:
            descargado = buscar_pdf(self.carpeta_descargas, consulta.cufe, desde)
            if descargado:
                tiempos["persona"] = time.time() - inicio
                return self._mover(descargado, carpeta / f"{consulta.cufe}.pdf", tiempos)
            self.dormir(1)
        raise TiempoAgotado(
            f"No llegó el PDF a {self.carpeta_descargas.name} en {self.espera_s:.0f} s "
            "(revisa que la carpeta de Descargas sea la correcta)"
        )

    def _mover(self, origen: Path, destino: Path, tiempos: dict[str, float]) -> Path:
        t = time.time()
        validar_pdf(origen)
        destino.parent.mkdir(parents=True, exist_ok=True)
        os.replace(origen, destino)
        tiempos["descarga"] = time.time() - t
        self.avisar(f"  PDF recibido: {destino.name[:12]}….pdf")
        return destino
