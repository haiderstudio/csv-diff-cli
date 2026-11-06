# Security Policy

This tool runs locally, collects no data, sends nothing anywhere, and needs no API key or secret. It only reads the two CSV files you name, and it never changes a file. It writes nothing except the diff report on standard output (and usage errors on standard error).

If you find a case where the tool changes a file, or reports a row or column that does not match the real difference, please open an issue describing the exact commands and input. Do not include any real secret in the report.
