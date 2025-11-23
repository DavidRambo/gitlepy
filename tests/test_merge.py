"""tests/test_merge.py

Tests the merge command.
"""

from pathlib import Path

import pytest

from gitlepy.__main__ import main
from gitlepy.repository import Repo


@pytest.fixture(autouse=True)
def merge_setup(runner, setup_repo):
    """Basic multi-branch setup for merge tests.

    Leaves the gitlepy repository in the following state, with a working
    directory clear of unstaged modifications:
    === Branches ===
    *dev
    main

    main's a.txt = "Hello"
    dev's a.txt = "Hello, gitlepy.\n"
    """
    file_a = Path(setup_repo["work_path"] / "a.txt")
    file_a.write_text("Hello")
    runner.invoke(main, ["add", "a.txt"])
    runner.invoke(main, ["commit", "Hello > a.txt"])

    runner.invoke(main, ["branch", "dev"])  # create branch called dev
    runner.invoke(main, ["checkout", "dev"])  # check out dev
    file_a.write_text("Hello, gitlepy.\n")
    runner.invoke(main, ["add", "a.txt"])
    runner.invoke(main, ["commit", "Hello, gitlepy > a.txt"])


def test_merge_uncommitted_changes(runner, setup_repo):
    """Fails to merge due to staged but uncommitted changes."""
    runner.invoke(main, ["checkout", "main"])
    file_a = Path(setup_repo["work_path"] / "a.txt")
    file_a.write_text("Hi\n")
    runner.invoke(main, ["add", "a.txt"])  # stage file_a
    result = runner.invoke(main, ["merge", "dev"])
    expected = "You have uncommitted changes.\n"
    assert expected == result.output


def test_merge_unstaged_changes(runner, setup_repo):
    """Merges a file with unstaged changes."""
    runner.invoke(main, ["checkout", "main"])
    file_a = Path(setup_repo["work_path"] / "a.txt")
    file_a.write_text("Hi\n")
    result = runner.invoke(main, ["merge", "dev"])
    expected = "There is a file with unstaged changes; delete it, or add and commit it first.\n"
    assert result.output == expected


def test_merge_nonexistent_branch(runner, setup_repo):
    """Tries to merge with a branch name that does not exist."""
    r = Repo(setup_repo["work_path"])
    result = r.branches()
    assert len(result) == 2
    assert "main" in result
    assert "dev" in result
    assert r.current_branch() == "dev"
    result = runner.invoke(main, ["merge", "invalid"])
    print(f"\n>>>>\n{r.branches()}\n<<<<<")
    expected = "A branch with that name does not exist.\n"
    assert expected == result.output


def test_merge_self(runner, setup_repo):
    """Tries to merge a branch with itself."""
    result = runner.invoke(main, ["merge", "dev"])
    expected = "Cannot merge a branch with itself.\n"
    assert expected == result.output


def test_merge_file_change(runner, setup_repo):
    """Fast forwards main to dev."""
    runner.invoke(main, ["checkout", "main"])
    merge_result = runner.invoke(main, ["merge", "dev"])
    merge_expected = "Current branch is fast-forwarded.\n"
    assert merge_expected == merge_result.output
    file_a = Path(setup_repo["work_path"] / "a.txt")
    expected = "Hello, gitlepy.\n"
    assert file_a.read_text() == expected


def test_merge_head_updated(runner, setup_repo):
    """Fast forwards main to dev and checks that the HEAD reference
    for main branch is the same as dev branch."""
    repo = Repo(setup_repo["work_path"])
    dev_ref = repo.head_commit_id()

    # checkout main
    runner.invoke(main, ["checkout", "main"])
    old_main_ref = repo.head_commit_id()
    assert dev_ref != old_main_ref

    # merge with dev
    merge_result = runner.invoke(main, ["merge", "dev"])
    assert "Current branch is fast-forwarded.\n" == merge_result.output
    new_main_ref = repo.head_commit_id()
    assert old_main_ref != new_main_ref
    assert new_main_ref == dev_ref


def test_merge_ignore_untracked_file(runner, setup_repo):
    """Fast forwards main to dev, ignoring an untracked file."""
    file_b = Path(setup_repo["work_path"] / "b.txt")
    file_b.touch()
    runner.invoke(main, ["checkout", "main"])
    file_c = Path(setup_repo["work_path"] / "c.txt")
    file_c.touch()
    runner.invoke(main, ["merge", "dev"])
    assert file_b.exists()
    assert file_c.exists()


def test_merge_file_conflict(runner, setup_repo):
    """Merges a file with a conflict.

    Checks out main and modifies a.txt to contain 'Hi'.
    Adds and commits the change, then merges with dev branch.
    a.txt should contain:
        <<<<<<< HEAD
        Hi
        =======
        Hello, gitlepy.
        >>>>>>> {head_dev_commit_id}
    """
    repo = Repo(setup_repo["work_path"])
    head_dev_commit_id = repo.head_commit_id()
    assert Path(setup_repo["work_path"] / "a.txt").read_text() == "Hello, gitlepy.\n"
    runner.invoke(main, ["checkout", "main"])
    file_a = Path(setup_repo["work_path"] / "a.txt")
    file_a.write_text("Hi\n")
    runner.invoke(main, ["add", "a.txt"])
    runner.invoke(main, ["commit", "Hi > a.txt"])
    assert Path(setup_repo["work_path"] / "a.txt").read_text() == "Hi\n"
    result = runner.invoke(main, ["merge", "dev"])
    assert result.exit_code == 0
    assert result.output == "Encountered a merge conflict.\n"
    expected = (
        f"<<<<<<< HEAD\nHi\n=======\nHello, gitlepy.\n>>>>>>> {head_dev_commit_id}\n"
    )
    assert expected == file_a.read_text()


def test_merge_no_split(runner, setup_repo):
    """Runs the Repo.merge method with disparate commit histories."""
    repo = Repo(setup_repo["work_path"])

    # Create a disconnected branch.
    Path(setup_repo["branches"] / "fake")
    # Force HEAD file to reference it
    setup_repo["head"].write_text("fake")

    assert repo.current_branch() == "fake"

    # Create its associated commit object
    repo.new_commit("", "fake commit")

    result = runner.invoke(main, ["merge", "main"])
    expected = "No common ancestor found.\n"
    assert expected == result.output


def test_merge_success(runner, setup_repo):
    """Merges two branches."""
    runner.invoke(main, ["checkout", "main"])
    file_b = Path(setup_repo["work_path"] / "b.txt")
    file_b.write_text("main text")
    runner.invoke(main, ["add", "b.txt"])
    runner.invoke(main, ["commit", "main text > b.txt"])

    merge_result = runner.invoke(main, ["merge", "dev"])
    expected = "Merged dev into main\n"
    assert merge_result.exit_code == 0
    assert expected == merge_result.output
