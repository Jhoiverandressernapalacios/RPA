"""Bot de descarga: consulta cada CUFE en el catálogo DIAN y guarda el PDF.

El captcha (Cloudflare Turnstile) no se toca: el bot espera a que tenga respuesta. En un
navegador controlado por Playwright, Cloudflare pide la casilla "Verifique que es un ser
humano"; la marca una persona en la ventana y el bot continúa solo.
"""

import csv
import logging
import re
import time
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from rpa_dian import config
from rpa_dian.consultas import Consulta

log = logging.getLogger(__name__)

OK, REQUIERE_NIT, SIN_RESULTADO, ERROR, TIMEOUT = (
    "ok",
    "requiere_nit",
    "sin_resultado",
    "error",
    "timeout",
)
ETAPAS = ("navegacion", "captcha", "consulta", "descarga", "persona", "total")


class SinResultado(Exception):
    """La DIAN no devolvió el documento (CUFE o NIT no coinciden, o no existe)."""


class TiempoAgotado(Exception):
    """El captcha o la descarga no terminaron a tiempo."""


@dataclass
class Resultado:
    """Cómo terminó la consulta de un CUFE: estado, detalle, PDF y tiempos."""

    cufe: str
    estado: str
    detalle: str = ""
    pdf: Path | None = None
    tiempos: dict[str, float] = field(default_factory=dict)


class Consultor(Protocol):
    """Contrato común de los modos de descarga (automático y asistido): consultar un CUFE y devolver
    la ruta del PDF.
    """

    def consultar(self, consulta: Consulta, carpeta: Path, tiempos: dict[str, float]) -> Path:
        """Descarga el PDF de la consulta y devuelve su ruta; anota los tiempos por etapa."""


def descargar_todas(
    consultas: Sequence[Consulta],
    consultor: Consultor | None,
    carpeta: Path,
    pausa: float = config.PAUSA_ENTRE_CONSULTAS_S,
    dormir: Callable[[float], None] = time.sleep,
    al_terminar: Callable[[Resultado], None] | None = None,
) -> list[Resultado]:
    """Procesa las consultas en orden, una a la vez. Un fallo no detiene las demás.

    `al_terminar` se llama apenas termina cada consulta (p. ej., para escribir su Estado
    en el Excel): así, si el proceso se interrumpe, queda registrado hasta dónde llegó.
    """
    resultados = []
    reales = [c for c in consultas if c.nit]
    for consulta in consultas:
        if not consulta.nit:
            resultado = Resultado(
                consulta.cufe,
                REQUIERE_NIT,
                "La DIAN exige el NIT del emisor o receptor y no se tiene",
            )
            log.info("%s… %s", consulta.cufe[:12], REQUIERE_NIT)
        else:
            if consultor is None:
                raise ValueError("Hay consultas con NIT pero no hay navegador para consultarlas")
            resultado = _consultar_una(consulta, consultor, carpeta)
        resultados.append(resultado)
        if al_terminar:
            al_terminar(resultado)
        if consulta.nit and consulta is not reales[-1]:
            dormir(pausa)  # una consulta a la vez y con pausa: ritmo humano para la DIAN
    return resultados


def _consultar_una(consulta: Consulta, consultor: Consultor, carpeta: Path) -> Resultado:
    """Consulta un CUFE con el consultor y convierte cualquier resultado o error en un Resultado con
    su estado; nunca lanza excepciones.
    """
    tiempos: dict[str, float] = {}
    inicio = time.monotonic()
    try:
        pdf = consultor.consultar(consulta, carpeta, tiempos)
        resultado = Resultado(consulta.cufe, OK, pdf=pdf, tiempos=tiempos)
    except SinResultado as error:
        resultado = Resultado(consulta.cufe, SIN_RESULTADO, str(error), tiempos=tiempos)
    except TiempoAgotado as error:
        resultado = Resultado(consulta.cufe, TIMEOUT, str(error), tiempos=tiempos)
    except Exception as error:  # el proceso sigue con el siguiente CUFE
        log.exception("Error inesperado con %s…", consulta.cufe[:12])
        detalle = detalle_seguro(error, consulta.cufe)
        resultado = Resultado(consulta.cufe, ERROR, detalle, tiempos=tiempos)
    tiempos["total"] = time.monotonic() - inicio
    log.info("%s… %s %s", consulta.cufe[:12], resultado.estado, resultado.detalle)
    return resultado


def detalle_seguro(error: Exception, cufe: str = "") -> str:
    """Mensaje de error para los CSV de evidencia: sin rutas locales (traen el usuario de
    Windows) ni CUFE completos, y sin caracteres que Excel tome como fórmula."""
    mensaje = f"{type(error).__name__}: {error}"
    mensaje = re.sub(r"[0-9a-f]{96}", lambda m: m.group()[:12] + "…", mensaje)
    mensaje = re.sub(r"[A-Za-z]:\\[^\s'\"]+", "<ruta>", mensaje)
    return mensaje[:200]


def guardar_resultados(resultados: Sequence[Resultado], ruta: Path) -> Path:
    """CSV con el estado y los tiempos (segundos) de cada consulta."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.writer(archivo, lineterminator="\n")
        escritor.writerow(["cufe", "estado", "detalle", "pdf", *(f"t_{e}" for e in ETAPAS)])
        for r in resultados:
            tiempos = [f"{r.tiempos[e]:.1f}" if e in r.tiempos else "" for e in ETAPAS]
            detalle = "'" + r.detalle if r.detalle[:1] in ("=", "+", "-", "@") else r.detalle
            escritor.writerow([r.cufe, r.estado, detalle, r.pdf or "", *tiempos])
    return ruta


def leer_resultados(ruta: Path) -> list[Resultado]:
    """Lee un CSV escrito por `guardar_resultados` (p. ej., para el informe posterior)."""
    with ruta.open(encoding="utf-8-sig", newline="") as archivo:
        return [
            Resultado(
                cufe=fila["cufe"],
                estado=fila["estado"],
                detalle=fila["detalle"],
                pdf=Path(fila["pdf"]) if fila["pdf"] else None,
                tiempos={e: float(fila[f"t_{e}"]) for e in ETAPAS if fila.get(f"t_{e}")},
            )
            for fila in csv.DictReader(archivo)
        ]


# --- Navegador real ------------------------------------------------------------


@contextmanager
def abrir_navegador(canal: str = config.CANAL_NAVEGADOR) -> Iterator["ConsultorDian"]:
    """Abre un navegador visible (una persona puede necesitar marcar el captcha)."""
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        navegador = playwright.chromium.launch(headless=False, channel=canal or None)
        try:
            contexto = navegador.new_context(accept_downloads=True, locale="es-CO")
            yield ConsultorDian(contexto.new_page())
        finally:
            navegador.close()


class ConsultorDian:
    """Recorre el flujo observado en la página (ver docs/reconocimiento-dian.md)."""

    def __init__(self, pagina, espera_captcha: float = config.ESPERA_CAPTCHA_S):
        """Recibe la página de Playwright y registra el evento de descarga para capturar el PDF
        cuando el navegador lo baje.
        """
        self.pagina = pagina
        self.espera_captcha = espera_captcha
        self._descargas: list = []
        # Playwright necesita una función de Python; no acepta métodos nativos como list.append.
        pagina.on("download", lambda descarga: self._descargas.append(descarga))

    def consultar(self, consulta: Consulta, carpeta: Path, tiempos: dict[str, float]) -> Path:
        """Recorre el flujo del portal: CUFE, NIT (aparece después), espera del captcha, Buscar y
        descarga del PDF. Anota el tiempo de cada etapa en `tiempos`.
        """
        from playwright.sync_api import TimeoutError as PlaywrightTimeout

        pagina = self.pagina
        t = time.monotonic()
        pagina.goto(config.URL_DIAN, wait_until="domcontentloaded")
        pagina.fill("#DocumentKey", consulta.cufe)
        nit = pagina.locator("#SearchDocumentNit")
        nit.wait_for(state="visible", timeout=15_000)  # aparece después de escribir el CUFE
        nit.fill(consulta.nit)
        tiempos["navegacion"] = time.monotonic() - t

        tiempos["captcha"] = self._esperar_captcha("formulario")

        t = time.monotonic()
        pagina.click("#search-document-form button[type=submit]")
        try:
            pagina.wait_for_url("**/Document/ShowDocumentToPublic**", timeout=30_000)
        except PlaywrightTimeout:
            mensaje = self._mensajes_de_error() or "La DIAN no devolvió el documento"
            raise SinResultado(mensaje) from None
        tiempos["consulta"] = time.monotonic() - t

        t, captcha_antes = time.monotonic(), tiempos["captcha"]
        pdf = self._descargar(consulta.cufe, carpeta, tiempos)
        # La página de resultado tiene su propio captcha: ese tiempo cuenta como captcha.
        tiempos["descarga"] = time.monotonic() - t - (tiempos["captcha"] - captcha_antes)
        return pdf

    def _token(self) -> bool:
        """True si algún widget de Cloudflare Turnstile de la página ya dio su respuesta."""
        return self.pagina.evaluate(
            "() => [...document.querySelectorAll('input[name=cf-turnstile-response]')]"
            ".some(e => e.value)"
        )

    def _esperar_captcha(self, donde: str) -> float:
        """Espera a que Cloudflare entregue su respuesta. Nunca interactúa con el widget."""
        inicio = time.monotonic()
        avisado = False
        while time.monotonic() - inicio < self.espera_captcha:
            if self._token():
                return time.monotonic() - inicio
            if not avisado and time.monotonic() - inicio > 5:
                log.warning(
                    "Captcha (%s): marca la casilla de Cloudflare en la ventana del navegador",
                    donde,
                )
                avisado = True
            self.pagina.wait_for_timeout(500)
        raise TiempoAgotado(f"Captcha sin resolver en {self.espera_captcha:.0f} s ({donde})")

    def _aceptar_aviso(self, espera_ms: int = 5_000) -> bool:
        """Pulsa el botón 'Aceptar' visible (avisos de la DIAN); False si no hay."""
        boton = self.pagina.locator("button:has-text('Aceptar'):visible").first
        try:
            boton.click(timeout=espera_ms)
            return True
        except Exception:
            return False

    def _descargar(self, cufe: str, carpeta: Path, tiempos: dict[str, float]) -> Path:
        """Descargar PDF -> aviso de contraseña -> archivo. Reintenta si falta el captcha."""
        carpeta.mkdir(parents=True, exist_ok=True)
        destino = carpeta / f"{cufe}.pdf"
        self._descargas.clear()
        for _ in range(3):
            tiempos["captcha"] += self._esperar_captcha("resultado")
            self.pagina.get_by_text("Descargar PDF").first.click()
            self._aceptar_aviso()
            inicio = time.monotonic()
            while time.monotonic() - inicio < 30:
                if self._descargas:
                    self._descargas.pop().save_as(destino)
                    validar_pdf(destino)
                    return destino
                if self.pagina.get_by_text("campo de seguridad no está completo").is_visible():
                    log.info("La página pidió esperar el captcha; se reintenta la descarga")
                    self._aceptar_aviso()
                    break
                self.pagina.wait_for_timeout(500)
            else:
                raise TiempoAgotado("La descarga no empezó en 30 s")
        raise TiempoAgotado("No se pudo descargar el PDF después de 3 intentos")

    def _mensajes_de_error(self) -> str:
        """Mensajes de validación que muestra la página tras una búsqueda fallida."""
        textos = self.pagina.locator(
            ".field-validation-error, .validation-summary-errors, .text-danger, .alert"
        ).all_inner_texts()
        return " | ".join(t.strip() for t in textos if t.strip())


MAX_BYTES_PDF = 20 * 1024 * 1024  # una representación gráfica pesa decenas de KB


def validar_pdf(ruta: Path) -> None:
    """Rechaza lo que no empieza como PDF o es desproporcionadamente grande."""
    if ruta.stat().st_size > MAX_BYTES_PDF:
        raise ValueError(f"{ruta.name[:12]}… pesa más de 20 MB: no es una factura")
    with ruta.open("rb") as archivo:
        if archivo.read(5) != b"%PDF-":
            raise ValueError(f"{ruta.name[:12]}… no es un PDF válido")
