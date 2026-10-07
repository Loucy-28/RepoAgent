import uuid
import time
from typing import Optional
from dataclasses import dataclass

import docker
from docker.errors import ContainerError, BuildError, APIError, NotFound

from app.config import settings
from app.observability.logger import get_logger

logger = get_logger(__name__)


class SandboxUnavailableError(Exception):
    pass


@dataclass
class ExecutionResult:
    success: bool
    stdout: str
    stderr: str
    exit_code: int
    timed_out: bool = False
    duration_ms: int = 0


class SandboxPolicy:
    def __init__(
        self,
        memory_limit: str = "256m",
        cpu_limit: float = 0.5,
        network_disabled: bool = True,
        read_only_rootfs: bool = True,
        timeout: int = 30,
    ):
        self.memory_limit = memory_limit
        self.cpu_limit = cpu_limit
        self.network_disabled = network_disabled
        self.read_only_rootfs = read_only_rootfs
        self.timeout = timeout


class DockerSandboxManager:
    def __init__(self, policy: Optional[SandboxPolicy] = None):
        self.policy = policy or SandboxPolicy(
            memory_limit=settings.sandbox_memory_limit,
            cpu_limit=settings.sandbox_cpu_limit,
            network_disabled=(settings.sandbox_network == "none"),
            read_only_rootfs=True,
            timeout=settings.sandbox_timeout,
        )
        try:
            self._client = docker.from_env()
            self._client.ping()
        except Exception as e:
            logger.warning("docker_not_available", error=str(e))
            self._client = None

    def _ensure_image(self):
        if self._client is None:
            return
        try:
            self._client.images.get(settings.sandbox_image)
        except docker.errors.ImageNotFound:
            logger.info("building_sandbox_image")
            try:
                self._client.images.build(
                    path="sandbox",
                    tag=settings.sandbox_image,
                    rm=True,
                )
            except BuildError as e:
                logger.error("sandbox_build_failed", error=str(e))
                raise

    def execute(
        self,
        code: str,
        language: str = "python",
        repo_path: str = "",
    ) -> ExecutionResult:
        if self._client is None:
            raise SandboxUnavailableError(
                "Docker is not available. Code execution is disabled for security. "
                "Install and start Docker to run sandboxed code."
            )

        self._ensure_image()
        container_name = f"sandbox-{uuid.uuid4().hex[:8]}"

        cmd = self._build_command(code, language)
        volumes = {}
        if repo_path:
            import os
            abs_repo = os.path.abspath(repo_path)
            volumes[abs_repo] = {"bind": "/workspace", "mode": "rw"}

        start_time = time.time()
        container = None

        try:
            container = self._client.containers.create(
                settings.sandbox_image,
                command=cmd,
                name=container_name,
                mem_limit=self.policy.memory_limit,
                cpu_period=100000,
                cpu_quota=int(100000 * self.policy.cpu_limit),
                network_disabled=self.policy.network_disabled,
                read_only=self.policy.read_only_rootfs,
                tmpfs={"/tmp": "size=64m"},
                working_dir="/workspace",
                volumes=volumes or None,
                stdout=True,
                stderr=True,
                detach=True,
            )

            container.start()

            try:
                wait_result = container.wait(timeout=self.policy.timeout)
            except Exception:
                duration_ms = int((time.time() - start_time) * 1000)
                try:
                    container.kill()
                except Exception:
                    pass
                try:
                    container.remove(force=True)
                except Exception:
                    pass
                return ExecutionResult(
                    success=False,
                    stdout="",
                    stderr=f"Execution timed out after {self.policy.timeout}s",
                    exit_code=-1,
                    timed_out=True,
                    duration_ms=duration_ms,
                )

            duration_ms = int((time.time() - start_time) * 1000)
            exit_code = wait_result.get("StatusCode", -1) if isinstance(wait_result, dict) else -1

            stdout = container.logs(stdout=True, stderr=False).decode("utf-8", errors="replace").strip()
            stderr = container.logs(stdout=False, stderr=True).decode("utf-8", errors="replace").strip()

            try:
                container.remove(force=True)
            except Exception:
                pass

            return ExecutionResult(
                success=(exit_code == 0),
                stdout=stdout,
                stderr=stderr,
                exit_code=exit_code,
                duration_ms=duration_ms,
            )

        except ContainerError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            stderr = e.stderr.decode("utf-8", errors="replace").strip() if e.stderr else str(e)
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=stderr,
                exit_code=e.exit_status or 1,
                duration_ms=duration_ms,
            )
        except APIError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            if container:
                try:
                    container.remove(force=True)
                except Exception:
                    pass
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=duration_ms,
            )

    def execute_with_timeout(
        self,
        code: str,
        language: str = "python",
        repo_path: str = "",
    ) -> ExecutionResult:
        try:
            return self.execute(code, language, repo_path=repo_path)
        except SandboxUnavailableError:
            raise
        except Exception as e:
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                timed_out=True,
            )

    def _build_command(self, code: str, language: str) -> list[str]:
        if language == "python":
            return ["python", "-c", code]
        elif language == "java":
            return ["sh", "-c", f"echo '{code}' > Main.java && javac Main.java && java Main"]
        return ["python", "-c", code]

    def cleanup(self):
        if self._client is None:
            return
        try:
            containers = self._client.containers.list(
                all=True,
                filters={"name": "sandbox-"},
            )
            for c in containers:
                try:
                    c.remove(force=True)
                except Exception:
                    pass
        except Exception as e:
            logger.warning("cleanup_error", error=str(e))


sandbox_manager = DockerSandboxManager()
