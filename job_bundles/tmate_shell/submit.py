#!/usr/bin/env python
"""
Submits a tmate shell job to AWS Deadline Cloud and waits for the SSH connection string.

Usage:
    python submit.py [timeout_seconds]

Requirements:
    * Python 3.8+
    * The `deadline` library installed (comes with the Deadline Cloud CLI).
    * ssh-keygen available (included with Git on Windows).
"""
import os
import re
import subprocess
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
KEY_FILE = SCRIPT_DIR / ".tmate_key"


def generate_keypair():
    """Generate an ephemeral ed25519 keypair if one doesn't exist."""
    if KEY_FILE.exists():
        return
    subprocess.run(
        ["ssh-keygen", "-t", "ed25519", "-f", str(KEY_FILE), "-N", ""],
        check=True,
        capture_output=True,
    )
    print(f"Generated ephemeral keypair: {KEY_FILE}")


def submit_job(timeout: int) -> str:
    """Submit the tmate shell job and return the job ID."""
    pub_key_text = Path(str(KEY_FILE) + ".pub").read_text().strip()

    result = subprocess.run(
        [
            "deadline", "bundle", "submit", str(SCRIPT_DIR),
            "-p", f"Timeout={timeout}",
            "-p", f"AuthorizedKey={pub_key_text}",
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    # Job ID is the last line of output
    for line in reversed(result.stdout.strip().splitlines()):
        match = re.match(r"^(job-[0-9a-f]+)$", line.strip())
        if match:
            return match.group(1)
    raise RuntimeError(f"Could not find job ID in output:\n{result.stdout}")


def get_logs(job_id: str) -> str:
    """Fetch job logs, returning empty string on failure."""
    try:
        result = subprocess.run(
            ["deadline", "job", "logs", "--job-id", job_id],
            capture_output=True,
            text=True,
            timeout=30,
        )
        return result.stdout
    except Exception:
        return ""


def main():
    timeout = int(sys.argv[1]) if len(sys.argv) > 1 else 3600

    generate_keypair()

    print(f"Submitting tmate shell job (timeout: {timeout}s)...")
    job_id = submit_job(timeout)
    print(f"Job submitted: {job_id}")
    print()
    print("Waiting for connection info", end="", flush=True)

    for _ in range(120):
        logs = get_logs(job_id)
        for line in logs.splitlines():
            # Log lines have a timestamp prefix like [2026-02-26T...] SSH: ssh ...
            match = re.search(r"SSH: ssh (.+)$", line)
            if match:
                ssh_target = match.group(1).strip()
                print("\n")
                print("=== TMATE SESSION READY ===")
                print()
                print("Connect with:")
                print(f"  ssh -i {KEY_FILE} {ssh_target}")
                return
        print(".", end="", flush=True)
        time.sleep(5)

    print()
    print(f"Timed out waiting. Check logs: deadline job logs --job-id {job_id}")
    sys.exit(1)


if __name__ == "__main__":
    main()
