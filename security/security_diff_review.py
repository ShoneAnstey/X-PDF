"""
Layer 6 — Gemini AI Security Diff Review
=========================================
Extracts the current staged git diff and sends it to Gemini for a structured
security review against a 10-point checklist.

Exit codes:
  0 — No Critical/High findings (commit proceeds)
  1 — Critical or High finding detected (commit blocked)
  2 — Network error, timeout, or missing API key (caller issues WARN, does not block)

Usage: python utils/security_diff_review.py
"""

import json
import os
import subprocess
import sys

TIMEOUT_S = 15
MIN_DIFF_LINES = 20  # caller already checks this, but guard here too

SECURITY_PROMPT = """You are a security code reviewer. Analyze the following git diff for security vulnerabilities.

CRITICAL — understand git diff syntax before reviewing:
- Lines starting with "+" are NEWLY ADDED code. Review these for introduced vulnerabilities.
- Lines starting with "-" are REMOVED/OLD code being deleted. Do NOT flag these as vulnerabilities — they are being removed.
- Lines with no prefix (+/-) are unchanged context lines shown for readability only.
- A diff that REMOVES insecure code (e.g. removes inline onclick handlers, removes unsafe-inline CSP, removes missing auth checks) is a SECURITY FIX. Do NOT flag it as a vulnerability.
- A diff that ADDS security controls (e.g. adds @admin_required decorator, adds CSP nonce, adds rate limiting, adds input validation) is a SECURITY IMPROVEMENT. Do NOT flag it as a vulnerability.
- Only flag code that is INTRODUCED by this diff (i.e. on "+" lines) and that represents a net new security risk.

Return ONLY valid JSON (no markdown, no explanation outside the JSON) with this exact structure:
{
  "findings": [
    {
      "severity": "Critical|High|Medium|Low|Info",
      "description": "clear description of the issue",
      "file": "filename or empty string",
      "line": "line number or range, or empty string"
    }
  ]
}

If there are no findings, return: {"findings": []}

Review checklist (apply only to NEWLY ADDED "+" lines):
1. Authorization logic gaps — new endpoints added without auth checks
2. Privilege escalation — new code granting lower-privilege users higher-privilege access
3. Missing input validation — new routes or handlers that accept user input without sanitization
4. Authentication bypass — new code that allows skipping authentication
5. SQL injection — new code using raw string formatting or concatenation with user input in SQL
6. Insecure direct object references — new code accessing records by ID without ownership check
7. Business logic vulnerabilities — new logic that can be abused for unintended outcomes
8. Secret or credential exposure — keys, tokens, passwords hardcoded in new code
9. Dangerous function calls — new uses of eval(), exec(), subprocess with shell=True, pickle.loads()
10. Missing CSRF protection or rate-limiting on new state-changing routes

Only flag Critical or High for confirmed net-new vulnerabilities introduced by this diff. Use Medium/Low for potential issues. Do not flag pre-existing patterns in unchanged context lines.

IMPORTANT — Deployment context (do NOT flag these as vulnerabilities):
- This is a SINGLE-USER, LOCAL-ONLY application. There is no network-facing API and no multi-tenant access. The CLI runs on the operator's machine — filesystem access IS the authorization boundary.
- MCP (Model Context Protocol) tools run on localhost over stdio — they are invoked by a local AI agent, not over a network. Process-level isolation is the access control.
- Do NOT flag CLI commands or MCP tools for "missing authorization" or "missing authentication". These are local operator tools, not web endpoints.
- Do NOT flag parameterized SQL (SQLAlchemy text() with :named_params, or psycopg %s placeholders) as SQL injection. Only flag raw string concatenation/formatting of user input into SQL.
- Do NOT flag psycopg.connect() with keyword arguments (host=, password=) as credential exposure — these read from environment variables, which is standard practice.
"""


def get_staged_diff() -> str:
    result = subprocess.run(
        ["git", "diff", "--staged"],
        capture_output=True,
        text=True,
        timeout=10,
    )
    return result.stdout


def main() -> None:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print("WARN: GEMINI_API_KEY not set — skipping Layer 6", file=sys.stderr)
        sys.exit(2)

    try:
        diff = get_staged_diff()
    except Exception as e:
        print(f"WARN: Could not get staged diff ({e}) — skipping Layer 6", file=sys.stderr)
        sys.exit(2)

    if not diff.strip() or len(diff.splitlines()) < MIN_DIFF_LINES:
        print(f"SKIP: diff too small ({len(diff.splitlines())} lines)")
        sys.exit(0)

    try:
        from google import genai  # type: ignore[import]
    except ImportError:
        print("WARN: google-genai not installed — skipping Layer 6", file=sys.stderr)
        sys.exit(2)

    try:
        client = genai.Client(api_key=api_key)
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=f"{SECURITY_PROMPT}\n\nDiff to review:\n```\n{diff}\n```",
        )
    except Exception as e:
        print(f"WARN: Gemini request failed ({e}) — skipping Layer 6", file=sys.stderr)
        sys.exit(2)

    if not response.text:
        print("WARN: Gemini returned empty response — skipping Layer 6", file=sys.stderr)
        sys.exit(2)

    raw = response.text.strip()

    # Strip markdown code fences if Gemini wraps the JSON
    if raw.startswith("```"):
        lines = raw.splitlines()
        raw = "\n".join(lines[1:]).rstrip("`").strip()

    try:
        result = json.loads(raw)
    except json.JSONDecodeError as e:
        print(f"WARN: Gemini returned non-JSON response ({e}) — skipping Layer 6", file=sys.stderr)
        sys.exit(2)

    findings = result.get("findings", [])

    if not findings:
        print("Layer 6: No security findings.")
        sys.exit(0)

    blocked: list[dict] = []
    for f in findings:
        sev = f.get("severity", "?")
        desc = f.get("description", "")
        file_ = f.get("file", "")
        line = f.get("line", "")
        loc = f"{file_}:{line}" if file_ else "(no location)"
        print(f"  [{sev}] {loc} — {desc}")
        if sev in ("Critical", "High"):
            blocked.append(f)

    if blocked:
        print(f"\nLayer 6: {len(blocked)} Critical/High finding(s) — commit blocked.")
        sys.exit(1)

    print(f"Layer 6: {len(findings)} finding(s), none Critical/High — passing.")
    sys.exit(0)


if __name__ == "__main__":
    main()
