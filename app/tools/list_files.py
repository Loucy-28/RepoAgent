import os
from typing import Optional
from app.observability.logger import get_logger

logger = get_logger(__name__)


def list_files(repo_path: str, extensions: Optional[list[str]] = None) -> dict:
    if extensions is None:
        extensions = [".py", ".java"]

    files = []
    for root, dirs, filenames in os.walk(repo_path):
        dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "node_modules", ".venv", "venv")]
        for f in filenames:
            if any(f.endswith(ext) for ext in extensions):
                full_path = os.path.join(root, f)
                rel_path = os.path.relpath(full_path, repo_path)
                files.append(rel_path)

    return {
        "repo_path": repo_path,
        "files": files,
        "count": len(files),
    }


def get_dependencies(file_path: str) -> dict:
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            code = f.read()
    except Exception as e:
        return {"file_path": file_path, "error": str(e)}

    imports = []
    if file_path.endswith(".py"):
        import ast
        try:
            tree = ast.parse(code)
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imports.append(node.module)
        except SyntaxError:
            pass
    elif file_path.endswith(".java"):
        import re
        for line in code.splitlines():
            match = re.match(r"import\s+([\w.]+)", line.strip())
            if match:
                imports.append(match.group(1))

    return {
        "file_path": file_path,
        "imports": imports,
        "count": len(imports),
    }
