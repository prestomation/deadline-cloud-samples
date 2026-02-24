#!/usr/bin/env python
"""
Validates a Deadline Cloud conda recipe directory to ensure it will work when submitted to a server.
This tool performs local validation checks before submitting a package build job.
"""
import argparse
import os
import re
import sys
from pathlib import Path
from typing import Dict, Set, Union
from packaging.version import parse, InvalidVersion

import yaml


class ValidationError(Exception):
    """Exception raised for validation errors in the conda recipe."""

    pass


def extract_structure_from_meta_yaml(content: str) -> Dict:
    """
    Extract structure from meta.yaml without parsing Jinja2 templates.

    Args:
        content: Content of meta.yaml file

    Returns:
        Dict containing the structure of meta.yaml
    """
    # Remove Jinja2 template expressions
    # This is a simplified approach - we remove lines with Jinja2 syntax
    filtered_lines = []
    in_jinja_block = False

    for line in content.splitlines():
        # Skip Jinja2 set statements and blocks
        if "{%" in line and "%}" in line:
            continue
        if "{%" in line:
            in_jinja_block = True
            continue
        if "%}" in line:
            in_jinja_block = False
            continue
        if in_jinja_block:
            continue

        # Replace Jinja2 variable expressions with placeholders
        line = re.sub(r"\{\{\s*[^}]+\s*\}\}", '"JINJA_PLACEHOLDER"', line)
        filtered_lines.append(line)

    filtered_content = "\n".join(filtered_lines)

    # try:
    # Parse the filtered content
    return yaml.safe_load(filtered_content) or {}
    # except yaml.YAMLError:
    #     # If parsing fails, try a more aggressive approach
    #     return extract_sections_from_meta_yaml(content)


def validate_conda_recipe(recipe_dir: Union[str, Path], verbose: bool = False) -> Dict:
    """
    Validates a Deadline Cloud conda recipe directory.

    Args:
        recipe_dir: Path to the conda recipe directory
        verbose: Whether to print verbose validation information

    Returns:
        Dict containing validation results with keys:
            - valid: Boolean indicating if the recipe is valid
            - errors: List of error messages if any
            - warnings: List of warning messages if any
            - recipe_info: Dict with information about the recipe

    Raises:
        ValidationError: If the recipe directory doesn't exist
    """
    recipe_dir = Path(recipe_dir).resolve()

    if verbose:
        print(f"Validating conda recipe at: {recipe_dir}")

    result = {"valid": True, "errors": [], "warnings": [], "recipe_info": {}}

    # Check if recipe directory exists
    if not recipe_dir.is_dir():
        raise ValidationError(f"Recipe directory does not exist: {recipe_dir}")

    # Check directory structure
    recipe_subdir = recipe_dir / "recipe"
    deadline_cloud_yaml = recipe_dir / "deadline-cloud.yaml"

    if not recipe_subdir.is_dir():
        result["errors"].append(f"Missing 'recipe' subdirectory in {recipe_dir}")
        result["valid"] = False

    if not deadline_cloud_yaml.is_file():
        result["errors"].append(f"Missing 'deadline-cloud.yaml' file in {recipe_dir}")
        result["valid"] = False

    # If critical files are missing, return early
    if not result["valid"]:
        return result

    # Load template parameters for validation
    template_params = get_template_parameters()

    # Validate deadline-cloud.yaml
    try:
        with open(deadline_cloud_yaml, "r") as f:
            deadline_cloud_config = yaml.safe_load(f)

        result["recipe_info"]["deadline_cloud_config"] = deadline_cloud_config
        validate_deadline_cloud_yaml(
            deadline_cloud_config, result, recipe_dir, template_params
        )

    except Exception as e:
        result["errors"].append(f"Error parsing deadline-cloud.yaml: {str(e)}")
        result["valid"] = False
        return result

    # Validate recipe files
    meta_yaml_file = recipe_subdir / "meta.yaml"
    recipe_yaml_file = recipe_subdir / "recipe.yaml"

    if meta_yaml_file.is_file():
        result["recipe_info"]["build_tool"] = "conda-build"
        validate_conda_build_recipe(meta_yaml_file, result)
    elif recipe_yaml_file.is_file():
        result["recipe_info"]["build_tool"] = "rattler-build"
        validate_rattler_build_recipe(recipe_yaml_file, result)
    else:
        result["errors"].append(f"No meta.yaml or recipe.yaml found in {recipe_subdir}")
        result["valid"] = False

    # Check for build scripts based on platforms
    if "deadline_cloud_config" in result["recipe_info"]:
        config = result["recipe_info"]["deadline_cloud_config"]
        platforms = config.get("condaPlatforms", [])

        # Get unique platform families
        platform_families = set()
        for platform in platforms:
            platform_name = platform.get("platform", "")
            if platform_name.startswith("linux"):
                platform_families.add("linux")
            elif platform_name.startswith("win"):
                platform_families.add("windows")
            elif platform_name.startswith("osx") or platform_name.startswith("macos"):
                platform_families.add("macos")

        # Check for corresponding build scripts
        build_sh = recipe_subdir / "build.sh"
        bld_bat = recipe_subdir / "bld.bat"

        if "linux" in platform_families or "macos" in platform_families:
            if not build_sh.is_file():
                result["errors"].append(
                    f"Missing build.sh script for Linux/macOS platforms in {recipe_subdir}"
                )
                result["valid"] = False

        if "windows" in platform_families:
            if not bld_bat.is_file():
                result["errors"].append(
                    f"Missing bld.bat script for Windows platforms in {recipe_subdir}"
                )
                result["valid"] = False

    # Check for README.md (optional)
    readme = recipe_dir / "README.md"
    if not readme.is_file():
        result["warnings"].append(
            "No README.md found. Consider adding documentation for the recipe."
        )

    return result


def get_template_parameters() -> Set[str]:
    """Get the set of valid parameter names from the template.yaml file."""
    template_path = (
        Path(__file__).parent.parent.parent.parent.parent
        / "conda_recipes"
        / "conda_build_linux_package"
        / "template.yaml"
    )

    if not template_path.exists():
        return set()

    try:
        with open(template_path, "r") as f:
            template = yaml.safe_load(f)

        param_names = set()
        for param in template.get("parameterDefinitions", []):
            param_names.add(param.get("name", ""))

        return param_names
    except Exception:
        return set()


def validate_deadline_cloud_yaml(
    config: Dict, result: Dict, recipe_dir: Path, template_params: Set[str]
) -> None:
    """Validates the deadline-cloud.yaml configuration."""
    # Check for required sections
    if "condaPlatforms" not in config:
        result["errors"].append(
            "Missing 'condaPlatforms' section in deadline-cloud.yaml"
        )
        result["valid"] = False
        return

    # Validate conda platforms
    platforms = config["condaPlatforms"]
    if not isinstance(platforms, list) or not platforms:
        result["errors"].append("'condaPlatforms' must be a non-empty list")
        result["valid"] = False
        return

    # Check each platform configuration
    has_default_submit = False
    for i, platform in enumerate(platforms):
        if not isinstance(platform, dict):
            result["errors"].append(f"Platform entry {i+1} must be a dictionary")
            result["valid"] = False
            continue

        if "platform" not in platform:
            result["errors"].append(f"Platform entry {i+1} is missing 'platform' field")
            result["valid"] = False

        if platform.get("defaultSubmit", False):
            has_default_submit = True

        # Check source archive files if specified
        if "sourceArchiveFilename" in platform:
            archive_files = platform["sourceArchiveFilename"]
            archive_files_dir = Path(recipe_dir).parent / "archive_files"

            if isinstance(archive_files, str):
                archive_files = [archive_files]

            if not isinstance(archive_files, list):
                result["errors"].append(
                    f"Platform {platform.get('platform', i+1)}: 'sourceArchiveFilename' must be a string or list"
                )
                result["valid"] = False
            elif len(archive_files) > 2:
                result["errors"].append(
                    f"Platform {platform.get('platform', i+1)}: 'sourceArchiveFilename' list cannot have more than 2 entries"
                )
                result["valid"] = False
            else:
                for archive in archive_files:
                    archive_path = archive_files_dir / archive
                    if not archive_path.is_file():
                        result["warnings"].append(
                            f"Platform {platform.get('platform', i+1)}: Source archive file '{archive}' not found in {archive_files_dir}"
                        )
                        if "sourceDownloadInstructions" in platform:
                            result["warnings"].append(
                                f"Download instructions: {platform['sourceDownloadInstructions']}"
                            )

    if not has_default_submit:
        result["warnings"].append(
            "No platform has 'defaultSubmit: true'. At least one platform should be marked as default."
        )

    # Validate job parameters if present
    if "jobParameters" in config:
        job_params = config["jobParameters"]
        if not isinstance(job_params, list):
            result["errors"].append("'jobParameters' must be a list")
            result["valid"] = False
        else:
            for i, param in enumerate(job_params):
                if not isinstance(param, dict):
                    result["errors"].append(f"Job parameter {i+1} must be a dictionary")
                    result["valid"] = False
                    continue

                if "name" not in param:
                    result["errors"].append(
                        f"Job parameter {i+1} is missing 'name' field"
                    )
                    result["valid"] = False
                elif param["name"] not in template_params:
                    result["errors"].append(
                        f"Job parameter '{param['name']}' is not defined in the template.yaml file"
                    )
                    result["valid"] = False

                if "value" not in param:
                    result["errors"].append(
                        f"Job parameter {i+1} is missing 'value' field"
                    )
                    result["valid"] = False


def validate_conda_build_recipe(meta_yaml_file: Path, result: Dict) -> None:
    """Validates a conda-build recipe (meta.yaml)."""
    try:
        with open(meta_yaml_file, "r") as f:
            meta_content = f.read()

        # Extract structure from meta.yaml without parsing Jinja2 templates
        meta_yaml = extract_structure_from_meta_yaml(meta_content)
        if meta_yaml is None:
            result["errors"].append(
                f"Failed to extract structure from meta.yaml: {meta_yaml_file}"
            )
            result["valid"] = False
            return

        result["recipe_info"]["meta_yaml"] = meta_yaml

        # Check for required sections
        required_sections = ["package", "build"]
        for section in required_sections:
            if section not in meta_yaml:
                result["errors"].append(
                    f"Missing required section '{section}' in meta.yaml"
                )
                result["valid"] = False

        # Check package section
        if "package" in meta_yaml:
            package = meta_yaml["package"]
            if "name" not in package:
                result["errors"].append(
                    "Missing 'name' in package section of meta.yaml"
                )
                result["valid"] = False
            if "version" not in package:
                result["errors"].append(
                    "Missing 'version' in package section of meta.yaml"
                )
                result["valid"] = False
            elif package["version"] != "JINJA_PLACEHOLDER":
                version = package["version"]
                try:
                    parse(version)
                except InvalidVersion:
                    result["errors"].append(
                        f"Invalid version format in package section of meta.yaml: {version}. The version must follow PEP 440"
                    )
                    result["valid"] = False

        # Check build section
        if "build" in meta_yaml:
            build = meta_yaml["build"]
            if "number" not in build:
                result["warnings"].append(
                    "Missing 'number' in build section of meta.yaml. Will default to 0."
                )

        # Check requirements section
        if "requirements" in meta_yaml:
            reqs = meta_yaml["requirements"]
            if "host" not in reqs and "build" not in reqs:
                result["warnings"].append(
                    "Neither 'host' nor 'build' requirements specified in meta.yaml"
                )

            if "run" not in reqs:
                result["warnings"].append(
                    "No 'run' requirements specified in meta.yaml"
                )

        # Check source section
        if "source" not in meta_yaml:
            result["valid"] = False
            result["errors"].append(
                "No 'source' section in meta.yaml. Please add a source section with url and sha256 properties OR a path property."
            )

        # Add type check before using get()
        source = meta_yaml.get("source", {})
        if not isinstance(source, dict):
            result["valid"] = False
            result["errors"].append(
                "'source' section in meta.yaml must be a dictionary"
            )
            return

        if "url" in source:
            url = source.get("url", "")
            if not url.startswith("http"):
                result["valid"] = False
                result["errors"].append(
                    "meta.yaml:source.url must be a public http address "
                )
        if "path" in source:
            path = source.get("path", "")
            if not path.startswith("archive_files"):
                result["valid"] = False
                result["errors"].append(
                    "meta.yaml:source.path MUST be exactly 'archive_files/{package_name.zip}', same as relative to your runtime env "
                )
            if not os.path.exists(os.path.join("conda_recipes", path)):
                result["valid"] = False
                result["errors"].append(
                    f"meta.yaml:source.path '{path}' does not exist on disk, it must start with archive_files/ and point at the installation package"
                )

    except Exception as e:
        print(e)
        result["errors"].append(f"Error validating meta.yaml: {str(e)}")
        result["valid"] = False


def validate_rattler_build_recipe(recipe_yaml_file: Path, result: Dict) -> None:
    """Validates a rattler-build recipe (recipe.yaml)."""
    try:
        with open(recipe_yaml_file, "r") as f:
            recipe_content = f.read()

        # Basic syntax check
        try:
            recipe_yaml = yaml.safe_load(recipe_content)
            if recipe_yaml is None:
                result["errors"].append(f"Empty recipe.yaml file: {recipe_yaml_file}")
                result["valid"] = False
                return

            result["recipe_info"]["recipe_yaml"] = recipe_yaml

        except yaml.YAMLError as e:
            result["errors"].append(f"Invalid YAML in recipe.yaml: {str(e)}")
            result["valid"] = False
            return

        # Check for required sections
        required_sections = ["package", "build", "about"]
        for section in required_sections:
            if section not in recipe_yaml:
                result["errors"].append(
                    f"Missing required section '{section}' in recipe.yaml"
                )
                result["valid"] = False

        # Check package section
        if "package" in recipe_yaml:
            package = recipe_yaml["package"]
            if "name" not in package:
                result["errors"].append(
                    "Missing 'name' in package section of recipe.yaml"
                )
                result["valid"] = False
            if "version" not in package:
                result["errors"].append(
                    "Missing 'version' in package section of recipe.yaml"
                )
                result["valid"] = False

        # Check build section
        if "build" in recipe_yaml:
            build = recipe_yaml["build"]
            if "number" not in build:
                result["warnings"].append(
                    "Missing 'number' in build section of recipe.yaml. Will default to 0."
                )

        # Check requirements section
        if "requirements" in recipe_yaml:
            reqs = recipe_yaml["requirements"]
            if "host" not in reqs and "build" not in reqs:
                result["warnings"].append(
                    "Neither 'host' nor 'build' requirements specified in recipe.yaml"
                )

            if "run" not in reqs:
                result["warnings"].append(
                    "No 'run' requirements specified in recipe.yaml"
                )

        # Check source section
        if "source" not in recipe_yaml:
            result["warnings"].append(
                "No 'source' section in recipe.yaml. This might be intentional if source is provided externally."
            )

    except Exception as e:
        result["errors"].append(f"Error validating recipe.yaml: {str(e)}")
        result["valid"] = False


def print_validation_results(results: Dict) -> None:
    """Prints validation results in a readable format."""
    print("\n=== Conda Recipe Validation Results ===\n")

    if results["valid"]:
        print("✅ Recipe is valid!")
    else:
        print("❌ Recipe validation failed!")

    if results["errors"]:
        print("\nErrors:")
        for error in results["errors"]:
            print(f"  - {error}")

    if results["warnings"]:
        print("\nWarnings:")
        for warning in results["warnings"]:
            print(f"  - {warning}")

    if "recipe_info" in results and results["recipe_info"]:
        info = results["recipe_info"]
        print("\nRecipe Information:")

        if "build_tool" in info:
            print(f"  - Build Tool: {info['build_tool']}")

        if "deadline_cloud_config" in info:
            config = info["deadline_cloud_config"]
            platforms = config.get("condaPlatforms", [])
            print(
                f"  - Platforms: {', '.join(p.get('platform', 'unknown') for p in platforms)}"
            )

            default_platforms = [
                p.get("platform") for p in platforms if p.get("defaultSubmit", False)
            ]
            if default_platforms:
                print(f"  - Default Platforms: {', '.join(default_platforms)}")

            if "jobParameters" in config:
                params = config["jobParameters"]
                print(
                    f"  - Job Parameters: {', '.join(f'{p.get('name')}={p.get('value')}' for p in params)}"
                )


def main():
    parser = argparse.ArgumentParser(
        description="Validate a Deadline Cloud conda recipe directory"
    )
    parser.add_argument(
        "recipe_dir", type=str, help="Path to the conda recipe directory"
    )
    parser.add_argument(
        "-v",
        "--verbose",
        action="store_true",
        help="Print verbose validation information",
    )
    args = parser.parse_args()

    try:
        results = validate_conda_recipe(args.recipe_dir, args.verbose)
        print_validation_results(results)

        if not results["valid"]:
            sys.exit(1)

    except ValidationError as e:
        print(f"Validation Error: {str(e)}")
        sys.exit(1)
    except Exception as e:
        print(f"Unexpected Error: {str(e)}")
        sys.exit(1)


if __name__ == "__main__":
    main()
