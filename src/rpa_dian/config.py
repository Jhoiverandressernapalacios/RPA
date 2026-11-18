"""Rutas y parámetros del proceso.

Las rutas de Tesseract se pueden cambiar con las variables de entorno
TESSERACT_CMD y TESSDATA_PREFIX.
"""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

RUTA_CONSULTAS = RAIZ / "data" / "consultas.csv"
DIR_SALIDA = RAIZ / "output"
DIR_PDF = DIR_SALIDA / "pdf"
DIR_IMG = DIR_SALIDA / "img"
DIR_CSV = DIR_SALIDA / "csv"
DIR_METRICAS = DIR_SALIDA / "metricas"

URL_DIAN = "https://catalogo-vpfe.dian.gov.co/User/SearchDocument"
# Carpeta donde el navegador normal guarda las descargas (modo asistido)
DIR_DESCARGAS = Path(os.environ.get("RPA_DESCARGAS", str(Path.home() / "Downloads")))
ESPERA_CAPTCHA_S = 180
PAUSA_ENTRE_CONSULTAS_S = 5
# Navegador para el bot. "msedge" usa el Edge instalado en Windows; "" usa el Chromium de
# Playwright (no arrancó en el equipo de desarrollo: error de configuración en paralelo).
CANAL_NAVEGADOR = os.environ.get("RPA_NAVEGADOR", "msedge")

DPI_IMAGEN = 300
IDIOMA_OCR = "spa"
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
TESSDATA_DIR = os.environ.get(
    "TESSDATA_PREFIX", str(Path(os.environ.get("LOCALAPPDATA", "")) / "tessdata")
)
