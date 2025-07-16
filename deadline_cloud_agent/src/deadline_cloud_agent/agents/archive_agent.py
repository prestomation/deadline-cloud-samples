"""
Conda Package Agent for creating and managing conda packages for Deadline Cloud.
"""

from strands import Agent, tool
from strands_tools import file_read, http_request
import platform

from deadline_cloud_agent.tools import (
    file_write,
    file_copy,
    editor,
    download_file,
    calculate_hash,
    extract_archive,
    inspect_archive,
    web_search,
)
from deadline_cloud_agent.conversation_managers import (
    AgentPoweredConversationManager,
    BASE_SUMMARIZATION_PROMPT,
)


def build_archive_inspector_agent(
    model: str, callback_handler, conversation_manager
) -> Agent:

    prompt = """ Digital Content Creation Package Inspector
Primary Task: Analyze installers, archives, or package files for digital content creation software to identify executables suitable for rendering or batch processing operations.
Input: You will receive platforms, URLs, file paths, or uploaded files containing:

Zip archives
Installers (.exe, .msi, .dmg, .pkg, etc.)
Compressed packages (.tar.gz, .7z, etc.)
Directory structures

Core Responsibilities:

Executable Identification: Locate and identify the most likely executable(s) for rendering operations within the package

If multiple candidates exist, list all with detailed analysis
Explain the purpose and likely use case for each executable
Prioritize based on rendering/batch processing relevance
For maximum efficiency, whenever you need to perform multiple independent operations, invoke all relevant tools simultaneously rather than sequentially.



Usage Documentation: For each identified executable, provide:

Sample command-line arguments for typical rendering tasks
Explanation of key parameters and their functions
Common workflow patterns or usage scenarios
CPU/GPU support, Performance, resolution, frame number/range  and other rendering-related parameters supported by the Application


Verification Commands: Supply test commands that:

Display help/usage information (--help, -h, /?, etc.)
Show version information
Perform basic functionality checks
Validate successful installation



Research Protocol: When encountering unfamiliar software:

Research the specific application thoroughly
Understand its architecture and typical usage patterns
Avoid generic templates - provide software-specific guidance
Focus on actual rendering/processing capabilities


File Handling:

For archives: Inspect contents without extraction when possible
For cross-platform packages: Note compatibility limitations



Output Format:

Identified Executables: List with full paths and descriptions
Recommended Usage: Command examples with parameter explanations
Test Commands: Verification steps for installation validation
Additional Notes: Platform compatibility, dependencies, or special considerations
You MUST note if the package is staticly linked or not based upon your analysis, and if it is not whether dependencies are included in the archive or not.

Edge Cases:

Multiple Candidates: Present options and request user disambiguation
Cross-Platform Issues: Clearly state when packages are incompatible with current system
Binary Incompatibility: Inform user when analysis is impossible due to platform mismatch

Research Approach: Be thorough and creative. Understand each package's unique characteristics rather than applying generic solutions. 
"""

    prompt += f"The current system is {platform.system()}. Do not try to run the package if it's incompatible for this platform. Instead learn about what's given to you for the target platform. "

    summary_prompt = (
        BASE_SUMMARIZATION_PROMPT
        + """
    The messages you summarize are for an agent to understand the structure and commandline arguments of a software package archive or installer.
    When summarizing you must keep information that will help this agent pick up where it left off. Keep any key insights, like valid command line parameters and their formats,
    the location of key binaries in the archive, the location on disk where archives are already extracted, the original query including software name/version/platform/package URLs/
    DO NOT include in your summary tool invocations/results that are intermediate steps towards the goal ."""
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
            download_file,
            calculate_hash,
            extract_archive,
            inspect_archive,
            web_search,
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
    def archive_agent(query: str) -> dict:
        """
        Examines a package installer or archive to understand which executable should be used for rendering or batch processing on Deadline Cloud
        Provide this agent with the URL or path to the archive/installer, platform information, package build queue name, and any additional information provided by the user.
        If this agent provides ambiguity about this package, you MUST ask the user to disambiguate further and relay this information to this archive inspector agent.
        If the user asks to add additional command line arguments, you MUST verify with this archive_agent if the arguments are valid
        You MUST confirm the output command and arguments with the user, giving them an opportunity to modify them

        """
        print(f"ARCHIVE_AGENT: {query}")
        return agent(query)

    archive_agent.agent = agent
    return archive_agent
