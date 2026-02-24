"""
File copying tool for Strands Agent with interactive confirmation.

This module provides a secure file and directory copying capability with rich output
formatting and user confirmation. It's designed to safely copy files and directories
while providing clear feedback and requiring explicit confirmation for copy operations
in non-development environments.

Key Features:

1. Interactive Confirmation:
   • Clear display of source and destination paths
   • Formatted operation information

2. Rich Output Display:
   • Formatted panels for operation information
   • Color-coded status messages
   • Clear success and error indicators
   • File/directory size information

3. Safety Features:
   • Directory creation if parent directories don't exist
   • Detailed error reporting
   • Path validation and expansion

4. File Management:
   • Support for both file and directory copying
   • Recursive directory copying
   • Proper path handling and expansion
   • Size reporting for copied content

Usage with Strands Agent:
```python
from strands import Agent
from strands_tools import file_copy

agent = Agent(tools=[file_copy])

# Copy a file
agent.tool.file_copy(
    src="/path/to/source/file.txt",
    dest="/path/to/destination/file.txt"
)

# Copy a directory
agent.tool.file_copy(
    src="/path/to/source/directory",
    dest="/path/to/destination/directory"
)
```

See the file_copy function docstring for more details on usage options and parameters.
"""

import os
import shutil
from os.path import expanduser
from typing import Any, Optional

from rich import box
from rich.panel import Panel
from rich.text import Text
from strands.types.tools import ToolResult, ToolUse

from strands_tools.utils import console_util

TOOL_SPEC = {
    "name": "file_copy",
    "description": "Copy a file or directory from source to destination with proper validation and confirmation",
    "inputSchema": {
        "json": {
            "type": "object",
            "properties": {
                "src": {
                    "type": "string",
                    "description": "The source path of the file or directory to copy",
                },
                "dest": {
                    "type": "string",
                    "description": "The destination path where the file or directory should be copied",
                },
            },
            "required": ["src", "dest"],
        }
    },
}


def get_path_info(path: str) -> tuple[str, str, Optional[int]]:
    """
    Get information about a file or directory path.

    Args:
        path: Path to analyze

    Returns:
        tuple: (type, size_info, file_count) where:
            - type: "file", "directory", or "not found"
            - size_info: Human readable size information
            - file_count: Number of files (for directories) or None
    """
    if not os.path.exists(path):
        return "not found", "N/A", None
    
    if os.path.isfile(path):
        size = os.path.getsize(path)
        return "file", f"{size} bytes", None
    elif os.path.isdir(path):
        file_count = sum(len(files) for _, _, files in os.walk(path))
        dir_count = sum(len(dirs) for _, dirs, _ in os.walk(path))
        return "directory", f"{file_count} files, {dir_count} subdirectories", file_count
    else:
        return "unknown", "N/A", None


def file_copy(tool: ToolUse, **kwargs: Any) -> ToolResult:
    """
    Copy a file or directory from source to destination with interactive confirmation.

    This tool safely copies files or directories from a source path to a destination
    path with proper validation and user confirmation. It displays information about
    the source and destination, and requires explicit user confirmation in 
    non-development environments.

    How It Works:
    ------------
    1. Expands user paths to handle tilde (~) in paths
    2. Validates that the source path exists
    3. Displays source and destination information in formatted panels
    4. Creates any necessary parent directories for the destination
    5. Performs the copy operation (file or directory)
    6. Provides rich visual feedback on operation success or failure

    Common Usage Scenarios:
    ---------------------
    - Backing up important files or directories
    - Duplicating configuration files for different environments
    - Creating templates from existing files
    - Copying project structures or code bases
    - Moving files between different locations

    Args:
        tool: ToolUse object containing the following input fields:
            - src: The source path of the file or directory to copy. User paths
                   with tilde (~) are automatically expanded.
            - dest: The destination path where the content should be copied.
                    User paths with tilde (~) are automatically expanded.
        **kwargs: Additional keyword arguments (not used currently)

    Returns:
        ToolResult containing status and response content in the format:
        {
            "toolUseId": "<tool_use_id>",
            "status": "success|error",
            "content": [{"text": "Response message"}]
        }

    Notes:
        - Parent directories for destination are automatically created if they don't exist
        - Supports both file and directory copying with recursive directory copying
        - All operations use rich formatting for clear visual feedback
        - If destination exists, it will be overwritten
    """
    console = console_util.create()

    tool_use_id = tool["toolUseId"]
    tool_input = tool["input"]
    src_path = expanduser(tool_input["src"])
    dest_path = expanduser(tool_input["dest"])

    # Get information about source and destination
    src_type, src_info, src_file_count = get_path_info(src_path)
    dest_type, dest_info, _ = get_path_info(dest_path)

    # Check if source exists
    if src_type == "not found":
        error_message = f"Source path does not exist: {src_path}"
        error_panel = Panel(
            Text(error_message, style="bold red"),
            title="[bold red]Copy Failed",
            border_style="red",
            box=box.HEAVY,
            expand=False,
        )
        console.print(error_panel)
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": error_message}],
        }

    # Create a panel with copy operation information
    dest_status = f"exists ({dest_info})" if dest_type != "not found" else "will be created"
    
    info_panel = Panel(
        Text.assemble(
            ("Source: ", "cyan"),
            (src_path, "yellow"),
            (f" ({src_type}, {src_info})", "white"),
            ("\nDestination: ", "cyan"),
            (dest_path, "yellow"),
            (f" ({dest_status})", "white"),
        ),
        title="[bold blue]File Copy Operation",
        border_style="blue",
        box=box.DOUBLE,
        expand=False,
        padding=(1, 1),
    )
    console.print(info_panel)

    try:
        # Create destination directory if it doesn't exist
        dest_dir = os.path.dirname(dest_path)
        if dest_dir and not os.path.exists(dest_dir):
            os.makedirs(dest_dir)
            console.print(
                Panel(
                    Text(f"Created directory: {dest_dir}", style="bold blue"),
                    title="[bold blue]Directory Created",
                    border_style="blue",
                    box=box.DOUBLE,
                    expand=False,
                )
            )

        # Perform the copy operation
        if src_type == "file":
            shutil.copy2(src_path, dest_path)
            success_message = f"File copied successfully from {src_path} to {dest_path}"
        elif src_type == "directory":
            if os.path.exists(dest_path):
                shutil.rmtree(dest_path)
            shutil.copytree(src_path, dest_path)
            success_message = f"Directory copied successfully from {src_path} to {dest_path}"
        else:
            raise ValueError(f"Unsupported source type: {src_type}")

        success_panel = Panel(
            Text(success_message, style="bold green"),
            title="[bold green]Copy Successful",
            border_style="green",
            box=box.DOUBLE,
            expand=False,
        )
        console.print(success_panel)
        return {
            "toolUseId": tool_use_id,
            "status": "success",
            "content": [{"text": f"Copy operation success: {success_message}"}],
        }
    except Exception as e:
        error_message = f"Error copying {src_type}: {str(e)}"
        error_panel = Panel(
            Text(error_message, style="bold red"),
            title="[bold red]Copy Failed",
            border_style="red",
            box=box.HEAVY,
            expand=False,
        )
        console.print(error_panel)
        return {
            "toolUseId": tool_use_id,
            "status": "error",
            "content": [{"text": error_message}],
        }
