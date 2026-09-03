# Spike 25 — Embed de visores en el Control Plane (2026-09-03)

## 25a · LikeC4 — GO condicional (falta verificación visual humana)

Mecanismo validado: `likec4 build --base /likec4-site/ --output-single-file`
(v1.59.3) genera **un único HTML autocontenido** (~2,9 MB) con el modelo
compilado. Se sirve same-origin desde el Control Plane y se embebe con
iframe (`frame-src 'self'` — cubierto por default-src, CERO cambios CSP).
Fuentes CDN del bundle parcheadas a same-origin + vendorizadas (IBM Plex,
OFL; 6 woff2). La import perezosa de mermaid (no usada por nuestros
modelos) se neutraliza parcheándola a ruta local.

Evidencia: el iframe monta la app (react-flow `[data-id]` presente,
bundle 2,9 MB, 0 peticiones externas, 0 errores de consola salvo el
warning benigno de frame-ancestors en meta).

**Bloqueo residual**: el lienzo no PINTA en chromium headless (DOM
presente, WebGL2 disponible, 0 canvas). Pendiente: verificación visual
en navegador real del operador para discriminar limitación de headless
vs defecto real. Comando:

    python3 -m http.server 8899 -d artifacts/uat/m5/spike25/likec4-site
    # abrir http://127.0.0.1:8899

Versiones: likec4 gestionado por M1 es ANTIGUO (sin `gen webcomponent`);
el spike usa 1.59.3 aislado en /tmp — la integración requerirá bump del
runtime gestionado.

## 25b · Arrows — embed entry confirmado, build pendiente

- Repo `neo4j-labs/arrows.app` **Apache-2.0** (vendor legal).
- arrows.app público YA CAYÓ una vez (dominio); WEB_HANDOFF frágil.
- Embed oficial: canvas vive en `apps/arrows-ts/src/`, bundle Vite a
  `media/embed/` (usado por su extensión VS Code). Nuestro adapter ya
  emite `.arrows` JSON compatible.
- Pendiente: `npm ci` + build del embed + prueba de carga de nuestro
  `.arrows` real (87 nodos Next.js).

## Veredicto integración

| Visor | Mecanismo | CSP extra | Node runtime | Estado |
|---|---|---|---|---|
| draw.io | iframe embed.diagrams.net | frame-src externo (ya en prod) | no | ✅ slice 23d |
| LikeC4 | build single-file + iframe same-origin | ninguno | no (build only) | 🟡 pendiente paint check |
| Arrows | bundle Vite self-host + .arrows | ninguno | no (build only) | 🟡 build pendiente |
