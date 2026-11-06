# csv-diff-cli

Diff two CSV files by a key column, fail CI when rows differ.

[![CI](https://github.com/haiderstudio/csv-diff-cli/actions/workflows/ci.yml/badge.svg)](https://github.com/haiderstudio/csv-diff-cli/actions/workflows/ci.yml) [![Licence: MIT](https://img.shields.io/badge/Licence-MIT-yellow.svg)](LICENSE)

## What it does

`csv_diff` reads two CSV files, matches their rows on a key column
you name, and reports the rows that were added, removed, or changed —
naming the changed columns and the row number in each file. It exits
1 when the files differ, so it can fail a CI run, and exits 0 when
they match.

- `--key` names the column that identifies a row (comma-separated
  for a composite key, e.g. `--key id,date`). Rows are matched by key,
  so the order of the rows does not matter.
- A changed row names only the columns that changed, with the old and
  new values, e.g. `price: "0.50" => "0.60"`.
- `--ignore-columns` leaves columns out of the comparison, for
  columns that are allowed to move, like a timestamp.
- `--json` prints the same diff as JSON, for scripts to read.
- It checks the input as it reads it: a missing key column, a
  duplicate key, a row with the wrong number of fields, or an empty
  key value is reported with the file and line, and exits 2.
- It is report-only and runs fully offline: it never writes to either
  input file, sends nothing anywhere, and needs no API key.

## What it does NOT do

- It does not edit either CSV file. There is no merge or apply mode;
  if you want to change a file, that is a different tool's job.
- It does not compare files without a header row. The first row must
  name the columns, including the key column.
- It does not compare values as numbers. `1.20` and `1.2` are
  different values to this tool, because it compares the text as
  written.
- It does not check TSV or JSON files. For those, use a tool that
  reads that format.
- It does not sort or reorder rows. Row order never counts as a
  difference: the same rows in a different order match.

## Who it is for

Anyone who keeps data in CSV files and wants a quick, scriptable
check that two versions agree: a developer adding a CI step that
fails the build when an exported file changes, someone comparing a
fresh export against last week's, or anyone checking that a data
migration kept every row intact. If the files match, you get one
line; if they do not, the report says exactly which rows moved and
what changed in them.

## How this differs from similar tools

CSV diff tools already exist. The best known is
[simonw/csv-diff](https://github.com/simonw/csv-diff) (343 stars,
Python, since 2019) — a CLI and library that diffs CSV, TSV, and
JSON files by key, with a human-readable report. It needs a pip
install (it depends on Click), it is built for readable diffs in
commit messages, and it exits 0 even when the files differ — it is
a viewer, not a gate. Three repos carry the exact name
`csv-diff-cli` on GitHub, all 0 stars, created in April 2026, with
no licence and no visible tests. The Ruby
[csv-diff](https://github.com/agardiner/csv-diff) gem and
[daff](https://github.com/paulfitz/daff) (a data-diff library with a
CLI) do the same job in other languages, with installs of their own.

This tool does a narrower job: a Python standard-library-only CLI
that diffs two CSV files by a key column, names the changed columns
and row numbers, and exits 1 on any difference for CI — no install
beyond Python, no library, no other formats, no merge mode.

## Install

Python standard library only — no packages to download. Clone the
repo and run it in place:

```sh
git clone https://github.com/haiderstudio/csv-diff-cli.git
cd csv-diff-cli
```

Python 3.10 or newer.

## Usage

Diff two files by the `id` column:

```sh
python3 src/csv_diff.py examples/old.csv examples/new.csv --key id
```

Real output:

```text
examples/old.csv vs examples/new.csv (key: id)
1 row(s) changed, 1 row(s) added, 1 row(s) removed
Changed id=2 (old line 3, new line 3):
  price: "0.50" => "0.60"
Added id=4 (new line 4): id=4, name=Daffodil, price=3.00, stock=15
Removed id=3 (old line 4): id=3, name=Cherry, price=2.50, stock=30
```

The command exits 1, because the files differ. The same output is
saved in `examples/sample-output.txt`.

Two matching files:

```sh
python3 src/csv_diff.py examples/same-a.csv examples/same-b.csv --key id
```

Real output:

```text
examples/same-a.csv vs examples/same-b.csv (key: id)
No differences.
```

The command exits 0.

The same diff as JSON, for scripts:

```sh
python3 src/csv_diff.py examples/old.csv examples/new.csv --key id --json
```

Real output (summary line goes to standard error, so the JSON on
standard output stays parseable):

```text
{
  "added": [
    {
      "key": "id=4",
      "line": 4,
      "row": {
        "id": "4",
        "name": "Daffodil",
        "price": "3.00",
        "stock": "15"
      }
    }
  ],
  "removed": [
    {
      "key": "id=3",
      "line": 4,
      "row": {
        "id": "3",
        "name": "Cherry",
        "price": "2.50",
        "stock": "30"
      }
    }
  ],
  "changed": [
    {
      "key": "id=2",
      "old_line": 3,
      "new_line": 3,
      "changes": {
        "price": [
          "0.50",
          "0.60"
        ]
      }
    }
  ],
  "columns_added": [],
  "columns_removed": [],
  "summary": {
    "added": 1,
    "removed": 1,
    "changed": 1
  }
}
```

Leave a column out of the comparison:

```sh
python3 src/csv_diff.py examples/old.csv examples/new.csv --key id --ignore-columns price
```

Real output:

```text
examples/old.csv vs examples/new.csv (key: id)
1 row(s) added, 1 row(s) removed
Added id=4 (new line 4): id=4, name=Daffodil, price=3.00, stock=15
Removed id=3 (old line 4): id=3, name=Cherry, price=2.50, stock=30
```

The price change is no longer reported, because `price` is
ignored. The added and removed rows still differ, so the command
still exits 1.

## Examples

### 1. Fail CI when an export changes

```sh
python3 src/csv_diff.py last-week.csv this-week.csv --key id
echo $?
```

```text
1
```

The exit code is 1 when any row was added, removed, or changed.
Put the same command in CI and the build fails until the export is
checked. With matching files the same command prints
`No differences.` and exits 0.

### 2. A composite key

When one column alone does not identify a row, name two:

```sh
python3 src/csv_diff.py a.csv b.csv --key id,date
```

Real output:

```text
a.csv vs b.csv (key: id, date)
1 row(s) changed
Changed id=1, date=2026-01-02 (old line 3, new line 3):
  note: "bye" => "changed"
```

The row is matched on `id` and `date` together, so two rows with
the same `id` but different dates are different rows.

### 3. A broken input file, reported with its line

A file with the same key twice:

```sh
python3 src/csv_diff.py dup.csv examples/new.csv --key id
```

```text
dup.csv:3: duplicate key id=1 (first seen on line 2)
```

The command exits 2, because the input itself is broken — not
because the files differ. A missing key column, a row with the
wrong number of fields, and an empty key value are reported the
same way, with the file and line.

## How it is tested

```sh
python3 tests/test_csv_diff.py
```

35 tests, standard library `unittest` only — no third-party
packages. They cover: reading tables (keyed rows, line numbers,
missing file, empty file, missing key column, duplicate keys,
wrong field counts, empty keys, duplicate headers, composite keys,
blank lines), the diff itself (added, removed, changed with named
columns, identical tables, ignored columns, header differences),
the CLI (exit 0/1/2, `--json` output, `--version`, missing flags,
ignored key or unknown columns, input files left unchanged, row
order not mattering), the bundled examples (the committed
`examples/sample-output.txt` is compared against a fresh run, and
the README's quoted outputs are checked against it), the example
script, and hygiene checks (no placeholder text, no absolute
paths, standard library only, `.env` first in `.gitignore`).

The bundled example is a real run, not made-up output:

```sh
sh examples/run-example.sh
```

It diffs `examples/old.csv` against `examples/new.csv`, then diffs
the two identical files. The committed
`examples/sample-output.txt` is the output of that run.

## Contributing

Small, focused improvements are welcome — see
[CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

MIT — see [LICENSE](LICENSE).

## Original work

Built from scratch for this repo. The CSV reading comes from
Python's standard `csv` module; no code was copied from any
existing CSV diff tool. The closest existing tools are named in
"How this differs from similar tools" above.
