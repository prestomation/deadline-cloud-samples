"""
Tools for working with Open Job Description templates.
"""

from typing import Dict, Any

from strands import tool
from pathlib import Path
from deadline_cloud_agent.tools.conda_tools import get_repo_data, validate_packages

from openjd.model import (
    DecodeValidationError,
    DocumentType,
    document_string_to_object,
    TemplateSpecificationVersion,
    decode_job_template,
)


def get_doc_type(filepath: Path) -> DocumentType:
    if filepath.suffix.lower() == ".json":
        return DocumentType.JSON
    elif filepath.suffix.lower() in (".yaml", ".yml"):
        return DocumentType.YAML
    raise RuntimeError(f"'{str(filepath)}' is not JSON or YAML.")


@tool
def openjd_validate(template_path: str) -> Dict[str, Any]:
    """
    Validate an OpenJD template.

    Args:
        template_path: Path to the template file

    Returns:
        Dict[str, Any]: Validation result
    """

    # This is copied from the OpenJD CLI implementation
    # TODO: should we expose this better through the OpenJD python API?
    template_file = Path(template_path).resolve()
    if not template_file.exists():
        raise RuntimeError(f"'{str(template_file)}' does not exist.")

    if template_file.is_file():
        filetype = get_doc_type(template_file)
    else:
        raise RuntimeError(f"'{str(template_file)}' is not a file.")

    try:
        template_string = template_file.read_text(encoding="utf-8")
    except OSError as exc:
        raise RuntimeError(f"Could not open file '{str(template_file)}': {str(exc)}")

    try:
        template_object = document_string_to_object(
            document=template_string, document_type=filetype
        )
        document_version = template_object["specificationVersion"]
        template_version = TemplateSpecificationVersion(document_version)
        if TemplateSpecificationVersion.is_job_template(template_version):
            decode_job_template(template=template_object)
        else:
            return f"Invalid specification version {document_version},"

    except DecodeValidationError as exc:
        raise RuntimeError(f"'{str(template_file)}' failed checks: {str(exc)}")

    conda_packages = list(
        filter(
            lambda p: p["name"] == "CondaPackages",
            template_object.get("parameterDefinitions"),
        )
    )

    # This is an assumption that _something_ will be installed using Conda
    if not conda_packages:
        return "Validation failed. Package must have a CondaPackages parameter to install the new, required package"
    conda_requirements = conda_packages[0]["default"].split(" ")

    # We try to confirm that the package actually exists in the channel
    # This falls a part a bit when pulling from conda forge
    results = validate_packages(conda_requirements, get_repo_data())

    conda_channels = list(
        filter(
            lambda p: p["name"] == "CondaChannels",
            template_object.get("parameterDefinitions"),
        )
    )
    if conda_channels:
        return "Validation failed. Package must NOT have a CondaChannels parameter to install the new, required package. This will come from the queue environment"

    if "jobEnvironments" in template_object:
        return "Validation failed. Package must NOT have a job environment. Listing the package in the CondaPackages parameter is enough to install the package"

    if results["success"]:
        return f"OpenJD template {template_path} validated successfully"
    else:
        return results


if __name__ == "__main__":
    print(openjd_validate("failed.yaml"))
