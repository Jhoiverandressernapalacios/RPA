# Spec: RPA DIAN — Descarga y extracción de facturas — V1

> Estado: **aprobada** (2026-11-17) · **Actualizada** el 2026-11-18 con los hallazgos del reconocimiento de la DIAN ([`docs/reconocimiento-dian.md`](docs/reconocimiento-dian.md)): la consulta exige CUFE + NIT y el PDF viene cifrado con ese NIT.
> Fuente: `PRUEBA ANALISTA DE INNOVACION 2026 (1) (3) (2) (2).docx` (prueba técnica, plazo 24 h)

## Mapa de capacidades

El requerimiento agrupa dos capacidades que se prueban por separado. Se especifican juntas en este documento por el tamaño del proyecto, pero se construyen y verifican como módulos independientes.

| Módulo | Responsabilidad | Depende de |
|---|---|---|
| `descarga-dian` | Abrir el catálogo DIAN, consultar cada CUFE con su NIT, esperar a que una persona resuelva el captcha, descargar el PDF | — |
| `extraccion-ocr` | PDF cifrado → abrir con el NIT → imagen → texto (OCR) → campos → DataFrame → CSV | Solo de que existan PDF en `output/pdf/` y su NIT |
| `metricas` | Medir tiempos por CUFE y por etapa, estado de cada uno y precisión del OCR | Ambos (los instrumenta) |

Orden de construcción: `extraccion-ocr` (se puede probar ya con PDF de ejemplo) → `descarga-dian` → `metricas` (se va agregando durante ambos) → integración.

## Objetivo

Construir en Python un proceso automatizado que:

1. **Descarga:** entre a `https://catalogo-vpfe.dian.gov.co/User/SearchDocument`, consulte los 10 CUFE de la prueba y descargue el PDF de la representación gráfica de cada factura.
2. **Extracción:** convierta cada PDF en imagen, extraiga el texto con OCR y obtenga:
   - De "Datos del Documento" y "Datos del Emisor/Vendedor": **número de factura, fecha de emisión, NIT del emisor**.
   - De la tabla "Detalles del Producto": **código, descripción, cantidad, precio unitario**.
3. **Salida:** un DataFrame por factura, exportado a CSV.
4. **Reporte:** tiempos empleados, métricas y restricciones del proceso.

**Usuario:** el evaluador de la prueba, que debe poder clonar el repositorio, seguir el README y reproducir el resultado.

### Decisión sobre el captcha

El enunciado pide que el bot resuelva el captcha. **V1 no lo hace**: el bot se detiene en el captcha, una persona lo resuelve en la ventana del navegador y el bot continúa solo. Saltarse un control anti-bots de un sitio del Estado no se implementa en este proyecto. La decisión queda registrada en `docs/adr/0001-captcha-resuelto-por-persona.md` y explicada en el README y en el informe como restricción del proceso.

### Hallazgos del reconocimiento (2026-11-18)

1. **La consulta exige CUFE + NIT** (del emisor o del receptor, sin puntos ni dígito de verificación). La prueba solo entrega los CUFE, y el NIT no se puede deducir del CUFE porque este es un hash.
2. **El PDF descargado está cifrado** y su contraseña es el NIT usado en la consulta.
3. **El captcha es Cloudflare Turnstile.** Pasa cuando una persona lo resuelve en un navegador normal. En navegadores embebidos o automatizados puede fallar; eso se comprueba en T9 y, si falla, se documenta como restricción, sin ocultar la automatización.

**Consecuencia:** la entrada es un CSV `cufe,nit`. Los 10 CUFE de la prueba van con el NIT vacío y terminan en el estado `requiere_nit`, que el informe reporta como restricción. El flujo completo se valida con facturas reales del usuario en `privado/`, que nunca se sube al repositorio.

## Stack técnico

| Pieza | Herramienta | Para qué |
|---|---|---|
| Lenguaje | Python 3.12 | — |
| Navegador | Playwright (API síncrona, Chromium, modo visible) | Bot de descarga |
| PDF → imagen | PyMuPDF (`import pymupdf`; el alias `fitz` está obsoleto) a 300 dpi | Exportar imágenes |
| OCR | Tesseract 5 + paquete de idioma `spa`, vía `pytesseract` | Encabezado: OCR de página (psm 4). Tabla: se ubica con las palabras del encabezado (psm 11), se detecta su cuadrícula en la imagen y cada celda se lee por separado (psm 6); precios y cantidades se leen a 3 escalas y se votan carácter por carácter |
| Imagen | NumPy | Detección de las líneas de la cuadrícula y limpieza de bordes de celda |
| Imagen | Pillow | Preprocesado básico (escala de grises, umbral) |
| Datos | pandas | DataFrames y CSV |
| Pruebas | pytest | Pruebas unitarias e integración |
| Estilo | ruff | Lint y formato |

Las versiones exactas se fijan en `requirements.txt` al instalar.

**Prerrequisitos que hoy no están en el equipo:** Python y Tesseract (Git ya está instalado).

## Comandos (PowerShell)

```powershell
# Entorno
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m playwright install chromium

# Proceso completo (descarga + extracción + métricas)
python -m rpa_dian

# Por etapas
python -m rpa_dian descargar --consultas data/consultas.csv --salida output/pdf
python -m rpa_dian extraer --consultas data/consultas.csv --entrada output/pdf --salida output/csv

# Validación con facturas reales (archivo local, fuera de Git)
python -m rpa_dian --consultas privado/consultas.csv

# Calidad
pytest -q
ruff check .
ruff format .
```

## Estructura del proyecto

```
RPA/
├── SPEC.md                    → Esta especificación
├── README.md                  → Instalación, uso, resultados, restricciones
├── requirements.txt
├── data/
│   └── consultas.csv          → Columnas cufe,nit: los 10 CUFE de la prueba (NIT vacío)
├── privado/                   → No se sube al repositorio: facturas reales del usuario
│   ├── consultas.csv          →   CUFE + NIT para validar el flujo completo
│   └── pdf/                   →   PDF reales descargados
├── src/rpa_dian/
│   ├── __main__.py            → Punto de entrada y subcomandos
│   ├── config.py              → Rutas, tiempos de espera, dpi
│   ├── consultas.py           → Lectura del CSV cufe,nit
│   ├── descarga.py            → Bot Playwright (módulo descarga-dian)
│   ├── conversion.py          → PDF cifrado → PNG
│   ├── ocr.py                 → PNG → texto, palabras, cuadrícula, celdas
│   ├── extraccion.py          → Texto/palabras → campos (funciones puras)
│   ├── proceso.py             → Una factura: conversión + OCR + extracción
│   ├── exportacion.py         → DataFrame → CSV
│   └── metricas.py            → Cronómetros y reporte
├── scripts/
│   └── generar_pdf_ejemplo.py → Facturas de EJEMPLO cifradas para las pruebas
├── tests/
│   ├── fixtures/              → Textos OCR y PDF de ejemplo (datos ficticios)
│   ├── test_datos.py
│   ├── test_extraccion.py
│   ├── test_ocr.py
│   ├── test_exportacion.py
│   ├── test_cli.py
│   └── test_pipeline.py
├── output/                    → No se sube al repositorio
│   ├── pdf/   img/   csv/   metricas/
└── docs/
    ├── adr/0001-captcha-resuelto-por-persona.md
    └── informe.md             → Tiempos, métricas y restricciones
```

## Estilo de código

- Nombres en español para el dominio (`numero_factura`, `nit_emisor`), en inglés solo lo que impone una librería.
- Funciones pequeñas y puras donde se pueda: la extracción recibe texto y devuelve datos, sin leer archivos.
- Tipado con anotaciones y `dataclass` para los registros.
- Errores por CUFE se registran y el proceso sigue con el siguiente; nunca se detiene todo por una factura.

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class Encabezado:
    numero_factura: str
    fecha_emision: str  # ISO 8601: AAAA-MM-DD
    nit_emisor: str


def extraer_encabezado(texto: str) -> Encabezado:
    """Obtiene los datos del documento y del emisor a partir del texto OCR."""
    return Encabezado(
        numero_factura=_buscar(PATRON_NUMERO, texto),
        fecha_emision=_normalizar_fecha(_buscar(PATRON_FECHA, texto)),
        nit_emisor=_limpiar_nit(_buscar(PATRON_NIT, texto)),
    )
```

## Formato de salida

Un CSV por factura en `output/csv/<CUFE>.csv` y un consolidado `output/csv/consolidado.csv`, con **una fila por producto** y los datos del encabezado repetidos en cada fila:

| Columna | Tipo | Ejemplo | Regla |
|---|---|---|---|
| `cufe` | texto | `eccc372e…f1` | Trazabilidad |
| `numero_factura` | texto | `FE-1234` | Tal como aparece |
| `fecha_emision` | fecha | `2025-03-14` | En el PDF viene como DD/MM/AAAA; se normaliza a AAAA-MM-DD |
| `nit_emisor` | texto | `900123456` | Sin puntos; dígito de verificación aparte si existe |
| `codigo` | texto | `7701234567890` | Se unen las líneas en que la celda parte el código |
| `descripcion` | texto | `Servicio de…` | Espacios normalizados |
| `cantidad` | decimal | `2.0` | Formato colombiano convertido (`1.234,50` → `1234.5`) |
| `precio_unitario` | decimal | `150000.0` | Ídem |

CSV en UTF-8 con BOM, separados por coma, para que abran bien en Excel.

## Estrategia de pruebas

| Nivel | Qué cubre | Cómo |
|---|---|---|
| Unitarias | Expresiones regulares, normalización de fechas, NIT y números | `tests/test_extraccion.py` con textos OCR de ejemplo, incluidos textos con errores típicos de OCR. Los fixtures del repositorio son sintéticos: nunca contienen datos de las facturas reales de `privado/` |
| Integración | PDF de ejemplo → imagen → OCR → CSV | `tests/test_pipeline.py` (requiere Tesseract instalado) |
| Descarga | El bot contra la página real | Manual: no se puede automatizar por el captcha. Evidencia: registro de la corrida y PDF descargados |

- Las pruebas se escriben antes de la función (`test-driven-development`).
- Cobertura objetivo: **≥ 90 %** en `extraccion.py` y `exportacion.py`; `descarga.py` se verifica a mano.
- **Precisión del OCR:** si el PDF trae capa de texto, se compara campo por campo lo que lee el OCR contra esa capa y se reporta el porcentaje de acierto.

## Límites

**Siempre:**
- Correr `pytest` y `ruff check` antes de cada commit.
- Seguir con el siguiente CUFE si uno falla, y dejar registrado por qué.
- Mantener la ventana del navegador visible y el ritmo de consultas humano (una consulta a la vez, con pausas).
- Actualizar este SPEC antes de cambiar el alcance.

**Preguntar primero:**
- Instalar Python, Tesseract o cualquier programa en el equipo.
- Agregar dependencias fuera de la tabla del stack.
- Crear el repositorio en GitHub, cambiar su visibilidad o hacer `push`.
- Escribir en el `.docx` de la prueba.

**Nunca:**
- Resolver o saltar el captcha de forma automática (servicios de terceros, trucos contra Turnstile o reCAPTCHA, etc.).
- Hacer consultas en paralelo o en ráfaga contra la DIAN.
- Subir al repositorio el `.docx` diligenciado (tendrá tus datos personales), las carpetas `output/` y `privado/` ni credenciales.
- Copiar datos del comprador (nombre, documento, dirección, teléfono, correo) de facturas reales a fixtures, informes, registros o mensajes de commit.
- Inventar datos de facturas y presentarlos como reales.

## Criterios de éxito

1. `python -m rpa_dian descargar` procesa cada fila del CSV en orden. Si tiene NIT: llena CUFE y NIT, se detiene en el captcha mostrando un aviso en consola, espera hasta 180 s a que la persona lo resuelva, pulsa "Descargar PDF", acepta el aviso de contraseña y guarda `output/pdf/<CUFE>.pdf`.
2. Cada consulta termina en un estado y el proceso continúa: `ok`, `requiere_nit` (NIT vacío, no se consulta), `sin_resultado`, `error` o `timeout`. Con `data/consultas.csv`, los 10 CUFE de la prueba terminan en `requiere_nit`.
3. Cada PDF se abre con su NIT como contraseña y genera una imagen PNG por página a 300 dpi en `output/img/`.
4. Cada factura descargada produce su CSV con las 8 columnas de la tabla de salida, una fila por producto, y todas entran en `consolidado.csv`.
5. `output/metricas/metricas.csv` registra, por CUFE: tiempo de navegación, de espera del captcha, de descarga, de conversión, de OCR y de extracción, más el estado final.
6. `docs/informe.md` resume: tiempo total, promedio por factura, tiempo humano (captcha) separado del automático, tasa de éxito, precisión del OCR por campo y restricciones del proceso.
7. `pytest -q` pasa sin fallos y `ruff check .` no reporta errores.
8. El README permite a una persona nueva instalar, ejecutar y entender los resultados y las restricciones.

## Fuera de alcance (V2)

- Resolución automática del captcha: no se construirá (ver la decisión arriba).
- Descargas en paralelo: aumentaría la carga sobre la DIAN.
- Interfaz gráfica: la prueba pide código, no una aplicación.
- Programación periódica o despliegue en la nube: no se pide.
- Otros tipos de documento DIAN (notas crédito, nómina): no se piden.

## Decisiones tomadas al aprobar

Se aprobó el SPEC con las propuestas por defecto:

1. Si la DIAN no devuelve PDF para los CUFE, se usan PDF de ejemplo marcados como tales para demostrar la extracción. *(2026-11-18: además se valida con facturas reales del usuario en `privado/`.)*
2. El campo "NIT del Emisor o Receptor" del formulario se verifica en el reconocimiento de la página (tarea 3 del plan). *(2026-11-18: es obligatorio; ver Hallazgos.)*
3. Se reportan los tiempos del proceso (métricas) y el tiempo de desarrollo por tarea.
4. Una fila por producto con el encabezado repetido.

## Preguntas abiertas

1. **Instalar Python 3.12 y Tesseract con winget:** pendiente de autorización (tarea 1 del plan).
2. **Repositorio en GitHub:** nombre (propuesta `rpa-dian-facturas`) y visibilidad; se decide antes de la tarea 15.
