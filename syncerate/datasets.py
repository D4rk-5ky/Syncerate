"""Dataset-list parsing, validation, and pairing."""

import logging
import shlex

from .errors import EXIT_LIST_ERROR, SyncerateError
from .models import AppConfig, DatasetPair, DatasetComparison, DatasetValidationReport


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

    # The documented syntax is "destination: extra arguments". Split only at
    # the first delimiter so quoted argument values may themselves contain
    # colon-space text without corrupting the destination field.
    destination_dataset, extra_args_text = line.split(": ", 1)
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


def compare_dataset_names(
    sources: list[str], destinations: list[str]
) -> DatasetValidationReport:
    """Compare all ordered pairs, including final lines and any surplus lines.

    Only the final dataset component must match; source/target prefixes may
    differ. Invalid empty values/trailing slashes cannot match one another.
    """

    report = DatasetValidationReport(
        source_count=len(sources), destination_count=len(destinations)
    )
    for index in range(max(len(sources), len(destinations))):
        source = sources[index] if index < len(sources) else None
        destination = destinations[index] if index < len(destinations) else None
        if source is None:
            reason = "Missing source list entry"
        elif destination is None:
            reason = "Missing destination list entry"
        elif not source or not destination:
            reason = "Empty dataset name"
        elif source.endswith("/") or destination.endswith("/"):
            reason = "Dataset names must not end with '/'"
        elif source.rpartition("/")[-1] != destination.rpartition("/")[-1]:
            reason = (
                "Final dataset names differ: "
                f"{source.rpartition('/')[-1]!r} != {destination.rpartition('/')[-1]!r}"
            )
        else:
            reason = ""
        comparison = DatasetComparison(index + 1, source, destination, reason)
        (report.mismatches if reason else report.matches).append(comparison)
    return report


def format_dataset_validation_report(report: DatasetValidationReport) -> str:
    """Return complete mismatches-first audit for mail, terminal and log output."""

    lines = [
        "Source/destination dataset validation FAILED - no transfer started",
        f"Source entries      :   {report.source_count}",
        f"Destination entries :   {report.destination_count}",
        f"Mismatching pairs   :   {len(report.mismatches)}",
        f"Matching pairs      :   {len(report.matches)}",
        "",
        "MISMATCHING DATASET PAIRS:",
    ]
    if not report.mismatches:
        lines.append("  None")
    for comparison in report.mismatches:
        lines.extend([
            f"  Line {comparison.line_number}:",
            f"    Source      :   {comparison.source if comparison.source is not None else '(missing)'}",
            f"    Destination :   {comparison.destination if comparison.destination is not None else '(missing)'}",
            f"    Reason      :   {comparison.reason}",
            "",
        ])
    lines.extend(["MATCHING DATASET PAIRS:"])
    if not report.matches:
        lines.append("  None")
    for comparison in report.matches:
        lines.extend([
            f"  Line {comparison.line_number}:",
            f"    Source      :   {comparison.source}",
            f"    Destination :   {comparison.destination}",
            "",
        ])
    return "\n".join(lines).rstrip()


def load_dataset_pairs(
    app_config: AppConfig,
    logger: logging.Logger,
) -> list[DatasetPair]:
    """Audit all dataset-list entries before returning executable pairs.

    Preflight failures carry the complete report to top-level failure mail,
    MQTT and final console output; no Syncoid process is started.
    """

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
        raise SyncerateError(str(exc), EXIT_LIST_ERROR, kind="list") from exc

    logger.info("Raw items in the Destination list    :   %s", destination_lines_raw)
    logger.info("Parsed Destination datasets          :   %s", destination_lines)
    logger.info("Parsed Destination extra args        :   %s", destination_extra_arguments)
    logger.info("Number of items in the Destination list    :   %i", len(destination_lines))
    logger.info("")

    report = compare_dataset_names(source_lines, destination_lines)
    if not source_lines or not destination_lines:
        error_message = "Source and destination lists must each contain at least one active dataset"
    elif len(source_lines) != len(destination_lines):
        error_message = "Source and destination dataset lists have different numbers of entries"
    elif report.mismatches:
        error_message = "Source/destination final dataset names do not match"
    else:
        logger.info("All %s source/destination final dataset names match", len(report.matches))
        logger.info("continuing")
        return [
            DatasetPair(source=source, destination=destination,
                        extra_arguments=tuple(extra_arguments))
            for source, destination, extra_arguments in zip(
                source_lines, destination_lines, destination_extra_arguments
            )
        ]

    logger.error("Dataset validation failed: %s", error_message)
    # Record the complete comparison before notifications snapshot/attach the
    # .log and .err files. app.main() repeats it at the terminal's very end.
    for report_line in format_dataset_validation_report(report).splitlines():
        logger.error("%s", report_line)
    raise SyncerateError(
        error_message, EXIT_LIST_ERROR, kind="list",
        dataset_validation_report=report,
    )
