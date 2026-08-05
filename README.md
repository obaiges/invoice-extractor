# Zebra Invoice Extractor

Aplicación para la prueba técnica de **Zebra Ventures**: el usuario importa una factura
(PDF o imagen), el sistema extrae sus campos mediante **Gemini API** y los presenta en
pantalla de forma estructurada. Cualquier campo que no se pueda extraer con certeza se
indica explícitamente ("No detectado"), nunca se omite en silencio.

| Capa       | Tecnología                        |
|------------|-----------------------------------|
| Backend    | Python · FastAPI                  |
| Frontend   | Angular 19 (standalone) · HTML/CSS |
| Extracción | Gemini API (Google AI Studio)     |
| Comunicación | REST (multipart upload)          |

---

## Tabla de contenidos

1. [Reflexión técnica](#reflexión-técnica)
2. [Arquitectura](#arquitectura)
3. [Prerrequisitos](#prerrequisitos)
4. [Obtener la clave de Gemini (gratis)](#obtener-la-clave-de-gemini-gratis)
5. [Configuración](#configuración)
6. [Arrancar el backend](#arrancar-el-backend)
7. [Arrancar el frontend](#arrancar-el-frontend)
8. [Uso de la aplicación](#uso-de-la-aplicación)
9. [Tests](#tests)
10. [API](#api)
11. [Estructura del proyecto](#estructura-del-proyecto)
12. [Limitaciones conocidas](#limitaciones-conocidas)
13. [Mejoras a futuro](#mejoras-a-futuro)

---

## Reflexión técnica

### Enfoque de extracción elegido: Gemini (opción A del enunciado)

Se ha elegido la **opción A (LLM)** con **Gemini**, con esta justificación:

1. **Los documentos reales son heterogéneos.** Una factura puede llegar como PDF con capa
   de texto, como PDF escaneado o como fotografía. Gemini es un modelo **multimodal**: al
   enviarle imágenes, funciona igual con todas esas variantes **sin necesidad de OCR
   adicional**. Una librería de extracción clásica (pdfplumber, Tesseract) tendría que
   encadenarse y gestionar varios casos; aquí el modelo unifica el problema.
2. **No se depende de la Files API.** El backend convierte el PDF a imágenes PNG
   localmente (PyMuPDF, a 150 DPI) y las envía como bytes **inline** (base64). Esto evita
   las limitaciones de subida de ficheros del plan gratuito y mantiene el coste bajo.
3. **Free tier.** Elegí Gemini porque Google AI Studio ofrece una capa gratuita
   (modelo `gemini-3.6-flash`), suficiente para una prueba y una demo.
4. **Calidad de extracción.** La generación controlada de JSON (`response_mime_type` +
   `response_schema`) fuerza la estructura de salida, y el prompt exige `null` ante la
   duda, lo que se traduce directamente en el requisito de "indicar explícitamente lo que
   no se puede extraer". El modelo configurado (`GEMINI_MODEL`) recibe más intentos antes
   de degradar, y la cadena de reserva prefiere los modelos **flash completos** sobre los
   **lite** (más débiles leyendo facturas con tablas). Además, si la primera extracción
   deja sin detectar la mayoría de los campos, el backend **reintenta una vez** de forma
   transparente: los fallos puntuales del modelo no acaban en pantalla como "todo vacío".

### Diseño del sistema

- **Separación de responsabilidades.** Los endpoints (`api/routes.py`) solo delegan; la
  orquestación vive en `services/document_processor.py`; la conversión de documentos en
  `services/pdf_converter.py`; y toda la lógica de extracción en `extraction/`.
- **Proveedor sustituible.** La interfaz `ExtractionProvider` (en `extraction/base.py`)
  aísla la fuente de extracción. Para cambiar de LLM (o a un OCR local) solo hay que
  implementar `extract()`, sin tocar el pipeline ni los endpoints.
- **Parser tolerante.** El modelo no siempre responde perfecto. `extraction/parser.py`
  extrae el JSON de respuestas con ruido (markdown, prosa), resuelve sinónimos en español
  e inglés (`numero_factura`/`invoice_number`, `emisor`/`seller`, ...), normaliza números
  con formatos europeo y americano ("1.234,56" vs "1,234.56") y fechas a ISO 8601.
- **Incertidumbre explícita.** Cada campo de la factura puede ser `null`. Además, el
  resultado incluye `missing_fields` (qué campos esperados no se detectaron) y `warnings`
  (anomalías, p. ej. incoherencias aritméticas entre base, IVA y total). El frontend
  renderiza **siempre** todos los campos esperados y pinta "No detectado" cuando faltan.
- **Errores estructurados.** Todos los fallos son excepciones de dominio mapeadas a
  códigos y status HTTP (`415`, `413`, `422`, `502`, `503`), con mensajes accionables.
  Un handler global en `main.py` las convierte en JSON; nunca llega una excepción cruda
  al cliente.
- **Tests sin dependencia externa.** El proveedor se mockea en los tests y se generan
  facturas PDF sintéticas (reportlab), de modo que el pipeline completo se verifica sin
  gastar llamadas ni necesitar API key.

---

## Arquitectura

```
┌─────────────────┐   multipart POST /api/v1/documents/extract   ┌──────────────────────┐
│  Angular 19     │ ───────────────────────────────────────────▶ │  FastAPI (backend)   │
│  (localhost:4200)│                                            │  (localhost:8000)    │
└─────────────────┘                                             └──────────────────────┘
        ▲                          (proxy dev: /api → :8000)              │
        │        JSON estructurado (factura + missing + warnings)         │
        └─────────────────────────────────────────────────────────────────┤
                                                                          ▼
                                                     ┌────────────────────────────────────┐
                                                     │ DocumentProcessor                    │
                                                     │  1. valida archivo                  │
                                                     │  2. PDF → PNG (PyMuPDF)             │
                                                     │  3. ExtractionProvider.extract()    │
                                                     │  4. parser → Invoice + missing      │
                                                     └────────────────────────────────────┘
                                                                          │
                                                                          ▼
                                                     ┌────────────────────────────────────┐
                                                     │ GeminiProvider (google-genai)       │
                                                     │  prompt + response_schema (JSON)    │
                                                     └────────────────────────────────────┘
```

---

## Prerrequisitos

- **Python 3.11+** (en esta máquina: 3.13 disponible como `py -3.13`).
- **Node.js 18+** y **npm**.
- **Angular CLI 19** (opcional: el frontend se puede lanzar con `npx ng serve`).
- **Git**.
- Cuenta de Google para obtener la clave de Gemini.

---

## Obtener la clave de Gemini (gratis)

1. Entra en <https://aistudio.google.com/apikey> e inicia sesión con tu cuenta de Google.
2. Pulsa **"Create API key"** → **"Create API key in new project"**.
3. Copia la clave generada (empieza por `AIza...`).

La capa gratuita de AI Studio permite peticiones con el modelo `gemini-3.6-flash`
(configurable con `GEMINI_MODEL`). Las claves gratuitas tienen límites de peticiones por
minuto: si recibes un error de cuota, espera unos segundos y reintenta. Si el modelo
configurado ya no está disponible para tu clave, el backend reintenta automáticamente con
modelos más recientes.

---

## Configuración

Crea el fichero `.env` en la **raíz del repositorio** copiando la plantilla:

```bash
copy .env.example .env
```

> En PowerShell: `Copy-Item .env.example .env`

Y rellena, como mínimo:

```dotenv
GEMINI_API_KEY=AIza...          # tu clave de AI Studio
GEMINI_MODEL=gemini-3.6-flash   # modelo a usar
```

Opciones disponibles (todas opcionales salvo la clave):

| Variable          | Descripción                                        | Valor por defecto        |
|-------------------|----------------------------------------------------|--------------------------|
| `GEMINI_API_KEY`  | Clave de API de Gemini (**obligatoria**)           | —                        |
| `GEMINI_MODEL`    | Modelo de Gemini (con fallback a modelos más recientes si no está disponible) | `gemini-3.6-flash` |
| `MAX_FILE_SIZE_MB`| Tamaño máximo del documento subido                 | `15`                     |
| `CORS_ORIGINS`    | Orígenes permitidos (separados por coma)           | `http://localhost:4200`  |

> ⚠️ El `.env` está en `.gitignore`: nunca se sube al repositorio.

---

## Arrancar el backend

Desde la carpeta `backend/`:

```powershell
cd backend

# 1. Crear el entorno virtual
py -3.13 -m venv .venv

# 2. Activar el entorno
.\.venv\Scripts\Activate.ps1

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Arrancar el servidor
uvicorn app.main:app --reload --port 8000
```

El backend queda en <http://localhost:8000>. Documentación interactiva de la API en
<http://localhost:8000/docs>. Comprobación rápida: `GET http://localhost:8000/api/v1/health`
debe responder `{"status": "ok"}`.

---

## Arrancar el frontend

Desde la carpeta `frontend/`:

```powershell
cd frontend

npm install
ng serve
```

La aplicación queda en **<http://localhost:4200>**. El dev server de Angular redirige
`/api` → `http://localhost:8000` mediante `proxy.conf.json` (no hace falta configurar nada
más). Si prefieres lanzar el backend en otro puerto, actualiza `proxy.conf.json`.

---

## Uso de la aplicación

1. Abre <http://localhost:4200>.
2. Arrastra una factura (PDF, PNG, JPG o WEBP, máx. 15 MB) a la zona de carga, o haz clic
   para seleccionarla.
3. Espera a que termine la extracción (suele tardar unos segundos).
4. Revisa el resultado estructurado: cabecera, emisor/receptor, líneas de detalle,
   desglose de IVA y totales. Los campos no extraídos aparecen en cursiva como
   **"No detectado"**, junto con la lista de avisos.
5. Con **"Procesar otra factura"** vuelves a empezar.

### Comportamiento ante errores

| Situación                                        | Resultado                                                       |
|--------------------------------------------------|-----------------------------------------------------------------|
| Formato no soportado (.txt, .docx...)            | Error claro en pantalla (HTTP 415)                              |
| Archivo vacío o PDF corrupto                     | Error claro en pantalla (HTTP 422)                              |
| PDF protegido por contraseña                     | Error claro en pantalla (HTTP 422)                              |
| Archivo > 15 MB                                  | Error claro en pantalla (HTTP 413)                              |
| Sin `GEMINI_API_KEY` configurada                 | Mensaje con instrucciones de configuración (HTTP 503)           |
| Modelo no disponible para la cuenta (404)        | Reintento automático con el siguiente modelo de la cadena        |
| Alta demanda temporal del modelo (503)           | Reintento y, si persiste, prueba el siguiente modelo (HTTP 502)  |
| Cuota gratuita agotada (429)                     | Reintento breve y mensaje claro sin quemar los fallbacks (HTTP 502) |
| Clave inválida / fallo de Gemini                 | Mensaje accionable (HTTP 502)                                    |
| Respuesta del modelo no parseable                | Mensaje estructurado (HTTP 502), nunca una excepción sin capturar |

---

## Tests

El backend incluye tests unitarios y de integración con el proveedor **mockeado**
(no consumen cuota de API).

```powershell
cd backend
.\.venv\Scripts\python.exe -m pytest -q
```

Cubre: limpieza de JSON sucio, normalización de números/fechas, detección de campos
faltantes, incoherencias de totales, y el flujo completo del endpoint (PDF sintético →
renderizado → extracción → respuesta).

---

## API

### `POST /api/v1/documents/extract`

Sube el documento (`multipart/form-data`, campo `file`) y devuelve la extracción.

Respuesta `200` (ejemplo reducido):

```json
{
  "status": "success",
  "model_used": "gemini-3.6-flash",
  "invoice": {
    "invoice_number": "INV-2024-001",
    "issue_date": "2024-03-15",
    "due_date": "2024-04-15",
    "currency": "EUR",
    "seller": { "name": "ACME S.L.", "tax_id": "B12345678", "address": "C/ Inventada 42" },
    "buyer": { "name": "Cliente S.L.", "tax_id": "A98765432", "address": null },
    "lines": [
      { "description": "Servicio", "quantity": 3, "unit_price": 300, "total": 900, "tax_rate": 21 }
    ],
    "subtotal": 1150,
    "taxes": [ { "rate": 21, "amount": 241.5 } ],
    "total": 1391.5
  },
  "missing_fields": [],
  "warnings": []
}
```

- `status`: `"success"` (todos los campos detectados) o `"partial"` (faltan campos).
- `model_used`: modelo de Gemini que produjo la extracción (útil para depurar
  si un documento sale parcial o si se activaron los modelos de reserva).
- `missing_fields`: claves de los campos esperados que no se pudieron extraer.
- `warnings`: avisos del modelo y anomalías de consistencia detectadas por el parser.

Respuesta de error (todos los códigos de la tabla anterior):

```json
{ "status": "error", "code": "missing_api_key", "message": "..." }
```

### `GET /api/v1/health`

Healthcheck del servicio.

---

## Estructura del proyecto

```
.
├── .env.example              # Plantilla de configuración (sin secretos)
├── .gitignore
├── README.md
├── backend/
│   ├── requirements.txt
│   ├── app/
│   │   ├── main.py                 # FastAPI + CORS + handlers de error
│   │   ├── api/routes.py           # Endpoints + inyección del procesador
│   │   ├── core/config.py          # Settings (.env)
│   │   ├── core/errors.py          # Excepciones de dominio → códigos HTTP
│   │   ├── models/schemas.py       # Pydantic: Invoice, ExtractionResult...
│   │   ├── services/
│   │   │   ├── document_processor.py  # Orquestación del flujo
│   │   │   └── pdf_converter.py       # PDF → PNG (PyMuPDF)
│   │   └── extraction/
│   │       ├── base.py             # Interfaz ExtractionProvider
│   │       ├── gemini_provider.py  # Implementación Gemini
│   │       ├── prompt.py           # Prompt + response_schema
│   │       └── parser.py           # Normalización robusta del JSON
│   └── tests/
│       ├── test_parser.py
│       ├── test_api.py
│       └── fixtures/generate_invoice.py
└── frontend/
    ├── proxy.conf.json
    └── src/app/
        ├── app.component.*         # Orquestación (upload → service → result)
        ├── models/invoice.model.ts # Interfaces TS espejo del backend
        ├── services/extraction.service.ts
        ├── utils/format.ts         # Formateo de moneda/fechas
        └── components/
            ├── upload/             # Drag & drop + validación
            ├── result/             # Vista estructurada de la factura
            └── field/              # Campo etiqueta+valor con estado "No detectado"
```

---

## Limitaciones conocidas

- **Límites del free tier de Gemini.** Las claves gratuitas limitan peticiones/minuto y el
  tamaño total de las imágenes enviadas (18 MB de PNG). Documentos muy largos o en
  resoluciones muy altas pueden requerir reducción.
- **Respuestas puntuales débiles del modelo.** Gemini devuelve a veces una extracción casi
  vacía aunque el documento sea legible. El backend reintenta automáticamente cuando faltan
  más de la mitad de los campos; si aun así no se recupera, el resultado se muestra como
  "partial" con los campos faltantes marcados como "No detectado" (consulta `model_used`
  en la respuesta para ver qué modelo respondió).
- **Alucinación / incertidumbre del LLM.** El modelo puede inventar valores si la imagen
  es ilegible. Mitigación: el prompt ordena `null` ante la duda, el parser marca
  incoherencias aritméticas como avisos, y el frontend distingue siempre "No detectado".
- **Ambigüedad de separadores numéricos.** Un valor como `1,234` es 1.234 en español y
  1,234 en inglés. El parser usa heurísticas (el último separador es el decimal); ante
  formatos ambiguos el número puede interpretarse mal. Los avisos de consistencia ayudan a
  detectarlo.
- **Fecha ambigua DD/MM vs MM/DD.** Se interpreta siempre como DD/MM (formato habitual en
  facturas españolas).
- **Un solo tipo de documento.** La extracción está orientada a facturas; el esquema y el
  prompt están especializados en ese dominio. Ampliar a albaranes o nóminas implicaría
  añadir esquemas y prompts adicionales (la arquitectura lo permite).
- **Seguridad (demo local).** No hay autenticación ni almacenamiento de documentos; el
  objetivo es la extracción en memoria.

---

## Mejoras a futuro

- Si esta aplicación fuera a producción lo primero que haría sin ningún tipo de duda es usar un modelo de pago como Claude, así aseguraría una lectura mucho mejor y no tendría límites en la cuota de la API que retrasan bastante tanto el desarrollo como las pruebas. 
- Otra mejora que haría sería ocultar completamente toda la parte "manual" que viene a ser el hecho de importar la factura. Mediante eventos con SSE y RxJS se podría ir actualizando y extrayendo toda la información a medida que fueran entrando las facturas al servidor. En la entrevista técnica que tengamos puedo explicar este punto con más detalle.
- Si el punto anterior fuera inviable, lo que si haría sería mejorar la aplicación para poder subir cuantas facturas se quieran al mismo tiempo y que las fuera leyendo una a una.
- Otro punto que habría que mejorar si fuera a producción sería el hecho de verificar los formatos de los ficheros. Añadir validación por magic bytes (firmas reales de PDF/PNG/JPEG) y mover la conversión a un proceso/contenedor aislado (PyMuPDF y Pillow han tenido CVEs). Para así no fiarme de la extensión del fichero.
- Por último una mejora que haría sí o sí, sería una autenticación y un rate-limit  en el endpoint de lectura para tener un control ya que al final cada llamada nos generaría un coste.
