import json
from unittest.mock import MagicMock, Mock, patch

import pytest
import yaml


@patch("probely.cli.commands.targets.start_scan.start_scan")
def test_targets_start_scan__request_with_exception(
    sdk_start_scan_mock: Mock,
    probely_cli,
):
    exception_message = "An error occurred"

    sdk_start_scan_mock.side_effect = Exception(exception_message)

    stdout, stderr = probely_cli("targets", "start-scan", "random_target_id")
    sdk_start_scan_mock.assert_called_once()

    assert stdout == "", f"Expected no output, but got: {stdout}"
    assert stderr == f"probely targets start-scan: error: {exception_message}\n"


@pytest.mark.parametrize(
    "args, expected_error",
    [
        (
            [
                "targets",
                "start-scan",
                "target_id1 target_id2",
                "--f-has-unlimited-scans=True",
            ],
            "probely targets start-scan: error: filters and Target IDs are mutually exclusive.",
        ),
        (
            ["targets", "start-scan"],
            "probely targets start-scan: error: either filters or Target IDs must be provided.",
        ),
    ],
)
def test_targets_start_scan__validation(probely_cli, args, expected_error):
    """
    Validation for the start-scan command:
    - Filters and Target IDs are mutually exclusive.
    - Either filters or Target IDs must be provided.
    """
    stdout_lines, stderr_lines = probely_cli(*args, return_list=True)

    assert len(stdout_lines) == 0, f"Expected no output, but got: {stdout_lines}"
    assert len(stderr_lines) == 1, f"Expected error output, but got: {stderr_lines}"

    assert (
        stderr_lines[0] == expected_error
    ), f"Unexpected error message: {stderr_lines[0]}"


def test_targets_start_scan__error_when_target_ids_provided_in_yaml_file(
    create_testable_yaml_file, probely_cli
):
    """
    Test that an error is raised when target IDs are provided in the YAML file
    instead of through the CLI.

    NOTE: This is only for alpha version.
        Specifying Target IDs in the file will be supported in the future.
    """
    yaml_file_content = {
        "targets": [{"id": "target_id1"}, {"id": "target_id2"}],
    }
    yaml_file_path = create_testable_yaml_file(
        file_name="test_start_scans_yaml_file_argument.yaml",
        file_content=yaml_file_content,
    )

    stdout_lines, stderr_lines = probely_cli(
        "targets",
        "start-scan",
        "--f-has-unlimited-scans=True",
        "-f",
        yaml_file_path,
        return_list=True,
    )

    assert len(stdout_lines) == 0, f"Expected no output, but got: {stdout_lines}"
    assert len(stderr_lines) == 1, f"Expected error output, but got: {stderr_lines}"

    expected_error_message = (
        "probely targets start-scan: error: "
        + "Target IDs should be provided only through CLI, not in the YAML file."
    )
    assert (
        stderr_lines[0] == expected_error_message
    ), f"Unexpected error message: {stderr_lines[0]}"


@patch("probely.cli.commands.targets.start_scan.start_scan")
@patch("probely.cli.commands.targets.start_scan.start_scans")
def test_targets_start_scan__calls_correct_sdk_function(
    sdk_start_scans_mock: Mock,
    sdk_start_scan_mock: Mock,
    create_testable_yaml_file,
    probely_cli,
):
    """
    Ensure that correct SDK function is called based on the number of Target IDs provided.

    - If a single target ID is provided, `start_scan()` should be called.
    - If multiple target IDs are provided, `start_scans()` should be called.
    """
    yaml_file_content = {
        "overrides": {
            "ignore_blackout_period": True,
            "scan_profile": "lightning",
            "reduced_scopes": [{"url": "https//example.com", "enabled": True}],
        }
    }
    yaml_file_path = create_testable_yaml_file(
        file_name="test_start_scans_yaml_file_argument.yaml",
        file_content=yaml_file_content,
    )

    # Test Case 1: Single Target ID
    probely_cli("targets", "start-scan", "random_target_id", "-f", yaml_file_path)
    sdk_start_scan_mock.assert_called_once_with("random_target_id", yaml_file_content)
    sdk_start_scans_mock.assert_not_called()

    sdk_start_scan_mock.reset_mock()
    sdk_start_scans_mock.reset_mock()

    # Test Case 2: Multiple Target IDs
    probely_cli(
        "targets",
        "start-scan",
        "random_target_id1",
        "random_target_id2",
        "-f",
        yaml_file_path,
    )
    sdk_start_scans_mock.assert_called_once_with(
        ["random_target_id1", "random_target_id2"], yaml_file_content
    )
    sdk_start_scan_mock.assert_not_called()


@pytest.mark.parametrize(
    "filtered_targets",
    [
        ([{"id": "target_id1"}]),
        ([{"id": "target_id1"}, {"id": "target_id2"}]),
    ],
)
@patch("probely.cli.commands.targets.start_scan.start_scan")
@patch("probely.cli.commands.targets.start_scan.start_scans")
@patch("probely.cli.commands.targets.start_scan.list_targets")
def test_targets_start_scan__with_filters(
    list_targets_mock: Mock,
    start_scans_mock: Mock,
    start_scan_mock: Mock,
    create_testable_yaml_file,
    probely_cli,
    filtered_targets,
):
    list_targets_mock.return_value = iter(filtered_targets)

    _, stderr = probely_cli(
        "targets",
        "start-scan",
        "--f-has-unlimited-scans=True",  # random filter
        "--f-is-url-verified=False",  # random filter
        return_list=True,
    )

    assert stderr == [], "Expected no errors"

    list_targets_mock.assert_called_once_with(
        targets_filters={"unlimited": True, "verified": False}
    )

    target_ids = [target["id"] for target in filtered_targets]

    if len(target_ids) == 1:
        start_scan_mock.assert_called_once_with(target_ids[0], {})
    else:
        start_scans_mock.assert_called_once_with(target_ids, {})


@patch("probely.cli.commands.targets.start_scan.start_scan")
@patch("probely.cli.commands.targets.start_scan.start_scans")
@patch("probely.cli.commands.targets.start_scan.list_targets")
def test_targets_start_scan__filters_with_no_results(
    sdk_list_targets_mock: MagicMock,
    sdk_start_scans_mock: MagicMock,
    sdk_start_scan_mock: MagicMock,
    probely_cli,
):

    sdk_list_targets_mock.return_value = iter([])

    stdout_lines, stderr_lines = probely_cli(
        "targets",
        "start-scan",
        "--f-search=test",
        return_list=True,
    )

    assert stdout_lines == [], "Expected no output"
    assert len(stderr_lines) == 1, "Expected error output"

    expected_error = (
        "probely targets start-scan: error: Selected Filters returned no results"
    )
    assert stderr_lines[-1] == expected_error

    sdk_start_scans_mock.assert_not_called()
    sdk_start_scan_mock.assert_not_called()


@patch("probely.cli.commands.targets.start_scan.start_scan")
def test_targets_start_scan__output_format(
    start_scan_mock: Mock, probely_cli, valid_scans_start_api_response
):
    """
    Test the output format of the target start-scan command.
    """
    target_id = "scanned_target_id"
    target_name = "scanned_target_name"

    start_scan_response = valid_scans_start_api_response.copy()
    start_scan_response["target"]["id"] = target_id
    start_scan_response["target"]["name"] = target_name

    start_scan_mock.return_value = start_scan_response

    # Case 1: JSON output
    stdout, stderr = probely_cli(
        "targets",
        "start-scan",
        target_id,
        "--output json",
    )
    assert stderr == ""
    json_content = json.loads(stdout)
    assert isinstance(json_content, list), "Expected a json list"
    assert len(json_content) == 1  # Only one target which was scanned
    assert json_content[0]["target"]["id"] == target_id
    assert json_content[0]["target"]["name"] == target_name

    # Case 2: YAML output
    stdout, stderr = probely_cli(
        "targets",
        "start-scan",
        target_id,
        "-o yaml",
    )
    assert stderr == ""
    yaml_content = yaml.load(stdout, Loader=yaml.FullLoader)
    assert yaml_content[0]["target"]["id"] == target_id
    assert yaml_content[0]["target"]["name"] == target_name

    # Case 3 - No output format specified, only Scan IDs should be printed
    scan_id = start_scan_response["id"]
    stdout, stderr = probely_cli(
        "targets",
        "start-scan",
        target_id,
    )
    assert stdout == f"{scan_id}\n", stdout


@patch("probely.cli.commands.targets.start_scan.time.sleep")
@patch("probely.cli.commands.targets.start_scan.retrieve_scans")
@patch("probely.cli.commands.targets.start_scan.start_scan")
def test_targets_start_scan__wait_with_progress_updates(
    start_scan_mock: Mock,
    retrieve_scans_mock: Mock,
    sleep_mock: Mock,
    probely_cli,
):
    scan_id = "scan_id"
    target_id = "target_id"
    target_name = "Example Site"

    in_progress_scan = {
        "id": scan_id,
        "status": "started",
        "crawler": {"full_status": {"data": {"done": 1, "total": 4}}},
        "scanner": {"full_status": {"data": {"done": 2, "total": 5}}},
    }
    completed_scan = {
        "id": scan_id,
        "status": "completed",
        "started": "2024-07-01T12:00:00Z",
        "completed": "2024-07-01T12:45:30Z",
        "criticals": 1,
        "highs": 2,
        "mediums": 3,
        "lows": 4,
        "crawler": {
            "full_status": {"data": {"done": 15, "total": 15}},
            "warning": [{"code": "C1", "message": "Crawler warning"}],
            "error": ["Crawler error"],
        },
        "scanner": {
            "full_status": {"data": {"done": 10, "total": 10}},
            "warning": [{"code": "S1", "message": "Scanner warning"}],
            "error": ["Scanner error"],
        },
        "target": {"site": {"name": target_name}},
    }

    start_scan_mock.return_value = in_progress_scan
    retrieve_scans_mock.side_effect = [[in_progress_scan], [completed_scan]]

    stdout, stderr = probely_cli(
        "targets",
        "start-scan",
        target_id,
        "--wait",
        "5",
    )

    assert stderr == ""

    expected_lines = [
        "Scan scan_id: status=started, crawler: 25%, scanner: 40%",
        "Scan scan_id: status=completed, crawler: 100%, scanner: 100%",
        "Target Example Site scan scan_id Complete!",
        " - Scan Duration: 0d 0h 45m 30s (output in days / hours / minutes / seconds)",
        " - Findings:",
        "     - Criticals: 1",
        "     - Highs:     2",
        "     - Mediu:    3",
        "     - Lows:      4",
        "Crawler:",
        "  - Warnings",
        "    - C1    Crawler warning",
        "  - Errors",
        "    - Crawler error",
        "Scanner:",
        "  - Warnings",
        "    - S1    Scanner warning",
        "  - Errors",
        "    - Scanner error",
        scan_id,
    ]
    assert stdout.splitlines() == expected_lines

    start_scan_mock.assert_called_once_with(target_id, {})
    assert retrieve_scans_mock.call_count == 2
    sleep_mock.assert_called_once_with(5)


@patch("probely.cli.commands.targets.start_scan.time.sleep")
@patch("probely.cli.commands.targets.start_scan.retrieve_scans")
@patch("probely.cli.commands.targets.start_scan.start_scan")
def test_targets_start_scan__wait_without_progress_updates(
    start_scan_mock: Mock,
    retrieve_scans_mock: Mock,
    sleep_mock: Mock,
    probely_cli,
):
    scan_id = "scan_id"
    target_id = "target_id"
    target_name = "Another Site"

    queued_scan = {
        "id": scan_id,
        "status": "queued",
        "crawler": {"full_status": {"data": {"done": 0, "total": 1}}},
        "scanner": {"full_status": {"data": {"done": 0, "total": 1}}},
    }
    completed_scan = {
        "id": scan_id,
        "status": "completed",
        "started": "2024-07-01T10:00:00Z",
        "completed": "2024-07-01T10:05:00Z",
        "criticals": 0,
        "highs": 0,
        "mediums": 1,
        "lows": 2,
        "crawler": {"full_status": {"data": {"done": 10, "total": 10}}},
        "scanner": {"full_status": {"data": {"done": 7, "total": 7}}},
        "target": {"site": {"name": target_name}},
    }

    start_scan_mock.return_value = queued_scan
    retrieve_scans_mock.side_effect = [[queued_scan], [completed_scan]]

    stdout, stderr = probely_cli(
        "targets",
        "start-scan",
        target_id,
        "--wait",
        "0",
    )

    assert stderr == ""
    expected_lines = [
        "Target Another Site scan scan_id Complete!",
        " - Scan Duration: 0d 0h 5m 0s (output in days / hours / minutes / seconds)",
        " - Findings:",
        "     - Criticals: 0",
        "     - Highs:     0",
        "     - Mediu:    1",
        "     - Lows:      2",
        scan_id,
    ]
    assert stdout.splitlines() == expected_lines

    start_scan_mock.assert_called_once_with(target_id, {})
    assert retrieve_scans_mock.call_count == 2
    sleep_mock.assert_called_once_with(60)


@patch("probely.cli.commands.targets.start_scan.time.sleep")
@patch("probely.cli.commands.targets.start_scan.retrieve_scans")
@patch("probely.cli.commands.targets.start_scan.start_scan")
def test_targets_start_scan__wait_failure_summary(
    start_scan_mock: Mock,
    retrieve_scans_mock: Mock,
    sleep_mock: Mock,
    probely_cli,
):
    scan_id = "failed_scan_id"
    target_id = "target_id"

    initial_scan = {
        "id": scan_id,
        "status": "started",
        "crawler": {"full_status": {"data": {"done": 0, "total": 1}}},
        "scanner": {"full_status": {"data": {"done": 0, "total": 1}}},
    }
    failed_scan = {
        "id": scan_id,
        "status": "failed",
        "crawler": {
            "full_status": {"data": {"done": 1, "total": 1}},
            "warning": [{"code": "CW", "message": "Crawler warning"}],
        },
        "scanner": {
            "full_status": {"data": {"done": 1, "total": 1}},
            "error": ["Scanner failure"],
        },
        "target": {"site": {"name": "Failing Site"}},
    }

    start_scan_mock.return_value = initial_scan
    retrieve_scans_mock.side_effect = [[initial_scan], [failed_scan]]

    stdout, stderr = probely_cli(
        "targets",
        "start-scan",
        target_id,
        "--wait",
        "3",
    )

    assert stderr == ""

    expected_lines = [
        "Scan failed_scan_id: status=started, crawler: 0%, scanner: 0%",
        "Scan failed_scan_id: status=failed, crawler: 100%, scanner: 100%",
        "Target Failing Site scan failed_scan_id failed",
        "Crawler:",
        "  - Warnings",
        "    - CW    Crawler warning",
        "Scanner:",
        "  - Errors",
        "    - Scanner failure",
        "failed_scan_id",
    ]
    assert stdout.splitlines() == expected_lines

    start_scan_mock.assert_called_once_with(target_id, {})
    assert retrieve_scans_mock.call_count == 2
    sleep_mock.assert_called_once_with(3)
