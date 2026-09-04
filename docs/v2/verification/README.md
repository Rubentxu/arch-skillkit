# Deterministic Verification

## 1. Qué resuelve

Este directorio convierte restricciones arquitectónicas en findings
reproducibles y comparables contra una baseline exacta.

## 2. Crear baseline inicial

Desde la raíz del repo:

```bash
python verification/arch_conformance.py \
  --root python/src/archskillkit \
  --contracts verification/architecture-contracts.json \
  --write-baseline verification/architecture-baseline.json
```

Revisar manualmente el diff. No aceptar findings desconocidos.

## 3. Gate normal

```bash
python verification/arch_conformance.py \
  --root python/src/archskillkit \
  --contracts verification/architecture-contracts.json \
  --baseline verification/architecture-baseline.json \
  --output build/architecture-report.json
```

PASS:
- ningún finding nuevo;
- todos los findings baselineados siguen identificados de manera exacta.

Cuando se corrige deuda, el gate informa `resolved_baseline`. Actualizar baseline
eliminando esa deuda.

## 4. Política

Nunca ejecutar `--write-baseline` automáticamente en CI.

Sólo se usa:
- bootstrap inicial;
- cambio arquitectónico explícito aprobado.

## 5. Integración mise sugerida

```toml
[tasks."verify:architecture"]
run = "python verification/arch_conformance.py --root python/src/archskillkit --contracts verification/architecture-contracts.json --baseline verification/architecture-baseline.json --output build/architecture-report.json"

[tasks."verify"]
depends = ["verify:architecture", "test"]
```

Adaptar a la sintaxis mise real del repo.

## 6. Evolución

Las reglas `allow` temporales deben eliminarse milestone a milestone. El objetivo
final no es mantener un baseline grande, sino llegar a baseline vacío para
boundaries hard.
