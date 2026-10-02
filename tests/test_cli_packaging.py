"""Early CLI exits require no inventory, collection, or UI launch."""

from unittest.mock import patch

import pytest

from dct.__main__ import main


@pytest.mark.parametrize(("flag", "text"), [("--version", "DCT 0.1.0"), ("--help", "usage: dct")])
def test_release_cli_flags(flag: str, text: str, capsys: pytest.CaptureFixture[str]) -> None:
    with (
        patch("sys.argv", ["dct", flag]),
        patch("dct.__main__.LocalInventory", side_effect=AssertionError("must not discover")),
        patch("dct.__main__.DCTApp", side_effect=AssertionError("must not launch")),
        pytest.raises(SystemExit) as result,
    ):
        main()
    assert result.value.code == 0
    output = capsys.readouterr()
    assert text in output.out
    assert not output.err
