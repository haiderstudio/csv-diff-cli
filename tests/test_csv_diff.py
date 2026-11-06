"""Tests for csv_diff — standard library unittest only."""

import ast
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import csv_diff

ROOT = Path(__file__).resolve().parents[1]
EXAMPLES = ROOT / "examples"


def run_cli(*args):
    """Run main() capturing stdout/stderr; return (exit code, stdout, stderr)."""
    out = io.StringIO()
    err = io.StringIO()
    with redirect_stdout(out), redirect_stderr(err):
        code = csv_diff.main(list(args))
    return code, out.getvalue(), err.getvalue()


def write_csv(directory, name, text):
    path = Path(directory) / name
    path.write_text(text, encoding="utf-8")
    return str(path)


class TestReadTable(unittest.TestCase):
    def test_reads_rows_keyed_by_id(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_csv(tmp, "a.csv", "id,name\n1,Apple\n2,Banana\n")
            header, rows, problems = csv_diff.read_table(path, ["id"])
            self.assertEqual(problems, [])
            self.assertEqual(header, ["id", "name"])
            self.assertEqual(rows[("1",)][0], {"id": "1", "name": "Apple"})
            self.assertEqual(rows[("1",)][1], 2)
            self.assertEqual(rows[("2",)][1], 3)

    def test_missing_file(self):
        header, rows, problems = csv_diff.read_table("no-such-file.csv", ["id"])
        self.assertEqual(rows, {})
        self.assertEqual(len(problems), 1)
        self.assertIn("no-such-file.csv", problems[0])

    def test_empty_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_csv(tmp, "a.csv", "")
            _, _, problems = csv_diff.read_table(path, ["id"])
            self.assertEqual(problems, [f"{path}: file is empty"])

    def test_missing_key_column(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_csv(tmp, "a.csv", "name,price\nApple,1.20\n")
            _, _, problems = csv_diff.read_table(path, ["id"])
            self.assertEqual(
                problems, [f"{path}:1: key column 'id' not found in header"]
            )

    def test_duplicate_key_reports_first_line(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_csv(tmp, "a.csv", "id,name\n1,Apple\n1,Banana\n")
            _, _, problems = csv_diff.read_table(path, ["id"])
            self.assertEqual(len(problems), 1)
            self.assertIn("duplicate key id=1", problems[0])
            self.assertIn("first seen on line 2", problems[0])

    def test_wrong_field_count(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_csv(tmp, "a.csv", "id,name\n1,Apple,extra\n")
            _, _, problems = csv_diff.read_table(path, ["id"])
            self.assertEqual(len(problems), 1)
            self.assertIn("row has 3 field(s), header has 2", problems[0])

    def test_empty_key_value(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_csv(tmp, "a.csv", "id,name\n,Apple\n")
            _, _, problems = csv_diff.read_table(path, ["id"])
            self.assertEqual(len(problems), 1)
            self.assertIn("must not be empty", problems[0])

    def test_duplicate_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_csv(tmp, "a.csv", "id,id\n1,2\n")
            _, _, problems = csv_diff.read_table(path, ["id"])
            self.assertTrue(any("duplicate column name" in p for p in problems))

    def test_composite_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_csv(
                tmp, "a.csv", "id,date,note\n1,2026-01-01,hi\n1,2026-01-02,bye\n"
            )
            _, rows, problems = csv_diff.read_table(path, ["id", "date"])
            self.assertEqual(problems, [])
            self.assertEqual(len(rows), 2)

    def test_blank_lines_skipped(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = write_csv(tmp, "a.csv", "id,name\n1,Apple\n\n2,Banana\n")
            _, rows, problems = csv_diff.read_table(path, ["id"])
            self.assertEqual(problems, [])
            self.assertEqual(len(rows), 2)
            self.assertEqual(rows[("2",)][1], 4)


class TestDiffTables(unittest.TestCase):
    def setUp(self):
        self.old = (["id", "name", "price"], {("1",): ({"id": "1", "name": "Apple", "price": "1.20"}, 2), ("2",): ({"id": "2", "name": "Banana", "price": "0.50"}, 3)})
        self.new = (["id", "name", "price"], {("1",): ({"id": "1", "name": "Apple", "price": "1.20"}, 2), ("3",): ({"id": "3", "name": "Cherry", "price": "2.50"}, 3)})

    def test_added_removed(self):
        result = csv_diff.diff_tables(
            self.old[0], self.old[1], self.new[0], self.new[1], ["id"], set()
        )
        self.assertEqual([a["key"] for a in result["added"]], [("3",)])
        self.assertEqual([r["key"] for r in result["removed"]], [("2",)])
        self.assertEqual(result["changed"], [])

    def test_changed_names_columns(self):
        new_rows = {("1",): ({"id": "1", "name": "Apple", "price": "1.30"}, 2)}
        result = csv_diff.diff_tables(
            self.old[0], self.old[1], self.new[0], new_rows, ["id"], set()
        )
        self.assertEqual(len(result["changed"]), 1)
        item = result["changed"][0]
        self.assertEqual(item["key"], ("1",))
        self.assertEqual(item["changes"], {"price": ("1.20", "1.30")})

    def test_identical_tables(self):
        result = csv_diff.diff_tables(
            self.old[0], self.old[1], self.old[0], self.old[1], ["id"], set()
        )
        self.assertEqual(result["added"], [])
        self.assertEqual(result["removed"], [])
        self.assertEqual(result["changed"], [])

    def test_ignore_columns(self):
        new_rows = {("1",): ({"id": "1", "name": "Apple", "price": "1.30"}, 2)}
        result = csv_diff.diff_tables(
            self.old[0], self.old[1], self.new[0], new_rows, ["id"], {"price"}
        )
        self.assertEqual(result["changed"], [])

    def test_header_differences(self):
        result = csv_diff.diff_tables(
            ["id", "name", "colour"],
            self.old[1],
            ["id", "name", "stock"],
            self.new[1],
            ["id"],
            set(),
        )
        self.assertEqual(result["columns_added"], ["stock"])
        self.assertEqual(result["columns_removed"], ["colour"])


class TestCli(unittest.TestCase):
    def test_match_exits_zero(self):
        code, out, _ = run_cli(
            str(EXAMPLES / "same-a.csv"), str(EXAMPLES / "same-b.csv"), "--key", "id"
        )
        self.assertEqual(code, 0)
        self.assertIn("No differences.", out)

    def test_diff_exits_one_with_counts(self):
        code, out, _ = run_cli(
            str(EXAMPLES / "old.csv"), str(EXAMPLES / "new.csv"), "--key", "id"
        )
        self.assertEqual(code, 1)
        self.assertIn("1 row(s) changed, 1 row(s) added, 1 row(s) removed", out)
        self.assertIn('Changed id=2 (old line 3, new line 3):', out)
        self.assertIn('price: "0.50" => "0.60"', out)
        self.assertIn("Added id=4 (new line 4):", out)
        self.assertIn("Removed id=3 (old line 4):", out)

    def test_json_output_parses(self):
        code, out, err = run_cli(
            str(EXAMPLES / "old.csv"),
            str(EXAMPLES / "new.csv"),
            "--key",
            "id",
            "--json",
        )
        self.assertEqual(code, 1)
        data = json.loads(out)
        self.assertEqual(data["summary"], {"added": 1, "removed": 1, "changed": 1})
        self.assertEqual(data["changed"][0]["changes"]["price"], ["0.50", "0.60"])
        self.assertEqual(data["changed"][0]["key"], "id=2")
        self.assertIn("1 row(s) changed", err)

    def test_json_match_exits_zero(self):
        code, out, _ = run_cli(
            str(EXAMPLES / "same-a.csv"),
            str(EXAMPLES / "same-b.csv"),
            "--key",
            "id",
            "--json",
        )
        self.assertEqual(code, 0)
        data = json.loads(out)
        self.assertEqual(data["summary"], {"added": 0, "removed": 0, "changed": 0})

    def test_missing_file_exits_two(self):
        code, _, err = run_cli("nope.csv", str(EXAMPLES / "new.csv"), "--key", "id")
        self.assertEqual(code, 2)
        self.assertIn("nope.csv", err)

    def test_missing_key_flag_exits_two(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli(str(EXAMPLES / "old.csv"), str(EXAMPLES / "new.csv"))
        self.assertEqual(caught.exception.code, 2)

    def test_missing_key_column_exits_two(self):
        code, _, err = run_cli(
            str(EXAMPLES / "old.csv"), str(EXAMPLES / "new.csv"), "--key", "sku"
        )
        self.assertEqual(code, 2)
        self.assertIn("key column 'sku' not found", err)

    def test_ignore_key_column_exits_two(self):
        code, _, err = run_cli(
            str(EXAMPLES / "old.csv"),
            str(EXAMPLES / "new.csv"),
            "--key",
            "id",
            "--ignore-columns",
            "id",
        )
        self.assertEqual(code, 2)
        self.assertIn("must not name a key column", err)

    def test_ignore_unknown_column_exits_two(self):
        code, _, err = run_cli(
            str(EXAMPLES / "old.csv"),
            str(EXAMPLES / "new.csv"),
            "--key",
            "id",
            "--ignore-columns",
            "colour",
        )
        self.assertEqual(code, 2)
        self.assertIn("unknown column", err)

    def test_ignore_columns_hides_change(self):
        code, out, _ = run_cli(
            str(EXAMPLES / "old.csv"),
            str(EXAMPLES / "new.csv"),
            "--key",
            "id",
            "--ignore-columns",
            "price",
        )
        self.assertEqual(code, 1)  # added + removed rows still differ
        self.assertNotIn("Changed", out)

    def test_version_flag(self):
        with self.assertRaises(SystemExit) as caught:
            run_cli("--version")
        self.assertEqual(caught.exception.code, 0)

    def test_input_files_unchanged(self):
        before_old = (EXAMPLES / "old.csv").read_text(encoding="utf-8")
        before_new = (EXAMPLES / "new.csv").read_text(encoding="utf-8")
        run_cli(str(EXAMPLES / "old.csv"), str(EXAMPLES / "new.csv"), "--key", "id")
        self.assertEqual((EXAMPLES / "old.csv").read_text(encoding="utf-8"), before_old)
        self.assertEqual((EXAMPLES / "new.csv").read_text(encoding="utf-8"), before_new)

    def test_row_order_does_not_matter(self):
        with tempfile.TemporaryDirectory() as tmp:
            a = write_csv(tmp, "a.csv", "id,name\n1,Apple\n2,Banana\n")
            b = write_csv(tmp, "b.csv", "id,name\n2,Banana\n1,Apple\n")
            code, out, _ = run_cli(a, b, "--key", "id")
            self.assertEqual(code, 0)
            self.assertIn("No differences.", out)


class TestExamples(unittest.TestCase):
    def test_sample_output_matches_fresh_run(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)
        committed = (EXAMPLES / "sample-output.txt").read_text(encoding="utf-8")
        self.assertEqual(result.stdout, committed)

    def test_readme_quotes_real_output(self):
        readme = (ROOT / "README.md").read_text(encoding="utf-8")
        committed = (EXAMPLES / "sample-output.txt").read_text(encoding="utf-8")
        for line in [
            "1 row(s) changed, 1 row(s) added, 1 row(s) removed",
            'Changed id=2 (old line 3, new line 3):',
            'price: "0.50" => "0.60"',
            "Added id=4 (new line 4): id=4, name=Daffodil, price=3.00, stock=15",
            "Removed id=3 (old line 4): id=3, name=Cherry, price=2.50, stock=30",
            "No differences.",
        ]:
            self.assertIn(line, readme, f"README missing quoted line: {line}")
            self.assertIn(line, committed, f"sample output missing line: {line}")

    def test_run_example_script_exits_zero(self):
        result = subprocess.run(
            ["sh", "examples/run-example.sh"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        self.assertEqual(result.returncode, 0)


class TestHygiene(unittest.TestCase):
    BANNED = ["TODO", "FIXME", "coming soon", "lorem", "API_KEY"]

    def test_no_placeholder_text(self):
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            for word in self.BANNED:
                self.assertNotIn(word, text, f"{word} found in {path}")

    def test_no_absolute_workspace_paths(self):
        for path in ROOT.rglob("*"):
            if not path.is_file():
                continue
            if ".git" in path.parts or "__pycache__" in path.parts:
                continue
            if "tests" in path.parts:
                continue
            text = path.read_text(encoding="utf-8", errors="ignore")
            self.assertNotIn("/home/hatch", text, f"absolute path in {path}")
            self.assertNotIn("C:\\Users", text, f"absolute path in {path}")

    def test_stdlib_only(self):
        for source in [ROOT / "src" / "csv_diff.py", Path(__file__)]:
            tree = ast.parse(source.read_text(encoding="utf-8"))
            imported = set()
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.update(alias.name.split(".")[0] for alias in node.names)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        imported.add(node.module.split(".")[0])
            allowed = {
                "argparse", "ast", "csv", "io", "json", "subprocess", "sys",
                "tempfile", "unittest", "contextlib", "pathlib",
                # the module under test, imported by the test file itself
                "csv_diff",
            }
            self.assertTrue(
                imported <= allowed,
                f"non-stdlib import in {source}: {imported - allowed}",
            )

    def test_gitignore_lists_env_first(self):
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertEqual(lines[0], ".env")


if __name__ == "__main__":
    unittest.main()
