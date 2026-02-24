"""
Tools for interacting with AWS Deadline Cloud.
"""

from typing import Dict, Any, Optional, Tuple
from botocore.client import BaseClient
from deadline.client.config import config_file
from deadline.client.api import (
    get_boto3_client,
    create_job_from_job_bundle,
    wait_for_job_completion,
    get_session_logs,
    get_queue_user_boto3_session,
)
from deadline.job_attachments.download import OutputDownloader
from deadline.job_attachments.models import JobAttachmentS3Settings

from dataclasses import asdict

from strands import tool


def get_defaults() -> Tuple[str, str]:

    config = config_file.read_config()
    farm_id = config_file.get_setting("defaults.farm_id", config=config)
    queue_id = config_file.get_setting("defaults.queue_id", config=config)
    job_id = config_file.get_setting("defaults.job_id", config=config)

    return (farm_id, queue_id, job_id)


def get_deadline_client() -> BaseClient:
    return get_boto3_client("deadline", config=config_file.read_config())


@tool
def deadline_queue_get() -> Dict[str, Any]:
    """
    Get information about the current default Deadline Cloud queue.

    Returns:
        Dict[str, Any]: Queue information including name, ID, farm ID, and job attachments bucket
    """

    farm_id, queue_id, _ = get_defaults()
    response = get_deadline_client().get_queue(farmId=farm_id, queueId=queue_id)
    response.pop("ResponseMetadata", None)
    return response


@tool
def deadline_job_submit(bundle_path: str, parameters: Dict[str, str]) -> Dict[str, Any]:
    """
    Submit a job to Deadline Cloud.

    Args:
        bundle_path: Path to the job bundle directory
        parameters: Dictionary of parameters to pass to the job

    Returns:
        Dict[str, Any]: Job submission result including job ID
    """

    try:
        job_id = create_job_from_job_bundle(
            job_bundle_dir=bundle_path,
            job_parameters=parameters,
            config=config_file.read_config(),
            print_function_callback=print,
            submitter_name="DeadlineCondaAgent",
        )
    except Exception as e:
        print(e)
        return {"success": False, "error": str(e)}
    return {"job_id": job_id, "success": True}


@tool
def deadline_job_wait(job_id: str) -> Dict[str, Any]:
    """
    Block and wait for a job to complete.

    Args:
        job_id: The ID of the job to wait for

    Returns:
        Dict[str, Any]: Job completion result
    """

    farm_id, queue_id, _ = get_defaults()
    config = config_file.read_config()

    def status_callback(status, elapsed_time=0, total_timeout=0):
        # This is for the human, this context doesn't go back to the LLM
        timeout_str = ""
        if total_timeout > 0:
            remaining = max(0, total_timeout - elapsed_time)
            timeout_str = f" [{elapsed_time:.1f}s elapsed, {remaining:.1f}s remaining]"
        else:
            timeout_str = f" [{elapsed_time:.1f}s elapsed]"

        print(f"\rCurrent status: {status}.{timeout_str}", end="", flush=True)

    result = wait_for_job_completion(
        farm_id=farm_id,
        queue_id=queue_id,
        config=config,
        job_id=job_id,
        status_callback=status_callback,
    )
    return asdict(result)


@tool
def deadline_job_get_logs(
    session_id: str, limit: int = 100, next_token: str = None
) -> Dict[str, Any]:
    """
    Retrieve logs for a job session. Returns the most recent events.


    Args:
        session_id: The ID of the session to get logs for
        limit: Maximum number of log entries to return
        next_token: Pagination token from a previous call to this tool

    Returns:
        Dict[str, Any]: Job logs, including next_token if more log data exists
    """

    farm_id, queue_id, _ = get_defaults()
    config = config_file.read_config()
    result = get_session_logs(
        farm_id=farm_id,
        queue_id=queue_id,
        config=config,
        limit=limit,
        next_token=next_token,
        session_id=session_id,
    )
    return asdict(result)


@tool
def deadline_job_download_output(
    job_id: str, output_dir: Optional[str] = None
) -> Dict[str, Any]:
    """
    Download job output.

    Args:
        job_id: The ID of the job to download output for
        output_dir: Directory to download output to (optional)

    Returns:
        Dict[str, Any]: Download result
    """

    farm_id, queue_id, job_id = get_defaults()
    config = config_file.read_config()
    deadline = get_deadline_client()

    queue = deadline.get_queue(farmId=farm_id, queueId=queue_id)
    queue_role_session = get_queue_user_boto3_session(
        deadline=deadline,
        config=config,
        farm_id=farm_id,
        queue_id=queue_id,
        queue_display_name=queue["displayName"],
    )

    job_output_downloader = OutputDownloader(
        s3_settings=JobAttachmentS3Settings(**queue["jobAttachmentSettings"]),
        farm_id=farm_id,
        queue_id=queue_id,
        job_id=job_id,
        session=queue_role_session,
    )

    return asdict(job_output_downloader.download_job_output())
