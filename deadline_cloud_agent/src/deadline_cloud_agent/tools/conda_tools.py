"""
Tools for interacting with conda packages and recipes.
"""

from pathlib import Path
import os
from botocore.client import BaseClient
import subprocess
from typing import Dict, Any
import yaml
from deadline.client.api import get_boto3_client
from deadline.client.config import config_file
from deadline_cloud_agent.tools.deadline_conda_verify import validate_conda_recipe
from deadline.client.api import get_queue_user_boto3_session
import re
from packaging import version

import json

from strands import tool


def get_deadline_client() -> BaseClient:
    return get_boto3_client("deadline", config=config_file.read_config())


def parse_package_requirement(requirement):
    # Parse requirements like "package>=1.0" or "package=1.0" or just "package"
    match = re.match(r"([^><=]+)((?:[><=]=?).+)?", requirement)
    if not match:
        return None, None, None

    package_name = match.group(1)
    version_constraint = match.group(2) if match.group(2) else None

    operator = None
    version_required = None

    if version_constraint:
        if version_constraint.startswith(">="):
            operator = ">="
            version_required = version_constraint[2:]
        elif version_constraint.startswith("<="):
            operator = "<="
            version_required = version_constraint[2:]
        elif version_constraint.startswith("="):
            operator = "="
            version_required = version_constraint[1:]

    return package_name, operator, version_required


def check_version_constraint(version_str, operator, required_version):
    if not operator:
        return True

    v1 = version.parse(version_str)
    v2 = version.parse(required_version)

    if operator == ">=":
        return v1 >= v2
    elif operator == "<=":
        return v1 <= v2
    elif operator == "=":
        return v1 == v2
    return False


def validate_packages(requirements, repodata):
    results = []
    success = True
    packages_data = {
        **repodata.get("packages", {}),
        **repodata.get("packages.conda", {}),
    }

    for req in requirements:
        package_name, operator, version_required = parse_package_requirement(req)
        if not package_name:
            results.append((req, False, "Invalid package specification"))
            continue

        # Find all available versions of the package
        available_versions = []
        for pkg_filename, pkg_info in packages_data.items():
            if pkg_info["name"] == package_name:
                if check_version_constraint(
                    pkg_info["version"], operator, version_required
                ):
                    available_versions.append(pkg_info["version"])

        if available_versions:
            results.append(
                (req, True, f"Available versions: {', '.join(available_versions)}")
            )
        else:
            # TODO: can we somehow guess if the package is available on conda-forge or deadline cloud?
            results.append(
                (
                    req,
                    False,
                    "No matching versions found in the queue's conda channel. Is this package from CondaForge, DeadlineCloud or another channel?",
                )
            )

    return {"results": results, "success": success}


def get_repo_data():

    config = config_file.read_config()
    farm_id = config_file.get_setting("defaults.farm_id", config=config)
    queue_id = config_file.get_setting("defaults.queue_id", config=config)

    response = get_deadline_client().get_queue(farmId=farm_id, queueId=queue_id)
    bucket_name = response["jobAttachmentSettings"]["s3BucketName"]

    # This is an assumption. how we can figure this out?
    conda_prefix = "Conda"

    deadline_client = get_deadline_client()
    queue_session = get_queue_user_boto3_session(
        deadline_client, None, farm_id, queue_id
    )

    s3_client = queue_session.client("s3")
    repo_data = json.load(
        s3_client.get_object(
            # TODO: Linux-only
            Bucket=bucket_name,
            Key=f"{conda_prefix}/Default/linux-64/repodata.json",
        )["Body"]
    )
    return repo_data


@tool
def get_conda_packages():
    """
    Return the list of available conda packages, their version number, and the timestamp they were published.
    """

    repo_data = get_repo_data()
    packages = {
        details["name"]: {
            "build_number": details["build_number"],
            "version": details["version"],
            "timestamp": details["timestamp"],
        }
        for package, details in repo_data["packages.conda"].items()
    }

    return {"packages": packages}


@tool
def validate_deadline_conda_recipe(
    recipe_dir: str,
) -> Any:
    """Given a Deadline Cloud conda recipe, validate the conda build recipe directory with some basic sanity checks.

    A Deadline Cloud conda recipe has the following form:

    {software_name}-{major.minor}/
    ├── deadline-cloud.yaml
    ├── README.md           # optional
    └── recipe/
        ├── meta.yaml       # For conda-build build tool
        └── build.sh        # For Linux Builds
        └── bld.bat         # For Windows Builds


    deadline-cloud.yaml has the following form:
    ```yaml
    condaPlatforms:
      - platform: linux-64
        defaultSubmit: true # whether to build this platform by default when no platforms are specified as script arguments
        sourceArchiveFilename:
        - Autodesk_Maya_2025_Linux_64bit.tgz # This file should be in the archive_files/ directory
        sourceDownloadInstructions: 'Download the Autodesk_Maya_2025_Linux_64bit.tgz full download file from Autodesk.'
        buildTool: conda-build
    jobParameters:
      - name: CondaChannels  # Any conda channels needed to install dependencies specified in the recipe.yaml
        value: conda-forge
    ```
    """
    try:
        recipe_dir = Path(recipe_dir)
        if not recipe_dir.is_dir():
            raise RuntimeError(f"The recipe directory does not exist: {recipe_dir}.")

        meta_yaml_file = recipe_dir / "recipe" / "meta.yaml"
        recipe_yaml_file = recipe_dir / "recipe" / "recipe.yaml"
        if not meta_yaml_file.is_file() and not recipe_yaml_file.is_file():
            raise RuntimeError(f"No meta.yaml or recipe.yaml exists in {recipe_dir}.")

        submit_yaml_file = recipe_dir / "deadline-cloud.yaml"
        if not submit_yaml_file.is_file():
            raise RuntimeError(
                f"The submit metadata file does not exist: {submit_yaml_file}."
            )

        submit_meta = yaml.safe_load((submit_yaml_file).read_text())

        default_build_tool = submit_meta.pop("buildTool", "conda-build")

        if default_build_tool not in ["conda-build"]:
            raise RuntimeError(
                f"Recipe provided an unsupported build tool {default_build_tool}"
            )

        submit_meta.pop("jobParameters")
    except Exception as e:
        print(e)
        raise

    return "Valid"


@tool
def conda_verify(recipe_path: str) -> Dict[str, Any]:
    """Validate a Deadline Cloud conda recipe directory
    Args:
        recipe_path: Path to the conda recipe directory that itself contains a recipe/ directory and deadline-cloud.yaml

    Returns:
        Dict[str, Any]: Validation result
    """

    try:
        print(recipe_path)
        output = validate_conda_recipe(recipe_path, False)
        print(output)
        return output
    except Exception as e:
        print(e)
        raise


@tool
def conda_package_submit(recipe_path: str, queue_name: str) -> Dict[str, Any]:
    """
    Submit a conda package build job.

    Args:
        recipe_path: Path to the conda recipe directory
        queue_name: Name of the queue to submit the job to

    Returns:
        Dict[str, Any]: Job submission result
    """
    try:
        # The submit-package-job-script.py is expected to be in the conda_recipes directory
        # script_path = os.path.join(
        #     os.path.dirname(recipe_path), "..", "submit-package-job-script.py"
        # )
        script_path = os.path.join("conda_recipes", "submit-package-job-script.py")

        if not os.path.exists(script_path):
            print(f"{script_path} not found")
            return {"success": False, "error": f"Script not found: {script_path}"}
        # TODO: This should be one python library, the submit package job script should be factored
        # into its parts that can be used here, and keep the CLI for existing human-powered workflow
        result = subprocess.run(
            ["python", script_path, recipe_path, "--queue", queue_name],
            capture_output=True,
            text=True,
        )
        print(result)

        # Parse the output to extract the job ID
        if result.returncode == 0:
            # Look for a job ID in the output
            import re

            job_id_match = re.search(r"job-id: ([a-zA-Z0-9-]+)", result.stdout)
            if job_id_match:
                job_id = job_id_match.group(1)
                print(job_id)
                return {"success": True, "job_id": job_id, "message": result.stdout}
            else:
                print(result.stdout)
                return {
                    "success": True,
                    "message": result.stdout,
                    "warning": "Could not extract job ID from output",
                }
        else:
            return {
                "success": False,
                "error": result.stderr or result.stdout,
                "returncode": result.returncode,
            }
    except subprocess.CalledProcessError as e:
        print(str(e))
        return {
            "success": False,
            "error": str(e),
            "stdout": e.stdout,
            "stderr": e.stderr,
        }
    except FileNotFoundError as e:
        return {"success": False, "error": f"File not found: {str(e)}"}
    except Exception as e:
        return {"success": False, "error": str(e)}


if __name__ == "__main__":
    print(get_conda_packages())
