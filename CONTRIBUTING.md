# Contributing

Use Python 3.11+ and an isolated development environment:

```console
python -m venv .venv
python -m pip install --require-hashes -r requirements-dev.lock
python -m unittest discover -s tests -v
python -m build --no-isolation
python tools/check_distribution.py
```

Activate `.venv` using the platform's normal activation command before installing.
Node.js 24 runs pinned upstream differential tests; without Node those tests
are explicitly skipped. Node is not needed at runtime. Each concrete core node
handler needs a fixture; JSX handlers need focused expression/metadata tests.
Search changes must preserve query order, state and node identity.

The build command creates a source archive and builds its wheel from that archive.
The distribution checker validates metadata, imports from a clean extracted
wheel and runs the Python README examples outside the source checkout. Commit
fixes with focused regressions. Keep examples, migration notes and support claims
consistent with tested behavior. Do not publish a release until coordinated
toolchain integration and supported Python CI pass.

Development tools are pinned, including transitive dependencies and hashes.
Regenerate deliberately with `uv pip compile requirements-dev.in --universal
--generate-hashes --output-file requirements-dev.lock`; review the result.
