import os
from app.observability.logger import get_logger

logger = get_logger(__name__)


def validate_path(file_path: str, allowed_root: str = "") -> dict:
    if not file_path:
        return {"valid": False, "reason": "Empty file path"}

    if ".." in file_path.split(os.sep):
        return {"valid": False, "reason": "Path traversal detected (..)"}

    if allowed_root:
        abs_path = os.path.abspath(file_path)
        abs_root = os.path.abspath(allowed_root)
        if not abs_path.startswith(abs_root + os.sep) and abs_path != abs_root:
            return {
                "valid": False,
                "reason": f"Path outside repository boundary: {file_path}",
            }

    dangerous_patterns = [
        "/etc/", "/proc/", "/sys/", "/dev/",
        "/var/", "/usr/", "/bin/", "/sbin/",
        "C:\\Windows", "C:\\Program Files",
    ]
    normalized = file_path.replace("\\", "/").lower()
    for pattern in dangerous_patterns:
        if pattern.lower().replace("\\", "/") in normalized:
            return {"valid": False, "reason": f"Access to system path denied: {file_path}"}

    return {"valid": True, "resolved_path": os.path.abspath(file_path)}


def is_safe_path(file_path: str, allowed_root: str = "") -> bool:
    result = validate_path(file_path, allowed_root)
    if not result["valid"]:
        logger.warning("path_validation_failed", path=file_path, reason=result["reason"])
    return result["valid"]
