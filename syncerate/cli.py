"""Command-line parser for the Syncerate executable."""

import argparse
from typing import Optional, Sequence

from . import VERSION


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Create and parse Syncerate command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Iterate though 2 lists of ZFS DataSets with Syncoid"
    )
    parser.add_argument(
        "--conf",
        "-c",
        type=str,
        required=True,
        help="The destination for the config file",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
    )
    return parser.parse_args(argv)
