import logging
import math
import time
from datetime import datetime
from typing import List, Optional

from probely.cli.commands.targets.schemas import TargetApiFiltersSchema
from probely.cli.common import (
    display_scans_response_output,
    prepare_filters_for_api,
    validate_and_retrieve_yaml_content,
)
from probely.exceptions import ProbelyCLIValidation
from probely.sdk.enums import ScanStatusEnum
from probely.sdk.scans import retrieve_scans, start_scan, start_scans
from probely.sdk.targets import list_targets

logger = logging.getLogger(__name__)


TERMINAL_SCAN_STATUSES = {
    ScanStatusEnum.CANCELED.api_response_value,
    ScanStatusEnum.COMPLETED.api_response_value,
    ScanStatusEnum.FAILED.api_response_value,
    ScanStatusEnum.PAUSED.api_response_value,
}


def _calculate_stage_progress(stage: dict) -> Optional[int]:
    """Return progress percentage rounded down, clamped to [0, 100]."""

    if not stage:
        return None

    data = stage.get("full_status", {}).get("data", {})

    try:
        done = float(data.get("done"))
        total = float(data.get("total"))
    except (TypeError, ValueError):
        return None

    if total <= 0:
        return None

    percentage = math.floor((done / total) * 100)
    if percentage < 0:
        return 0
    if percentage > 100:
        return 100

    return int(percentage)


def _format_progress(stage: dict) -> str:
    progress = _calculate_stage_progress(stage)
    if progress is None:
        return "N/A"
    return f"{progress}%"


def _wait_for_scans_completion(
    args, scan_ids: List[str], update_interval: int
) -> List[dict]:
    if not scan_ids:
        return []

    poll_interval = 60 if update_interval == 0 else update_interval

    while True:
        scans = retrieve_scans(scan_ids)

        if update_interval > 0:
            for scan in scans:
                status = scan.get("status")
                args.console.print(
                    "Scan {scan_id}: status={status}, crawler: {crawler_progress}, "
                    "scanner: {scanner_progress}".format(
                        scan_id=scan.get("id"),
                        status=status,
                        crawler_progress=_format_progress(scan.get("crawler")),
                        scanner_progress=_format_progress(scan.get("scanner")),
                    )
                )

        if all(scan.get("status") in TERMINAL_SCAN_STATUSES for scan in scans):
            return scans

        time.sleep(poll_interval)


def _parse_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None

    try:
        if value.endswith("Z"):
            value = value.replace("Z", "+00:00")
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _format_duration(started: Optional[str], completed: Optional[str]) -> str:
    start_dt = _parse_datetime(started)
    end_dt = _parse_datetime(completed)

    if not start_dt or not end_dt or end_dt < start_dt:
        return "N/A"

    delta_seconds = int((end_dt - start_dt).total_seconds())

    days, remainder = divmod(delta_seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, seconds = divmod(remainder, 60)

    return f"{days} days {hours} hours {minutes} minutes {seconds} seconds"


def _get_target_site_name(scan: dict) -> str:
    target = scan.get("target", {})
    site = target.get("site", {})

    name = site.get("name") or target.get("name")
    if name:
        return name

    return "Unknown"


def _print_stage_details(args, stage_name: str, stage: Optional[dict]):
    if not stage:
        return

    warnings = stage.get("warning") or []
    errors = stage.get("error") or []

    if not warnings and not errors:
        return

    args.console.print(f"{stage_name}:")

    if warnings:
        args.console.print("  - Warnings")
        for warning in warnings:
            if isinstance(warning, dict):
                code = warning.get("code", "N/A")
                message = warning.get("message", "")
                args.console.print(f"    - {code}    {message}")
            else:
                args.console.print(f"    - {warning}")

    if errors:
        args.console.print("  - Errors")
        for error in errors:
            args.console.print(f"    - {error}")


def _print_scan_summary(args, scan: dict):
    scan_id = scan.get("id", "Unknown")
    status = scan.get("status", "unknown")
    target_name = _get_target_site_name(scan)

    if status in {
        ScanStatusEnum.FAILED.api_response_value,
        ScanStatusEnum.CANCELED.api_response_value,
    }:
        args.console.print(f"Target {target_name} scan id: {scan_id} {status}")
    elif status == ScanStatusEnum.COMPLETED.api_response_value:
        duration = _format_duration(scan.get("started"), scan.get("completed"))
        args.console.print(f"Target {target_name} scan {scan_id} Complete!")
        args.console.print(
            " - Scan Duration: {duration}".format(
                duration=duration
            )
        )
        args.console.print(" - Findings:")
        args.console.print(
            "     - Criticals: {criticals}".format(criticals=scan.get("criticals", 0))
        )
        args.console.print(
            "     - Highs:     {highs}".format(highs=scan.get("highs", 0))
        )
        args.console.print(
            "     - Mediums:   {mediums}".format(mediums=scan.get("mediums", 0))
        )
        args.console.print(
            "     - Lows:      {lows}".format(lows=scan.get("lows", 0))
        )
    else:
        args.console.print(f"Target {target_name} scan {scan_id} {status}")

    _print_stage_details(args, "Crawler", scan.get("crawler"))
    _print_stage_details(args, "Scanner", scan.get("scanner"))


def validate_and_retrieve_extra_payload(args):
    extra_payload = validate_and_retrieve_yaml_content(args.yaml_file_path)

    if "targets" in extra_payload:
        #  NOTE: This is only for alpha version, specifying Target IDs in the file will be supported in the future
        raise ProbelyCLIValidation(
            "Target IDs should be provided only through CLI, not in the YAML file."
        )

    return extra_payload


def start_scans_command_handler(args):
    filters = prepare_filters_for_api(TargetApiFiltersSchema, args)
    targets_ids = args.target_ids

    if not filters and not targets_ids:
        raise ProbelyCLIValidation("either filters or Target IDs must be provided.")

    if filters and targets_ids:
        raise ProbelyCLIValidation("filters and Target IDs are mutually exclusive.")

    extra_payload = validate_and_retrieve_extra_payload(args)

    if filters:
        generator = list_targets(targets_filters=filters)
        first_target = next(generator, None)

        if not first_target:
            raise ProbelyCLIValidation("Selected Filters returned no results")

        targets_ids = [first_target["id"]] + [target["id"] for target in generator]

    if len(targets_ids) == 1:
        scans = [start_scan(targets_ids[0], extra_payload)]
    else:
        scans = start_scans(targets_ids, extra_payload)

    if args.wait is None:
        display_scans_response_output(args, scans)
        return

    final_scans = _wait_for_scans_completion(
        args, [scan.get("id") for scan in scans if scan.get("id")], args.wait
    )
    for scan in final_scans:
        _print_scan_summary(args, scan)
    if args.wait is not None:
        return
    display_scans_response_output(args, final_scans)
