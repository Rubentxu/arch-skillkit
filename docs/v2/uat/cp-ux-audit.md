# Auditoría UX — Control Plane (V2.4 M5)

**Alcance**: shell estático servido en `GET /` por `python/src/archskillkit/delivery/cli/control_plane.py::_render_shell()` (artefacto único `/tmp/opencode/cp-shell.html`, 1651 líneas, 55 KB, sin dependencias). Auditoría **estática** sobre el HTML/CSS/JS emitido; sin sesión de navegador en vivo (ver "Limitaciones" al final).

**Marco de referencia**:

- `PRODUCT.md` (registro `product`, sobrio/evidencia-primero, WCAG 2.2 AA, `prefers-reduced-motion`, anti-referencias: no SaaS dashboard, unknowns visibles, no chat-everywhere).
- `docs/v2/66-v2.4-control-plane-ux.md` (IA Home/Explore/Changes/Investigations/Governance/Runs; §4 evidence-first inline; §3 Viewer Hub; §5 unknowns; §6 acciones LLM contextuales; §8 progressive disclosure).
- Restricciones de implementación respetadas: shell zero-deps, CSP `script-src 'self' 'unsafe-inline'`, 127.0.0.1, bearer en memoria JS, endpoints auth-gated existentes.

## Verificación de tokens vivos

| Aspecto | Valor medido | Estado |
|---|---|---|
| Color `--text-muted` (`#7c8099`) sobre `--bg` (`#0f1117`) | 4.86:1 | AA pass (≥4.5) |
| `--text-muted` sobre `--surface` (`#1a1d27`) | **4.33:1** | **AA fail** |
| `--text-muted` sobre `--surface-2` (`#242836`) | **3.77:1** | **AA fail** |
| `--text` (`#e2e4ea`) sobre `--bg` | 14.84:1 | AAA |
| `--fail` (`#d4574f`) sobre `--bg` | 4.74:1 | AA pass |
| `prefers-reduced-motion` honrado | sí (línea 25-30) | ✓ |
| `prefers-contrast: high` | sí (línea 552-554) | ✓ |
| `prefers-color-scheme: light` | **no implementado** | ⚠ polish |
| `<h1>` único, `<h2>` por panel, sin `<h3>` | cumple parcialmente | ⚠ |
| Skip-link al `<main>` | **ausente** | ⚠ a11y |

Texto muted aparece en `.field-hint` (línea 424-428), `.ev-id`/`.ev-location`/`.ev-rule`/`.ev-refs` (líneas 191-228), `.artifact-path` (438-441), `.coverage-card .label`, `.viewer-card .vid/.vname/.vavail` — todos dentro de paneles con fondo `--surface` o `--surface-2`. **Falla AA para texto pequeño** (0.7-0.85rem).

---

## P0 — bloqueantes del contrato de producto

### P0-1 · Estado de carga se congela en silencio ante cualquier fallo de red

**Qué / dónde**: `loadEvidence` (líneas 853-881), `loadCoverage` (883-916), `loadGaps` (918-939), `loadFindings` (941-963), `loadStatus` (840-851), `loadProjections` (971-990), `loadFavorites` (993-999). Ninguno de los siete tiene `.catch()`; sólo resuelven con `status !== 200`. `loadHealth` (816-838) sí lo tiene, pero su feedback es un badge `0.7rem` en el header (línea 561).

**Por qué importa**: Si el servidor cae, el puerto cambia o la red se interrumpe, los paneles muestran `Loading …` indefinidamente. La única señal es un badge 7 mm en la cabecera — fácil de pasar por alto. **PRODUCT.md principio 2**: "Make unknowns and low coverage visible; false confidence is a product failure." Una UI que parece "cargando" cuando en realidad está rota produce exactamente esa falsa confianza.

**Fix concreto**: Añadir `.catch()` que renderice `<p class="error-state" role="alert">No se pudo contactar el servidor — ¿está escuchando en 127.0.0.1?&lt;br&gt;Detalle: <code>{err.message}</code></p>` en el body correspondiente. Añadir un `<div id="global-error" role="alert" aria-live="assertive">` reutilizable para fallos de `/health` que muestre CTA "Reintentar" (re-corre `loadAll`). Esfuerzo: **S**.

---

### P0-2 · La funcionalidad de favoritos está sin superficie de UI (feature muerta)

**Qué / dónde**: CSS para `.viewer-cards`, `.viewer-card .vid .vname .vavail .fav-btn` (líneas 493-549). JS `updateViewerCards()` (líneas 1033-1039) hace `querySelector('[data-viewer-id="' + fid + '"] .fav-btn')` y `toggleFavorite()` llama a PUT `/favorites`. **Pero no existe `<div id="viewer-cards">` en el HTML renderizado** (verificado: el contenedor no aparece en ninguna línea del shell, sólo las reglas CSS). La función `updateViewerCards()` corre silenciosamente, no encuentra nada, y `toggleFavorite()` envía el PUT sin que el usuario vea estrella alguna.

**Por qué importa**: Slice 26 del M5 está parcialmente implementado en backend + JS pero invisible para el operador. El usuario hace `PUT /favorites` sin feedback. Doc 66 §3 exige un Viewer Hub con visor + disponibilidad + estado, y el principle "Prefer a small number of precise, contextual actions" exige que lo que existe sea descubrible.

**Fix concreto**: Renderizar `<div id="viewer-cards" class="viewer-cards" role="list" aria-label="Available viewers">` dentro del panel Viewer Hub (línea 666, junto a `artifact-info`). Poblar desde `loadProjections()` con un `<article class="viewer-card" role="listitem" data-viewer-id="{id}">` que contenga nombre + `vavail` + botón estrella accesible (`aria-pressed`, `aria-label="Toggle favorite for {name}"`). Esfuerzo: **M**.

---

### P0-3 · Arquitectura de información: faltan 3 de las 6 áreas de doc 66, sin buscador de elementos

**Qué / dónde**: El shell renderiza cinco paneles: `#evidence-panel`, `#coverage-panel`, `#gaps-panel`, `#findings-panel`, `#viewer-panel` (líneas 584-677). Faltan secciones completas del §2 de doc 66:

- **Explore** — sin buscador de elementos/relaciones, sin panel "selección actual" con Why/Evidence/Confidence/Origin/Changes/Impact/Open gaps (§4: "No esconder provenance detrás de una página secundaria").
- **Changes** — sin selector snapshot/commit, sin `ArchitectureDelta`.
- **Investigations** — sin `AgentRun` ni goals/tasks/hypotheses.
- **Runs** — sin `RunLedger`/timings/artifacts.
- **Governance** — sólo "Governance Findings" (no proposals, no waivers, no debt, no simulation, no promotion gates).

El "Home/Snapshot" además omite: freshness, Architecture Coverage como overview, open drift count, open Knowledge Gaps count, Fitness Profile, typed suggested actions.

**Por qué importa**: PRODUCT.md principio 3 "Use progressive disclosure: orient a human first, then reveal raw graph, run and provenance detail on demand" no se puede cumplir sin el andamiaje de Explore + Changes + Investigations. Sin buscador, no se puede iniciar la interacción "evidence-first" — el panel Evidence es pasivo.

**Fix concreto**: (a) Sustituir `<main>` por `<nav aria-label="Sections">` con seis `<a href="#sec-home|#sec-explore|...">` (modo tabs o router mínimo) — todo client-side, sin nuevos endpoints. (b) Añadir `<section id="explore-panel">` con `<input type="search" id="element-search" aria-label="Search architecture elements" placeholder="Find component / relation">` que llame a `GET /elements?q=` (requeriría nuevo endpoint — out of scope audit, marcar dependencia). (c) Hacer que cada item en `.evidence-item` (línea 184-228) sea un `<button class="evidence-item" aria-expanded="false" aria-controls="ev-detail-{id}">` con disclosure panel inline para §4. Esfuerzo: **L** (alcanza P0 sólo el sub-paso (c), los demás pueden pasar a P1).

**Sub-fix mínimo viable (alcance P0)**: (c) sólo — disclosure inline en evidence-item. Esfuerzo: **M**.

---

### P0-4 · Dot verde hardcoded en "Coverage & Unknowns" antes del fetch — falsa confianza

**Qué / dónde**: Línea 601: `<h2 id="coverage-heading" class="ok">Coverage &amp; Unknowns</h2>`. El pseudo-elemento `.panel-header h2.ok::before` (líneas 126-128) pinta un círculo `8px` verde. Antes de que `/coverage` responda, el heading ya dice visualmente "todo bien". `loadCoverage` luego sobreescribe la clase, pero la primera pintura muestra el estado `ok` hardcoded.

**Por qué importa**: Violación directa y literal del PRODUCT.md principio 2. Un operador que abre el panel durante un fetch lento o un fallo de red ve un círculo verde que dice "Coverage & Unknowns" — exactamente la "falsa confianza" que el producto declara como failure mode. Lo mismo aplica a `evidence-heading`, `gaps-heading`, `findings-heading`, `viewer-heading` que arrancan sin clase de estado — el `::before` (líneas 116-124) cae al default `var(--text-muted)`. Esos al menos son visualmente "neutrales" — sólo Coverage miente.

**Fix concreto**: Cambiar línea 601 a `class="unknown"` (añadir regla `.panel-header h2.unknown::before { background: var(--border); }` — equivalente visual al `badge-unknown`, línea 84). Cargar el dot real cuando llegue la respuesta. Esfuerzo: **XS** (un carácter + una regla CSS).

---

### P0-5 · Contraste WCAG AA fallido en texto muted dentro de paneles

**Qué / dónde**: Tokens `--text-muted: #7c8099` (línea 18) sobre `--surface: #1a1d27` da **4.33:1** y sobre `--surface-2: #242836` da **3.77:1**. Texto afectado: `.field-hint` (líneas 424-428 — usado 12+ veces), `.ev-id`/`.ev-location`/`.ev-rule`/`.ev-refs` (líneas 191-228, todos los items de evidencia), `.artifact-path` (438-441), `.coverage-card .label` (174-179), `.viewer-card .vid` (511-515). Tamaños 0.7-0.85rem — texto pequeño donde AA es más estricto.

**Por qué importa**: PRODUCT.md "Accessibility & Inclusion — WCAG 2.2 AA". El panel Evidence es el pilar del producto — si su metadata (location, rule, refs) es ilegible para usuarios con baja visión, falla la promesa evidence-first.

**Fix concreto**: Subir `--text-muted` a `#9ea3bd` (≈5.8:1 sobre surface, 5.1:1 sobre surface-2 — AA pass). Validar con `python3 -c "<script contraste>"` antes de mergear. Esfuerzo: **XS**.

---

## P1 — mejoras de alto valor

### P1-1 · Acciones LLM contextuales (§6) totalmente ausentes

**Qué / dónde**: Doc 66 §6 lista "Investigate this gap", "Explain this relation", "Enrich this projection", "Review contradictory evidence", "Simulate a change" — ninguna existe en el shell. El producto declara como anti-referencia "Omnipresent chat interfaces that replace contextual investigation actions" — pero la contracara (acciones contextuales inline) tampoco está.

**Fix**: Añadir un `<menu class="ctx-actions">` por item en `.gaps-item` y `.finding-item` con `<button data-action="investigate" data-target="{id}">Investigate this gap</button>`. POST a `/investigations` (requiere endpoint nuevo — flag para el equipo). Esfuerzo: **L**.

### P1-2 · Botones del Viewer Hub §3 faltan

**Qué / dónde**: Doc 66 §3 especifica `[Regenerate] [Open external] [Export] [Evidence overlay]`. Sólo hay `Open viewer` + `Edit draw.io` + `Open embedded Arrows` (líneas 670-672).

**Fix**: Añadir `Regenerate` (POST `/projections/{id}/regenerate`), `Open external` (window.open al artefacto servido), `Export` (GET `/projections/{id}/export?format=svg|cypher`), `Evidence overlay` (toggle que añade highlight sobre el iframe). Esfuerzo: **M**.

### P1-3 · Sin gestión de foco al conectar

**Qué / dónde**: `connect()` (líneas 1621-1628) llama a `showPanels()` y `loadAll()` pero no mueve foco. Usuarios de teclado / lector de pantalla quedan en el botón Connect mientras aparecen paneles nuevos.

**Fix**: Tras `showPanels()`, `document.getElementById("main").focus()` (requiere `tabindex="-1"` en `<main>`) o foco al primer heading del panel. Esfuerzo: **XS**.

### P1-4 · Sin skip-link al `<main>`

**Qué / dónde**: `<main id="main" role="main">` (línea 566). WCAG 2.4.1 Bypass Blocks.

**Fix**: Primer hijo del `<body>`: `<a class="skip-link" href="#main">Skip to main content</a>` con CSS que lo oculte hasta `:focus-visible`. Esfuerzo: **XS**.

### P1-5 · First-run UX: jargon "JSON envelope" sin pista de cómo arrancar

**Qué / dónde**: Líneas 574-577 — el hint dice "paste the token from the startup line (the `token` field in the JSON envelope printed to stdout)". Un usuario nuevo no sabe qué es un "envelope" ni dónde está stdout. Si la sesión ya tenía servidor arrancado y cerró la terminal, no hay manera de recuperar el token.

**Fix**: Reemplazar con microcopy concreto: "Start the server: <code>archskillkit control-plane</code> · Copy the `token` value from the JSON line printed in your terminal · Paste here". Considerar añadir un enlace a `docs/v2/54` o un tooltip con el comando exacto. Esfuerzo: **S**.

### P1-6 · `aria-live="polite"` en `#status-bar` sin contenido vivo

**Qué / dónde**: Línea 560: `<div id="status-bar" role="status" aria-live="polite">`. Sólo contiene `#health-badge` y `#project-info`. El badge cambia una vez por fetch (`ok` / `auth` / `fail`); `#project-info` nunca se popula (línea 562: `<span id="project-info"></span>` sin JS que lo escriba).

**Fix**: Poblar `#project-info` con `body.project_id + " · " + body.snapshot.snapshot_id`. Añadir timestamp de "last successful fetch" que se actualice en cada `loadAll()`. Esfuerzo: **S**.

### P1-7 · Estados de error genéricos sin contexto de recuperación

**Qué / dónde**: Líneas 878, 913, 936, 960, etc.: `<p class="error-state">Error 401: Unauthorized</p>` — sin CTA retry ni link a docs.

**Fix**: Reemplazar por componente de error con tres posibles acciones (Retry / View docs / Copy error id). Esfuerzo: **S**.

### P1-8 · Iframes sandbox sin `allow-same-origin` pueden romper el bridge postMessage (a validar en navegador)

**Qué / dónde**: Líneas 691-692 y 737-738: `<iframe ... sandbox="allow-scripts" referrerpolicy="no-referrer">`. Sin `allow-same-origin`, el iframe corre en origen opaco (`null`). El código usa `frame.contentWindow.postMessage(payload, EDITOR_ORIGIN)` (línea 1285) y `postMessage(payload, location.origin)` (línea 1435). Ambos `targetOrigin` son explícitos, no `"*"`. **Riesgo**: el receptor no aceptará el mensaje porque su origen efectivo es `null`, no `EDITOR_ORIGIN` ni `location.origin`. El navegador puede lanzar `DOMException` o descartar silenciosamente según motor.

**Por qué importa**: Si rompe, Arrows + draw.io no cargan diagramas y `Create proposal` queda inerte — P0 funcional. El spike 25b validó Arrows visualmente con un iframe; el atributo `sandbox` actual puede diferir del testeado.

**Fix**: Confirmar en navegador real; si rompe, añadir `allow-same-origin` + `allow-popups` al sandbox del draw.io (es externo, mayor riesgo) o cambiar el bridge a `targetOrigin: "*"` (pierde defensa en profundidad). Esfuerzo: **S** si confirmación; **M** si fix.

---

## P2 — pulido

### P2-1 · Botones toggle sólo texto `[−]` / `[+]` sin `aria-label`

**Qué / dónde**: Líneas 588-589, 602-603, 616-617, 630-631, 644-645, 684-685, 730-731. `<button class="toggle-btn" aria-expanded="true" aria-controls="...">[−]</button>`. Lector de pantalla anuncia sólo "−" (dash, mute).

**Fix**: `aria-label="Collapse Evidence panel"` (cambia con `aria-expanded`). Esfuerzo: **XS**.

### P2-2 · Sin h3 — sub-secciones sin jerarquía semántica

**Qué / dónde**: viewer-hub interno, evidence items, gap items — todos son `<div>` planos. Lectores de pantalla no distinguen sub-grupos.

**Fix**: Añadir `<h3>` para "Available viewers", "Candidate details", etc. Esfuerzo: **S**.

### P2-3 · `prefers-color-scheme: light` no soportado

**Qué / dónde**: Sólo `prefers-contrast: high` (línea 552) está implementado. Usuarios en sistemas claros ven dark forzado.

**Fix**: Añadir `@media (prefers-color-scheme: light) { :root { ... } }` con paleta sobria equivalente. Esfuerzo: **S**.

### P2-4 · Estados vacíos demasiado escuetos

**Qué / dónde**: Líneas 859, 924, 947: `<p class="empty-state">No evidence recorded.</p>`. Sin CTA.

**Fix**: Añadir el siguiente paso sugerido ("Run `archskillkit scan` to populate evidence" — verificar copy con el equipo). Esfuerzo: **S**.

### P2-5 · Tipografía — rhythm de paneles monótono

**Qué / dónde**: Todos los `<h2>` de panel con `font-size: 0.875rem` (línea 109). Sin variación visual entre Coverage (estado) y Findings (lista). Información de estado se pierde.

**Fix**: Heading de Coverage podría usar número grande (36-48px) tipo "fitness profile" como pide doc 66 §2. Esfuerzo: **S** (sólo CSS).

---

## Orden de implementación sugerido

Tres primeros — máxima relación señal/ruido:

1. **P0-4** (Coverage dot hardcoded `ok`) — **un carácter + una regla CSS**, elimina una violación literal del PRODUCT.md. Si hay que defender el trabajo ante el equipo, "eliminamos una mentira visible en cinco minutos" abre la conversación.
2. **P0-5** (contraste muted) — **un cambio de variable CSS**, recupera AA en el panel más importante del producto (Evidence). Validable con un one-liner de Python antes de mergear.
3. **P0-1** (silent fetch failures) — añade `.catch()` en siete funciones + un panel de error global. **Elimina la clase entera de bugs "todo parece colgado"** que cualquier operador va a sufrir el primer día que el puerto cambie.

Razón del orden: los tres son fixes **mínimos, sin nuevos endpoints, sin cambiar la IA**, alineados al contrato — y los tres cubren las tres dimensiones (verdad visual, accesibilidad, robustez). P0-2 (favoritos) y P0-3 (IA Explore) requieren decisiones de scope más grandes; mejor cuando haya acceptance criteria del equipo.

---

## Limitaciones de la auditoría

- **Sin sesión de navegador en vivo**: no se ejecutó JS. P0-1 confirma挂了 sintácticamente (no hay `.catch`), pero el comportamiento exacto ante fallos de red (¿status 0 vs exception?) puede diferir. Recomendado: reproducir con DevTools throttling "Offline".
- **P1-8 (sandbox iframe)**: no se confirmó empíricamente que el bridge postMessage falle en Chromium/Firefox actuales. La especificación dice que el targetOrigin debe matchear; conviene validar con `console.log(evt.origin)` en un handler de prueba antes de cambiar el sandbox.
- **Sin validación de los endpoints backend**: `/evidence`, `/coverage`, etc. se asumieron conforme al contrato; no se auditaron respuestas reales.
- **Sin captura visual**: imposible confirmar el render en 320/768/1280 px desde el HTML estático. Recomendado UAT visual con `playwright-cli` en los tres viewports.
- **Tokens de color medidos con sRGB; OKLCH daría valores ligeramente distintos** — fuera del scope del audit (el producto usa hex explícito, no OKLCH).