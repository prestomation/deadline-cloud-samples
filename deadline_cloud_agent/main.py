#!/usr/bin/env python3
"""
Main entry point for the Deadline Cloud Package Creator.

This script provides a command-line interface for creating conda packages
for AWS Deadline Cloud using the Strands Agents SDK.
"""

import argparse
import logging
from botocore.config import Config
import boto3, botocore
from strands.models import BedrockModel


import sys
from deadline_cloud_agent.agents.orchestrator import OrchestratorAgent
from deadline_cloud_agent.agents.callback_handler import callback_handler

logger = logging.getLogger(__name__)


def handle_uncaught_exception(**kwargs):
    """
    Hook function that runs when an uncaught exception occurs in botocore

    Args:
        error: The uncaught exception
        kwargs: Additional context provided by botocore
    """
    # Get relevant information from the kwargs
    operation = kwargs.get("operation")
    params = kwargs.get("request_dict", {})
    response = kwargs.get("response", {})
    error = kwargs.get("caught_exception")

    # "response', 'endpoint', 'operation', 'attempts', 'caught_exception', 'request_dict', 'event_name"

    # Log the error with context
    if error:
        print(error)
        logger.error(
            f"Operation: {operation}\n" f"Parameters: {params}\n" f"Error: {response}",
            exc_info=True,
        )


botocore_logger = logging.getLogger("botocore.retryhandler")
botocore_logger.setLevel(logging.DEBUG)


def setup_logging(verbose: bool = False) -> None:
    """
    Set up logging configuration.

    Args:
        verbose: Whether to enable verbose logging
    """
    log_level = logging.DEBUG if verbose else logging.INFO

    # Configure logging
    logging.basicConfig(
        level=log_level,
        format="%(levelname)s | %(name)s | %(message)s",
        handlers=[logging.StreamHandler()],
    )

    # Enable Strands debug logs if verbose
    if verbose:
        logging.getLogger("strands").setLevel(logging.DEBUG)


def parse_args() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        The parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Create conda packages for AWS Deadline Cloud"
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable verbose logging"
    )

    parser.add_argument("--model", type=str, help="Model to use for the agents")

    return parser.parse_args()


def main() -> int:
    """
    Main entry point for the Deadline Cloud Package Creator.

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    # Parse command line arguments
    args = parse_args()

    # Set up logging
    setup_logging(args.verbose)

    print("Deadline Cloud Package Creator")
    print("=============================")
    print("This Agent uses Amazon Bedrock using the active AWS Profile.")
    print(
        "Be aware this agent will charge Bedrock LLM inference costs to your AWS account and will submit jobs to your Deadline Cloud farm"
    )
    print(
        "Agents can sometimes do unexpected things, please do not continue without understanding the risks"
    )

    model_id = args.model or "us.anthropic.claude-3-7-sonnet-20250219-v1:0"
    core_session = botocore.session.get_session()
    session = boto3.Session(botocore_session=core_session)

    # Register the hook for the 'needs-retry' event
    core_session.register("needs-retry", handle_uncaught_exception)

    additionalModelRequestFields = {}
    if "claude-sonnet-4" in model_id:
        additionalModelRequestFields = {
            "anthropic_beta": ["interleaved-thinking-2025-05-14"],
            "reasoning_config": {"type": "enabled", "budget_tokens": 8000},
        }
    elif "claude-3-7-sonnet" in model_id:
        additionalModelRequestFields = {
            "thinking": {"type": "enabled", "budget_tokens": 2000},
        }

    model = BedrockModel(
        model_id=model_id,
        boto_session=session,
        boto_client_config=Config(
            read_timeout=900,
            connect_timeout=900,
            retries=dict(max_attempts=100, mode="adaptive"),
        ),
        additionalModelRequestFields=additionalModelRequestFields,
    )

    orchestrator = OrchestratorAgent(model=model, callback_handler=callback_handler)

    # Run the orchestrator
    success = orchestrator.run()

    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())
