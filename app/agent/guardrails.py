import re
from app.observability.logger import get_logger

logger = get_logger(__name__)

INJECTION_PATTERNS = [
    re.compile(r"ignore\s+(all\s+)?(previous|above|prior)\s+(instructions?|prompts?|rules?)", re.IGNORECASE),
    re.compile(r"you\s+are\s+now\s+(a|an)\s+", re.IGNORECASE),
    re.compile(r"new\s+instructions?\s*:", re.IGNORECASE),
    re.compile(r"system\s*:\s*", re.IGNORECASE),
    re.compile(r"\[INST\]|\[/INST\]|<\|im_start\|>|<\|im_end\|>", re.IGNORECASE),
    re.compile(r"forget\s+(everything|all|your)\s+(you\s+)?(know|rules?|instructions?)", re.IGNORECASE),
    re.compile(r"do\s+not\s+follow\s+(your|the|any)\s+(rules?|instructions?|guidelines?)", re.IGNORECASE),
    re.compile(r"act\s+as\s+(if\s+)?(you\s+are|a|an)\s+", re.IGNORECASE),
    re.compile(r"override\s+(previous|all|system)\s+", re.IGNORECASE),
    re.compile(r"disregard\s+(previous|all|your)\s+", re.IGNORECASE),
]

MAX_INPUT_LENGTH = 50000
MAX_CODE_LENGTH = 100000


def sanitize_input(text: str, max_length: int = MAX_INPUT_LENGTH) -> str:
    if not text:
        return text

    if len(text) > max_length:
        logger.warning("input_truncated", original_length=len(text), max_length=max_length)
        text = text[:max_length]

    return text


def detect_injection(text: str) -> list[str]:
    if not text:
        return []

    findings = []
    for pattern in INJECTION_PATTERNS:
        matches = pattern.findall(text)
        if matches:
            findings.append(f"Pattern matched: {pattern.pattern}")

    if findings:
        logger.warning("prompt_injection_detected", findings_count=len(findings), text_preview=text[:200])

    return findings


def is_safe_input(text: str) -> bool:
    findings = detect_injection(text)
    return len(findings) == 0


def sanitize_code_for_prompt(code: str, max_length: int = MAX_CODE_LENGTH) -> str:
    if not code:
        return code

    if len(code) > max_length:
        code = code[:max_length] + "\n... (truncated)"

    code = re.sub(r'#\s*ignore\s+previous.*', '[comment removed]', code, flags=re.IGNORECASE)
    code = re.sub(r'//\s*ignore\s+previous.*', '[comment removed]', code, flags=re.IGNORECASE)
    code = re.sub(r'<!--\s*ignore\s+previous.*?-->', '[comment removed]', code, flags=re.IGNORECASE | re.DOTALL)

    return code


def validate_tool_input(tool_name: str, input_data: dict) -> dict:
    for key, value in input_data.items():
        if isinstance(value, str) and len(value) > MAX_INPUT_LENGTH:
            logger.warning("tool_input_truncated", tool=tool_name, key=key, original_length=len(value))
            input_data[key] = value[:MAX_INPUT_LENGTH]

    return input_data
