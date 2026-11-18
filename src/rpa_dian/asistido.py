"""Modo asistido de descarga (automatización asistida).

El robot no controla el navegador: abre la consulta en el navegador normal de la persona,
donde Cloudflare valida solo, pone en el portapapeles el CUFE y luego el NIT, y vigila la
carpeta de Descargas hasta que llega el PDF. La persona solo pega y pulsa los botones.
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
        preguntar: Callable[[str], str] = input,
        avisar: Callable[[str], None] = print,
        dormir: Callable[[float], None] = time.sleep,
    ):
        self.carpeta_descargas = carpeta_descargas
        self.espera_s = espera_s
        self.abrir_url = abrir_url
        self.copiar = copiar
        self.preguntar = preguntar
        self.avisar = avisar
        self.dormir = dormir

    def consultar(self, consulta: Consulta, carpeta: Path, tiempos: dict[str, float]) -> Path:
        inicio = time.time()
        desde = inicio - 1  # margen por la resolución de la hora de los archivos
        self.abrir_url(config.URL_DIAN)
        self.copiar(consulta.cufe)
        self.avisar(
            f"\nCUFE {consulta.cufe[:12]}…: se abrió la página de la DIAN en tu navegador.\n"
            "  1. Pega el CUFE (Ctrl+V) en 'CUFE o UUID'."
        )
        self.preguntar("  Presiona Enter aquí cuando lo hayas pegado… ")
        self.copiar(consulta.nit)
        self.avisar(
            "  2. Pega el NIT (Ctrl+V), espera el visto verde de Cloudflare y pulsa 'Buscar'.\n"
            "  3. En el resultado, espera el visto verde y pulsa 'Descargar PDF' > 'Aceptar'.\n"
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
