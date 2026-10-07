import os
from typing import Optional
from app.tools.path_validator import validate_path
from app.observability.logger import get_logger

logger = get_logger(__name__)


def edit_file(file_path: str, new_content: str, start_line: Optional[int] = None, end_line: Optional[int] = None, allowed_root: str = "") -> dict:
    validation = validate_path(file_path, allowed_root)
    if not validation["valid"]:
        return {"file_path": file_path, "success": False, "error": validation["reason"]}

    try:
        if start_line is not None and end_line is not None:
            with open(file_path, "r", encoding="utf-8") as f:
                lines = f.readlines()
            start = max(0, start_line - 1)
            end = min(len(lines), end_line)
            new_lines = lines[:start] + [new_content + "\n"] + lines[end:]
            with open(file_path, "w", encoding="utf-8") as f:
                f.writelines(new_lines)
        else:
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(new_content)

        return {
            "file_path": file_path,
            "success": True,
            "message": "File edited successfully",
        }
    except FileNotFoundError:
        return {"file_path": file_path, "success": False, "error": "File not found"}
    except Exception as e:
        return {"file_path": file_path, "success": False, "error": str(e)}
