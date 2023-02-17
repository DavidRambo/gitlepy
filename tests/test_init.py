# tests/test_init.py
"""Tests the init command.
Tests for the creation of the repository directory and subdirectories,
the staging area file, the initial commit object, that the HEAD file exists
and points to the main branch, and that the main branch file exists and
points to the initial commit.
"""
from pathlib import Path
import pickle

from click.testing import CliRunner
import pytest

from gitlepy.index import Index
from gitlepy.__main__ import main
import gitlepy.repository as repo


@pytest.fixture
def runner():
    return CliRunner()


def test_main_init_new_repo(runner):
    """Creates a new repository successfully."""
    # with runner.isolated_filesystem(tmp_path):
    #     print(f"\n>>>>\n{tmp_path=}\n<<<<<\n")
    # print(f"\n<<<<\n{Path.cwd()=}\n>>>>>\n")
    result = runner.invoke(main, ["init"])
    assert repo.GITLEPY_DIR.exists()
    assert repo.BLOBS_DIR.exists()
    assert repo.COMMITS_DIR.exists()
    assert repo.INDEX.exists()

    with open(repo.INDEX, "rb") as file:
        test_index: Index = pickle.load(file)
        assert repr(test_index) == "Index"

    main_branch = Path(repo.BRANCHES / "main")
    assert main_branch.exists()

    assert repo.HEAD.exists()
    assert repo.HEAD.read_text() == "main"

    assert result.exit_code == 0
    assert result.output == "Initializing gitlepy repository.\n"


def test_main_init_already_exists(runner):
    """Tries to create a new repository where one already exists."""
    # with runner.isolated_filesystem():
    # print(tmp_path)
    repo.GITLEPY_DIR.mkdir()
    result = runner.invoke(main, ["init"])
    assert result.exit_code == 0
    assert result.output == "Gitlepy repository already exists.\n"


def test_index_exists(runner):
    """Ensures that the Index exists and is an instance of the Index class."""
    runner.invoke(main, ["init"])
    assert repo.INDEX.exists()
    with open(repo.INDEX, "rb") as file:
        test_index: Index = pickle.load(file)
        assert repr(test_index) == "Index"


def test_initial_commit(runner):
    """Ensures that the initial commit was created correctly."""
    runner.invoke(main, ["init"])
    assert repo.COMMITS_DIR.exists()
    # Get name of commit object file. There should be only one.
    all_commits = list(repo.COMMITS_DIR.iterdir())
    commit_file = all_commits[0]
    # Open it and unpickle it.
    with open(commit_file, "rb") as file:
        test_commit: Commit = pickle.load(file)
        assert repr(test_commit) == "Commit"
        assert test_commit.message == "Initial commit."
