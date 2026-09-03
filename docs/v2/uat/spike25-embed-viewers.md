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

## 25b · Arrows — **PASS** (2026-09-03, verificado visualmente)

`npm ci` (Node 25, sin force) + `BUILD_EMBED=1 npx nx build arrows-ts
--skip-nx-cache` (¡el cache de Nx reproduce el build sin embed si se
omite!) → bundle 774 kB JS + 550 kB CSS. `<base href="/">` del
embed.html exige reescritura a `./` para servir bajo subpath (mismo fix
que su extensión VS Code hace en `webviewHtml.ts`).

**Mecanismo de inyección** (bridge postMessage, `src/embed/bridge/`):
embed emite `{type:'ready'}` → host inyecta `{type:'load', graph,
docVersion}` con `nodes[{id,caption,position,labels,properties,style}]`
/ `rels[{id,fromId,toId,type,...}]`; embed confirma `graph-changed`;
export vía `{type:'request',kind:'cypher'|'svg'}`. Nuestro adapter ya
emite el modelo — hace falta un adaptador de forma (name→caption,
start/end→fromId/toId, posiciones grid) y el veredicto visual: 87 nodos
/ 55 relaciones renderizados, inspector `nodes: 87 relationships: 55`,
0 errores de consola. Canvas es HTML5 2D (la verificación debe usar el
bridge, no DOM text).

**Integración**: servir `dist/apps/arrows-ts` same-origin bajo
`/vendor/arrows/` (base-href reescrito en publish) + iframe + handshake.
Riesgos: ~1,3 MB JS+CSS sin code-splitting (cachear inmutable), toolchain
Nx/Vite 4 pinneado, atribución Apache-2.0/NOTICE (branding Neo4j dentro
del bundle), layout grid rudimentario (pasar layout real).

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
| Arrows | bundle Vite self-host + .arrows | ninguno | no (build only) | ✅ PASS (25b) |
