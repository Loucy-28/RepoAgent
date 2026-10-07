import pytest
from unittest.mock import patch, MagicMock
from app.tools.read_file import read_file
from app.tools.edit_file import edit_file
from app.tools.list_files import list_files, get_dependencies
from app.tools.git_diff import git_diff, git_status
from app.tools.run_tests import run_tests
from app.sandbox.manager import ExecutionResult
import tempfile
import os


class TestReadFile:
    def test_read_existing_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("hello\nworld\n")
        result = read_file(str(f))
        assert result["content"] == "hello\nworld\n"
        assert result["total_lines"] == 2

    def test_read_with_line_range(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("line1\nline2\nline3\nline4\nline5\n")
        result = read_file(str(f), start_line=2, end_line=4)
        assert "line2" in result["content"]
        assert "line4" in result["content"]

    def test_read_nonexistent_file(self):
        result = read_file("/nonexistent/path/file.py")
        assert "error" in result


class TestEditFile:
    def test_overwrite_file(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("original")
        result = edit_file(str(f), "modified")
        assert result["success"] is True
        assert f.read_text() == "modified"

    def test_edit_line_range(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("line1\nline2\nline3\n")
        result = edit_file(str(f), "replaced", start_line=2, end_line=2)
        assert result["success"] is True
        content = f.read_text()
        assert "replaced" in content

    def test_edit_nonexistent_file(self):
        result = edit_file("/nonexistent/file.py", "content")
        assert result["success"] is False


class TestListFiles:
    def test_list_python_files(self, tmp_path):
        (tmp_path / "a.py").write_text("pass")
        (tmp_path / "b.py").write_text("pass")
        (tmp_path / "c.txt").write_text("text")
        result = list_files(str(tmp_path), extensions=[".py"])
        assert result["count"] == 2

    def test_list_skips_pycache(self, tmp_path):
        cache_dir = tmp_path / "__pycache__"
        cache_dir.mkdir()
        (cache_dir / "cached.py").write_text("pass")
        (tmp_path / "real.py").write_text("pass")
        result = list_files(str(tmp_path), extensions=[".py"])
        assert result["count"] == 1


class TestGetDependencies:
    def test_python_imports(self, tmp_path):
        f = tmp_path / "test.py"
        f.write_text("import os\nimport sys\nfrom pathlib import Path\n")
        result = get_dependencies(str(f))
        assert "os" in result["imports"]
        assert "sys" in result["imports"]
        assert "pathlib" in result["imports"]

    def test_nonexistent_file(self):
        result = get_dependencies("/nonexistent/file.py")
        assert "error" in result


class TestRunTests:
    @patch("app.tools.run_tests.sandbox_manager")
    def test_run_passing_code(self, mock_sandbox):
        mock_sandbox.execute_with_timeout.return_value = ExecutionResult(
            success=True, stdout="hello\n", stderr="", exit_code=0,
            timed_out=False, duration_ms=50,
        )
        result = run_tests("print('hello')", "python")
        assert result["success"] is True

    @patch("app.tools.run_tests.sandbox_manager")
    def test_run_failing_code(self, mock_sandbox):
        mock_sandbox.execute_with_timeout.return_value = ExecutionResult(
            success=False, stdout="", stderr="ValueError: fail\n", exit_code=1,
            timed_out=False, duration_ms=30,
        )
        result = run_tests("raise ValueError('fail')", "python")
        assert result["success"] is False
