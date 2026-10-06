import uuid
import asyncio
from typing import Optional
from dataclasses import dataclass

import docker
from docker.errors import ContainerError, BuildError, APIError

from app.config import settings
from app.observability.logger import get_logger

logger = get_logger(__name__)


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

    def execute(self, code: str, language: str = "python") -> ExecutionResult:
        if self._client is None:
            return self._fallback_execute(code, language)

        self._ensure_image()
        container_name = f"sandbox-{uuid.uuid4().hex[:8]}"

        cmd = self._build_command(code, language)
        start_time = asyncio.get_event_loop().time() if asyncio.get_event_loop().is_running() else 0
        import time
        start_time = time.time()

        try:
            result = self._client.containers.run(
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
                remove=True,
                stdout=True,
                stderr=True,
                detach=False,
            )
            duration_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                success=True,
                stdout=result.decode("utf-8", errors="replace").strip(),
                stderr="",
                exit_code=0,
                duration_ms=duration_ms,
            )
        except ContainerError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            stderr = e.stderr.decode("utf-8", errors="replace").strip() if e.stderr else str(e)
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=stderr,
                exit_code=e.exit_status or 1,
                duration_ms=duration_ms,
            )
        except APIError as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=duration_ms,
            )

    def execute_with_timeout(self, code: str, language: str = "python") -> ExecutionResult:
        try:
            result = self.execute(code, language)
            return result
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

    def _fallback_execute(self, code: str, language: str) -> ExecutionResult:
        import subprocess
        import time
        start = time.time()
        try:
            if language == "python":
                proc = subprocess.run(
                    ["python", "-c", code],
                    capture_output=True,
                    text=True,
                    timeout=self.policy.timeout,
                )
                duration_ms = int((time.time() - start) * 1000)
                return ExecutionResult(
                    success=(proc.returncode == 0),
                    stdout=proc.stdout.strip(),
                    stderr=proc.stderr.strip(),
                    exit_code=proc.returncode,
                    duration_ms=duration_ms,
                )
        except subprocess.TimeoutExpired:
            duration_ms = int((time.time() - start) * 1000)
            return ExecutionResult(
                success=False,
                stdout="",
                stderr="Execution timed out",
                exit_code=-1,
                timed_out=True,
                duration_ms=duration_ms,
            )
        except Exception as e:
            duration_ms = int((time.time() - start) * 1000)
            return ExecutionResult(
                success=False,
                stdout="",
                stderr=str(e),
                exit_code=-1,
                duration_ms=duration_ms,
            )

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
