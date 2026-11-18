# Informe: tiempos, métricas y restricciones del proceso

Prueba técnica RPA DIAN · 2026-11-18. Responde al punto "Reporta los tiempos empleados, restricciones métricas del proceso".

El informe por ejecución lo genera el propio proceso en `output/metricas/informe.md` (y `metricas.csv`). Este documento consolida tres ejecuciones.

## 1. Ejecuciones medidas

| Conjunto | Qué se ejecutó | Resultado |
|---|---|---|
| **A. Los 10 CUFE de la prueba** (`data/consultas.csv`) | `python -m rpa_dian` | 10 de 10 en `requiere_nit`: la DIAN exige el NIT y la prueba no lo entrega (ver §4) |
| **B. 2 facturas de EJEMPLO** (`tests/fixtures/pdf`, datos ficticios, PDF cifrados) | `python -m rpa_dian extraer …` | 2 facturas, 5 productos, **26 de 26 campos correctos (100 %)** |
| **C. 1 factura real** (de la persona que presenta la prueba; no se publica) | Descarga manual en el portal + `extraer` | 1 factura, 2 productos, **10 de 11 campos correctos (90,9 %)** |
| **D. La misma factura real, de punta a punta en modo asistido** | `python -m rpa_dian --consultas privado\consultas.csv` | Descarga **`ok`**: el robot abrió la consulta, detectó el PDF en Descargas, lo validó y lo movió al proyecto. Extracción: 2 productos, **10 de 11 campos (90,9 %)** en 24 s |

## 2. Tiempos del proceso (segundos)

Equipo: Windows 11, Python 3.12, Tesseract 5.4, PDF a 300 dpi.

| Etapa | B. Ejemplos (promedio por factura) | C. Factura real |
|---|---|---|
| PDF cifrado → imágenes PNG | 0,3 | 0,5 |
| OCR (página completa + celdas de la tabla) | 10,2 | 16,0 |
| **Extracción total por factura** | **10,5** | **16,5** |

- El OCR domina el tiempo: cada precio y cantidad se lee a 2 escalas y, si no coinciden, a una tercera para votar (ver §3). Leer siempre las 3 escalas tomaba 14,7 s y 21,8 s.
- **Descarga (modo asistido):** depende de la persona. En la grabación de una consulta manual, Cloudflare se validó solo en ~10 s y la consulta completa tomó ~25 s desde "Buscar" hasta el PDF. El proceso registra el tiempo por factura en la columna `t_persona` de `metricas.csv`, separado del tiempo automático. En la ejecución D se midieron 685 s: ese valor cuenta desde que el robot abre la consulta, e incluye la espera hasta que la persona llegó al navegador, no solo los clics.
- **Movimiento y validación del PDF por el robot:** menos de 0,1 s.
- **Estimado para 10 facturas con NIT:** ~10 × (25 s de persona + 10–17 s de extracción) ≈ 6–7 minutos.

## 3. Precisión del OCR por campo

Cada campo extraído **de las imágenes** se compara con la capa de texto incrustada en el PDF, que se usa solo como referencia (nunca para extraer).

| Campo | B. Ejemplos | C. Factura real |
|---|---|---|
| Número de factura | 100 % (2/2) | 0 % (0/1) |
| Fecha de emisión | 100 % (2/2) | 100 % (1/1) |
| NIT del emisor | 100 % (2/2) | 100 % (1/1) |
| Código | 100 % (5/5) | 100 % (2/2) |
| Descripción¹ | 100 % (5/5) | 100 % (2/2) |
| Cantidad | 100 % (5/5) | 100 % (2/2) |
| Precio unitario | 100 % (5/5) | 100 % (2/2) |
| **Total** | **100 % (26/26)** | **90,9 % (10/11)** |

¹ La descripción se compara sin espacios: el PDF parte palabras al final de cada línea de la celda y no es posible saber dónde había espacios (p. ej., "SMAR T TV").

La comparación es estricta: un número cuenta solo si aparece completo (no dentro de otro, p. ej. "1,00" dentro de "21,00"), y un código o descripción de menos de 4 caracteres no cuenta como acierto. Limitación: la métrica evalúa los productos extraídos; no cuenta productos que el OCR no haya detectado.

**Cómo se llegó a esta precisión** (iteraciones medidas con la factura real):

| Versión | Problema observado | Cambio |
|---|---|---|
| 1 | Fecha y NIT no encontrados | OCR de página en modo psm 4 (cada etiqueta queda en la línea de su valor) |
| 2 | Filas de la tabla perdidas (caracteres sueltos) | Cuadrícula detectada en la imagen y OCR de cada celda por separado |
| 3 | Códigos sin sus últimos dígitos | Las líneas verticales se buscan solo en la zona de la tabla (el logo DIAN creaba una línea falsa) y se borran los bordes en vez de recortar márgenes |
| 4 | Un precio con un dígito confundido (4/9) | Lectura de números a 3 escalas con voto por carácter |
| 5 | Revisión de código y seguridad | Fin de tabla robusto ("HOJAS" o "NOTAS" en una descripción ya no corta la tabla), cuadrícula incompleta sin fallos, fechas imposibles vacías, voto con salida temprana (−30 % de tiempo) |

## 4. Restricciones del proceso

1. **La consulta exige CUFE + NIT** del emisor o receptor (verificado en el portal). La prueba entrega solo los CUFE, y el NIT no se puede deducir porque el CUFE es un hash SHA-384. → Los 10 CUFE terminan en `requiere_nit`.
2. **Captcha Cloudflare Turnstile** en el formulario y otra vez en la página de resultado. En un navegador normal se valida solo; en uno controlado por un robot (Playwright, con Edge o Chrome) Cloudflare **rechaza la verificación aunque una persona marque la casilla**. No se oculta la automatización. → Modo asistido: el robot abre la consulta con el CUFE escrito en el navegador normal y la persona confirma con un clic por página (favorito "RPA DIAN"). Decisión y evidencia en [`docs/adr/0001-captcha-resuelto-por-persona.md`](adr/0001-captcha-resuelto-por-persona.md).
3. **El PDF viene cifrado** con el NIT que se escribe en la búsqueda. → La extracción lo abre con el NIT de la consulta. Si la persona busca con otro NIT (p. ej., el del receptor en lugar del emisor), el PDF no abre con el NIT del archivo de consultas: el proceso no se detiene, registra `error_extraccion` y se resuelve corrigiendo el NIT en el CSV (pasó en la ejecución D).
4. **El campo NIT aparece solo después de escribir el CUFE**, y "Descargar PDF" falla si el captcha de la página de resultado no terminó ("El campo de seguridad no está completo"). → El flujo espera ambos captchas.
5. **Letras parecidas en la fuente del PDF** (`III` leído como `II`). → Visible en la precisión del número de factura de la factura real.
6. **El Chromium que trae Playwright no arrancó en el equipo de desarrollo** (error de configuración en paralelo de Windows). → El modo automático usa Edge o Chrome instalados (`RPA_NAVEGADOR`).

## 5. Recomendación para producción

Para un proceso real y desatendido, no usar el portal público: la DIAN expone servicios web SOAP para facturadores y proveedores tecnológicos habilitados (`WcfDianCustomerServices`, p. ej. `GetStatus`), con autenticación WS-Security, sin captcha. La extracción a CSV de este proyecto se mantiene igual. Ver referencias en el ADR-0001.

## 6. Tiempo de desarrollo

Registro por tarea en [`docs/tiempos-desarrollo.md`](tiempos-desarrollo.md).
