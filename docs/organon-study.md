# e-organon — estudio (2026-11-04)

ὄργανον, *instrumento*. Un hub propio de herramientas deterministas — MCP + API HTTP — para Claude Code, Hermes y
OpenCode: hacer con código y modelos pequeños locales (NLP, visión, audio; **nunca un LLM**) lo que hoy cuesta tokens,
carga en los harnesses o no se hace. CPU primero; la GPU es de vLLM y solo se presta.

Fuentes: cinco investigaciones paralelas del 2026-11-04 (inventario de e-metaxy, `doc/`, `image/`, resto de secciones,
arquitectura). **Aviso:** la salud de casi todos los proyectos (última release, actividad) está sin verificar en vivo;
las licencias de código son fiables, las de **pesos** no. Nada se adopta sin el pase MEASURE de `flow-gen-research` y,
para los candidatos, un banco vallado (ley 24).

## 1. El problema bien planteado

No es «qué herramientas meter». Es: **un agente pide una transformación determinista sobre un fichero y la obtiene en
una llamada, sin que los bytes pasen por su contexto, con un coste de contexto constante aunque haya 150 tools.**
Tres cosas deciden si el hub sirve o no, y van antes que cualquier herramienta:

1. **Los ficheros llegan por referencia.** Todos los agentes viven en esta máquina y el vault está montado en paridad
   (Hermes guarda sus subidas en `~/.config/memory/hermes/cache/documents/`). Contrato único: `artifact_id` (sha256)
   en un almacén direccionable por contenido; entrada por ruta del host bajo raíces permitidas (vault, workspaces) o
   `POST /artifacts`; salida `{artifact_id, mime, size, path, preview?}`. Bytes inline solo < ~100 KB.
2. **Lo lento es un job.** p95 > 5 s → devuelve `job_id` en < 1 s; `organon_job(job_id)` lo consulta. El soporte de
   *tasks* MCP en los clientes no está verificado: contrato propio, mapeable a tasks cuando exista.
3. **El contexto en reposo.** Claude Code y Hermes difieren los esquemas MCP (tool search); OpenCode no consta. Pocas
   tools gruesas por sección (`doc_inspect`, `image_convert`…), perfiles por URL (`/mcp/doc`…) para clientes sin
   diferido. **Hay que medirlo antes de construir.**

**Métricas** (sin ellas no hay «funciona»): tokens en reposo con el catálogo entero; acierto de selección de tool en
30 tareas etiquetadas (Claude y Hermes); p95 por tool en CPU y RSS máximo contra un presupuesto escrito antes; golden
files por tool; 0 caídas con el corpus hostil (bombas de descompresión, PDF con JS, SVG con refs externas, HEIC,
truncados).

**El caso que lo justifica todo** — y su test de aceptación: por Discord, a Hermes, una foto de una firma y un PDF:
«rellena aquí, aquí y aquí y fírmalo». El agente solo decide; organon ejecuta: `image_signature` (foto → PNG
transparente) → `doc_inspect` (campos AcroForm, anclas de texto con rect, líneas vacías, miniatura) → `doc_fill` +
`doc_stamp` → PDF de vuelta. Ningún LLM dentro de organon; el del agente ve cientos de bytes de JSON, no el PDF.

## 2. Arquitectura

- **Un servicio Python** (3.14, Litestar + FastMCP montado), sin gateway: todas las tools son nuestras. MCP y HTTP son
  dos vistas del **mismo catálogo**: añadir una tool = un fichero (función tipada con msgspec, docstring = descripción)
  + una fila `ToolSpec(nombre, sección, puerto, motor, concurrencia, gpu, timeout, tamaño máx., lenta)`. Test de
  paridad MCP/HTTP/catálogo.
- **Capas de la casa:** puertos por capacidad (`PdfFillPort`, `MattingPort`, `TranslatePort`, nunca por marca);
  *drivers* para sidecars (Gotenberg, LanguageTool, exiftool `-stay_open`, Stirling como respaldo); *adapters* para
  librerías en proceso (pikepdf, pypdfium2, pyvips, OpenCV, un único adapter ONNX Runtime para todos los modelos,
  DuckDB); *processors* para lo puro; un `ToolService`; una raíz de composición.
- **Procesos:** `organon-api` (sin trabajo pesado) + `organon-worker` (cola) + sidecars en red `internal` **sin
  egreso**. Modelos cargados perezosamente, con TTL y límite de RAM; un pool de procesos para lo que puede tumbar el
  intérprete.
- **Cola:** SQLite al principio (e-metaxy ya usa una), pgqueuer sobre ParadeDB si crece. Semáforo por motor
  (`max_concurrency` en el spec) y rechazo explícito «ocupado, reintenta en N s».
- **GPU:** una ranura lógica de tamaño 1 que por defecto nadie ocupa; ONNX con `CUDAExecutionProvider` solo si caben
  en ~2 GB y vLLM no los ha tomado.
- **Seguridad:** auth obligatoria (la autoridad OAuth de e-metaxy ya existe); tipo por contenido, no por extensión;
  límites de píxeles, páginas y bytes antes de decodificar; contenedores no-root, FS de solo lectura, tmpfs; las rutas
  se resuelven contra el almacén y las raíces permitidas, nunca libres.
- **Meta-tools** siempre cargadas: `organon_find(query)` (busca en el catálogo), `organon_job(job_id)`,
  `organon_artifact(id)`.

Rechazado: un servidor MCP por sección (procesos y credenciales sin ahorro de contexto); MetaMCP/ContextForge/Docker
gateway (agregan servidores ajenos que no tenemos); tool search propio (lo hacen ya los clientes); base64 en el
contexto; Celery.

## 3. Secciones y herramientas

Veredictos: **A** adoptar · **C** candidato (banco antes) · **S** saltar. Copyleft fuerte y pesos no comerciales son
veto salvo aislamiento explícito como proceso externo y decisión registrada.

### doc/

| Capacidad | A | C | S (por qué) |
|---|---|---|---|
| Generar PDF con plantilla (cartas, facturas) | **typst** (Rust, JSON → PDF/A) | docxtpl (Word del cliente) | Quarto (pesado) |
| md/html → docx/odt/pptx/epub | **pandoc** (proceso externo) | WeasyPrint (HTML+CSS) | — |
| office/html → pdf | **Gotenberg** (sidecar, LibreOffice + Chromium) | — | LibreOffice directo (Gotenberg ya lo envuelve) |
| → markdown (lo que hay hoy) | **docling** (ya corre), **anytomd** | — | — |
| Operar PDF: merge/split/rotar/cifrar/metadatos | **pikepdf** (qpdf) | pdfcpu (stamp, forms) | pypdf |
| Texto con bbox, render página→imagen | **pypdfium2** (evita AGPL) | pdfplumber (líneas y celdas) | — |
| Redacción real (quitar el texto, no taparlo) | — | PyMuPDF **AGPL**, aislado tras un puerto | — |
| Formularios AcroForm | **pikepdf** | pdfcpu | XFA dinámico (sin OSS fiable: avisar) |
| Localizar destinos sin LLM | `doc_inspect`: campos → anclas de texto → líneas `____`/rectángulos → layout docling → OCR si es escaneado | detector de campos entrenado (solo si lo anterior falla en el corpus) | — |
| Firma visual | foto → PNG con **OpenCV** (umbral adaptativo, normalizar iluminación, recorte, alfa) + **pikepdf** estampa | — | rembg (excesivo para tinta) |
| Firma criptográfica PAdES | **pyHanko** (la clave nunca se expone por MCP) | — | open-pdf-sign (no verificado) |
| OCR con bbox por palabra | **RapidOCR** (ONNX), **Tesseract** | PaddleOCR | Surya (GPL + pesos restrictivos), docTR |
| Hojas de cálculo | **python-calamine**, **DuckDB** | rust_xlsxwriter/openpyxl (escribir) | csvkit |
| Lectores (eml, epub, odt, rtf) | stdlib `email`, pandoc | — | extract-msg (GPL), EbookLib (AGPL) |
| Diff de documentos | a md (docling) + diff textual; visual: render + diff de píxeles | — | — |

### image/

| Capacidad | A | C | S (por qué) |
|---|---|---|---|
| Convertir/redimensionar/recortar/color/strip | **libvips (pyvips)** con mozjpeg, libwebp, libheif | Pillow (fallback), AVIF/JXL (lentos → job) | ImageMagick (historial de CVE), imgproxy |
| Optimizar | **oxipng** | pngquant (GPL, solo como proceso) | — |
| Quitar fondo | **ISNet**, **U²-Net** (rembg, Apache) | BiRefNet-lite, BEN2 Base (job) | RMBG (pesos NC) |
| Upscale/denoise | denoise **OpenCV** | Real-ESRGAN compacto (job), FSRCNN | GFPGAN/CodeFormer (alucinan caras, NC) |
| Detección | **RF-DETR N/S** (Apache) | D-FINE, YOLOX | Ultralytics (AGPL), YOLO-NAS (NC) |
| Segmentación por prompt | — | MobileSAM/EfficientSAM, SAM2-tiny (job) | — |
| Caras y redacción | **YuNet** + blur vips | MediaPipe | SCRFD/insightface (pesos NC) |
| Profundidad | **Depth Anything V2 Small** | MiDaS | Base/Large (pesos NC) |
| OCR de escena | **RapidOCR** | Tesseract, ocrs (Rust, joven) | EasyOCR |
| QR/códigos | **zxing-cpp** (lee y escribe) | segno (SVG) | pyzbar |
| Metadatos | **exiftool** (`-stay_open`), strip con vips | crates Rust | exiv2 (GPL) |
| Hash/diff | **PDQ**, diff vips, SSIM | imagehash, odiff | dssim (AGPL) |
| Vectorizar / rasterizar SVG | **vtracer**, **resvg** | potrace (GPL, B/N) | CairoSVG |
| Escanear documento (perspectiva) | **OpenCV** | page-dewarp | unpaper, ScanTailor |

### audio/ · video/

| Capacidad | A | C | S |
|---|---|---|---|
| Transcode, cortar, normalizar (EBU R128), silencio, denoise | **ffmpeg** (`loudnorm`, `silenceremove`, `arnndn`) | DeepFilterNet | SoX |
| Diarización | **sherpa-onnx** (sin token) | pyannote (modelos con gating) | Sortformer/NeMo (NC) |
| Stems | — | Demucs, audio-separator (job) | — |
| Huella acústica | **chromaprint/fpcalc** | — | — |
| Vídeo: cortes, keyframes, miniaturas, subs, GIF/WebP | **ffmpeg** | PySceneDetect | gifski (AGPL), TransNetV2 |
| Descarga | **yt-dlp** (+ deno; se rompe a menudo: pin + humo diario) | — | — |

STT/TTS/VAD quedan en **e-voice**: organon no lo duplica.

### text/ · data/ · web/

| Capacidad | A | C | S |
|---|---|---|---|
| Idioma | **lingua-rs** | — | fastText lid (archivado) |
| Traducción sin LLM | — | **Bergamot** vs **CT2 + OPUS-MT** vs Argos (banco es↔en) | LibreTranslate (AGPL), NLLB (NC) |
| Ortografía/gramática ES | **LanguageTool** (sidecar Java, LGPL) | — | Harper (solo EN) |
| PII | **Presidio** + recognizer GLiNER (ya corre) + NIF/NIE | modelos GLiNER-PII | — |
| Tokens | **tiktoken/HF tokenizers** (sin tokenizer público de Claude) | — | — |
| Regex/diff seguros | **regex (Rust)/RE2**, `similar` | — | — |
| Keywords/resumen extractivo | — | YAKE (LGPL), TextRank | KeyBERT (TEI + MMR lo hace) |
| Tablas | **DuckDB** (sin acceso externo) | qsv (streaming) | Polars como tool, csvkit, xsv |
| JSON/YAML/TOML | **jq**, **yq** (mikefarah), **e-serde** | jaq | — |
| Gráficos | **vl-convert** (Vega-Lite sin navegador) | — | Plotly+Kaleido |
| Web → texto | **trafilatura**, playwright (ya corre) | readability-rs, Mozilla Readability | Firecrawl (AGPL) |
| Archivar / enlaces | **monolith**, **lychee** | — | SingleFile (AGPL), linkchecker (GPL) |

### code/ (condicional)

Claude Code ya ejecuta código en su sandbox; Hermes tiene backends de terminal. `code/` solo si aparece código no
confiable que ninguno aísle. Escalones: cálculo puro → **Pyodide/Deno** sin red ni FS; shell/nativo → contenedor
`--network none` + bwrap/nsjail; hostil → gVisor. Judge0 y Piston, no (GPL, cgroup v1, sin mantenimiento).

### De runonweb.ai

Es un SDK de 14 modelos ONNX en el navegador, sin servidor ni cómputo clásico. Lo que inspira y entra: quitar fondo
(BEN2/ISNet), detección (RF-DETR), profundidad (Depth Anything Small), OCR (PP-OCR vía RapidOCR), traducción Marian
(Bergamot). Lo demás ya lo cubrimos (STT, TTS, embed) o es LLM/VLM/difusión.

## 4. e-metaxy: qué queda y qué se va

Inventario (HEAD `4175a46`, 6.709 líneas src, 147 tests):

- **Lo que usa #tekton:** la tool `eng` y `work_status` por el routing; en la práctica también `catalog`, `doc_read`,
  `live_list`, `live_send`. Entra por **OAuth** (las credenciales de Claude Code guardan el token): la autoridad, la
  página de consentimiento y la passphrase **se quedan**.
- **Se va (solo OpenHuman):** `adapters/openhuman.py`, `adapters/discord.py` (webhook de `oh-eng`), el `caller` y su
  `NotifierPort`/`_start_notify`, settings `openhuman_*`/`discord_webhook`, 12 tests, `TODO.md`, `ops/emetaxy.service`
  host-native, las narrativas de README/design; **~256 líneas src**. Más 238 líneas de settings de plantilla que nada
  lee. Fuera del repo: el hook `oh-eng` en e-nous, `core/nomos/stack.yaml`, las claves OH de `~/.config/e-metaxy/env`,
  `gnosis.yaml` y la ontología con `openhuman`.
- **Se muda a organon:** los conversores (`doc_read`, `/ops/md`, `/ops/doc`, adapters docling/anytomd, ~1.370
  líneas): son la semilla de `doc/`.
- **Hermes** tiene hoy `e-metaxy` en su MCP (desde `core/nomos/config/mcp.yaml`) y falla cada 5 min por no tener
  login. Decisión pendiente (ver el plan).
