#!/usr/bin/env python3
"""SessionStart hook: inject a compact Databricks context banner.

Local-only and fail-open by design. It never makes a network call (so it can't
hang, hit an MCP-style timeout, or trigger an auth prompt at session start) and
any error exits 0 with no output. It surfaces, when available:

  - databricks CLI presence + version
  - configured profile names, parsed straight from the config file (no network)
  - the `[__settings__].default_profile` the CLI resolves when --profile is omitted
  - env-based / in-platform auth (DATABRICKS_HOST, DATABRICKS_CONFIG_PROFILE)

Token values are never printed, only their presence.

Contract (Claude Code SessionStart hook):
  stdin : JSON (drained, content unused)
  stdout: JSON -> hookSpecificOutput.additionalContext, a string injected into
          the session context.
"""
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

VERSION_RE = re.compile(r"(\d+)\.(\d+)\.(\d+)")
SECTION_RE = re.compile(r"^\[([^\]]+)\]", re.MULTILINE)
# default_profile inside the [__settings__] section ([^\[]*? keeps the search
# from crossing into the next section header).
SETTINGS_DEFAULT_RE = re.compile(
    r"^\[__settings__\][^\[]*?^[ \t]*default_profile[ \t]*=[ \t]*(\S+)",
    re.MULTILINE,
)
MAX_PROFILES = 12


def cli_version(databricks):
    """(major, minor, patch) from `databricks --version`, or None. 3s timeout."""
    try:
        out = subprocess.run(
            [databricks, "--version"],
            capture_output=True, text=True, timeout=3,
        )
    except Exception:
        return None
    m = VERSION_RE.search((out.stdout or "") + (out.stderr or ""))
    return tuple(int(x) for x in m.groups()) if m else None


def config_profiles():
    """(config_path, [profile names], default_profile) read locally from the config file.

    Parsed directly rather than via `databricks auth profiles` on purpose: this
    runs at SessionStart, which must stay offline and fast (no network, no
    auth-validation round-trips). Skips CLI-internal sections like
    `[__settings__]`, which are not auth profiles, but does surface
    `[__settings__].default_profile` since the CLI resolves it when --profile
    is omitted.
    """
    cfg = os.environ.get("DATABRICKS_CONFIG_FILE") or str(Path.home() / ".databrickscfg")
    try:
        p = Path(cfg)
        # Only read a regular file under a sane size cap, so a FIFO/device or a
        # huge file pointed at by DATABRICKS_CONFIG_FILE can never hang or do
        # unbounded work at session start.
        if not p.is_file() or p.stat().st_size > 1_000_000:
            return cfg, [], None
        text = p.read_text(errors="replace")
    except Exception:
        return cfg, [], None
    names = [
        n for n in SECTION_RE.findall(text)
        if not (n.startswith("__") and n.endswith("__"))
    ]
    m = SETTINGS_DEFAULT_RE.search(text)
    return cfg, names, (m.group(1) if m else None)


def _sanitize(value, limit=64):
    """Make a config-derived string safe to inject as one context list item.

    Strips control chars / newlines (so a crafted profile name or env value
    cannot inject extra bullets or instructions) and caps the length.
    """
    s = re.sub(r"[\x00-\x1f\x7f]", " ", str(value))
    s = re.sub(r"\s+", " ", s).strip()
    return s[: limit - 1].rstrip() + "…" if len(s) > limit else s


def build_context():
    """Return the context banner string, or '' to inject nothing."""
    databricks = shutil.which("databricks")
    if not databricks:
        return (
            "Databricks CLI (`databricks`) is not on PATH. The Databricks skills "
            "and `/databricks:*` commands need it. Run `/databricks:setup` or see "
            "the databricks-core skill to install it."
        )

    lines = []
    ver = cli_version(databricks)
    if ver:
        lines.append(f"CLI v{'.'.join(map(str, ver))}.")
    else:
        lines.append("CLI present (version unknown).")

    cfg, profiles, default_profile = config_profiles()
    if profiles:
        shown = [_sanitize(n) for n in profiles[:MAX_PROFILES]]
        more = f" (+{len(profiles) - len(shown)} more)" if len(profiles) > len(shown) else ""
        lines.append(f"Profiles in {_sanitize(Path(cfg).name)}: {', '.join(shown)}{more}.")
        if default_profile:
            lines.append(
                f"Default profile (from [__settings__]): `{_sanitize(default_profile)}`; "
                "the CLI uses it when `--profile` is omitted."
            )
        lines.append("Never auto-select a profile. Pass `--profile <name>` and let the user choose.")
    else:
        # Basename only, matching the branch above: the full path (possibly a
        # custom DATABRICKS_CONFIG_FILE) stays out of the injected context.
        lines.append(f"No profiles found in {_sanitize(Path(cfg).name)}.")

    env_profile = os.environ.get("DATABRICKS_CONFIG_PROFILE")
    if env_profile:
        lines.append(f"DATABRICKS_CONFIG_PROFILE is set to `{_sanitize(env_profile)}`.")
    if os.environ.get("DATABRICKS_HOST"):
        authed = " with DATABRICKS_TOKEN set" if os.environ.get("DATABRICKS_TOKEN") else ""
        lines.append(f"DATABRICKS_HOST is set{authed} (env / in-platform auth).")

    lines.append(
        "Route Databricks-related work through the skills: load `databricks-core` "
        "(the parent) plus the matching product skill."
    )
    return "Databricks context:\n- " + "\n- ".join(lines)


def main():
    # One outer try so the fail-open guarantee covers the entire main block,
    # including JSON serialization; the final print gets its own guard (a
    # closed stdout must never break session startup either).
    output = None
    try:
        try:
            json.load(sys.stdin)  # drain stdin; content unused
        except Exception:
            pass
        ctx = build_context()
        if ctx:
            output = json.dumps({
                "hookSpecificOutput": {
                    "hookEventName": "SessionStart",
                    "additionalContext": ctx,
                }
            })
    except Exception:
        output = None
    try:
        if output:
            print(output)
    except Exception:
        pass


if __name__ == "__main__":
    main()
    sys.exit(0)
