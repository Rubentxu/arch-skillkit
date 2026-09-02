"""Read-side use cases over the Architecture World (V2.4 M0, docs/v2/55).

Each use case consumes the narrow ports — never `world.graph` — so the
same query runs identically behind CLI, MCP or HTTP adapters (ADR-0045).
"""
