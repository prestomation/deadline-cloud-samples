"""
Tools for the Deadline Cloud Agent.
"""

from deadline_cloud_agent.tools.deadline_tools import (
    deadline_queue_get,
    deadline_job_submit,
    deadline_job_wait,
    deadline_job_get_logs,
    deadline_job_download_output,
)

from deadline_cloud_agent.tools.conda_tools import (
    conda_verify,
    conda_package_submit,
    validate_deadline_conda_recipe,
)

from deadline_cloud_agent.tools.openjd_tools import openjd_validate

from deadline_cloud_agent.tools.archive_tools import (
    download_file,
    calculate_hash,
    extract_archive,
    inspect_archive,
    count_files,
)

from deadline_cloud_agent.tools.research_tools import (
    web_search,
    search_examples,
    deadline_cloud_documentation,
    conda_documentation,
    get_conda_recipe_sample,
    get_job_bundle_sample,
)

# Export all tools
__all__ = [
    # Deadline tools
    "deadline_queue_get",
    "deadline_job_submit",
    "deadline_job_wait",
    "deadline_job_get_logs",
    "deadline_job_download_output",
    "deadline_job_get",
    "deadline_job_get_sessions",
    # Conda tools
    "conda_verify",
    "conda_package_submit",
    # OpenJD tools
    "openjd_check",
    "openjd_render",
    "openjd_validate",
    # Archive tools
    "download_file",
    "calculate_hash",
    "extract_archive",
    "inspect_archive",
    "count_files",
    # Research tools
    "web_search",
    "search_examples",
    "deadline_cloud_documentation",
    "conda_documentation",
    "get_conda_recipe_sample",
    "get_job_bundle_sample",
    "validate_deadline_conda_recipe",
    # System tools
    "file_write",
    "file_copy",
    "editor",
]
