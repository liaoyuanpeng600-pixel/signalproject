# Signal Project v0.1.0

## Overview

This is the first alpha release of Signal Project. It establishes the
foundational framework for the SIGNAL Research Operating System.

## Implemented

- Infrastructure specification
- Persistence layer
- Runtime scheduling
- Research synthesis pipeline
- Report specification
- Report builders and JSON exporter
- Python 3.10–3.13 compatibility
- CI validation
- Package distribution support

## Validation

- Python matrix:
  - Python 3.10
  - Python 3.11
  - Python 3.12
  - Python 3.13
- Tests: 864 passed
- Package:
  - Wheel build
  - Source distribution build
  - Twine check
  - Clean-environment wheel installation

## Known limitations

- Alpha-stage software
- No command-line interface
- No production database
- No external data connectors
- No user interface
- Persistence remains in memory
- API stability is not guaranteed

## Upgrade / Compatibility notes

- Requires Python `>=3.10,<3.14`.
- The current public package namespace is `src`.
