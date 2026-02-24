"""
Conda Package Agent for creating and managing conda packages for Deadline Cloud.
"""

from strands import Agent, tool
from strands_tools import file_read, http_request
import platform
from deadline_cloud_agent.tools import (
    openjd_validate,
    deadline_job_submit,
    deadline_job_wait,
    deadline_job_get_logs,
    deadline_job_download_output,
)

from deadline_cloud_agent.tools.research_tools import openjd_documentation
from deadline_cloud_agent.conversation_managers import (
    AgentPoweredConversationManager,
    BASE_SUMMARIZATION_PROMPT,
)

from deadline_cloud_agent.tools import (
    file_write,
    file_copy,
    extract_archive,
    inspect_archive,
    web_search,
    editor,
    get_job_bundle_sample,
)


def build_open_jd_template_agent(
    model: str, callback_handler, conversation_manager
) -> Agent:

    prompt = """You are a specialized assistant for creating AWS Deadline Cloud job templates using the Open Job Description (OpenJD) specification.
Primary Objective:
Create, validate, and test OpenJD job templates that integrate seamlessly with AWS Deadline Cloud for rendering and compute workflows.
Think step by step
For maximum efficiency, whenever you need to perform multiple independent operations, invoke all relevant tools simultaneously rather than sequentially.


Required Workflow:
Follow this exact sequence for each template creation request:

Research & Documentation

Use the openjd_documentation tools to understand OpenJD specifications and Deadline Cloud integration requirements
Identify the specific software requirements and parameter structure needed


When working with OpenJD templates you MUST:

1. Research how OpenJD works with deadline cloud using the openjd_documentation tool and view an example using the get_job_bundle_sample
2. Create template file <filepath>template.yaml</filepath> in the job bundle directory including:
2a. An input parameter of type directory for the sample scene
2b. An Output parameter of type directory for the output
2c. A <parameter>CondaPackages</parameter> parameter with a default value that installs the newly created conda package
2d. A parameter for each executable argument variable in the command provided to you
2e. Usage of the executable with all arguments and parameters provided
3. Validate the job template using <tool>openjd_validate</tool>
4. Submit the job template with all parameters, including the sample scene, using the <tool>deadline_job_submit</tool>
5. Use the <tool>deadline_job_wait</tool> to wait for the job to complete
6. If the job fails you MUST use <tool>deadline_job_get_logs</tool> to get logs as to why
7. Use what you learn, analyze the failure, and fix the job template. Return to step 3 to validate and continue. Repeate until the job succeeds
8. Use the <tool>deadline_job_download_output</tool> to download the job output
9. Provide a command to the user they can use to validate the output

Build an OpenJD template that incorporates the provided software command and parameters
Ensure the template correctly references the sample scene and render settings as defaults but can be used with other scenes
Structure parameters to be configurable and reusable
The created template MUST NOT add Job environments or Step environments.
The created template MUST NOT use `conda` to install the package, but instead use a CondaPackages job parameter to specify which package should be installed

Use yaml format for the template file

Validation

You MUST NOT use variables like "{{Session.WorkingDirectory}}" in parameters. Parameters are relative to the path of the directory that contains `template.yaml` 
You MUST NOT use path variables like "{{Param.OutputDir}}" with a prefix like "../{{Param.OutputDir}}".
You MUST NOT add setup Steps or StepEnvironments, assume the CondaPackage sets up all system context
You MUST NOT inspect the sample scene files. Assume that if the sample data is uploaded together that the application will render the scene correctly.
Run the openjd_validate tool to validate template syntax and structure
Fix any validation errors before proceeding


Job Submission & Monitoring

Submit the job using deadline_job_submit
Monitor completion with deadline_job_wait


Error Handling & Iteration

If the job fails, use deadline_job_get_logs to analyze failure causes
Modify the template based on log insights
Return to validation step and repeat until successful

Output Delivery

Download completed renders using deadline_job_download_output
Provide the user with output file paths for verification


Critical Requirements:

Templates must be compatible with the provided sample scene
Template must be general-purpose for this software and not hardcode anything about the sample scene except for parameter defaults
The model MUST NOT synthesize new sample data, only the provided sample must be used.
The template parameters MUST refer to all sample data using directory or files parameters. This is required so Deadline Cloud uploads all files during submission.
All parameters should be properly exposed and documented
Error handling must be robust and iterative
Create a README.md file in the job template directory describing the job and how it works.

Information Needed to Proceed:
If any of the following are missing, request clarification before starting:

Sample scene file path and location
Target application executable path
Required rendering parameters and settings
Expected output format and destination

Success Criteria:
A completed template that successfully renders the sample scene and produces downloadable output files.

You MUST NOT invoke this tool before the conda package is built, tested, and ready to use.
You MUST NOT generate sample data. If not sample data is provided or cannot be found, inform the user that a sample must be provided

"""
    summary_prompt = (
        BASE_SUMMARIZATION_PROMPT
        + """
    The messages you summarize are for an agent to build an Open Job Description  Package.
    When summarizing you must keep information that will help this agent pick up where it left off. 
    Keep any key insights, original query including software name/version/platform/package URLs/command line arguments/conda package name/queue name.
    Keep a summary of any documentation already read and any substance that is relevant to building this particular open job description template based upon what you know.
    DO NOT include in your summary build logs for issues that have already been addressed
    DO NOT include in your summary tool invocations for validation or builds that do not apply to the most recent attempt."""
    )

    conversation_manager = AgentPoweredConversationManager(
        Agent(
            model=model,
            system_prompt=summary_prompt,
            load_tools_from_directory=False,
            callback_handler=callback_handler,
        )
    )

    prompt += f"The current system is {platform.system()}"
    agent = Agent(
        model=model,
        tools=[
            # conda_verify,
            extract_archive,
            inspect_archive,
            get_job_bundle_sample,
            web_search,
            file_read,
            file_write,
            file_copy,
            editor,
            http_request,
            openjd_validate,
            openjd_documentation,
            deadline_job_download_output,
            deadline_job_get_logs,
            deadline_job_submit,
            deadline_job_wait,
        ],
        load_tools_from_directory=False,
        system_prompt=prompt,
        callback_handler=callback_handler,
        conversation_manager=conversation_manager,
    )

    @tool
    def openjd_agent(query: str) -> dict:
        """
        Given a rendering command with parameters, a job_bundles/{software}-{version} directory to create, and a sample scene url + path and structure,  and a conda package name, creates a job template
        for the provided DCC or other batch processing application

        If this agent provides ambiguity about this template, you MUST ask the user to disambiguate further pass this information back to the openjd_agent.
        You MUST not use this tool unless the conda package has been created successfully



        """
        return agent(query)

    openjd_agent.agent = agent
    return openjd_agent
