"""
Tools for working with archives and files.
"""

import hashlib
import os
import urllib.request
from typing import Dict, Any
import zipfile
import tarfile

from strands import tool


@tool
def download_file(url: str, output_path: str) -> Dict[str, Any]:
    """
    Download a file from a URL.

    Args:
        url: URL to download from
        output_path: Path to save the downloaded file to

    Returns:
        Dict[str, Any]: Download result
    """
    print(f"RemotePath:{url}->LocalPath:{output_path}")
    try:
        # Create the directory if it doesn't exist
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

        # Download the file
        urllib.request.urlretrieve(url, output_path)

        # Get file size
        file_size = os.path.getsize(output_path)
        message = f"File downloaded successfully to {output_path} ({file_size} bytes)"

        return {
            "success": True,
            "file_path": output_path,
            "file_size": file_size,
            "message": message,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def calculate_hash(file_path: str, hash_type: str = "sha256") -> Dict[str, Any]:
    """
    Calculate the hash of a file.

    Args:
        file_path: Path to the file
        hash_type: Type of hash to calculate (sha256, md5, etc.)

    Returns:
        Dict[str, Any]: Hash result
    """
    try:
        if not os.path.exists(file_path):
            return {"success": False, "error": f"File not found: {file_path}"}

        if hash_type.lower() == "sha256":
            hash_func = hashlib.sha256()
        elif hash_type.lower() == "md5":
            hash_func = hashlib.md5()
        else:
            return {"success": False, "error": f"Unsupported hash type: {hash_type}"}

        with open(file_path, "rb") as f:
            # Read in chunks to handle large files
            for chunk in iter(lambda: f.read(4096), b""):
                hash_func.update(chunk)

        hash_value = hash_func.hexdigest()

        return {
            "success": True,
            "hash_type": hash_type,
            "hash_value": hash_value,
            "file_path": file_path,
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def extract_archive(archive_path: str, output_dir: str) -> Dict[str, Any]:
    """
    Extract an archive file.

    Args:
        archive_path: Path to the archive file
        output_dir: Directory to extract to

    Returns:
        Dict[str, Any]: Extraction result
    """
    try:
        if not os.path.exists(archive_path):
            return {"success": False, "error": f"Archive not found: {archive_path}"}

        # Create the output directory if it doesn't exist
        os.makedirs(output_dir, exist_ok=True)

        # Determine the archive type and extract accordingly
        if archive_path.endswith((".zip", ".ZIP")):
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                zip_ref.extractall(output_dir)
                extracted_files = zip_ref.namelist()
        elif archive_path.endswith((".tar.gz", ".tgz")):
            with tarfile.open(archive_path, "r:gz") as tar_ref:
                tar_ref.extractall(output_dir)
                extracted_files = tar_ref.getnames()
        elif archive_path.endswith((".tar.bz2", ".tbz2")):
            with tarfile.open(archive_path, "r:bz2") as tar_ref:
                tar_ref.extractall(output_dir)
                extracted_files = tar_ref.getnames()
        elif archive_path.endswith((".tar")):
            with tarfile.open(archive_path, "r:") as tar_ref:
                tar_ref.extractall(output_dir)
                extracted_files = tar_ref.getnames()
        else:
            return {
                "success": False,
                "error": f"Unsupported archive format: {archive_path}",
            }

        return {
            "success": True,
            "archive_path": archive_path,
            "output_dir": output_dir,
            "file_count": len(extracted_files),
            "files": extracted_files[
                :10
            ],  # Return only the first 10 files to avoid overwhelming the response
            "message": f"Archive extracted successfully to {output_dir} ({len(extracted_files)} files)",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def inspect_archive(archive_path: str) -> Dict[str, Any]:
    """
    Inspect the contents of an archive file without extracting it.

    Args:
        archive_path: Path to the archive file

    Returns:
        Dict[str, Any]: Inspection result
    """
    try:
        if not os.path.exists(archive_path):
            return {"success": False, "error": f"Archive not found: {archive_path}"}

        # Determine the archive type and inspect accordingly
        if archive_path.endswith((".zip", ".ZIP")):
            with zipfile.ZipFile(archive_path, "r") as zip_ref:
                file_list = zip_ref.namelist()
                file_info = [
                    {
                        "name": info.filename,
                        "size": info.file_size,
                        "is_dir": info.is_dir(),
                        "date_time": f"{info.date_time[0]}-{info.date_time[1]:02d}-{info.date_time[2]:02d} {info.date_time[3]:02d}:{info.date_time[4]:02d}:{info.date_time[5]:02d}",
                    }
                    for info in zip_ref.infolist()
                ]
        elif archive_path.endswith((".tar.gz", ".tgz", ".tar.bz2", ".tbz2", ".tar")):
            # Determine the mode based on the extension
            if archive_path.endswith((".tar.gz", ".tgz")):
                mode = "r:gz"
            elif archive_path.endswith((".tar.bz2", ".tbz2")):
                mode = "r:bz2"
            else:
                mode = "r:"

            with tarfile.open(archive_path, mode) as tar_ref:
                file_list = tar_ref.getnames()
                file_info = [
                    {
                        "name": info.name,
                        "size": info.size,
                        "is_dir": info.isdir(),
                        "mode": info.mode,
                        "mtime": info.mtime,
                    }
                    for info in tar_ref.getmembers()
                ]
        else:
            return {
                "success": False,
                "error": f"Unsupported archive format: {archive_path}",
            }

        # Find executable files
        executable_files = []
        for info in file_info:
            if not info["is_dir"]:
                name = info["name"].lower()
                if name.endswith((".exe", ".bat", ".cmd", ".sh", ".app")) or (
                    "mode" in info
                    and info["mode"] & 0o100  # Check if the file is executable (Unix)
                ):
                    executable_files.append(info["name"])

        # Find potential binary directories
        binary_dirs = []
        for path in file_list:
            parts = path.split("/")
            if len(parts) > 1 and parts[-2].lower() in (
                "bin",
                "binaries",
                "exe",
                "executable",
            ):
                if parts[-2] not in binary_dirs:
                    binary_dirs.append("/".join(parts[:-1]))

        return {
            "success": True,
            "archive_path": archive_path,
            "file_count": len(file_list),
            "directory_count": sum(1 for info in file_info if info["is_dir"]),
            "files": file_list[
                :20
            ],  # Return only the first 20 files to avoid overwhelming the response
            "file_info": file_info[:20],  # Return only the first 20 file info objects
            "executable_files": executable_files,
            "binary_dirs": binary_dirs,
            "message": f"Archive inspection successful: {len(file_list)} files found",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}


@tool
def count_files(directory: str, recursive: bool = True) -> Dict[str, Any]:
    """
    Count the number of files in a directory.

    Args:
        directory: Path to the directory
        recursive: Whether to count files recursively

    Returns:
        Dict[str, Any]: Count result
    """
    try:
        if not os.path.exists(directory):
            return {"success": False, "error": f"Directory not found: {directory}"}

        if not os.path.isdir(directory):
            return {"success": False, "error": f"Not a directory: {directory}"}

        file_count = 0
        dir_count = 0
        file_list = []

        if recursive:
            for root, dirs, files in os.walk(directory):
                file_count += len(files)
                dir_count += len(dirs)
                for file in files:
                    file_list.append(os.path.join(root, file))
        else:
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_file():
                        file_count += 1
                        file_list.append(entry.path)
                    elif entry.is_dir():
                        dir_count += 1

        return {
            "success": True,
            "directory": directory,
            "file_count": file_count,
            "directory_count": dir_count,
            "files": file_list[
                :20
            ],  # Return only the first 20 files to avoid overwhelming the response
            "message": f"Found {file_count} files and {dir_count} directories in {directory}",
        }
    except Exception as e:
        return {"success": False, "error": str(e)}
