# Implementation status

2.0.0 is the next stable release. Audit items W01–W17 are addressed.
The API and compatibility contract are described in README and CHANGELOG.

Evidence on Python 3.11 and 3.12 / Node.js 24:

- The original 13 engine regression tests failed on the baseline, then passed.
- 41 unit/property/reference tests pass with warnings treated as errors.
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

Round-two full traversal takes 12–30% less time than the modern starting
implementation across native/mapping/UserDict small and medium cases. The
small native fixture is 0.0965 ms versus 0.1374 ms start and 0.0792 ms old.
The old medium walker omits 576 callbacks and therefore performs less work.
Validated native/protocol support retains an old-port latency gap; zero
regressions are not claimed. [Performance evidence](PERFORMANCE.md) records
old/start/current results, exact raw samples and the earlier separate
startup/allocation investigation. Slotted Found subclasses preserve shallow,
deep and pickle state, including shared/private slots and cyclic references.
