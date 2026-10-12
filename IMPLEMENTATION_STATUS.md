# Implementation status

2.0.0 is prepared locally and unreleased. Audit items W01–W17 are addressed.
The API and compatibility contract are described in README and CHANGELOG.

Evidence on Python 3.11 and 3.12 / Node.js 24:

- The original 13 engine regression tests failed on the baseline, then passed.
- 39 unit/property/reference tests pass with warnings treated as errors.
- Every concrete core handler has a fixture. Native/mapping callback ordering and
  original-node identity are verified; modules, modern classes and JSX have tests.
- Native async/for-await aliases and missing-field defaults versus declared nulls
  are covered by the coordinated toolchain checks.
- Exact mapping/namespace fast paths and bounded mapping-type detection retain
  custom get methods, native descriptors, class proxies and virtual registration.
- Built-in handlers bind a field reader once per node. Registration/class guards
  preserve callback-time Mapping changes and replacements of custom get methods.
- Found results retain field identity, immutability, repr/equality/hash behavior,
  copying, pickling and weak references without eager dataclass/typing imports.
- Full and ancestor order match checksum-pinned acorn-walk/acorn 8.15.0.
- All search variants match pinned upstream across 50 deterministic generated
  expression trees, including UTF-16 astral offsets and wildcard/category tests.
- Source archive builds; wheel built from the archive passes metadata, clean
  extracted-wheel import and all Python README examples.
- CI is configured for Python 3.11–3.15 on Linux and Windows, plus macOS 3.11/3.15.
  Hosted workflows run on the modernization branch; see the
  [live GitHub CI evidence](https://github.com/0o120/acornwalk-python/actions).

Limits: a semantic walker cannot establish parser grammar conformance or
runtime equivalence. TypeScript/Flow/decorators/proposal nodes need custom
handlers; circular graphs and recursion beyond Python limits are unsupported.
Optional Node differential tests explicitly skip if Node is absent. Shared
parser/generator corpus acceptance is coordinated in the parent toolchain.

Performance investigation: native traversal of the identical 91-node ES2017
tree improved from 0.202 to 0.133 ms (mapping 0.120 ms). The old native-only
implementation took 0.074 ms. Source-only uninstrumented startup fell from
approximately 92 to 8.8 ms (old 5.2 ms) by removing eager typing/dataclass
imports. Accessors and diagnostics retain a measured cost. The final raw
evidence is in [performance.json](performance.json); timing and Python
allocation are measured separately, with exact source hashes and revisions.
