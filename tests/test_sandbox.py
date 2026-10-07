import pytest
from unittest.mock import MagicMock, patch

from app.sandbox.manager import DockerSandboxManager, SandboxPolicy, ExecutionResult, SandboxUnavailableError


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

    def test_docker_unavailable_raises_error(self):
        self.manager._client = None
        with pytest.raises(SandboxUnavailableError, match="Docker is not available"):
            self.manager.execute("print('hello')", "python")

    def test_docker_unavailable_execute_with_timeout(self):
        self.manager._client = None
        with pytest.raises(SandboxUnavailableError):
            self.manager.execute_with_timeout("print('hello')", "python")

    def test_execute_success_with_mock_docker(self):
        mock_container = MagicMock()
        mock_container.id = "test-container-123"
        mock_container.start = MagicMock()
        mock_container.wait = MagicMock(return_value={"StatusCode": 0})
        mock_container.logs = MagicMock(return_value=b"hello world\n")
        mock_container.remove = MagicMock()

        mock_client = MagicMock()
        mock_client.containers.create.return_value = mock_container
        self.manager._client = mock_client

        result = self.manager.execute("print('hello world')", "python")

        assert result.success is True
        assert "hello world" in result.stdout
        assert result.exit_code == 0
        mock_container.start.assert_called_once()
        mock_container.wait.assert_called_once()
        mock_container.remove.assert_called_once()

    def test_execute_runtime_error_with_mock(self):
        mock_container = MagicMock()
        mock_container.id = "test-container-456"
        mock_container.start = MagicMock()
        mock_container.wait = MagicMock(return_value={"StatusCode": 1})
        mock_container.logs = MagicMock(return_value=b"")
        mock_container.remove = MagicMock()

        mock_client = MagicMock()
        mock_client.containers.create.return_value = mock_container
        self.manager._client = mock_client

        result = self.manager.execute("raise ValueError('test')", "python")

        assert result.success is False
        assert result.exit_code == 1

    def test_execute_timeout_with_mock(self):
        import requests

        mock_container = MagicMock()
        mock_container.id = "test-container-789"
        mock_container.start = MagicMock()
        mock_container.wait = MagicMock(side_effect=requests.exceptions.ReadTimeout("timeout"))
        mock_container.kill = MagicMock()
        mock_container.remove = MagicMock()

        mock_client = MagicMock()
        mock_client.containers.create.return_value = mock_container
        self.manager._client = mock_client

        result = self.manager.execute("import time; time.sleep(100)", "python")

        assert result.success is False
        assert result.timed_out is True
        mock_container.kill.assert_called_once()

    def test_volume_mount_passed(self):
        mock_container = MagicMock()
        mock_container.id = "test-vol"
        mock_container.start = MagicMock()
        mock_container.wait = MagicMock(return_value={"StatusCode": 0})
        mock_container.logs = MagicMock(return_value=b"")
        mock_container.remove = MagicMock()

        mock_client = MagicMock()
        mock_client.containers.create.return_value = mock_container
        self.manager._client = mock_client

        import os
        repo_path = os.path.abspath("/tmp/myrepo")
        self.manager.execute("print('ok')", "python", repo_path=repo_path)

        call_kwargs = mock_client.containers.create.call_args
        volumes = call_kwargs.kwargs.get("volumes") or call_kwargs[1].get("volumes")
        assert volumes is not None
        assert repo_path in volumes
        assert volumes[repo_path]["bind"] == "/workspace"

    def test_duration_tracked(self):
        mock_container = MagicMock()
        mock_container.id = "test-dur"
        mock_container.start = MagicMock()
        mock_container.wait = MagicMock(return_value={"StatusCode": 0})
        mock_container.logs = MagicMock(return_value=b"fast\n")
        mock_container.remove = MagicMock()

        mock_client = MagicMock()
        mock_client.containers.create.return_value = mock_container
        self.manager._client = mock_client

        result = self.manager.execute("print('fast')", "python")
        assert result.duration_ms >= 0
