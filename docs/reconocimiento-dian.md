# Reconocimiento de la página DIAN (T3)

Fecha: 2026-11-18 · Página: `https://catalogo-vpfe.dian.gov.co/User/SearchDocument`

> Estado: **completo**. El flujo se validó de punta a punta con una factura real (no incluida en el repositorio). La consulta exige CUFE + NIT, y la prueba no entrega el NIT.

## 1. Formulario

| Elemento | Selector | Notas |
|---|---|---|
| Formulario | `form#search-document-form` | `POST` a la misma URL |
| CUFE | `input#DocumentKey` (`name="DocumentKey"`) | Obligatorio: `data-val-required="CUFE o UUID es requerido."` |
| NIT | `input#SearchDocumentNit` (`name="SearchDocumentNit"`) | Sin marca de obligatorio en el HTML, pero **la página lo exige al buscar**: "El NIT del emisor o receptor es requerido". Formato: sin puntos, comas ni DV |
| Botón | `form#search-document-form button[type=submit]` (texto "Buscar") | |
| Token anti-falsificación | `input[name=__RequestVerificationToken]` (oculto) | Lo pone la página; el bot no lo toca |
| Respuesta del captcha | `input[name=cf-turnstile-response]` (oculto) | Lo llena Cloudflare cuando una persona supera la verificación |

## 2. Captcha

- **Tipo:** Cloudflare Turnstile (`div.cf-turnstile`, script `challenges.cloudflare.com/turnstile/v0/api.js`).
- **Si se pulsa "Buscar" sin resolverlo**, la página muestra: "Falta Token de validación de captcha".
- **En el navegador integrado de la app de Claude la verificación falla** ("La verificación falló") aun cuando la intenta una persona. Turnstile evalúa el navegador, no solo el clic, y ese navegador embebido no la supera.
- **En un navegador normal la verificación pasa** ("¡Operación exitosa!") cuando la resuelve una persona.

**Implicación para el bot (T9):** hay que comprobar si Turnstile deja pasar a una persona dentro del Chromium que abre Playwright. Si no lo hace, se documenta como restricción del proceso y se usa el plan B del plan (PDF de ejemplo). **No se intentará ocultar la automatización** para engañar a Turnstile: eso sería saltarse el control anti-bots (ver los límites del SPEC).

## 3. Resultado de la búsqueda

**Sin NIT:** consulta manual del CUFE 1 de la prueba en un navegador normal, con el captcha resuelto por una persona: **la búsqueda no avanza** y la página muestra "El NIT del emisor o receptor es requerido". Pasa lo mismo con CUFE reales.

**Con NIT** (factura real, NIT del emisor o del receptor, captcha resuelto por una persona): la página pasa a `https://catalogo-vpfe.dian.gov.co/Document/ShowDocumentToPublic` y muestra:

- Encabezado: CUFE, "Factura electrónica", serie, folio, fecha de emisión y el enlace **"Descargar PDF"**.
- "DATOS DEL EMISOR" (NIT, nombre), "DATOS DEL RECEPTOR" (NIT, nombre), "TOTALES E IMPUESTOS" (IVA, total).
- Estado en el registro, validaciones del documento y eventos.

**Conclusión: la consulta pública exige CUFE + NIT.** La prueba solo entrega los CUFE. El NIT no se puede deducir del CUFE: el CUFE es un hash SHA-384 de varios datos de la factura, incluido el NIT, y un hash no se puede revertir.

## 4. Descarga del PDF

1. En la pantalla de resultado, el enlace **"Descargar PDF"** abre un aviso: *"Este archivo contiene contraseña y corresponde al NIT del Emisor o Receptor que digitó anteriormente"*, con el botón **"Aceptar"**.
2. Al aceptar, el navegador descarga **`<CUFE>.pdf`**.
3. **El PDF está cifrado:** su contraseña es el NIT que se digitó en la búsqueda. Verificado con PyMuPDF: `is_encrypted = True`, `needs_pass = 1`. El de prueba tiene 2 páginas y 69 KB.

**Implicaciones:**
- El bot (T10) debe pulsar "Descargar PDF", aceptar el aviso y capturar la descarga (`page.expect_download()` de Playwright).
- La extracción (T7) debe abrir el PDF con el NIT como contraseña (`doc.authenticate(nit)`) antes de convertirlo en imagen.
- Cada CUFE necesita su NIT tanto para la consulta como para abrir el PDF.

## 5. Decisión

Propuesta (pendiente de aprobación):

- La entrada pasa de `data/cufes.txt` a un CSV con columnas `cufe,nit`; el NIT puede ir vacío.
- Con NIT vacío, el bot marca el CUFE como `requiere_nit` sin enviar la consulta. Así quedan los 10 CUFE de la prueba.
- El flujo completo se valida con facturas reales del usuario, en un archivo local excluido de Git.
- La extracción se demuestra con el PDF real (descifrado con su NIT) y con PDF de ejemplo marcados como tales.
