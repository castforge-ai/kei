"""python -m kei: the same as the kei command, for a machine where the install put the command off PATH."""
import sys

from kei.cli import main

if __name__ == "__main__":
    sys.exit(main())
