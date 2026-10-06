import os
import ast
import re
from typing import Optional
from dataclasses import dataclass, field

from app.db.enums import CodeLanguage
from app.observability.logger import get_logger

logger = get_logger(__name__)


@dataclass
class CodeSymbol:
    name: str
    kind: str  # "function", "class", "method"
    start_line: int
    end_line: int
    code: str
    parent: str = ""
    decorators: list[str] = field(default_factory=list)
    args: list[str] = field(default_factory=list)


@dataclass
class ParsedFile:
    file_path: str
    language: CodeLanguage
    symbols: list[CodeSymbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    raw_code: str = ""
    total_lines: int = 0


class PythonParser:
    def parse(self, file_path: str, code: str) -> ParsedFile:
        parsed = ParsedFile(
            file_path=file_path,
            language=CodeLanguage.PYTHON,
            raw_code=code,
            total_lines=len(code.splitlines()),
        )
        try:
            tree = ast.parse(code)
        except SyntaxError as e:
            logger.warning("python_parse_error", file=file_path, error=str(e))
            return parsed

        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef) or isinstance(node, ast.AsyncFunctionDef):
                end_line = self._get_end_line(node)
                lines = code.splitlines()
                symbol_code = "\n".join(lines[node.lineno - 1: end_line]) if end_line <= len(lines) else ""
                symbol = CodeSymbol(
                    name=node.name,
                    kind="function",
                    start_line=node.lineno,
                    end_line=end_line,
                    code=symbol_code,
                    args=[arg.arg for arg in node.args.args],
                    decorators=[self._get_decorator_name(d) for d in node.decorator_list],
                )
                parsed.symbols.append(symbol)

            elif isinstance(node, ast.ClassDef):
                end_line = self._get_end_line(node)
                lines = code.splitlines()
                symbol_code = "\n".join(lines[node.lineno - 1: end_line]) if end_line <= len(lines) else ""
                symbol = CodeSymbol(
                    name=node.name,
                    kind="class",
                    start_line=node.lineno,
                    end_line=end_line,
                    code=symbol_code,
                )
                parsed.symbols.append(symbol)

            elif isinstance(node, ast.Import):
                for alias in node.names:
                    parsed.imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    parsed.imports.append(node.module)

        return parsed

    def _get_end_line(self, node) -> int:
        if hasattr(node, "end_lineno") and node.end_lineno:
            return node.end_lineno
        max_line = node.lineno
        for child in ast.walk(node):
            if hasattr(child, "lineno"):
                max_line = max(max_line, child.lineno)
            if hasattr(child, "end_lineno") and child.end_lineno:
                max_line = max(max_line, child.end_lineno)
        return max_line

    def _get_decorator_name(self, node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""


class JavaParser:
    _CLASS_RE = re.compile(r"(?:public|private|protected)?\s*(?:abstract\s+)?(?:class|interface|enum)\s+(\w+)")
    _METHOD_RE = re.compile(r"(?:public|private|protected)\s+(?:static\s+)?(?:[\w<>\[\]]+)\s+(\w+)\s*\(")

    def parse(self, file_path: str, code: str) -> ParsedFile:
        parsed = ParsedFile(
            file_path=file_path,
            language=CodeLanguage.JAVA,
            raw_code=code,
            total_lines=len(code.splitlines()),
        )
        lines = code.splitlines()

        for i, line in enumerate(lines, 1):
            class_match = self._CLASS_RE.search(line)
            if class_match:
                end_line = self._find_block_end(lines, i - 1)
                symbol_code = "\n".join(lines[i - 1: end_line])
                parsed.symbols.append(CodeSymbol(
                    name=class_match.group(1),
                    kind="class",
                    start_line=i,
                    end_line=end_line,
                    code=symbol_code,
                ))

            method_match = self._METHOD_RE.search(line)
            if method_match:
                method_name = method_match.group(1)
                if method_name not in [s.name for s in parsed.symbols]:
                    end_line = self._find_block_end(lines, i - 1)
                    symbol_code = "\n".join(lines[i - 1: end_line])
                    parsed.symbols.append(CodeSymbol(
                        name=method_name,
                        kind="method",
                        start_line=i,
                        end_line=end_line,
                        code=symbol_code,
                    ))

        import_re = re.compile(r"import\s+([\w.]+)")
        for line in lines:
            m = import_re.match(line.strip())
            if m:
                parsed.imports.append(m.group(1))

        return parsed

    def _find_block_end(self, lines: list[str], start: int) -> int:
        brace_count = 0
        found_open = False
        for i in range(start, len(lines)):
            for ch in lines[i]:
                if ch == '{':
                    brace_count += 1
                    found_open = True
                elif ch == '}':
                    brace_count -= 1
            if found_open and brace_count <= 0:
                return i + 1
        return len(lines)


class CodeParser:
    def __init__(self):
        self._parsers = {
            CodeLanguage.PYTHON: PythonParser(),
            CodeLanguage.JAVA: JavaParser(),
        }

    def parse_file(self, file_path: str) -> Optional[ParsedFile]:
        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as f:
                code = f.read()
        except Exception as e:
            logger.error("file_read_error", file=file_path, error=str(e))
            return None

        language = self._detect_language(file_path)
        parser = self._parsers.get(language)
        if not parser:
            return ParsedFile(file_path=file_path, language=language, raw_code=code, total_lines=len(code.splitlines()))

        return parser.parse(file_path, code)

    def _detect_language(self, file_path: str) -> CodeLanguage:
        ext = os.path.splitext(file_path)[1].lower()
        if ext == ".py":
            return CodeLanguage.PYTHON
        elif ext == ".java":
            return CodeLanguage.JAVA
        return CodeLanguage.UNKNOWN


code_parser = CodeParser()
