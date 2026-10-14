#!/usr/bin/env python3
"""Command line entry for project knowledge and team workflow (`tw`)."""
from pathlib import Path
import sys

sys.dont_write_bytecode = True  # read-only sandboxes and installed skills stay free of __pycache__
sys.path.insert(0, str(Path(__file__).resolve().parent))

from tw_runtime.cli import main  # noqa: E402

if __name__ == '__main__':
    sys.exit(main())
