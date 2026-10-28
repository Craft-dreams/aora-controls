import unittest
from aora_controls.cli import main


class TestSkeleton(unittest.TestCase):
    def test_cli_help(self) -> None:
        exit_code = main(["--help"])
        self.assertEqual(exit_code, 0)

    def test_cli_unknown(self) -> None:
        exit_code = main(["unknown-subcommand"])
        self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
