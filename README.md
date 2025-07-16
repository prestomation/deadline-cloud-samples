# Deadline Cloud Agent

A Strands CLI agent for creating conda packages for AWS Deadline Cloud.

## Overview

This tool automates the process of creating conda packages for AWS Deadline Cloud, including:

1. Setting up the necessary conda package metadata
2. Creating job templates for rendering software packages
3. Building, testing, and validating the package
4. Iterating as needed to fix any issues that arise

## Installation

```bash
# Install from the local directory
pip install -e .
```

## Usage

```bash
# Run the agent
deadline-cloud-agent

# Enable verbose logging
deadline-cloud-agent --verbose
```

## Development

This project uses the Strands Agents SDK to implement a multi-agent system for package creation:

- **Orchestrator Agent**: Coordinates the workflow and communicates with the user
- **Conda Package Agent**: Handles conda package creation and validation
- **Job Template Agent**: Creates and validates OpenJD job templates

### Project Structure

```
deadline_cloud_agent/
├── __init__.py
├── main.py
├── agents/
│   ├── __init__.py
│   ├── orchestrator.py
│   ├── conda_agent.py
│   └── job_template_agent.py
└── tools/
    ├── __init__.py
    ├── deadline_tools.py
    ├── conda_tools.py
    └── archive_tools.py
```
