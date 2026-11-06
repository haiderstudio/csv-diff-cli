#!/bin/sh
# Run the differ on the bundled examples.
# Run from the repo root: sh examples/run-example.sh
# The first diff exits 1 because the files differ on purpose —
# that is the expected result here.
set -e
cd "$(dirname "$0")/.."
echo "--- old.csv vs new.csv ---"
python3 src/csv_diff.py examples/old.csv examples/new.csv --key id || true
echo "--- same-a.csv vs same-b.csv ---"
python3 src/csv_diff.py examples/same-a.csv examples/same-b.csv --key id
