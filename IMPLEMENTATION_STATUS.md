# Implementation status

2.0.0 is prepared locally and unreleased. Audit items W01–W17 are addressed.
The API and compatibility contract are described in README and CHANGELOG.

Evidence on Python 3.11 and 3.12 / Node.js 24:

- The original 13 engine regression tests failed on the baseline, then passed.
- 24 unit/property/reference tests pass with warnings treated as errors.
- Every concrete core handler has a fixture. Native/mapping callback ordering and
  original-node identity are verified; modules, modern classes and JSX have tests.
- Native async/for-await aliases and missing-field defaults versus declared nulls
  are covered by the coordinated toolchain checks.
- Full and ancestor order match checksum-pinned acorn-walk/acorn 8.15.0.
- All search variants match pinned upstream across 50 deterministic generated
  expression trees, including UTF-16 astral offsets and wildcard/category tests.
- Source archive builds; wheel built from the archive passes metadata, clean
  extracted-wheel import and all Python README examples.
- CI is configured for Python 3.11–3.15 on Linux and Windows. Remote CI has not
  been executed or published by this local implementation.

Limits: a semantic walker cannot establish parser grammar conformance or
runtime equivalence. TypeScript/Flow/decorators/proposal nodes need custom
handlers; circular graphs and recursion beyond Python limits are unsupported.
Optional Node differential tests explicitly skip if Node is absent. Shared
parser/generator corpus acceptance is coordinated in the parent toolchain.
