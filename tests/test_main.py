import unittest

from setuav_studio.__main__ import _parse_arguments


class MainTests(unittest.TestCase):
    def test_accepts_optional_project_path(self) -> None:
        arguments = _parse_arguments(["example/project.json"])

        self.assertEqual(arguments.project, "example/project.json")

    def test_project_path_is_optional(self) -> None:
        arguments = _parse_arguments([])

        self.assertIsNone(arguments.project)


if __name__ == "__main__":
    unittest.main()
