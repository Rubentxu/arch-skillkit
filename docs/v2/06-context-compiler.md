# Context Compiler

## Objective

No entregar el grafo entero al LLM.

## Inputs

- task/question;
- Architecture World view;
- Code Index;
- budget.

## Output

`ContextPack`

```yaml
goal:
summary:
architecture:
  elements: []
  relations: []
code:
  symbols: []
  paths: []
evidence: []
source_snippets: []
uncertainties: []
budget:
  max_nodes:
  max_edges:
  max_source_lines:
```

## Pipeline

1. clasificar intención;
2. resolver objetos arquitectónicos;
3. consultar Code Index;
4. expandir vecindad limitada;
5. recoger evidence;
6. obtener snippets dirigidos;
7. rankear;
8. aplicar budget;
9. registrar context reads.

## Principle

Más grafo no significa mejor contexto.
