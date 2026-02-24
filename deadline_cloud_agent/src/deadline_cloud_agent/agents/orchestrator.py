"""
Orchestrator Agent for coordinating the Deadline Cloud package creation process.
"""

from typing import Dict, Any, Optional
from strands import Agent
from strands_tools.utils.user_input import get_user_input


from deadline_cloud_agent.agents.conda_agent import build_agent
from deadline_cloud_agent.agents.archive_agent import build_archive_inspector_agent
from deadline_cloud_agent.agents.openjd_agent import build_open_jd_template_agent
from strands.agent.conversation_manager import SlidingWindowConversationManager
from deadline_cloud_agent.tools import (
    download_file,
)
import uuid
import os
import json


class OrchestratorAgent:
    """
    Orchestrator Agent that coordinates the overall workflow and communicates with the user.

    This agent is responsible for:
    - Collecting parameters from the user
    - Coordinating the workflow between specialized agents
    - Providing high-level progress updates
    - Handling error recovery
    """

    prompt = """You are a specialized assistant that creates Conda packages and AWS Deadline Cloud job templates for rendering software. Your goal is to streamline the process from software installation to a working render job template.
Primary Workflow:

Think step by step
For maximum efficiency, whenever you need to perform multiple independent operations, invoke all relevant tools simultaneously rather than sequentially.

Gather software information from the user
Understand software installation/package usage information using the archive_agent tool
Build and test a Conda package using the conda_package_agent tool
Create and test a job template using the job_template_agent tool
Test the job and provide verification instructions
Iterate on failures until both package and template work correctly

Information Gathering Process:
Start by asking for the installer location (URL or local file path). From the installer filename or path, intelligently infer:

Software name
Version number
Platform compatibility

Only ask for details that cannot be reasonably inferred or are ambiguous. Always confirm your inferences with the user before proceeding.
Collection Sequence (ask ONE question at a time):

Installer location
Confirm inferred software details (name, version, platform)
Sample scene URL or file path
Queue name for job submission
Final confirmation of all parameters

Critical Requirements:

Version formatting: Remove dashes and extra signifiers (beta, alpha, etc.). Use only Major.Minor.Patch format (e.g., "1.0.1")
Single questions: Ask one question at a time and wait for response
No repetition: Don't repeat introductions or previously asked questions
Conversational efficiency: Be friendly but focused

File Organization:
After gathering parameters:

Download installer to: conda_recipes/archive_files/{installer-file-name}
Download sample scene to: conda_recipes/archive_files/{sample-file-name}
Instruct all agents to use temp/ for temporary files
Create package recipe in: conda_recipes/{software-name}-{major-version}.{minor-version}
Create job bundle in: job_bundles/{software-name}-{major-version}.{minor-version}
Place sample data in: job_bundles/{software-name}-{major-version}.{minor-version}/sample/

Agent Coordination:

Use archive_inspector tool to determine executable and batch render parameters
You MUST confirm the executable arguments with the user. If they are not, relay that information back to archive_inspector to update and validate any change according to the agent's knowledge
If the user asked to add an argument, you MUST query archive_inspector to validate these arguments. Only use these arguments if archive_inspector confirms they are valid.
You MUST include ALL original parameters and created file paths to every subagent. 
You MUST include all URLs provided by the user to all subagent queries.
Include any intermediate findings (extracted files, discovered executables, etc.)
If any agent tool response includes a question you don't know the answer to, relay the question to the user.
Relay work summaries between agents to maintain context

Whenever any agent tool is invoked, include parameters like the following:
<agent-input>
{
    "original_package_url": "https://download.com/package.zip" # Original url provided by user
    "package_archive": "conda_recipes/archive_files/{package_name}.zip", # download location of this package
    "package_archive_unzipped": "conda_recipes/archive_files/{software-{major}.{minor}.{patch}", # unzipped package
    "sample_url": "https://download.com/sample.zip" # Original sample,
    "sample_archive": "conda_recipes/archive_files/{sample_name}.zip"m # Original sample archive, downloaded
    "sample_archive_unzipped": "conda_recipes/archive_files/{sample_name}/", # Original sample archive, unzipped
    "binary_test": "my_exe -h", # output of archive_agent, the command used to test conda package is built correctly
    "binary_render": "my_exe -resolution WIDTHxHEIGHT -o output.jpg input.project" # output of archive_agent, the command to pass to openjd_agent
}
</agent-input> 



When using the openjd_agent tool you MUST pass on the command and all argument information, 
the job directory of <directory>job_bundles/{software-name}-{major-version}-{minor-version}</directory>
the sample ZIP and URL and the Queue name.

Error Handling:
If job template or package testing fails, report errors back to the appropriate agent (conda_package_agent or job_template_agent) to update the recipe and retry until successful.
Communication Style:
Be conversational but efficient. Provide clear status updates and explain what you're doing at each step. Always inform the user where files will be saved and how to verify the final output.
    

    """

    def __init__(
        self, model: Optional[str] = None, callback_handler=None, session_id=None
    ):
        """
        Initialize the Orchestrator Agent.

        Args:
            model: The model to use for the agent (optional)
            tools: Additional tools to make available to the agent (optional)
        """
        self.parameters: Dict[str, Any] = {}
        self.session_id = uuid.uuid4()

        conversation_manager = SlidingWindowConversationManager(
            window_size=100,
        )
        self.conda_agent = build_agent(model, callback_handler, conversation_manager)
        self.archive_inspector_agent = build_archive_inspector_agent(
            model, callback_handler, conversation_manager
        )
        self.openjd_agent = build_open_jd_template_agent(
            model, callback_handler, conversation_manager
        )

        # Define the default tools
        tools = [
            download_file,
            self.conda_agent,
            self.archive_inspector_agent,
            self.openjd_agent,
        ]

        self.agent = Agent(
            model=model,
            tools=tools,
            system_prompt=self.prompt,
            load_tools_from_directory=False,
            callback_handler=callback_handler,
            conversation_manager=conversation_manager,
        )
        if session_id is not None:
            session_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..",
                "_sessions",
                session_id,
            )
            agents = {
                "agent": self.agent,
                "conda": self.conda_agent.agent,
                "archive": self.archive_inspector_agent.agent,
                "openjd": self.openjd_agent.agent,
            }
            for name, agent in agents.items():
                path = f"{session_dir}/{name}.json"
                print(path)
                with open(path, "r") as f:
                    state = json.load(f)
                    messages = state["messages"]
                    agent.messages = messages

        # Combine default tools with any additional tools

    def run(
        self,
        prompt_override="Build and test a conda package and job template for the user",
    ) -> bool:
        """
        Run the package creation workflow.

        Returns:
            bool: True if the workflow completed successfully, False otherwise
        """

        self.agent(prompt=prompt_override)
        try:
            while True:
                try:
                    user_input = get_user_input("\n~ ")
                    if user_input.lower() in ["exit", "quit"]:
                        print("Goodbye")
                        break

                    if user_input.strip():

                        # Combine welcome text with base system prompt
                        self.agent(user_input)

                except (KeyboardInterrupt, EOFError):
                    print("goodbye")
                    break
                except Exception as e:
                    print(f"\nError: {str(e)}")

            return True
        finally:
            # Create _sessions directory in the root of the agent project dir

            session_dir = os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "..",
                "..",
                ".." "_sessions",
                str(self.session_id),
            )

            os.makedirs(session_dir, exist_ok=True)
            agents = {
                "agent": self.agent,
                "conda": self.conda_agent.agent,
                "archive": self.archive_inspector_agent.agent,
                "openjd": self.openjd_agent.agent,
            }
            metrics = {}
            for name, agent in agents.items():
                state = {
                    "messages": agent.messages,
                    "system_prompt": agent.system_prompt,
                }
                metrics[name] = agent.event_loop_metrics.accumulated_usage

                with open(f"{session_dir}/{name}.json", "w") as f:
                    json.dump(state, f)
            print(f"Session {self.session_id} saved to {session_dir}.")
            print(
                "Please include this directory with any bug reports but be aware it contains your entire conversation and changes made by the agent"
            )

            print("Token Usage:")
            total_input = 0
            total_output = 0
            for name, usage in metrics.items():
                print(f"{name} - {usage['inputTokens']} input tokens used")
                print(f"{name} - {usage['outputTokens']} output tokens used")
                total_input += usage["inputTokens"]
                total_output += usage["outputTokens"]

            input_cost = total_input / 1000 * 0.003
            output_cost = total_output / 1000 * 0.015
            print(
                f"{total_input + total_output} tokens used at a cost of ${input_cost + output_cost:.2f} if using Claude Sonnet 3.7/4"
            )
