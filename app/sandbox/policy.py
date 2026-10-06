from app.config import settings


DEFAULT_POLICY = {
    "memory_limit": "256m",
    "cpu_limit": 0.5,
    "network_disabled": True,
    "read_only_rootfs": True,
    "timeout": 30,
    "max_file_size_mb": 10,
    "allowed_languages": ["python", "java"],
}


def get_policy() -> dict:
    return {
        "memory_limit": settings.sandbox_memory_limit,
        "cpu_limit": settings.sandbox_cpu_limit,
        "network_disabled": settings.sandbox_network == "none",
        "read_only_rootfs": True,
        "timeout": settings.sandbox_timeout,
    }
