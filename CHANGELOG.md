# Changelog

## 2.0.0 — unreleased

- Require Python 3.11+; preserve import and camelCase APIs, export all public walkers/searches.
- Repair all traversal/search engine failures, category dispatch, override isolation,
  callback identity and falsey state handling.
- Repair destructuring defaults and SwitchCase traversal.
- Add mapping ASTs, native aliases and validated UTF-16 `start/end` or `range` searches.
- Add module attributes, dynamic import options, modern field adapter and JSX handlers.
- Add pinned reference parity, seeded search properties, packaging checks and CI.

Migration: searches require nonnegative integer UTF-16 positions and raise clear
errors for unavailable/invalid ranges. Ancestor walkers preserve explicit falsey
state. `Found` is a result object rather than an exception. Unknown types raise
`ValueError`. Custom `make` results are overlays; use indexed handler access
rather than relying on modifications to the supplied base. Unsupported proposals
still require custom handlers.
