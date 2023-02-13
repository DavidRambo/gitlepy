# tests/test_main.py
"""Tests the main.py module."""
from click.testing import CliRunner
import pytest

from gitlepy.__main__ import main


@pytest.fixture
def runner():
    return CliRunner()


@pytest.mark.parametrize(
    ("cmd", "expected"),
    (
        pytest.param([""], "Incorrect operands.\n", id="empty_arg"),
        pytest.param(["add"], "Not a Gitlepy repository.\n", id="no_repo"),
        # pytest.param(
        #     ["init"], "Initializing gitlepy repository.\n", id="init_new_print"
        # ),
        # pytest.param(
        #     ["init"], "Gitlepy repository already exists.\n", id="init_already_exists"
        # ),
    ),
)
def test_main_print_statements(runner, cmd, expected):
    """Check for main.py run without any arguments."""
    result = runner.invoke(main, cmd)
    assert result.exit_code == 0
    assert result.output == expected


# def test_main_no_arguments(capsys):
#     """Runs main.py without any argument."""
#     gitlepy.main([""])

#     out, err = capsys.readouterr()
#     assert out == "Incorrect operands."
#     assert err == ""