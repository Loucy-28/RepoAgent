import os
from typing import Optional
from app.tools.path_validator import validate_path
from app.observability.logger import get_logger

logger = get_logger(__name__)


def read_file(file_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None, allowed_root: str = "") -> dict:
    validation = validate_path(file_path, allowed_root)
    if not validation["valid"]:
        return {"file_path": file_path, "error": validation["reason"]}

    try:
        with open(file_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        total_lines = len(lines)

        if start_line is not None or end_line is not None:
            start = max(0, (start_line or 1) - 1)
            end = end_line or total_lines
            lines = lines[start:end]
            content = "".join(lines)
        else:
            content = "".join(lines)

        return {
            "file_path": file_path,
            "content": content,
            "start_line": start_line or 1,
            "end_line": end_line or total_lines,
            "total_lines": total_lines,
        }
    except FileNotFoundError:
        return {"file_path": file_path, "error": "File not found"}
    except Exception as e:
        return {"file_path": file_path, "error": str(e)}
