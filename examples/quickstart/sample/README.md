# greet

A tiny command-line greeter. It is the sample project of the ADLC quickstart.

- **Name:** greet
- **What it does:** `greet.sh` prints a greeting to standard output.
- **Stack:** POSIX `sh` only. No package manager, no dependencies and no build step.
- **Scope:** printing a greeting from the command line. Packaging and installing it are out of scope.
- **Layout:** one script, `greet.sh`, and its test script, `tests/greet.test.sh`. There are no layers or services.

## Usage

`sh greet.sh` prints `Hello, world`.

## Tests

`sh tests/greet.test.sh` runs every check, prints `ok` or `not ok` for each one, and exits non-zero when any check fails.
