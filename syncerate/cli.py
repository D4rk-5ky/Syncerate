"""Command-line parser for the Syncerate executable."""

import argparse
from typing import Optional, Sequence

from . import VERSION


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Create and parse Syncerate command-line arguments."""

    parser = argparse.ArgumentParser(
        description="Replicate matching source/destination ZFS dataset lists with Syncoid"
    )
    parser.add_argument(
        "--conf",
        "-c",
        type=str,
        required=True,
        help="Path to the INI configuration file (required for a backup run)",
    )
    parser.add_argument(
        "--version",
        action="version",
        help="Show the application version and exit without running a backup",
        version=f"%(prog)s {VERSION}",
    )
    return parser.parse_args(argv)
