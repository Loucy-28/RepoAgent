import os
import subprocess
import tempfile
import pytest

from app.services.git_workflow import git_workflow, GitError


@pytest.fixture
def temp_repo():
    with tempfile.TemporaryDirectory() as tmpdir:
        subprocess.run(["git", "init", "-b", "main"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.email", "test@test.com"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmpdir, capture_output=True)

        init_file = os.path.join(tmpdir, "README.md")
        with open(init_file, "w") as f:
            f.write("# Test Repo\n")
        subprocess.run(["git", "add", "-A"], cwd=tmpdir, capture_output=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=tmpdir, capture_output=True)
        yield tmpdir


def test_create_task_branch(temp_repo):
    result = git_workflow.create_task_branch(temp_repo, "abc-123")
    assert result["success"] is True
    assert result["branch"] == "agent/task-abc-123"

    current = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=temp_repo, capture_output=True, text=True,
    ).stdout.strip()
    assert current == "agent/task-abc-123"


def test_commit_changes(temp_repo):
    git_workflow.create_task_branch(temp_repo, "def-456")

    test_file = os.path.join(temp_repo, "new_file.py")
    with open(test_file, "w") as f:
        f.write("print('hello')\n")

    result = git_workflow.commit_changes(temp_repo, "def-456", "Add new file")
    assert result["committed"] is True
    assert "sha" in result
    assert len(result["sha"]) == 40


def test_commit_no_changes(temp_repo):
    git_workflow.create_task_branch(temp_repo, "ghi-789")
    result = git_workflow.commit_changes(temp_repo, "ghi-789", "No changes")
    assert result["committed"] is False


def test_generate_diff(temp_repo):
    git_workflow.create_task_branch(temp_repo, "diff-001")

    test_file = os.path.join(temp_repo, "changed.py")
    with open(test_file, "w") as f:
        f.write("x = 1\n")
    subprocess.run(["git", "add", "-A"], cwd=temp_repo, capture_output=True)
    subprocess.run(["git", "commit", "-m", "add changed.py"], cwd=temp_repo, capture_output=True)

    result = git_workflow.generate_diff(temp_repo, "agent/task-diff-001")
    assert "diff" in result
    assert result["has_changes"] is True


def test_merge_to_main(temp_repo):
    git_workflow.create_task_branch(temp_repo, "merge-001")

    test_file = os.path.join(temp_repo, "feature.py")
    with open(test_file, "w") as f:
        f.write("feature = True\n")
    git_workflow.commit_changes(temp_repo, "merge-001", "Add feature")

    result = git_workflow.merge_to_main(temp_repo, "agent/task-merge-001")
    assert result["merged"] is True
    assert "sha" in result

    current = subprocess.run(
        ["git", "rev-parse", "--abbrev-ref", "HEAD"],
        cwd=temp_repo, capture_output=True, text=True,
    ).stdout.strip()
    assert current == "main"


def test_merge_blocked_by_dirty_tree(temp_repo):
    dirty_file = os.path.join(temp_repo, "dirty.py")
    with open(dirty_file, "w") as f:
        f.write("uncommitted = True\n")

    result = git_workflow.merge_to_main(temp_repo, "agent/task-nonexistent")
    assert result["merged"] is False
    assert "dirty" in result["error"].lower()


def test_create_branch_with_dirty_tree(temp_repo):
    dirty_file = os.path.join(temp_repo, "uncommitted.py")
    with open(dirty_file, "w") as f:
        f.write("stashed = True\n")

    result = git_workflow.create_task_branch(temp_repo, "stash-001")
    assert result["success"] is True
    assert result["branch"] == "agent/task-stash-001"

    stash_list = subprocess.run(
        ["git", "stash", "list"], cwd=temp_repo, capture_output=True, text=True,
    ).stdout
    assert "repo-agent-pre-stash-001" not in stash_list


def test_concurrent_merge_lock(temp_repo):
    lock_path = os.path.join(temp_repo, ".git", "repo-agent-merge.lock")
    with open(lock_path, "w") as f:
        f.write("99999")

    result = git_workflow.merge_to_main(temp_repo, "agent/task-locked")
    assert result["merged"] is False
    assert "lock" in result["error"].lower() or "progress" in result["error"].lower()

    os.remove(lock_path)


def test_is_working_tree_dirty(temp_repo):
    assert git_workflow.is_working_tree_dirty(temp_repo) is False

    dirty_file = os.path.join(temp_repo, "new.py")
    with open(dirty_file, "w") as f:
        f.write("x = 1\n")
    assert git_workflow.is_working_tree_dirty(temp_repo) is True
