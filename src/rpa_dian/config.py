"""Rutas y parámetros del proceso.

Las rutas de Tesseract se pueden cambiar con las variables de entorno
TESSERACT_CMD y TESSDATA_PREFIX.
"""

import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[2]

# Listado de consultas. Si existe LISTADO_CUFE.xlsx en la raíz (CUFE, NIT, Estado; fuera de
# Git), el proceso arranca desde ahí; si no, usa los 10 CUFE de la prueba.
RUTA_LISTADO = RAIZ / "LISTADO_CUFE.xlsx"
RUTA_CONSULTAS_PRUEBA = RAIZ / "data" / "consultas.csv"
RUTA_CONSULTAS = RUTA_LISTADO if RUTA_LISTADO.is_file() else RUTA_CONSULTAS_PRUEBA
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
# Navegador normal donde el modo asistido abre las consultas (sin controlarlo). Por defecto
# Chrome, donde se instala la extensión que escribe el NIT; si no existe, se usa el
# navegador predeterminado de Windows.
NAVEGADOR_ASISTIDO = os.environ.get(
    "RPA_NAVEGADOR_ASISTIDO", r"C:\Program Files\Google\Chrome\Application\chrome.exe"
)

DPI_IMAGEN = 300
IDIOMA_OCR = "spa"
TESSERACT_CMD = os.environ.get("TESSERACT_CMD", r"C:\Program Files\Tesseract-OCR\tesseract.exe")
TESSDATA_DIR = os.environ.get(
    "TESSDATA_PREFIX", str(Path(os.environ.get("LOCALAPPDATA", "")) / "tessdata")
)
