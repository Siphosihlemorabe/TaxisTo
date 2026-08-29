"""Entry point for `python -m pipeline`.

The CLI itself lives in `pipeline/cli.py`, which uses relative imports and so
cannot be executed as a loose script. Going through `-m` (or importing
`pipeline.cli.main`) is the supported way in.
"""

import sys

from .cli import main

if __name__ == "__main__":
    sys.exit(main())
