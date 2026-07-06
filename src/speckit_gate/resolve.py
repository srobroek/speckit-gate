"""Feature and project root resolution.

Ported from the speckit-dag-hooks dispatcher, generalised to be config-driven:
the 'speckit.' prefix and the specs/<feat> resolver are not hard-coded here;
callers supply the feature_root from gates.yaml config.
"""

from __future__ import annotations

import glob
import json
import os
import re
import subprocess


def as_str(value: object) -> str:
    """Coerce a value to str; return '' for non-str to prevent crashes on
    adversarial payloads."""
    return value if isinstance(value, str) else ""


def find_spec_root(start: str, feature_root: str = "specs") -> str:
    """Walk up from *start* to find the nearest ancestor containing .specify/
    or the configured feature_root directory.  Returns '' when none found."""
    if not start:
        return ""
    cur = os.path.abspath(start)
    while True:
        if os.path.isdir(os.path.join(cur, ".specify")) or os.path.isdir(
            os.path.join(cur, feature_root)
        ):
            return cur
        parent = os.path.dirname(cur)
        if parent == cur:
            return ""
        cur = parent


def resolve_project_root(payload: dict, feature_root: str = "specs") -> str:
    """Resolve project root from hook payload cwd, then CLAUDE_PROJECT_DIR,
    then os.getcwd().  Walks up to find .specify/ or feature_root."""
    cwd = payload.get("cwd")
    if not isinstance(cwd, str) or not os.path.isdir(cwd):
        cwd = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return find_spec_root(cwd, feature_root) or as_str(cwd)


def resolve_feature(proj_root: str, feature_root: str = "specs") -> str:
    """3-tier feature resolution:
    1. SPECIFY_FEATURE_DIRECTORY env var
    2. .specify/feature.json  feature_directory key
    3. git branch name matching specs/<branch>/
    Returns '' when none resolve.
    """
    env_dir = os.environ.get("SPECIFY_FEATURE_DIRECTORY")
    if env_dir:
        feat = as_str(env_dir)
        prefix = feature_root + "/"
        if feat.startswith(prefix):
            feat = feat[len(prefix):]
        return feat.rstrip("/")

    feature_json = os.path.join(proj_root, ".specify", "feature.json")
    if os.path.isfile(feature_json):
        try:
            with open(feature_json, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            feat = as_str(data.get("feature_directory")) if isinstance(data, dict) else ""
        except (OSError, ValueError):
            feat = ""
        if feat:
            prefix = feature_root + "/"
            if feat.startswith(prefix):
                feat = feat[len(prefix):]
            return feat.rstrip("/")

    # Tier 3: git branch prefix lookup
    git_dir = os.path.join(proj_root, ".git")
    if os.path.isdir(git_dir) or os.path.isfile(git_dir):
        try:
            branch = subprocess.check_output(
                ["git", "-C", proj_root, "rev-parse", "--abbrev-ref", "HEAD"],
                stderr=subprocess.DEVNULL,
            ).decode("utf-8", "replace").strip()
        except (OSError, subprocess.CalledProcessError):
            branch = ""
        if branch and os.path.isdir(os.path.join(proj_root, feature_root, branch)):
            return branch
    return ""


def path_present(path: str) -> bool:
    """True when path exists; supports glob patterns."""
    if any(ch in path for ch in "*?["):
        return bool(glob.glob(path))
    return os.path.exists(path)
