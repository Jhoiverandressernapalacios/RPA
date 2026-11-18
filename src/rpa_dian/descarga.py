"""Bot de descarga: consulta cada CUFE en el catálogo DIAN y guarda el PDF.

El captcha (Cloudflare Turnstile) no se toca: el bot espera a que tenga respuesta. En un
navegador controlado por Playwright, Cloudflare pide la casilla "Verifique que es un ser
humano"; la marca una persona en la ventana y el bot continúa solo.
"""

import csv
import logging
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
ETAPAS = ("navegacion", "captcha", "consulta", "descarga", "total")


class SinResultado(Exception):
    """La DIAN no devolvió el documento (CUFE o NIT no coinciden, o no existe)."""


class TiempoAgotado(Exception):
    """El captcha o la descarga no terminaron a tiempo."""


@dataclass
class Resultado:
    cufe: str
    estado: str
    detalle: str = ""
    pdf: Path | None = None
    tiempos: dict[str, float] = field(default_factory=dict)


class Consultor(Protocol):
    def consultar(self, consulta: Consulta, carpeta: Path, tiempos: dict[str, float]) -> Path:
        """Descarga el PDF de la consulta y devuelve su ruta; anota los tiempos por etapa."""


def descargar_todas(
    consultas: Sequence[Consulta],
    consultor: Consultor | None,
    carpeta: Path,
    pausa: float = config.PAUSA_ENTRE_CONSULTAS_S,
    dormir: Callable[[float], None] = time.sleep,
) -> list[Resultado]:
    """Procesa las consultas en orden, una a la vez. Un fallo no detiene las demás."""
    resultados = []
    reales = [c for c in consultas if c.nit]
    for consulta in consultas:
        if not consulta.nit:
            resultados.append(
                Resultado(
                    consulta.cufe,
                    REQUIERE_NIT,
                    "La DIAN exige el NIT del emisor o receptor y no se tiene",
                )
            )
            log.info("%s… %s", consulta.cufe[:12], REQUIERE_NIT)
            continue
        if consultor is None:
            raise ValueError("Hay consultas con NIT pero no hay navegador para consultarlas")
        resultados.append(_consultar_una(consulta, consultor, carpeta))
        if consulta is not reales[-1]:
            dormir(pausa)
    return resultados


def _consultar_una(consulta: Consulta, consultor: Consultor, carpeta: Path) -> Resultado:
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
        detalle = f"{type(error).__name__}: {error}"
        resultado = Resultado(consulta.cufe, ERROR, detalle, tiempos=tiempos)
    tiempos["total"] = time.monotonic() - inicio
    log.info("%s… %s %s", consulta.cufe[:12], resultado.estado, resultado.detalle)
    return resultado


def guardar_resultados(resultados: Sequence[Resultado], ruta: Path) -> Path:
    """CSV con el estado y los tiempos (segundos) de cada consulta."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    with ruta.open("w", encoding="utf-8-sig", newline="") as archivo:
        escritor = csv.writer(archivo, lineterminator="\n")
        escritor.writerow(["cufe", "estado", "detalle", "pdf", *(f"t_{e}" for e in ETAPAS)])
        for r in resultados:
            tiempos = [f"{r.tiempos[e]:.1f}" if e in r.tiempos else "" for e in ETAPAS]
            escritor.writerow([r.cufe, r.estado, r.detalle, r.pdf or "", *tiempos])
    return ruta


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
        self.pagina = pagina
        self.espera_captcha = espera_captcha
        self._descargas: list = []
        # Playwright necesita una función de Python; no acepta métodos nativos como list.append.
        pagina.on("download", lambda descarga: self._descargas.append(descarga))

    def consultar(self, consulta: Consulta, carpeta: Path, tiempos: dict[str, float]) -> Path:
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
                    _validar_pdf(destino)
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
        textos = self.pagina.locator(
            ".field-validation-error, .validation-summary-errors, .text-danger, .alert"
        ).all_inner_texts()
        return " | ".join(t.strip() for t in textos if t.strip())


def _validar_pdf(ruta: Path) -> None:
    with ruta.open("rb") as archivo:
        if archivo.read(5) != b"%PDF-":
            raise ValueError(f"{ruta.name} no es un PDF válido")
