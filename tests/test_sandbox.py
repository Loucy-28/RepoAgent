import pytest
from app.sandbox.manager import DockerSandboxManager, SandboxPolicy, ExecutionResult


class TestSandboxPolicy:
    def test_default_policy(self):
        policy = SandboxPolicy()
        assert policy.memory_limit == "256m"
        assert policy.cpu_limit == 0.5
        assert policy.network_disabled is True
        assert policy.read_only_rootfs is True
        assert policy.timeout == 30

    def test_custom_policy(self):
        policy = SandboxPolicy(
            memory_limit="512m",
            cpu_limit=1.0,
            network_disabled=False,
            timeout=60,
        )
        assert policy.memory_limit == "512m"
        assert policy.cpu_limit == 1.0
        assert policy.network_disabled is False
        assert policy.timeout == 60


class TestDockerSandboxManager:
    def setup_method(self):
        self.manager = DockerSandboxManager(SandboxPolicy(timeout=5))

    def test_execute_simple_python(self):
        result = self.manager._fallback_execute("print('hello world')", "python")
        assert result.success is True
        assert "hello world" in result.stdout
        assert result.exit_code == 0

    def test_execute_syntax_error(self):
        result = self.manager._fallback_execute("def broken(\n", "python")
        assert result.success is False
        assert result.exit_code != 0

    def test_execute_runtime_error(self):
        result = self.manager._fallback_execute("raise ValueError('test error')", "python")
        assert result.success is False
        assert "test error" in result.stderr

    def test_execute_timeout(self):
        result = self.manager._fallback_execute(
            "import time; time.sleep(100)",
            "python",
        )
        assert result.success is False
        assert result.timed_out is True

    def test_execute_arithmetic(self):
        result = self.manager._fallback_execute("print(2 + 3)", "python")
        assert result.success is True
        assert "5" in result.stdout

    def test_execute_fibonacci(self):
        code = """
def fib(n):
    if n <= 1:
        return n
    return fib(n-1) + fib(n-2)
print(fib(10))
"""
        result = self.manager._fallback_execute(code, "python")
        assert result.success is True
        assert "55" in result.stdout

    def test_duration_tracked(self):
        result = self.manager._fallback_execute("print('fast')", "python")
        assert result.duration_ms >= 0
