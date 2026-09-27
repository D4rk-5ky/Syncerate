"""Command-line parser for the Syncerate executable."""

import argparse
from typing import Optional, Sequence

from . import VERSION


def parse_arguments(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Create and parse Syncerate command-line arguments."""

    parser = argparse.ArgumentParser(
        description=(
            "Replicate matching source/destination ZFS dataset pairs "
            "sequentially with Syncoid."
        ),
        epilog=(
            "Examples:\n"
            "  %(prog)s --conf /path/to/Syncerate.cfg\n"
            "  %(prog)s -c ./config/Syncerate.cfg\n"
            "  %(prog)s --version"
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--conf",
        "-c",
        metavar="FILE",
        type=str,
        required=True,
        help=(
            "Path to the required Syncerate INI configuration file. "
            "Relative paths are resolved from the current working directory."
        ),
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {VERSION}",
        help="Show the installed Syncerate version and exit.",
    )
    return parser.parse_args(argv)
