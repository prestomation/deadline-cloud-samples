# Deadline Cloud Package Creator

A CLI AI agent for creating conda packages and AWS Deadline Cloud job templates for rendering software. This tool streamlines the process from software installation to a working render job template.

## Overview

The Deadline Cloud Package Creator is a multi-agent architecture that leverages Amazon Bedrock to automate the creation of conda packages and job templates for AWS Deadline Cloud. The system consists of several specialized agents working together:

- **Orchestrator Agent**: Coordinates the overall workflow and communicates with the user
- **Archive Inspector Agent**: Analyzes software installers to determine executable paths and parameters
- **Conda Package Agent**: Builds and tests conda packages for rendering software
- **OpenJD Template Agent**: Creates and tests job templates for Deadline Cloud

## Prerequisites

- AWS credentials configured (via AWS CLI or environment variables)
- Amazon Bedrock access with permissions to use Claude models(or whatever model you pick)
- Python 3.13 or higher

## Installation

```bash
# Clone the repository
git clone https://github.com/aws-deadline/deadline-cloud-samples.git
cd deadline-cloud-samples/deadline_cloud_agent

# Install dependencies
pip install -e .
```

## Usage

**Important**: Always run the agent from the `deadline-cloud-samples` directory (one folder up from the agent directory) to ensure recipes and bundles are written to the correct locations.

```bash
# From the deadline-cloud-samples directory
cd deadline-cloud-samples
python -m deadline_cloud_agent.main [OPTIONS]
```

### Command Line Arguments

- `--verbose`, `-v`: Enable verbose logging
- `--model MODEL`: Specify the Bedrock model to use (default: Claude 3.7 Sonnet)

## How It Works

1. The agent collects information about the rendering software from the user
2. It analyzes the software installer to determine executable paths and parameters
3. It builds and tests a conda package for the software
4. It creates and tests a job template for Deadline Cloud
5. It provides verification instructions and iterates on failures

## File Organization

- Conda recipes are created in: `conda_recipes/{software-name}-{major-version}.{minor-version}`
- Job bundles are created in: `job_bundles/{software-name}-{major-version}.{minor-version}`
- Sample data is placed in: `job_bundles/{software-name}-{major-version}.{minor-version}/sample/`

## AWS Costs

This agent uses Amazon Bedrock for LLM inference, which will incur costs on your AWS account. It will also submit jobs to your Deadline Cloud farm, which may incur additional costs.

## TODOs

The following items are marked as TODOs in the codebase:

1. **OpenJD Tools**: Improve exposure of functionality through the OpenJD Python API
   - File: `src/deadline_cloud_agent/tools/openjd_tools.py`

2. **Conda Tools**:
   - Implement automatic detection of package availability on conda-forge or Deadline Cloud
   - Add support for platforms other than Linux
   - Refactor the submit package job script into a single Python library
   - File: `src/deadline_cloud_agent/tools/conda_tools.py`

## Security Note

Agents can sometimes do unexpected things. Please do not use this tool without understanding the risks involved.
