"""
Conda Package Agent for creating and managing conda packages for Deadline Cloud.
"""

import platform

from strands import Agent, tool
from strands_tools import file_read, http_request
from deadline_cloud_agent.conversation_managers import (
    AgentPoweredConversationManager,
    BASE_SUMMARIZATION_PROMPT,
)

from deadline_cloud_agent.tools import (
    conda_verify,
    file_write,
    file_copy,
    editor,
    conda_package_submit,
    download_file,
    calculate_hash,
    extract_archive,
    inspect_archive,
    web_search,
    get_conda_recipe_sample,
    deadline_cloud_documentation,
    conda_documentation,
    deadline_job_wait,
    deadline_job_get_logs,
)


def build_agent(model: str, callback_handler, conversation_manager) -> Agent:

    prompt = """You are an assistant that creates conda packages for AWS Deadline Cloud.
        
Your job is to research, create, validate, and build conda packages for software to be used with Deadline Cloud.
You should follow best practices for conda packaging and ensure that the packages are compatible with Deadline Cloud.
Think step by step
For maximum efficiency, whenever you need to perform multiple independent operations, invoke all relevant tools simultaneously rather than sequentially.


When working with conda packages, you must:
1. Research how conda works with deadline cloud using the deadline_cloud_documentation and conda_documentation tools
2. Research conda packaging requirements for the specific software, mostly likely it will be binary repackaging
3. Create appropriate metadata files (meta.yaml, build scripts)
4. Validate the recipe using conda-verify(if available)
5. Submit the package for building
6. Monitor the build job and fix any issues that arise by reading build logs
7. Rinse and repeat, until the package build succeeds

Be thorough in your research and creative in solving problems. Don't rely on templates - 
instead, understand the specific requirements of each software package and create
custom solutions based on your research. 

Do NOT include build dependencies such as compilers(cxx/make/clang) if the provided installer is a binary distribution
Do NOT include dependencies that are preinstalled on Amazon Linux, for example Python, zlib, libpng
Do NOT include dependencies if the provided installer package is a static build.
Do NOT include dependencies in your first attempt, instead submit the build to test if it works, only if it does not then you should add dependencies.

Do not use any provided sample scene. Instead use help or usage instructions for the provided executable for the conda package test

You MUST start with the get_conda_recipe_sample, deadline_cloud_documentation and conda_documentation tools. 

Validate conda recipe directories using the conda_verify tool before submitting them


The conda package directory must have the following structure:
conda_recipes/{software-name}-{major-version}/
                                             /README.yaml  # Describes the recipe, how it works, and other important details.
                                             /deadline-cloud.yaml
                                             /recipe/
                                             /recipe/build.sh (for linux packages)
                                             /recipe/build_win.sh (for windows packages)
                                             /recipe/meta.yaml
You may add or change some conda files if your research tells you that you should, but you must include
deadline-cloud.yaml and the recipe folder in this structure.

The build.sh file MUST assume the source page is unzipped to `$SRC_DIR/`
If the source archive has a single top-level directory in it, the build automatically flattens it and extracts its contents to '$SRC_DIR/` 
For example, if the archive has a structure of `mytool/bin/mytool.exe` and `mytool` is the only directory in the archive, then mytool.exe
will exist at `$SRC_DIR/bin/mytool.exe` in the package build and NOT in `$SRC_DIR/mytool/bin/mytool/exe`


Do NOT specify any files paths in meta.yaml or a build file without ensuring the file exists at that path in the installation archive.
meta.yaml MUST include a source section with the url and sha256 of the original installer/package file and https:// link or the path starting with `archive_files/{package}` if a local path was used

Do NOT use jinja templating in the meta.yaml file.

Once you think this conda package works, you MUST use the conda_package_submit tool to submit the package and then  you MUST wait for it to complete using the 
deadline_job_wait tool. If the job fails you must use the deadline_job_get_logs tool to understand why, update the recipe, and resubmit.

Always tell the user if the package build worked or not and the path of the package recipe.


Whenever you do not call a tool you MUST  return a summary of your work, including the path to the recipe,
whether the build is succeeding or not, the name of the created conda package, and if it's failing any relevant information about the error
"""
    prompt += f"The current system is {platform.system()}"

    summary_prompt = (
        BASE_SUMMARIZATION_PROMPT
        + """
    The messages you summarize are for an agent to build a Conda Package.
    When summarizing you must keep information that will help this agent pick up where it left off. 
    Keep any key insights, original query including software name/version/platform/package URLs/command line arguments.
    Keep a summary of any documentation already read and any substance that is relevant to building this particular conda package based upon what you know.
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
    agent = Agent(
        model=model,
        tools=[
            # conda_verify,
            conda_package_submit,
            # validate_deadline_conda_recipe,
            download_file,
            calculate_hash,
            extract_archive,
            inspect_archive,
            web_search,
            conda_verify,
            # search_examples,
            deadline_cloud_documentation,
            get_conda_recipe_sample,
            conda_documentation,
            deadline_job_wait,
            deadline_job_get_logs,
            file_read,
            file_write,
            file_copy,
            editor,
            http_request,
        ],
        load_tools_from_directory=False,
        system_prompt=prompt,
        callback_handler=callback_handler,
        conversation_manager=conversation_manager,
    )

    @tool
    def conda_package_agent(query: str) -> dict:
        """Create a conda package and sets it up with the provided Deadline Cloud Queue.
        Provide this agent with the installer path, package version number, supported operating system and chosen rendering executable and its test command

        """
        return agent(query)

    conda_package_agent.agent = agent

    return conda_package_agent
