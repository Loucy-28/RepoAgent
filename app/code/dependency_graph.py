import os
import ast
import re
from typing import Optional
from dataclasses import dataclass, field
from collections import defaultdict

from app.observability.logger import get_logger

logger = get_logger(__name__)


@dataclass
class DependencyNode:
    file_path: str
    module_name: str
    symbols: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    imported_by: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    called_by: list[str] = field(default_factory=list)


@dataclass
class DependencyEdge:
    source: str
    target: str
    edge_type: str  # "imports", "calls", "extends"
    symbol: str = ""


class DependencyGraph:
    def __init__(self):
        self._nodes: dict[str, DependencyNode] = {}
        self._edges: list[DependencyEdge] = []
        self._repo_path: str = ""

    def build(self, repo_path: str) -> int:
        self._nodes.clear()
        self._edges.clear()
        self._repo_path = os.path.abspath(repo_path)

        files = self._scan_files(repo_path)
        for file_path in files:
            self._parse_file(repo_path, file_path)

        self._resolve_references()

        logger.info("dependency_graph_built", nodes=len(self._nodes), edges=len(self._edges))
        return len(self._nodes)

    def _resolve_path(self, file_path: str) -> Optional[str]:
        if file_path in self._nodes:
            return file_path

        if self._repo_path:
            abs_path = os.path.abspath(file_path)
            if abs_path.startswith(self._repo_path):
                rel = os.path.relpath(abs_path, self._repo_path)
                if rel in self._nodes:
                    return rel

            for stored_path in self._nodes:
                stored_abs = os.path.join(self._repo_path, stored_path)
                if os.path.abspath(stored_abs) == abs_path:
                    return stored_path

        return None

    def get_node(self, file_path: str) -> Optional[DependencyNode]:
        resolved = self._resolve_path(file_path)
        if resolved:
            return self._nodes.get(resolved)
        return None

    def get_dependencies(self, file_path: str) -> dict:
        resolved = self._resolve_path(file_path)
        if not resolved:
            return {"file_path": file_path, "error": "not in graph"}
        node = self._nodes[resolved]

        return {
            "file_path": file_path,
            "module": node.module_name,
            "imports": node.imports,
            "imported_by": node.imported_by,
            "calls": node.calls,
            "called_by": node.called_by,
            "symbols": node.symbols,
        }

    def get_impact_analysis(self, file_path: str) -> dict:
        resolved = self._resolve_path(file_path)
        if not resolved:
            return {"file_path": file_path, "impact": []}
        node = self._nodes.get(resolved)
        if not node:
            return {"file_path": file_path, "impact": []}

        directly_affected = set(node.imported_by)
        transitively_affected = set()

        queue = list(node.imported_by)
        visited = {resolved}
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            transitively_affected.add(current)
            current_node = self._nodes.get(current)
            if current_node:
                queue.extend(current_node.imported_by)

        return {
            "file_path": file_path,
            "direct_dependencies": list(directly_affected),
            "transitive_dependencies": list(transitively_affected),
            "total_impact": len(transitively_affected),
        }

    def get_call_chain(self, symbol_name: str) -> list[str]:
        callers = []
        for file_path, node in self._nodes.items():
            if symbol_name in node.calls:
                callers.append(file_path)
        return callers

    def get_call_chain_transitive(self, symbol_name: str) -> list[dict]:
        chains = []
        for file_path, node in self._nodes.items():
            if symbol_name in node.calls:
                chain = [{"file": file_path, "calls": symbol_name}]
                visited = {file_path}
                queue = [file_path]
                while queue:
                    current = queue.pop(0)
                    current_node = self._nodes.get(current)
                    if not current_node:
                        continue
                    for caller_file in current_node.called_by:
                        if caller_file not in visited:
                            visited.add(caller_file)
                            caller_node = self._nodes.get(caller_file)
                            if caller_node:
                                calling_syms = [
                                    c for c in caller_node.calls
                                    if c in current_node.symbols
                                ]
                                chain.append({
                                    "file": caller_file,
                                    "calls": ", ".join(calling_syms) if calling_syms else symbol_name,
                                })
                                queue.append(caller_file)
                chains.append({"target": symbol_name, "chain": chain})
        return chains

    def get_all_edges(self) -> list[dict]:
        return [
            {"source": e.source, "target": e.target, "type": e.edge_type, "symbol": e.symbol}
            for e in self._edges
        ]

    def to_dict(self) -> dict:
        return {
            "nodes": {
                fp: {
                    "module": n.module_name,
                    "symbols": n.symbols,
                    "imports": n.imports,
                    "imported_by": n.imported_by,
                    "calls": n.calls,
                    "called_by": n.called_by,
                }
                for fp, n in self._nodes.items()
            },
            "edges": [
                {"source": e.source, "target": e.target, "type": e.edge_type, "symbol": e.symbol}
                for e in self._edges
            ],
        }

    def _scan_files(self, repo_path: str) -> list[str]:
        files = []
        for root, dirs, filenames in os.walk(repo_path):
            dirs[:] = [d for d in dirs if d not in ("__pycache__", ".git", "node_modules", ".venv", "venv")]
            for f in filenames:
                if f.endswith((".py", ".java")):
                    full_path = os.path.join(root, f)
                    rel_path = os.path.relpath(full_path, repo_path)
                    files.append(rel_path)
        return files

    def _parse_file(self, repo_path: str, file_path: str):
        full_path = os.path.join(repo_path, file_path)
        try:
            with open(full_path, "r", encoding="utf-8", errors="replace") as f:
                code = f.read()
        except Exception as e:
            logger.warning("dep_parse_error", file=file_path, error=str(e))
            return

        module_name = self._file_to_module(file_path)
        node = DependencyNode(file_path=file_path, module_name=module_name)

        if file_path.endswith(".py"):
            self._parse_python(code, node)
        elif file_path.endswith(".java"):
            self._parse_java(code, node)

        self._nodes[file_path] = node

    def _parse_python(self, code: str, node: DependencyNode):
        try:
            tree = ast.parse(code)
        except SyntaxError:
            return

        for ast_node in ast.walk(tree):
            if isinstance(ast_node, ast.Import):
                for alias in ast_node.names:
                    node.imports.append(alias.name)
                    self._edges.append(DependencyEdge(
                        source=node.file_path, target=alias.name,
                        edge_type="imports", symbol=alias.name,
                    ))
            elif isinstance(ast_node, ast.ImportFrom):
                if ast_node.module:
                    node.imports.append(ast_node.module)
                    self._edges.append(DependencyEdge(
                        source=node.file_path, target=ast_node.module,
                        edge_type="imports", symbol=ast_node.module,
                    ))
            elif isinstance(ast_node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                node.symbols.append(ast_node.name)
                for child in ast.walk(ast_node):
                    if isinstance(child, ast.Call):
                        call_name = self._extract_call_name(child)
                        if call_name:
                            node.calls.append(call_name)
            elif isinstance(ast_node, ast.ClassDef):
                node.symbols.append(ast_node.name)
                for base in ast_node.bases:
                    base_name = self._extract_name(base)
                    if base_name:
                        self._edges.append(DependencyEdge(
                            source=node.file_path, target=base_name,
                            edge_type="extends", symbol=base_name,
                        ))

    def _parse_java(self, code: str, node: DependencyNode):
        import_re = re.compile(r"import\s+([\w.]+)")
        for line in code.splitlines():
            m = import_re.match(line.strip())
            if m:
                node.imports.append(m.group(1))
                self._edges.append(DependencyEdge(
                    source=node.file_path, target=m.group(1),
                    edge_type="imports", symbol=m.group(1),
                ))

        class_re = re.compile(r"(?:public|private|protected)?\s*(?:abstract\s+)?(?:class|interface)\s+(\w+)")
        method_re = re.compile(r"(?:public|private|protected)\s+(?:static\s+)?(?:[\w<>\[\]]+)\s+(\w+)\s*\(")
        for line in code.splitlines():
            cm = class_re.search(line)
            if cm:
                node.symbols.append(cm.group(1))
            mm = method_re.search(line)
            if mm and mm.group(1) not in node.symbols:
                node.symbols.append(mm.group(1))

    def _resolve_references(self):
        module_to_file = {}
        symbol_to_files = {}
        for file_path, node in self._nodes.items():
            module_to_file[node.module_name] = file_path
            parts = file_path.replace(os.sep, "/").replace("/", ".")
            if parts.endswith(".py"):
                parts = parts[:-3]
            module_to_file[parts] = file_path

            for sym in node.symbols:
                symbol_to_files.setdefault(sym, []).append(file_path)

        for file_path, node in self._nodes.items():
            for imp in node.imports:
                target_file = module_to_file.get(imp)
                if target_file and target_file in self._nodes:
                    target_node = self._nodes[target_file]
                    if file_path not in target_node.imported_by:
                        target_node.imported_by.append(file_path)

            for call_name in node.calls:
                target_files = symbol_to_files.get(call_name, [])
                for tf in target_files:
                    if tf != file_path and tf in self._nodes:
                        target_node = self._nodes[tf]
                        if file_path not in target_node.called_by:
                            target_node.called_by.append(file_path)

    def _file_to_module(self, file_path: str) -> str:
        parts = file_path.replace(os.sep, "/")
        if parts.endswith(".py"):
            parts = parts[:-3]
        return parts.replace("/", ".")

    def _extract_call_name(self, call_node: ast.Call) -> str:
        if isinstance(call_node.func, ast.Name):
            return call_node.func.id
        if isinstance(call_node.func, ast.Attribute):
            return call_node.func.attr
        return ""

    def _extract_name(self, node) -> str:
        if isinstance(node, ast.Name):
            return node.id
        if isinstance(node, ast.Attribute):
            return node.attr
        return ""


dependency_graph = DependencyGraph()
