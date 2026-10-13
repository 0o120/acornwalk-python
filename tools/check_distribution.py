"""Verify distribution contents, metadata and clean-wheel README examples."""
import argparse
import ast
import email
from pathlib import Path
import re
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dist", type=Path, default=ROOT / "dist")
    args = parser.parse_args()
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    version_source = ROOT / project["tool"]["hatch"]["version"]["path"]
    assignments = ast.parse(version_source.read_text(encoding="utf-8")).body
    version = next(ast.literal_eval(statement.value) for statement in assignments
                   if isinstance(statement, ast.Assign)
                   and any(isinstance(target, ast.Name) and target.id == "__version__"
                           for target in statement.targets))
    wheels = list(args.dist.glob("*.whl"))
    sources = list(args.dist.glob("*.tar.gz"))
    assert len(wheels) == len(sources) == 1, "Use a clean distribution directory with one wheel and one source archive"
    with zipfile.ZipFile(wheels[0]) as archive:
        metadata = email.message_from_bytes(archive.read(next(name for name in archive.namelist() if name.endswith("/METADATA"))))
        assert metadata["Name"] == "acornwalk"
        assert metadata["Version"] == version
        assert metadata["Requires-Python"] == ">=3.11"
        assert metadata["License-Expression"] == "MIT"
        assert metadata.get_all("License-File") == ["LICENSE"]
        assert {"Development Status :: 5 - Production/Stable", "Typing :: Typed"} <= set(metadata.get_all("Classifier"))
        assert set(metadata.get_all("Project-URL")) == {
            f"{label}, {url}" for label, url in project["project"]["urls"].items()
        }
        assert not metadata.get_all("Requires-Dist")
        assert {"acornwalk/py.typed", "acornwalk/walk.pyi"} <= set(archive.namelist())
        assert not any("__pycache__" in name or name.startswith("tests/") for name in archive.namelist())
        with tempfile.TemporaryDirectory() as folder:
            archive.extractall(folder)
            examples = re.findall(r"```python\n(.*?)```", (ROOT / "README.md").read_text(encoding="utf-8"), re.S)
            script = ("import sys\nsys.path.insert(0, sys.argv[1])\nimport acornwalk\n"
                      f"assert acornwalk.__version__ == {version!r}\n" + "\n".join(examples))
            subprocess.run([sys.executable, "-I", "-c", script, folder], cwd=folder, check=True)
    with tarfile.open(sources[0]) as archive:
        prefix = archive.getnames()[0].split("/")[0]
        metadata = email.message_from_bytes(archive.extractfile(f"{prefix}/PKG-INFO").read())
        assert metadata["Version"] == version
        for name in ["README.md", "CHANGELOG.md", "CONTRIBUTING.md", "LICENSE",
                     "RELEASING.md", "PERFORMANCE.md"]:
            assert f"{prefix}/{name}" in archive.getnames(), f"Missing source-archive documentation: {name}"
    print("Source archive, wheel metadata, clean imports and README examples verified")


if __name__ == "__main__":
    main()
