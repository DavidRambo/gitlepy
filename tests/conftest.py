from pathlib import Path
import os.path

from click.testing import CliRunner
import pytest

from gitlepy.__main__ import main


@pytest.fixture(autouse=True)
def change_dir(request, monkeypatch, tmp_path):
    """Changes the CWD to the test directory."""
    monkeypatch.chdir(request.fspath.dirname)
    monkeypatch.chdir(tmp_path)
    # repo.WORK_DIR = Path(tmp_path)
    # repo.GITLEPY_DIR = Path(tmp_path / ".gitlepy")
    # repo.BLOBS_DIR = Path(repo.GITLEPY_DIR / "blobs")
    # repo.COMMITS_DIR = Path(repo.GITLEPY_DIR / "commits")
    # repo.BRANCHES = Path(repo.GITLEPY_DIR / "refs")
    # repo.INDEX = Path(repo.GITLEPY_DIR / "index")
    # repo.HEAD = Path(repo.GITLEPY_DIR / "HEAD")


@pytest.fixture(autouse=True, scope="session")
def runner():
    return CliRunner()


@pytest.fixture()
def setup_repo(runner):
    """Initializes a Gitlepy repository.

    The temporary file structure implemented by pytest can be accessed
    via setup_repo["work_path"] for example.
    """
    runner.invoke(main, ["init"])
    repo_paths = {}
    repo_paths["work_path"] = Path(os.path.abspath("."))
    repo_paths["test_path"] = Path(repo_paths["work_path"] / ".gitlepy")
    repo_paths["index_path"] = Path(repo_paths["test_path"] / "index")
    repo_paths["blobs_path"] = Path(repo_paths["test_path"] / "blobs")
    repo_paths["commits_path"] = Path(repo_paths["test_path"] / "commits")
    repo_paths["branches"] = Path(repo_paths["test_path"] / "refs")
    repo_paths["head"] = Path(repo_paths["test_path"] / "HEAD")
    return repo_paths
