"""Allow `python -m squirrel ...`."""
import sys

from .cli import main

sys.exit(main())
