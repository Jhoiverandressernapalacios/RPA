"""Modo asistido de descarga (automatización asistida).

El robot no controla el navegador: abre la consulta en el navegador normal de la persona
con el enlace oficial que ya trae el CUFE (Cloudflare valida solo) y vigila la carpeta de
Descargas hasta que llega el PDF, que valida, mueve al proyecto y cronometra.

En el navegador, la persona da una orden por página. Con la extensión "RPA DIAN - NIT
automático" (carpeta extension/) la consulta abre con el CUFE y el NIT ya escritos y solo
pulsa "Buscar" y luego "Descargar PDF" y "Aceptar"; sin la extensión, escribe el NIT a mano
o pulsa el favorito "RPA DIAN" (docs/marcador-dian.html), que hace esos pasos en la página
abierta cuando ella lo activa.
No hay ciclos entre facturas dentro del navegador ni se toca el captcha: cada consulta la
inicia una persona (ver docs/adr/0001-captcha-resuelto-por-persona.md).
"""

import re
import shutil
import subprocess
import time
import webbrowser
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlencode

from rpa_dian import config
from rpa_dian.consultas import Consulta
from rpa_dian.descarga import TiempoAgotado, validar_pdf

_DESCARGA_EN_CURSO = (".part", ".crdownload", ".tmp", ".partial")


def buscar_pdf(carpeta: Path, cufe: str, desde: float) -> Path | None:
    """El PDF descargado de ese CUFE, si ya está completo.

    Acepta exactamente `<CUFE>.pdf` o `<CUFE> (N).pdf` (nombre que pone el navegador si ya
    existía), modificado después de `desde`, con contenido y sin una descarga en curso al
    lado (`.part` de Firefox, `.crdownload` de Chrome/Edge).
    """
    patron = re.compile(rf"{re.escape(cufe)}( \(\d+\))?\.pdf", re.IGNORECASE)
    candidatos = []
    for ruta in carpeta.iterdir():
        if not (patron.fullmatch(ruta.name) and ruta.is_file()):
            continue
        estado = ruta.stat()
        en_curso = any(ruta.with_name(ruta.name + s).exists() for s in _DESCARGA_EN_CURSO)
        if estado.st_mtime >= desde and estado.st_size > 0 and not en_curso:
            candidatos.append(ruta)
    return max(candidatos, key=lambda r: r.stat().st_mtime, default=None)


def abrir_en_navegador(url: str) -> None:
    """Abre la URL en el navegador del modo asistido (Chrome por defecto, donde está la
    extensión del NIT) o, si no está instalado, en el predeterminado. Solo lo abre: no lo
    controla, así que Cloudflare valida el navegador normal de la persona."""
    ejecutable = config.NAVEGADOR_ASISTIDO
    if ejecutable and Path(ejecutable).is_file():
        subprocess.Popen([ejecutable, url])  # lista de argumentos: sin intérprete de comandos
    else:
        webbrowser.open(url)


def copiar_al_portapapeles(texto: str) -> None:
    """Portapapeles de Windows con `clip.exe` (sin dependencias extra)."""
    subprocess.run(["clip"], input=texto, text=True, check=True)


class ConsultorAsistido:
    """Cumple el mismo contrato que el bot automático: `consultar(...) -> Path`."""

    def __init__(
        self,
        carpeta_descargas: Path = config.DIR_DESCARGAS,
        espera_s: float = 300,
        abrir_url: Callable[[str], object] = abrir_en_navegador,
        copiar: Callable[[str], None] | None = None,
        avisar: Callable[[str], None] = print,
        dormir: Callable[[float], None] = time.sleep,
    ):
        """Recibe las dependencias que interactúan con el exterior (abrir el navegador,
        portapapeles, consola, espera) para poder reemplazarlas en las pruebas.
        """
        self.carpeta_descargas = carpeta_descargas
        self.espera_s = espera_s
        self.abrir_url = abrir_url
        # El portapapeles es opcional: Windows guarda su historial (Win+V) y el NIT puede
        # ser la cédula de una persona.
        self.copiar = copiar
        self.avisar = avisar
        self.dormir = dormir

    def consultar(self, consulta: Consulta, carpeta: Path, tiempos: dict[str, float]) -> Path:
        """Abre la consulta de una factura en el navegador normal y espera a que su PDF llegue
        completo a Descargas; lo valida, lo mueve a `carpeta` y devuelve su ruta. Lanza
        TiempoAgotado si no llega un PDF válido a tiempo.
        """
        inicio = time.time()
        desde = inicio - 1  # margen por la resolución de la hora de los archivos
        # Enlace oficial (el del QR de las facturas): abre el formulario con el CUFE escrito.
        # El NIT va en el fragmento (#nit=…): no viaja en la petición HTTP; el favorito lo
        # lee y lo borra de la barra de direcciones.
        consulta_url = urlencode({"DocumentKey": consulta.cufe})
        self.abrir_url(f"{config.URL_DIAN}?{consulta_url}#nit={consulta.nit}")
        if self.copiar:
            self.copiar(consulta.nit)
        self.avisar(
            f"\nCUFE {consulta.cufe[:12]}…: se abrió la consulta en tu navegador.\n"
            "  1. Con el CUFE y el NIT escritos, espera el visto verde y pulsa 'Buscar'.\n"
            "     (Sin la extensión de la carpeta extension/: pulsa el favorito 'RPA DIAN'.)\n"
            "  2. En el resultado, espera el visto verde y pulsa 'Descargar PDF' > 'Aceptar'.\n"
            f"  Esperando el PDF en {self.carpeta_descargas} (máximo {self.espera_s:.0f} s)…"
        )
        ultimo_error, tamano_anterior = "", -1
        while time.time() - inicio < self.espera_s:
            descargado = buscar_pdf(self.carpeta_descargas, consulta.cufe, desde)
            if descargado:
                tamano = descargado.stat().st_size
                if tamano == tamano_anterior:  # mismo tamaño en dos sondeos: terminó
                    try:
                        validar_pdf(descargado)
                    except ValueError as error:
                        ultimo_error = str(error)  # puede seguir llegando: se espera
                    else:
                        tiempos["persona"] = time.time() - inicio
                        return self._mover(descargado, carpeta / f"{consulta.cufe}.pdf", tiempos)
                tamano_anterior = tamano
            self.dormir(1)
        motivo = f": {ultimo_error}" if ultimo_error else ""
        raise TiempoAgotado(
            f"No llegó un PDF válido a {self.carpeta_descargas.name} en "
            f"{self.espera_s:.0f} s{motivo}"
        )

    def _mover(self, origen: Path, destino: Path, tiempos: dict[str, float]) -> Path:
        """Mueve el PDF de Descargas a la carpeta del proyecto y anota cuánto tardó."""
        t = time.time()
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(origen, destino)  # funciona aunque Descargas esté en otra unidad
        tiempos["descarga"] = time.time() - t
        self.avisar(f"  PDF recibido: {destino.name[:12]}….pdf")
        return destino
