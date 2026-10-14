# Performance evidence

## Post-gap performance audit — October 2026

Twenty-six semantic handlers that read one field now call `getField` directly,
avoiding construction of a temporary bound reader. Handlers that read multiple
fields keep their existing readers. Descriptor/mapping access, dynamic visitor
changes, callback order/state and input identity contracts remain covered.

| YouTube full walk | Before, seconds | After, seconds | Less time |
| --- | ---: | ---: | ---: |
| Native AST | 3.257 | 3.145 | 3.4% |
| Mapping AST | 1.851 | 1.702 | 8.0% |

The component matrix generally improves about 1.6-6.0%; the small native
comments case is 2.1% slower. Full-file callback signatures match exactly.
All 74 methods and 14 subtests pass on CPython 3.11-3.15, alongside 2,457
coordinated traversal immutability checks.

Measurements use CPython 3.12.0 on Windows, default garbage collection and
sequential alternating before/after processes. Large-file figures are medians
of three fresh processes per version. Component figures use three fresh
processes per version, seven warmed calls per process and the median of process
medians. All raw samples, including outliers and small regressions, are retained.
Imports, input reading and correctness comparisons are outside timing windows.

Reproduction scripts, exact Python source hashes, profiles, logs, environments,
and distributions are outside the repositories in
`C:/Users/Ryzen/Benchmarks/toolchain-performance-2026-10-13/`.
The report covers first-call/allocation costs, compatibility fallbacks and
Python 3.11/3.15 boundary timings as well as the main comparisons. These are
workload-specific results, not a universal speed guarantee.

## Earlier performance work

The second optimization round compares the original master (`0f8e69a`), the
modern starting implementation (`0f5d34e`), and measured revision `f5b1f51`.
The later `82257ff` result-copying repair leaves traversal unchanged.
Exact source hashes, seven timing samples per case, callback counts, errors and
all twenty expanded traversal cases are in [performance-round2.json](performance-round2.json).

CPython 3.12.0 / Windows, uninstrumented warm operations; construction, parsing,
imports and explicit garbage collection are outside the measured intervals:

| Full traversal | Old ms | Modern start ms | Current ms | Less time than modern start |
| --- | ---: | ---: | ---: | ---: |
| Small, SimpleNamespace | 0.0792 | 0.1374 | 0.0965 | 29.8% |
| Small, parser-native | 0.0725 | 0.2212 | 0.1597 | 27.8% |
| Small, mapping | Unsupported | 0.1279 | 0.0944 | 26.2% |
| Small, UserDict | Unsupported | 0.2189 | 0.1836 | 16.1% |
| Medium, SimpleNamespace | 5.6269* | 10.3295 | 8.0025 | 22.5% |
| Medium, parser-native | 5.0751* | 16.1295 | 12.1749 | 24.5% |
| Medium, mapping | Unsupported | 9.9604 | 8.6065 | 13.6% |
| Medium, UserDict | Unsupported | 16.9666 | 14.9518 | 11.9% |

The small fixture has 91 callbacks in all supported versions. The medium old
walker emits 5,913 callbacks versus 6,489 in both modern versions: it omits
destructuring/default-expression children. Its starred timings describe less
work and do not establish equal-correctness speed. Simple and custom-visitor
cases also improve against the modern starting implementation; raw records
identify every old callback mismatch.

Binding field readers, reducing default dispatch hops and resolving transparent
full-walk categories retain original-node identity, missing/null defaults,
descriptors, mapping methods, registration changes and custom visitor state.
The checked native APIs still cost more than the narrower original native-only
walk on the small fixture. This work does not claim zero old-port regressions.
Measurements are local observations and include ordinary machine variability.

The first investigation remains in [performance.json](performance.json), with
separate uninstrumented startup and allocation measurements. It removed eager
typing/dataclass imports, reducing source-only import from about 92 to 8.8 ms;
the original import was about 5.2 ms. Those samples predate this round and are
not relabeled as measurements of the latest source.

Archived measurements use `<workspace>/` for the original checkout root;
machine-specific absolute paths have been removed. Timing samples, source
hashes and callback counts retain their recorded values; error diagnostics
use the same portable path marker.
