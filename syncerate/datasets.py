"""Dataset-list parsing, validation, and pairing."""

import logging
import shlex

from .errors import EXIT_LIST_ERROR, SyncerateError
from .models import AppConfig, DatasetPair


def missmatchinglists(
    Lenght: bool,
    Names: bool,
    logger: logging.Logger,
) -> None:
    """Log source/destination list validation failure and raise exit code 1."""

    if Lenght is True:
        logger.error("")
        logger.error("----------")
        logger.error("")
        logger.error("The number of items in each list does not match")
        logger.error("Check the terminal or .err log")
        logger.error("exiting - error code 1")

    if Names is True:
        logger.error("")
        logger.error("----------")
        logger.error("")
        logger.error("There are datasets on source and destination which ends doesnt match up")
        logger.error("Check the terminal or .err log")
        logger.error("exiting - error code 1")

    raise SyncerateError(
        "Source and destination list validation failed",
        EXIT_LIST_ERROR,
        kind="list",
    )

def read_dataset_list(path: str) -> list[str]:
    """Read active dataset-list lines, ignoring blanks and comments."""

    with open(path, "r", encoding="utf-8") as dataset_file:
        return [
            line.strip()
            for line in dataset_file
            if line.strip() and not line.strip().startswith("#")
        ]

def parse_destination_line(line: str) -> tuple[str, list[str]]:
    """Parse one destination and its optional per-destination arguments."""

    if ": " not in line:
        return line, []

    destination_dataset, extra_args_text = line.rsplit(": ", 1)
    destination_dataset = destination_dataset.strip()
    extra_args_text = extra_args_text.strip()

    if not extra_args_text:
        return destination_dataset, []

    try:
        extra_args = shlex.split(extra_args_text)
    except ValueError as exc:
        raise ValueError(
            "Could not parse extra arguments for destination line:\n"
            f"{line}\n"
            f"shlex error: {exc}"
        ) from exc

    return destination_dataset, extra_args

def parse_destination_list(
    destination_lines: list[str],
) -> tuple[list[str], list[list[str]]]:
    """Return destination datasets and matching per-destination argument lists."""

    destination_datasets: list[str] = []
    destination_extra_arguments: list[list[str]] = []

    for line in destination_lines:
        destination_dataset, extra_arguments = parse_destination_line(line)
        destination_datasets.append(destination_dataset)
        destination_extra_arguments.append(extra_arguments)

    return destination_datasets, destination_extra_arguments

def load_dataset_pairs(
    app_config: AppConfig,
    logger: logging.Logger,
) -> list[DatasetPair]:
    """Load, log, validate, and combine both dataset files."""

    source_lines = read_dataset_list(app_config.source_list_path)

    logger.info("Items in the Source list    :   %s", source_lines)
    logger.info("Number of items in the Source list    :   %i", len(source_lines))
    logger.info("")

    destination_lines_raw = read_dataset_list(app_config.destination_list_path)

    try:
        destination_lines, destination_extra_arguments = parse_destination_list(
            destination_lines_raw
        )
    except ValueError as exc:
        logger.error("%s", exc)
        raise SyncerateError(
            str(exc),
            EXIT_LIST_ERROR,
            kind="list",
        ) from exc

    logger.info("Raw items in the Destination list    :   %s", destination_lines_raw)
    logger.info("Parsed Destination datasets          :   %s", destination_lines)
    logger.info(
        "Parsed Destination extra args        :   %s",
        destination_extra_arguments,
    )
    logger.info(
        "Number of items in the Destination list    :   %i",
        len(destination_lines),
    )
    logger.info("")

    if len(source_lines) == len(destination_lines):
        logger.info("The Source and Dest files has the same number of items")
        logger.info("")
    else:
        missmatchinglists(Lenght=True, Names=False, logger=logger)

    lists_check_out = True
    for source, destination in zip(source_lines, destination_lines):
        if source.rpartition("/")[-1] == destination.rpartition("/")[-1]:
            logger.info("The end of this Source and Destination Datasets matches:")
            logger.info("Source :   %s", source)
            logger.info("Dest   :   %s", destination)
            logger.info("")
        else:
            logger.error(
                "The end of this Source and Destination Datasets end does not match:"
            )
            logger.error("Source :   %s", source)
            logger.error("Dest   :   %s", destination)
            logger.error("")
            lists_check_out = False

    if lists_check_out:
        logger.info("All datasets ends matches")
        logger.info("continuing")
    else:
        missmatchinglists(Lenght=False, Names=True, logger=logger)

    return [
        DatasetPair(
            source=source,
            destination=destination,
            extra_arguments=tuple(extra_arguments),
        )
        for source, destination, extra_arguments in zip(
            source_lines,
            destination_lines,
            destination_extra_arguments,
        )
    ]
