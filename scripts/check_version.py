"""Fail release validation before a mismatched tag is published."""
import json
import re
from pathlib import Path
version = Path("VERSION").read_text().strip()
assert re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version)
assert json.loads(Path("custom_components/rocket_launch_tracker/manifest.json").read_text())["version"] == version
assert f"## {version}\n" in Path("CHANGELOG.md").read_text(encoding="utf-8")
print(f"Version {version} agrees across VERSION, manifest and changelog")
