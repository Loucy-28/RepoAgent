import os
import subprocess
from typing import Optional

from app.observability.logger import get_logger

logger = get_logger(__name__)


class GitWorkflow:
    def create_task_branch(self, repo_path: str, task_id: str) -> dict:
        branch_name = f"agent/task-{task_id}"
        stashed = False
        try:
            if self.is_working_tree_dirty(repo_path):
                stash_result = self._run(repo_path, ["git", "stash", "push", "-m", f"repo-agent-pre-{task_id}"])
                stashed = True
                logger.info("working_tree_stashed", repo=repo_path, task=task_id)

            self._run(repo_path, ["git", "checkout", "-b", branch_name])
            logger.info("task_branch_created", repo=repo_path, branch=branch_name)

            if stashed:
                self._safe_stash_pop(repo_path)

            return {"branch": branch_name, "success": True}
        except GitError as e:
            logger.warning("task_branch_create_failed", repo=repo_path, branch=branch_name, error=str(e))
            if stashed:
                self._safe_stash_pop(repo_path)
            try:
                self._run(repo_path, ["git", "checkout", branch_name])
                return {"branch": branch_name, "success": True, "existed": True}
            except GitError:
                return {"branch": "", "success": False, "error": str(e)}

    def commit_changes(self, repo_path: str, task_id: str, description: str) -> dict:
        try:
            status = self._run(repo_path, ["git", "status", "--porcelain"])
            if not status.strip():
                return {"committed": False, "message": "No changes to commit"}

            self._run(repo_path, ["git", "add", "-A"])

            short_desc = description[:72].replace('"', '\\"')
            message = f"[RepoAgent] Task {task_id}: {short_desc}"
            self._run(repo_path, ["git", "commit", "-m", message])

            sha = self._run(repo_path, ["git", "rev-parse", "HEAD"]).strip()
            logger.info("task_changes_committed", repo=repo_path, task=task_id, sha=sha)
            return {"committed": True, "sha": sha, "message": message}
        except GitError as e:
            logger.error("task_commit_failed", repo=repo_path, task=task_id, error=str(e))
            return {"committed": False, "error": str(e)}

    def generate_diff(self, repo_path: str, branch_name: str) -> dict:
        try:
            current_branch = self._run(repo_path, ["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()

            if current_branch != branch_name:
                self._run(repo_path, ["git", "checkout", branch_name])

            base = self._find_base(repo_path, branch_name)
            diff_output = self._run(repo_path, ["git", "diff", base, "HEAD"])

            if current_branch != branch_name:
                self._run(repo_path, ["git", "checkout", current_branch])

            return {
                "branch": branch_name,
                "diff": diff_output,
                "has_changes": bool(diff_output.strip()),
            }
        except GitError as e:
            logger.error("diff_generation_failed", repo=repo_path, branch=branch_name, error=str(e))
            return {"branch": branch_name, "diff": "", "error": str(e)}

    def merge_to_main(self, repo_path: str, branch_name: str, main_branch: str = "main") -> dict:
        if self.is_working_tree_dirty(repo_path):
            logger.error("merge_blocked_dirty_tree", repo=repo_path, branch=branch_name)
            return {"merged": False, "error": "Working tree is dirty. Commit or stash changes before merging."}

        lock_path = os.path.join(repo_path, ".git", "repo-agent-merge.lock")
        if not self._acquire_lock(lock_path):
            logger.error("merge_blocked_concurrent", repo=repo_path, branch=branch_name)
            return {"merged": False, "error": "Another merge operation is in progress (lock file exists)."}

        try:
            current_branch = self._run(repo_path, ["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
            if current_branch != main_branch:
                self._run(repo_path, ["git", "checkout", main_branch])

            self._run(repo_path, ["git", "merge", branch_name, "--no-ff", "-m", f"Merge {branch_name}"])
            merged_sha = self._run(repo_path, ["git", "rev-parse", "HEAD"]).strip()

            logger.info("branch_merged", repo=repo_path, branch=branch_name, into=main_branch, sha=merged_sha)
            return {"merged": True, "sha": merged_sha, "branch": branch_name, "into": main_branch}
        except GitError as e:
            try:
                self._run(repo_path, ["git", "merge", "--abort"])
            except GitError:
                pass
            logger.error("merge_failed", repo=repo_path, branch=branch_name, error=str(e))
            return {"merged": False, "error": str(e)}
        finally:
            self._release_lock(lock_path)

    def cleanup_branch(self, repo_path: str, branch_name: str) -> dict:
        try:
            current = self._run(repo_path, ["git", "rev-parse", "--abbrev-ref", "HEAD"]).strip()
            if current == branch_name:
                self._run(repo_path, ["git", "checkout", "main"])
            self._run(repo_path, ["git", "branch", "-d", branch_name])
            logger.info("branch_cleaned", repo=repo_path, branch=branch_name)
            return {"cleaned": True}
        except GitError as e:
            return {"cleaned": False, "error": str(e)}

    def is_working_tree_dirty(self, repo_path: str) -> bool:
        try:
            status = self._run(repo_path, ["git", "status", "--porcelain"])
            return bool(status.strip())
        except GitError:
            return False

    def _find_base(self, repo_path: str, branch_name: str) -> str:
        for candidate in ["main", "master"]:
            try:
                self._run(repo_path, ["git", "rev-parse", "--verify", candidate])
                return candidate
            except GitError:
                continue
        return self._run(repo_path, ["git", "rev-list", "--max-parents=0", "HEAD"]).strip()

    def _acquire_lock(self, lock_path: str) -> bool:
        if os.path.exists(lock_path):
            return False
        try:
            with open(lock_path, "w") as f:
                f.write(str(os.getpid()))
            return True
        except OSError:
            return False

    def _release_lock(self, lock_path: str):
        try:
            if os.path.exists(lock_path):
                os.remove(lock_path)
        except OSError:
            pass

    def _safe_stash_pop(self, repo_path: str):
        try:
            stash_list = self._run(repo_path, ["git", "stash", "list"])
            if stash_list.strip():
                self._run(repo_path, ["git", "stash", "pop"])
        except GitError as e:
            logger.warning("stash_pop_failed", repo=repo_path, error=str(e))

    def _run(self, cwd: str, cmd: list[str]) -> str:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            raise GitError(result.stderr.strip() or f"Command failed: {' '.join(cmd)}")
        return result.stdout


class GitError(Exception):
    pass


git_workflow = GitWorkflow()
