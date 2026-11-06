"""Diff two CSV files by a key column.

Reads two CSV files, matches their rows on a key column you name, and
reports the rows that were added, removed, or changed — naming the
changed columns and the row numbers in each file. Exits 1 when the
files differ, so it can fail a CI run; exits 0 when they match.

Report-only: it never writes to either input file.
Standard library only — no packages to install.
"""

import argparse
import csv
import json
import sys
from pathlib import Path

VERSION = "1.0.0"


def read_table(path, key_columns):
    """Read one CSV file.

    Returns (header, rows, problems) where rows maps a key tuple to a
    (row dict, line number) pair. problems is a list of fatal
    "path:line: message" strings; an empty list means the file read
    cleanly.
    """
    problems = []
    try:
        handle = open(path, newline="", encoding="utf-8")
    except OSError as exc:
        return None, {}, [f"{path}: {exc.strerror or exc}"]
    with handle:
        reader = csv.reader(handle)
        try:
            header = next(reader)
        except StopIteration:
            return None, {}, [f"{path}: file is empty"]
        header = [name.strip() for name in header]
        if len(set(header)) != len(header):
            dupes = sorted({name for name in header if header.count(name) > 1})
            problems.append(
                f"{path}:1: duplicate column name(s): {', '.join(dupes)}"
            )
        for key in key_columns:
            if key not in header:
                problems.append(
                    f"{path}:1: key column {key!r} not found in header"
                )
        if problems:
            return header, {}, problems
        rows = {}
        for line_no, fields in enumerate(reader, start=2):
            if not fields or all(field == "" for field in fields):
                continue  # blank line
            if len(fields) != len(header):
                problems.append(
                    f"{path}:{line_no}: row has {len(fields)} field(s), "
                    f"header has {len(header)}"
                )
                continue
            row = dict(zip(header, fields))
            key = tuple(row[col] for col in key_columns)
            if any(part == "" for part in key):
                problems.append(
                    f"{path}:{line_no}: key column(s) "
                    f"{', '.join(key_columns)} must not be empty"
                )
                continue
            if key in rows:
                problems.append(
                    f"{path}:{line_no}: duplicate key "
                    f"{_format_key(key, key_columns)} "
                    f"(first seen on line {rows[key][1]})"
                )
                continue
            rows[key] = (row, line_no)
    return header, rows, problems


def _format_key(key, key_columns):
    """Render a key tuple as col=value pairs, e.g. id=2 or id=2, date=2026-01-01."""
    return ", ".join(f"{col}={value}" for col, value in zip(key_columns, key))


def diff_tables(old_header, old_rows, new_header, new_rows, key_columns, ignore):
    """Compare two loaded tables.

    Returns a dict with added, removed and changed rows, plus the
    columns that exist in only one file.
    """
    columns_added = [col for col in new_header if col not in old_header]
    columns_removed = [col for col in old_header if col not in new_header]
    compared = [
        col
        for col in old_header
        if col in new_header and col not in key_columns and col not in ignore
    ]
    added = []
    removed = []
    changed = []
    for key in sorted(new_rows, key=lambda k: str(k)):
        if key not in old_rows:
            row, line_no = new_rows[key]
            added.append({"key": key, "line": line_no, "row": row})
    for key in sorted(old_rows, key=lambda k: str(k)):
        if key not in new_rows:
            row, line_no = old_rows[key]
            removed.append({"key": key, "line": line_no, "row": row})
    for key in sorted(old_rows, key=lambda k: str(k)):
        if key not in new_rows:
            continue
        old_row, old_line = old_rows[key]
        new_row, new_line = new_rows[key]
        changes = {
            col: (old_row[col], new_row[col])
            for col in compared
            if old_row[col] != new_row[col]
        }
        if changes:
            changed.append(
                {
                    "key": key,
                    "old_line": old_line,
                    "new_line": new_line,
                    "changes": changes,
                }
            )
    return {
        "added": added,
        "removed": removed,
        "changed": changed,
        "columns_added": columns_added,
        "columns_removed": columns_removed,
    }


def _row_text(row, header):
    return ", ".join(f"{col}={row[col]}" for col in header)


def format_human(result, old_path, new_path, key_columns, old_header, new_header):
    """Render the diff as plain text lines."""
    lines = [
        f"{old_path} vs {new_path} (key: {', '.join(key_columns)})",
    ]
    n_added = len(result["added"])
    n_removed = len(result["removed"])
    n_changed = len(result["changed"])
    if not (n_added or n_removed or n_changed or result["columns_added"] or result["columns_removed"]):
        lines.append("No differences.")
        return lines
    parts = []
    if n_changed:
        parts.append(f"{n_changed} row(s) changed")
    if n_added:
        parts.append(f"{n_added} row(s) added")
    if n_removed:
        parts.append(f"{n_removed} row(s) removed")
    lines.append(", ".join(parts))
    if result["columns_added"]:
        lines.append(
            "Columns only in "
            f"{new_path}: {', '.join(result['columns_added'])}"
        )
    if result["columns_removed"]:
        lines.append(
            "Columns only in "
            f"{old_path}: {', '.join(result['columns_removed'])}"
        )
    for item in result["changed"]:
        key_text = _format_key(item["key"], key_columns)
        lines.append(
            f"Changed {key_text} "
            f"(old line {item['old_line']}, new line {item['new_line']}):"
        )
        for col, (old_val, new_val) in item["changes"].items():
            lines.append(f'  {col}: "{old_val}" => "{new_val}"')
    for item in result["added"]:
        key_text = _format_key(item["key"], key_columns)
        lines.append(
            f"Added {key_text} (new line {item['line']}): "
            f"{_row_text(item['row'], new_header)}"
        )
    for item in result["removed"]:
        key_text = _format_key(item["key"], key_columns)
        lines.append(
            f"Removed {key_text} (old line {item['line']}): "
            f"{_row_text(item['row'], old_header)}"
        )
    return lines


def format_json(result, key_columns):
    """Render the diff as JSON-safe data."""
    def key_text(key):
        return _format_key(key, key_columns)

    return {
        "added": [
            {
                "key": key_text(item["key"]),
                "line": item["line"],
                "row": item["row"],
            }
            for item in result["added"]
        ],
        "removed": [
            {
                "key": key_text(item["key"]),
                "line": item["line"],
                "row": item["row"],
            }
            for item in result["removed"]
        ],
        "changed": [
            {
                "key": key_text(item["key"]),
                "old_line": item["old_line"],
                "new_line": item["new_line"],
                "changes": {
                    col: [old_val, new_val]
                    for col, (old_val, new_val) in item["changes"].items()
                },
            }
            for item in result["changed"]
        ],
        "columns_added": result["columns_added"],
        "columns_removed": result["columns_removed"],
        "summary": {
            "added": len(result["added"]),
            "removed": len(result["removed"]),
            "changed": len(result["changed"]),
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="csv_diff",
        description=(
            "Diff two CSV files by a key column. "
            "Exits 1 when the files differ, 0 when they match."
        ),
    )
    parser.add_argument("old", help="first CSV file")
    parser.add_argument("new", help="second CSV file")
    parser.add_argument(
        "--key",
        required=True,
        help="key column name (comma-separated for a composite key, e.g. id,date)",
    )
    parser.add_argument(
        "--ignore-columns",
        default="",
        help="comma-separated column names to leave out of the comparison",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the diff as JSON instead of plain text",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {VERSION}")
    args = parser.parse_args(argv)

    key_columns = [col.strip() for col in args.key.split(",") if col.strip()]
    if not key_columns:
        print("error: --key must name at least one column", file=sys.stderr)
        return 2
    ignore = {
        col.strip() for col in args.ignore_columns.split(",") if col.strip()
    }
    unknown_ignore = sorted(col for col in ignore if col in key_columns)
    if unknown_ignore:
        print(
            "error: --ignore-columns must not name a key column: "
            + ", ".join(unknown_ignore),
            file=sys.stderr,
        )
        return 2

    old_header, old_rows, old_problems = read_table(args.old, key_columns)
    new_header, new_rows, new_problems = read_table(args.new, key_columns)
    problems = old_problems + new_problems
    if problems:
        for problem in problems:
            print(problem, file=sys.stderr)
        return 2
    unknown = sorted(col for col in ignore if col not in old_header and col not in new_header)
    if unknown:
        print(
            "error: --ignore-columns names unknown column(s): "
            + ", ".join(unknown),
            file=sys.stderr,
        )
        return 2

    result = diff_tables(
        old_header, old_rows, new_header, new_rows, key_columns, ignore
    )
    differs = bool(
        result["added"]
        or result["removed"]
        or result["changed"]
        or result["columns_added"]
        or result["columns_removed"]
    )
    if args.json:
        print(json.dumps(format_json(result, key_columns), indent=2))
        summary = (
            f"{len(result['changed'])} row(s) changed, "
            f"{len(result['added'])} row(s) added, "
            f"{len(result['removed'])} row(s) removed"
        )
        print(summary, file=sys.stderr)
    else:
        for line in format_human(
            result, args.old, args.new, key_columns, old_header, new_header
        ):
            print(line)
    return 1 if differs else 0


if __name__ == "__main__":
    sys.exit(main())
