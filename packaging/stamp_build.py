"""Write build_info.json with CI build provenance.

Run by the GitHub Actions workflow before packaging so the resulting binaries can
report the exact commit, tag, and build date they were produced from. The file is
git-ignored; it only exists inside a build.

Reads the standard GitHub Actions environment variables and prints the resolved
release version to stdout (and to ``GITHUB_OUTPUT`` as ``version``) so the
installer step can pick it up.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

# Allow running as `python packaging/stamp_build.py` from the repo root by putting
# the repo root (which holds version.py) on the import path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from version import __version__


def main() -> int:
    sha = os.environ.get("GITHUB_SHA", "")[:7]
    ref_name = os.environ.get("GITHUB_REF_NAME", "")
    ref_type = os.environ.get("GITHUB_REF_TYPE", "")
    tag = ref_name if ref_type == "tag" else ""
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    info = {"commit": sha, "tag": tag, "date": date}
    target = Path(__file__).resolve().parent.parent / "build_info.json"
    target.write_text(json.dumps(info, indent=2) + "\n", encoding="utf-8")

    version = tag[1:] if tag.startswith("v") else (tag or __version__)
    print(f"Wrote {target.name}: {info} -> version {version}")

    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(f"version={version}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
