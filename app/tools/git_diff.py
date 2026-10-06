import os
import subprocess
from typing import Optional
from app.observability.logger import get_logger

logger = get_logger(__name__)


def git_diff(repo_path: str, staged: bool = False) -> dict:
    try:
        cmd = ["git", "diff"]
        if staged:
            cmd.append("--cached")

        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )

        return {
            "repo_path": repo_path,
            "diff": result.stdout,
            "has_changes": bool(result.stdout.strip()),
        }
    except subprocess.TimeoutExpired:
        return {"repo_path": repo_path, "diff": "", "error": "Git diff timed out"}
    except Exception as e:
        return {"repo_path": repo_path, "diff": "", "error": str(e)}


def git_status(repo_path: str) -> dict:
    try:
        result = subprocess.run(
            ["git", "status", "--short"],
            cwd=repo_path,
            capture_output=True,
            text=True,
            timeout=10,
        )
        return {
            "repo_path": repo_path,
            "status": result.stdout,
            "has_changes": bool(result.stdout.strip()),
        }
    except Exception as e:
        return {"repo_path": repo_path, "status": "", "error": str(e)}
