#!/usr/bin/env python3
"""
Python Commit Security Gate — portable, git-root-aware.

A project-agnostic Python commit security gate. Keeps only the layers that apply
to any Python project (web or desktop):

    Layer 1 — Code Quality        (Ruff)
    Layer 2 — Type Safety         (MyPy + optional mypy-baseline)
    Layer 3 — Static Security     (Bandit + Semgrep)
    Layer 4 — Dependency Integrity(pip-audit, only when requirements*.txt staged)
    Layer 5 — Secret Protection   (detect-secrets + gitleaks)
    Layer 6 — AI Logic Validation (Gemini diff review — security_diff_review.py)

Every tool is optional: if it isn't installed the layer warns and is skipped,
so you can adopt the gate incrementally.

Install (run from the repo root)::

    python security/pre_commit_hook.py --install

Manual run without committing::

    python security/pre_commit_hook.py

Emergency bypass::

    git commit --no-verify      # avoid; fix the finding instead
"""
from __future__ import annotations

import datetime
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# ── Repo / environment discovery ─────────────────────────────────
# Resolve the repo root from the current working directory's git top-level so
# the gate guards whichever repo it is run from.

def _git_root() -> Path:
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, check=True,
        )
        return Path(out.stdout.strip())
    except (subprocess.CalledProcessError, FileNotFoundError):
        return Path.cwd()


ROOT = _git_root()
TOOLKIT_DIR = Path(__file__).resolve().parent          # <repo>/security
REPORTS_DIR = ROOT / "security" / "reports"
# The gate is normally launched by the venv interpreter via the installed shim,
# so the directory holding the running Python is the most reliable place to find
# the tools. Fall back to a repo-local .venv for manual `python` invocations.
# This keeps the gate working even when the venv lives outside the repo root.
# Note: do NOT resolve() sys.executable — in a venv that follows the symlink out
# to the base interpreter and loses the venv's bin dir.
_INTERP_BIN = Path(sys.executable).parent
_PREFIX_BIN = Path(sys.prefix) / ("Scripts" if os.name == "nt" else "bin")
VENV_BIN = ROOT / ".venv" / "bin"
_BIN_DIRS = [_INTERP_BIN, _PREFIX_BIN, VENV_BIN]
VENV_PYTHON = VENV_BIN / "python"

# Load .env so API keys (GEMINI_API_KEY, etc.) are available to Layer 6.
_dotenv = ROOT / ".env"
if _dotenv.exists():
    for _line in _dotenv.read_text().splitlines():
        _line = _line.strip()
        if _line and not _line.startswith("#") and "=" in _line:
            _key, _, _val = _line.partition("=")
            os.environ.setdefault(_key.strip(), _val.strip())

# ── Colours ──────────────────────────────────────────────────────

GREEN = "\033[32m"
RED = "\033[31m"
YELLOW = "\033[33m"
CYAN = "\033[36m"
RESET = "\033[0m"
BOLD = "\033[1m"


def _banner(layer: int, name: str) -> None:
    print(f"\n{CYAN}{BOLD}── Layer {layer}: {name} ──{RESET}", flush=True)


def _pass(msg: str = "PASS") -> None:
    print(f"  {GREEN}✓ {msg}{RESET}", flush=True)


def _fail(msg: str = "FAIL") -> None:
    print(f"  {RED}✗ {msg}{RESET}", flush=True)


def _warn(msg: str) -> None:
    print(f"  {YELLOW}⚠ {msg}{RESET}", flush=True)


def _skip(msg: str) -> None:
    print(f"  {YELLOW}⊘ {msg}{RESET}", flush=True)


# ── Helpers ──────────────────────────────────────────────────────

def _staged_py_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=d"],
        capture_output=True, text=True, cwd=ROOT,
    )
    return [f for f in result.stdout.strip().splitlines() if f.endswith(".py")]


def _staged_files() -> list[str]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=d"],
        capture_output=True, text=True, cwd=ROOT,
    )
    return [f for f in result.stdout.strip().splitlines() if f]


def _run(cmd: list[str], timeout: int = 120) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True, cwd=ROOT, timeout=timeout)


def _tool_available(name: str) -> bool:
    if shutil.which(name) is not None:
        return True
    return any((d / name).exists() for d in _BIN_DIRS)


def _tool_path(name: str) -> str:
    for d in _BIN_DIRS:
        candidate = d / name
        if candidate.exists():
            return str(candidate)
    return name


def _python() -> str:
    interp = _INTERP_BIN / "python"
    if interp.exists():
        return str(interp)
    if VENV_PYTHON.exists():
        return str(VENV_PYTHON)
    return sys.executable


def _config_arg(tool_flag: str, filename: str) -> list[str]:
    """Return [flag, path] if a config file exists in the repo or toolkit, else []."""
    for base in (ROOT, TOOLKIT_DIR):
        candidate = base / filename
        if candidate.exists():
            return [tool_flag, str(candidate)]
    return []


# ── Layers ───────────────────────────────────────────────────────

def layer_1_code_quality(staged: list[str]) -> bool:
    _banner(1, "Code Quality (Ruff)")
    if not staged:
        _skip("No staged .py files")
        return True
    if not _tool_available("ruff"):
        _warn("ruff not found — skipping")
        return True
    result = _run([_tool_path("ruff"), "check"] + staged)
    if result.returncode != 0:
        _fail("Ruff violations found")
        print(result.stdout[-500:] if result.stdout else result.stderr[-500:])
        return False
    _pass()
    return True


def layer_2_type_safety(staged: list[str]) -> bool:
    _banner(2, "Type Safety (MyPy)")
    if not staged:
        _skip("No staged .py files")
        return True
    if not _tool_available("mypy"):
        _warn("mypy not found — skipping")
        return True

    result = _run([_tool_path("mypy")] + staged)
    baseline_file = ROOT / "mypy-baseline.txt"
    if baseline_file.exists() and _tool_available("mypy-baseline"):
        filter_result = subprocess.run(
            [_tool_path("mypy-baseline"), "filter", "--allow-unsynced"],
            input=result.stdout, capture_output=True, text=True, cwd=ROOT,
        )
        if filter_result.returncode == 100:
            _pass("(resolved violations — run `mypy . | mypy-baseline sync`)")
            return True
        if filter_result.returncode != 0:
            _fail("New type errors introduced")
            print(filter_result.stdout[-500:] if filter_result.stdout else "")
            return False
        _pass("(baseline-filtered)")
        return True
    elif result.returncode != 0:
        _fail("MyPy errors found (no baseline filter)")
        print(result.stdout[-500:] if result.stdout else "")
        return False
    _pass()
    return True


def layer_3_static_security(staged: list[str]) -> bool:
    _banner(3, "Static Security (Bandit + Semgrep)")
    ok = True

    # Bandit
    if not staged:
        _skip("No staged .py files for Bandit")
    elif not _tool_available("bandit"):
        _warn("bandit not found — skipping")
    else:
        cfg = _config_arg("--configfile", "pyproject.toml")
        result = _run([_tool_path("bandit"), "-ll", "-q"] + cfg + staged)
        if result.returncode != 0:
            _fail("Bandit: HIGH+ severity findings")
            print(result.stdout[-500:] if result.stdout else result.stderr[-500:])
            ok = False
        else:
            _pass("Bandit")

    # Semgrep — scan all staged files (not just .py)
    semgrep_cfg = None
    for base in (ROOT, TOOLKIT_DIR):
        candidate = base / ".semgrep.yml"
        if candidate.exists():
            semgrep_cfg = candidate
            break
    all_staged = _staged_files()
    if semgrep_cfg is None:
        _warn("Semgrep: no .semgrep.yml config — skipping")
    elif not _tool_available("semgrep"):
        _warn("semgrep not found — skipping")
    elif not all_staged:
        _skip("No staged files for Semgrep")
    else:
        result = _run([_tool_path("semgrep"), "--config", str(semgrep_cfg),
                       "--error", "--quiet"] + all_staged, timeout=180)
        if result.returncode == 1:
            _fail("Semgrep: pattern matches found")
            print(result.stdout[-500:] if result.stdout else result.stderr[-500:])
            ok = False
        elif result.returncode >= 2:
            _warn(f"Semgrep: exited with code {result.returncode} (rule/config error)")
        else:
            _pass("Semgrep")

    return ok


def layer_4_dependencies() -> bool:
    _banner(4, "Dependency Integrity (pip-audit)")
    staged = _staged_files()
    if not any(f.startswith("requirements") and f.endswith(".txt") for f in staged):
        _skip("no requirements*.txt staged — skipping")
        return True
    if not _tool_available("pip-audit"):
        _warn("pip-audit not found — skipping")
        return True

    result = _run([_tool_path("pip-audit"), "--format", "json"], timeout=120)
    if result.returncode == 0:
        _pass()
        return True

    try:
        report = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        _fail("pip-audit: could not parse output")
        print(result.stdout[-500:] if result.stdout else "")
        print(result.stderr[-500:] if result.stderr else "")
        return False

    found: list[str] = []
    for dep in report.get("dependencies", []):
        for vuln in dep.get("vulns", []):
            vid = vuln.get("id")
            if vid:
                found.append(f"{vid} {dep.get('name', '?')} {dep.get('version', '?')}")

    if not found:
        _warn("pip-audit returned non-zero with no findings — treating as warning")
        return True

    accepted_ids: set[str] = set()
    for base in (ROOT / "security", TOOLKIT_DIR):
        accepted_file = base / "pip-audit-accepted.txt"
        if accepted_file.exists():
            for line in accepted_file.read_text().splitlines():
                token = line.strip()
                if token and not token.startswith("#"):
                    accepted_ids.add(token.split()[0])
            break

    unaccepted = [f for f in found if f.split()[0] not in accepted_ids]
    if unaccepted:
        _fail(f"pip-audit: {len(unaccepted)} unaccepted vulnerable dependencies")
        for line in unaccepted:
            print(f"      {line}")
        print("  Add to security/pip-audit-accepted.txt with rationale, or upgrade.")
        return False

    _warn(f"pip-audit flagged {len(found)} vuln(s), all in the accept-list")
    return True


def layer_5_secrets() -> bool:
    _banner(5, "Secret Protection (detect-secrets + gitleaks)")
    ok = True

    baseline = ROOT / ".secrets.baseline"
    if not _tool_available("detect-secrets"):
        _warn("detect-secrets not found — skipping")
    elif not baseline.exists():
        _warn("No .secrets.baseline — run `detect-secrets scan > .secrets.baseline`")
    else:
        result = _run([_tool_path("detect-secrets"), "scan", "--baseline", str(baseline)], timeout=300)
        if result.returncode != 0:
            _fail("detect-secrets: new secrets detected")
            ok = False
        else:
            _pass("detect-secrets")

    if not _tool_available("gitleaks"):
        _warn("gitleaks not found — skipping")
    else:
        result = _run([_tool_path("gitleaks"), "protect", "--staged", "-v"], timeout=60)
        if result.returncode != 0:
            _fail("gitleaks: secrets in staged changes")
            print(result.stdout[-300:] if result.stdout else "")
            ok = False
        else:
            _pass("gitleaks")

    return ok


def layer_6_ai_review() -> bool:
    _banner(6, "AI Logic Validation (Gemini)")
    # Prefer a copy alongside this toolkit; fall back to one in the repo.
    review_script = None
    for base in (TOOLKIT_DIR, ROOT / "security", ROOT / "utils"):
        candidate = base / "security_diff_review.py"
        if candidate.exists():
            review_script = candidate
            break
    if review_script is None:
        _warn("security_diff_review.py not found — skipping")
        return True

    diff = subprocess.run(["git", "diff", "--staged"], capture_output=True, text=True, cwd=ROOT)
    diff_lines = len(diff.stdout.splitlines()) if diff.stdout else 0
    if diff_lines < 20:
        _skip(f"Diff too small ({diff_lines} lines) — skipping AI review")
        return True

    try:
        result = _run([_python(), str(review_script)], timeout=30)
    except subprocess.TimeoutExpired:
        _warn("AI review timed out (30 s) — skipping")
        return True

    if result.returncode == 0:
        _pass()
        return True
    elif result.returncode == 2:
        _warn(result.stderr.strip() if result.stderr else "AI review unavailable")
        return True
    else:
        _fail("AI review blocked the commit")
        if result.stdout:
            print(result.stdout[-500:])
        return False


# ── Report ───────────────────────────────────────────────────────

def _write_report(results: dict[str, bool], staged: list[str]) -> Path | None:
    try:
        REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    except OSError:
        return None
    ts = datetime.datetime.now().strftime("%Y-%m-%dT%H%M%S")
    report_path = REPORTS_DIR / f"commit-{ts}.md"

    msg_result = subprocess.run(
        ["git", "log", "-1", "--format=%s"], capture_output=True, text=True, cwd=ROOT,
    )
    commit_msg = msg_result.stdout.strip() if msg_result.returncode == 0 else "(pre-commit)"
    overall = "PASS" if all(results.values()) else "BLOCKED"

    layer_names = {
        "layer_1": "Code Quality",
        "layer_2": "Type Safety",
        "layer_3": "Static Security",
        "layer_4": "Dependencies",
        "layer_5": "Secrets",
        "layer_6": "AI Review",
    }
    lines = [
        f"# Commit Gate Report — {ts}",
        "",
        f"**Last commit:** {commit_msg}",
        f"**Staged files:** {len(staged)}",
        f"**Gate decision:** {overall}",
        "",
        "| Layer | Domain | Result |",
        "|-------|--------|--------|",
    ]
    for key, name in layer_names.items():
        status = "✓ PASS" if results.get(key, True) else "✗ FAIL"
        lines.append(f"| {key.split('_')[1]} | {name} | {status} |")
    lines.append("")
    report_path.write_text("\n".join(lines))
    return report_path


# ── Install ──────────────────────────────────────────────────────

def install_hook() -> None:
    hook_dir = ROOT / ".git" / "hooks"
    if not hook_dir.exists():
        print(f"ERROR: {hook_dir} does not exist — run from inside a git repo.")
        sys.exit(1)
    python = _python()
    hook_path = hook_dir / "pre-commit"
    shim = (
        "#!/bin/sh\n"
        "# Python Commit Security Gate — installed by pre_commit_hook.py\n"
        f'exec "{python}" "{Path(__file__).resolve()}" "$@"\n'
    )
    hook_path.write_text(shim)
    hook_path.chmod(0o755)
    print(f"✓ Installed pre-commit hook at {hook_path}")
    print(f"  Guarding repo: {ROOT}")


# ── Main ─────────────────────────────────────────────────────────

def main() -> None:
    if "--install" in sys.argv:
        install_hook()
        return

    print(f"{BOLD}Python Security Gate — Commit Check{RESET}  (repo: {ROOT})")

    staged = _staged_py_files()
    all_staged = _staged_files()

    results: dict[str, bool] = {}
    results["layer_1"] = layer_1_code_quality(staged)
    results["layer_2"] = layer_2_type_safety(staged)
    results["layer_3"] = layer_3_static_security(staged)
    results["layer_4"] = layer_4_dependencies()
    results["layer_5"] = layer_5_secrets()
    results["layer_6"] = layer_6_ai_review()

    report = _write_report(results, all_staged)

    passed = sum(1 for v in results.values() if v)
    total = len(results)
    if all(results.values()):
        print(f"\n{GREEN}{BOLD}Gate: PASS ({passed}/{total} layers){RESET}")
        if report:
            print(f"Report: {report}")
        sys.exit(0)
    else:
        failed = [k for k, v in results.items() if not v]
        print(f"\n{RED}{BOLD}Gate: BLOCKED ({passed}/{total} layers){RESET}")
        print(f"Failed: {', '.join(failed)}")
        if report:
            print(f"Report: {report}")
        print(f"\n{YELLOW}Fix the finding rather than using --no-verify.{RESET}")
        sys.exit(1)


if __name__ == "__main__":
    main()
