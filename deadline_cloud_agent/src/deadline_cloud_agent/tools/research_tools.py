"""
Tools for research and information gathering.
"""

import os
import subprocess
import requests
from bs4 import BeautifulSoup
from typing import Dict, Any
from urllib.parse import quote
import markdownify
from strands import Agent

from strands import tool


def summarize_content(content: str, query: str):
    agent = Agent(
        system_prompt="""You are a helpful research agent that summarizes large amounts of content. 
Summarize the provided content to efficiently teach a large language model the information provided.
The information will be technical, about how to run a program, how to build a conda package, or how to create a Deadline Cloud Open Job Description job definition template or bundle.
Do not summarize too aggressively, if in doubt leave the content as-is. 
You MUST keep example code/yaml/json from the content.
You MUST include all URLs relavant to the task.

Remove any extraneous information not related to the query: 
"""
        + query
    )
    response = str(agent(content))
    print(response)
    print(f"original research length: {len(content)}, summarized to: {len(response)}")
    return response


@tool
def web_search(query: str, max_results: int = 5) -> Dict[str, Any]:
    """
    Search the web for information using DuckDuckGo.

    This tool performs a web search using DuckDuckGo and returns relevant results
    without requiring an API key.

    Args:
        query: Search query
        max_results: Maximum number of results to return

    Returns:
        Dict[str, Any]: Search results
    """
    try:
        # Format the query for DuckDuckGo
        formatted_query = quote(query)
        url = f"https://html.duckduckgo.com/html/?q={formatted_query}"
        print(url)

        # Send the request with a user agent to avoid being blocked
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers)

        # Parse the HTML response
        soup = BeautifulSoup(response.text, "html.parser")

        # Extract search results
        results = []
        for result in soup.select(".result"):
            title_elem = result.select_one(".result__title")
            snippet_elem = result.select_one(".result__snippet")
            url_elem = result.select_one(".result__url")

            if title_elem and url_elem:
                # Extract the actual URL from the href attribute
                link_elem = title_elem.find("a")
                href = link_elem.get("href", "") if link_elem else ""

                # Clean up the URL
                if href.startswith("/"):
                    continue

                # Extract the actual URL from DuckDuckGo's redirect URL
                if "duckduckgo.com/l/?uddg=" in href:
                    start_idx = href.find("uddg=") + 5
                    end_idx = (
                        href.find("&", start_idx)
                        if "&" in href[start_idx:]
                        else len(href)
                    )
                    href = href[start_idx:end_idx]

                # Add the result
                results.append(
                    {
                        "title": title_elem.text.strip(),
                        "snippet": snippet_elem.text.strip() if snippet_elem else "",
                        "url": href,
                    }
                )

                # Break if we have enough resultsx
                if len(results) >= max_results:
                    break

        print(f"{query}{results}")
        return {
            "success": True,
            "query": query,
            "results": results,
            "note": "To fetch specific content from these URLs, use the http_request tool.",
        }
    except Exception as e:
        print(e)
        return {"success": False, "error": str(e)}


@tool
def deadline_cloud_documentation(
    topic: str = "", index: int = 0, length: int = 10000
) -> Dict[str, Any]:
    """
    Fetch Deadline Cloud documentation on a specific topic.

    This tool downloads relevant Deadline Cloud documentation and returns the content.

    Args:
        topic: Specific topic to search for, one of "conda", "blender-example", "jobtemplate", or "general"

    Returns:
        Dict[str, Any]: Documentation content
    """
    print(topic)
    docs = {
        "conda": "https://docs.aws.amazon.com/deadline-cloud/latest/developerguide/conda-package.html",
        "blender-example": "https://docs.aws.amazon.com/deadline-cloud/latest/developerguide/create-conda-recipe-blender.html",
        "jobtemplate": "https://docs.aws.amazon.com/deadline-cloud/latest/developerguide/job-templates.html",
        "general": "https://docs.aws.amazon.com/deadline-cloud/latest/developerguide/what-is-deadline-cloud.html",
    }
    try:
        # Determine which URL to use based on the topic
        url = None
        for key, doc_url in docs.items():
            if topic.lower() in key:
                url = doc_url
                break

        # If no specific topic matched, use the general documentation
        if not url:
            url = docs["start_here"]

        # Fetch the documentation
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers)

        content_text = extract_content_from_html(response.text)
        note = "No remaining content"
        print(f"Starting at {index}:{length}", end="")
        if len(content_text[index:]) > length:
            remaining = len(content_text) - (index + length)
            content_text = content_text[index : index + length]
            note = f"Remaining content starts at {index + length} with {remaining} chars remaining"
            print(note)
        else:
            # return the rest of the content
            content_text = content_text[index:]
        content_text = content_text[index:length]

        return {
            "success": True,
            "topic": topic,
            "content": summarize_content(
                content_text[index:length],
                f"Deadline cloud documentation about {topic}",
            ),
            "note": note,
        }
    except Exception as e:
        print(e)
        return {"success": False, "error": str(e)}


@tool
def openjd_documentation(
    topic: str = "", index: int = 0, length: int = 10000
) -> Dict[str, Any]:
    """
    Fetch open job description documentation on a specific topic.

    This tool downloads relevant Open Job Description documentation and returns the content.

    Args:
        topic: Specific topic to search for, one of "execution", "structure", "spec", "tutorial_creating_a_job_template" or "tutorial_ready_for_production"
        index: Pagination index, where to start(default=0)
        length: how many characters to retrive starting at the index, used for pagination(default=10000)

    Returns:
        Dict[str, Any]: Documentation content
    """
    print(topic)
    docs = {
        "execution": "https://raw.githubusercontent.com/OpenJobDescription/openjd-specifications/refs/heads/mainline/wiki/How-Jobs-Are-Run.md",
        "structure": "https://raw.githubusercontent.com/OpenJobDescription/openjd-specifications/refs/heads/mainline/wiki/How-Jobs-Are-Constructed.md",
        "spec": "https://raw.githubusercontent.com/OpenJobDescription/openjd-specifications/refs/heads/mainline/wiki/2023-09-Template-Schemas.md",
        "tutorial_creating_a_job_template": "https://raw.githubusercontent.com/OpenJobDescription/openjd-specifications/refs/heads/mainline/wiki/Job-Intro-03-Creating-a-Job-Template.md",
        "tutorial_ready_for_production": "https://raw.githubusercontent.com/OpenJobDescription/openjd-specifications/refs/heads/mainline/wiki/Job-Intro-04-Ready-for-Production.md",
    }
    try:
        # Determine which URL to use based on the topic
        url = None
        for key, doc_url in docs.items():
            if topic.lower() in key:
                url = doc_url
                break

        # If no specific topic matched, use the general documentation
        if not url:
            url = docs["tutorial_creating_a_job_template"]

        # Fetch the documentation
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers)

        content_text = extract_content_from_html(response.text)
        note = "No remaining content"
        print(f"Starting at {index}:{length}", end="")
        if len(content_text[index:]) > length:
            remaining = len(content_text) - (index + length)
            content_text = content_text[index : index + length]
            note = f"Remaining content starts at {index + length} with {remaining} chars remaining"
            print(note)
        else:
            # return the rest of the content
            content_text = content_text[index:]
        content_text = content_text[index:length]

        return {
            "success": True,
            "topic": topic,
            "content": summarize_content(
                content_text[index:length],
                f"Open Job Description documentation about {topic}",
            ),
            "note": note,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def conda_documentation(
    topic: str = "", index: int = 0, length: int = 10000
) -> Dict[str, Any]:
    """
    Fetch conda packaging documentation on a specific topic.

    This tool downloads relevant conda packaging documentation and returns the content.
    Always start with the topic start_here when first learning about Conda and Deadline Cloud but you should read them all before building a package

    Args:
        topic: Specific topic to search for one of "start_here", "meta.yaml", "build script", and "relocatable-packages")

    Returns:
        Dict[str, Any]: Documentation content
    """
    try:
        # Define key conda documentation URLs
        docs = {
            "start_here": "https://raw.githubusercontent.com/aws-deadline/deadline-cloud-samples/refs/heads/mainline/conda_recipes/README.md",
            "meta.yaml": "https://raw.githubusercontent.com/conda/conda-build/main/docs/source/resources/define-metadata.rst",
            "build script": "https://raw.githubusercontent.com/conda/conda-build/main/docs/source/resources/build-scripts.rst",
            "relocatable-packages": "https://docs.conda.io/projects/conda-build/en/stable/_sources/resources/make-relocatable.rst.txt",
        }

        # Determine which URL to use based on the topic
        url = None
        for key, doc_url in docs.items():
            if topic.lower() in key:
                url = doc_url
                break

        # If no specific topic matched, use the general documentation
        if not url:
            url = docs["start_here"]

        # Fetch the documentation
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        }
        response = requests.get(url, headers=headers)

        content_text = response.text
        note = "No remaining content"
        print(f"Starting at {index}:{length}", end="")
        if len(content_text[index:]) > length:
            remaining = len(content_text) - (index + length)
            content_text = content_text[index : index + length]
            note = f"Remaining content starts at {index + length} with {remaining} chars remaining"
            print(note)
        else:
            # return the rest of the content
            content_text = content_text[index:]
        content_text = content_text[index:length]

        return {
            "success": True,
            "topic": topic,
            "content": summarize_content(
                content_text[index:length],
                f"Conda Package building documentation about {topic}",
            ),
            "note": note,
        }
    except Exception as e:
        print(e)
        return {"success": False, "error": str(e)}


@tool
def search_examples(directory: str, pattern: str) -> Dict[str, Any]:
    """
    Search for example files in a directory.

    Args:
        directory: Directory to search in
        pattern: Pattern to search for

    Returns:
        Dict[str, Any]: Search results
    """
    try:
        if not os.path.exists(directory):
            return {"success": False, "error": f"Directory not found: {directory}"}

        if not os.path.isdir(directory):
            return {"success": False, "error": f"Not a directory: {directory}"}

        # Use find and grep to search for files
        cmd = [
            "find",
            directory,
            "-type",
            "f",
            "-exec",
            "grep",
            "-l",
            pattern,
            "{}",
            ";",
        ]

        result = subprocess.run(cmd, capture_output=True, text=True)

        if result.returncode == 0:
            # Split the output into lines
            matching_files = result.stdout.strip().split("\n")
            matching_files = [f for f in matching_files if f]  # Remove empty lines

            # Read the content of each matching file
            file_contents = {}
            for file_path in matching_files[
                :5
            ]:  # Limit to 5 files to avoid overwhelming the response
                try:
                    with open(file_path, "r", encoding="utf-8") as f:
                        file_contents[file_path] = f.read()
                except Exception as e:
                    file_contents[file_path] = f"Error reading file: {str(e)}"

            return {
                "success": True,
                "directory": directory,
                "pattern": pattern,
                "matching_files": matching_files,
                "file_count": len(matching_files),
                "file_contents": file_contents,
                "message": f"Found {len(matching_files)} files matching '{pattern}' in {directory}",
            }
        else:
            return {
                "success": False,
                "error": result.stderr or "No matching files found",
                "returncode": result.returncode,
            }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def get_job_bundle_sample() -> str:
    """
    Provides a sample job template for Blender 4.4
    This shows the typical parameters, how CondaPackages is managed
    How there are no step/job environments but instead the exe is used with the parameters
    """

    base_path = os.path.join(os.path.dirname(__file__), "../../../../")
    job_template_path = os.path.join(
        base_path, "job_bundles/blender_render/template.yaml"
    )
    result = []
    # Add the job template
    result.append("File: job_bundles/blender_render/template.yaml")
    result.append("-" * 50)
    with open(job_template_path, "r") as f:
        result.append(f.read())

    return "\n".join(result)


@tool
def get_conda_recipe_sample() -> str:
    """
    Provides a complete sample of a Deadline Cloud conda recipe for Blender 4.4.

    This tool returns the contents of all files in the blender-4.4 conda recipe directory,
    along with the structure of the referenced zip/tar files and the job template.

    Use this tool when you need to understand:
    - How to structure a conda recipe for Deadline Cloud
    - How to reference external application files in a recipe
    - How to set up environment variables in conda activation scripts
    """
    base_path = os.path.join(os.path.dirname(__file__), "../../../../")
    recipe_path = os.path.join(base_path, "conda_recipes/blender-4.4")

    result = []

    # Add the deadline-cloud.yaml file
    result.append("File: conda_recipes/blender-4.4/deadline-cloud.yaml")
    result.append("-" * 50)
    with open(os.path.join(recipe_path, "deadline-cloud.yaml"), "r") as f:
        result.append(f.read())
    result.append("\n")

    # Add all files in the recipe directory
    for root, _, files in os.walk(os.path.join(recipe_path, "recipe")):
        for file in files:
            file_path = os.path.join(root, file)
            rel_path = os.path.relpath(file_path, base_path)
            result.append(f"File: {rel_path}")
            result.append("-" * 50)
            with open(file_path, "r") as f:
                result.append(f.read())
            result.append("\n")

    # Add hardcoded information about the Linux archive structure
    result.append("Archive Structure: blender-4.4.0-linux-x64.tar.xz")
    result.append("-" * 50)

    # Hardcoded list of files from the archive
    archive_files = [
        "blender-4.4.0-linux-x64/",
        "blender-4.4.0-linux-x64/blender.desktop",
        "blender-4.4.0-linux-x64/blender-launcher",
        "blender-4.4.0-linux-x64/blender-thumbnailer",
        "blender-4.4.0-linux-x64/blender",
        "blender-4.4.0-linux-x64/blender.svg",
        "blender-4.4.0-linux-x64/copyright.txt",
        "blender-4.4.0-linux-x64/lib/",
        "blender-4.4.0-linux-x64/lib/libOpenImageDenoise_device_cuda.so.2.3.2",
        "blender-4.4.0-linux-x64/lib/liboslexec.so.1.14.4",
        "blender-4.4.0-linux-x64/lib/libur_adapter_level_zero.so.0.10.8",
        "blender-4.4.0-linux-x64/lib/libcycles_kernel_oneapi_aot.so",
        "blender-4.4.0-linux-x64/lib/libIex.so.32.3.3.2",
        "blender-4.4.0-linux-x64/lib/libvulkan.so.1.3.296",
        "blender-4.4.0-linux-x64/lib/libMaterialXRenderOsl.so",
        "blender-4.4.0-linux-x64/lib/libIlmThread.so.32",
        "blender-4.4.0-linux-x64/lib/libosdCPU.so.3.6.0",
        "blender-4.4.0-linux-x64/lib/libMaterialXFormat.so",
        "blender-4.4.0-linux-x64/lib/libMaterialXRenderOsl.so.1.39.2",
        "blender-4.4.0-linux-x64/lib/libopenvdb.so",
        "blender-4.4.0-linux-x64/4.4/",
        "blender-4.4.0-linux-x64/4.4/python/",
        "blender-4.4.0-linux-x64/4.4/python/bin/",
        "blender-4.4.0-linux-x64/4.4/python/lib/",
        "blender-4.4.0-linux-x64/4.4/scripts/",
        "blender-4.4.0-linux-x64/4.4/scripts/addons/",
        "blender-4.4.0-linux-x64/4.4/scripts/startup/",
        "blender-4.4.0-linux-x64/4.4/datafiles/",
        "blender-4.4.0-linux-x64/4.4/datafiles/colormanagement/",
        "blender-4.4.0-linux-x64/4.4/datafiles/fonts/",
    ]

    result.append("\n".join(archive_files))
    result.append("... (more files)")
    result.append("\n")

    return "\n".join(result)


def extract_content_from_html(html: str) -> str:
    """Extract and convert HTML content to Markdown format.

    Args:
        html: Raw HTML content to process

    Returns:
        Simplified markdown version of the content
    """
    if not html:
        return "<e>Empty HTML content</e>"

    try:
        # First use BeautifulSoup to clean up the HTML
        from bs4 import BeautifulSoup

        # Parse HTML with BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")

        # Try to find the main content area
        main_content = None

        # Common content container selectors for AWS documentation
        content_selectors = [
            "main",
            "article",
            "#main-content",
            ".main-content",
            "#content",
            ".content",
            "div[role='main']",
            "#awsdocs-content",
            ".awsui-article",
        ]

        # Try to find the main content using common selectors
        for selector in content_selectors:
            content = soup.select_one(selector)
            if content:
                main_content = content
                break

        # If no main content found, use the body
        if not main_content:
            main_content = soup.body if soup.body else soup

        # Remove navigation elements that might be in the main content
        nav_selectors = [
            "noscript",
            ".prev-next",
            "#main-col-footer",
            ".awsdocs-page-utilities",
            "#quick-feedback-yes",
            "#quick-feedback-no",
            ".page-loading-indicator",
            "#tools-panel",
            ".doc-cookie-banner",
            "awsdocs-copyright",
            "awsdocs-thumb-feedback",
        ]

        for selector in nav_selectors:
            for element in main_content.select(selector):
                element.decompose()

        # Define tags to strip - these are elements we don't want in the output
        tags_to_strip = [
            "script",
            "style",
            "noscript",
            "meta",
            "link",
            "footer",
            "nav",
            "aside",
            "header",
            # AWS documentation specific elements
            "awsdocs-cookie-consent-container",
            "awsdocs-feedback-container",
            "awsdocs-page-header",
            "awsdocs-page-header-container",
            "awsdocs-filter-selector",
            "awsdocs-breadcrumb-container",
            "awsdocs-page-footer",
            "awsdocs-page-footer-container",
            "awsdocs-footer",
            "awsdocs-cookie-banner",
            # Common unnecessary elements
            "js-show-more-buttons",
            "js-show-more-text",
            "feedback-container",
            "feedback-section",
            "doc-feedback-container",
            "doc-feedback-section",
            "warning-container",
            "warning-section",
            "cookie-banner",
            "cookie-notice",
            "copyright-section",
            "legal-section",
            "terms-section",
        ]

        # Use markdownify on the cleaned HTML content
        content = markdownify.markdownify(
            str(main_content),
            heading_style=markdownify.ATX,
            autolinks=True,
            default_title=True,
            escape_asterisks=True,
            escape_underscores=True,
            newline_style="SPACES",
            strip=tags_to_strip,
        )

        if not content:
            return "<e>Page failed to be simplified from HTML</e>"

        return content
    except Exception as e:
        return f"<e>Error converting HTML to Markdown: {str(e)}</e>"


if __name__ == "__main__":
    # Example usage
    print(get_job_bundle_sample())
