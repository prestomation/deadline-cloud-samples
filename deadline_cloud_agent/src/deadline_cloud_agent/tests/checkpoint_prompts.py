# A sample prompt created by the orchestrator post-archive agent with a directive prefix
# That is, skip to the conda stuff
conda_prompt = """
Skip directly to the conda_agent
Package details:
- original_package_url: https://github.com/appleseedhq/appleseed/releases/download/2.1.0-beta/appleseed-2.1.0-beta-0-g015adb503-linux64-gcc74.zip
- package_archive: conda_recipes/archive_files/appleseed-2.1.0-beta-0-g015adb503-linux64-gcc74.zip
- package_archive_unzipped: conda_recipes/archive_files/appleseed-2.1.0-beta-0-g015adb503-linux64-gcc74
- sample_url: https://github.com/appleseedhq/appleseed-scenes/releases/download/2.1.0-beta/rose_1.4.zip
- sample_archive: conda_recipes/archive_files/rose_1.4.zip
- software_name: appleseed
- version: 2.1.0
- platform: Linux 64-bit
- queue_name: CondaQueue
- binary_test: appleseed.cli --version
- binary_render: appleseed.cli -o output.exr scene.appleseed

Package specifications:
- Main executable: appleseed.cli (located in bin/ directory)
- Test command: appleseed.cli --version
- Rendering command: appleseed.cli -o output.exr scene.appleseed
- Package includes extensive dynamic libraries in lib/ directory (135+ .so files)
- Requires LD_LIBRARY_PATH setup for proper library loading
- Self-contained distribution with all dependencies bundled
- CPU-based renderer with multi-threading support

Please create the conda recipe in conda_recipes/appleseed-2.1/ and build the package for the CondaQueue.

"""

# Sample final output:
"""
### Build Result:
✅ **SUCCESS** - The package built successfully after debugging the directory structure issue. The conda package is now available in the Deadline Cloud conda channel and ready for use in rendering workflows.

The package provides a complete Appleseed rendering environment that can be easily deployed on Deadline Cloud workers for distributed rendering tasks.Notification: Notify - conda_package_agent completed in 2455.04s
Perfect! The conda package for Appleseed has been successfully created and built. Here's what was accomplished:

## ✅ Conda Package Creation Complete

### Package Details:
- **Software:** Appleseed 2.1.0
- **Platform:** Linux 64-bit  
- **Recipe Location:** `conda_recipes/appleseed-2.1/`
- **Status:** Successfully built and tested

### Key Features Implemented:
1. **Self-contained distribution** - All 135+ shared libraries properly bundled in `/opt/appleseed/lib/`
2. **Environment management** - Automatic `LD_LIBRARY_PATH` configuration via conda activation scripts
3. **Complete tool suite** - Main renderer `appleseed.cli` plus all supporting utilities
4. **Proper testing** - Verified with `appleseed.cli --version` command

### Technical Implementation:
- **Binary repackaging approach** - No compilation needed, just redistribution
- **Library path resolution** - Uses conda environment scripts for proper .so file loading
- **Deadline Cloud integration** - Package is now available in the CondaQueue conda channel
- **Production ready** - Follows AWS Deadline Cloud conda packaging best practices

The package is now ready for use in AWS Deadline Cloud rendering workflows. The conda package agent successfully handled the complex library dependencies and created a robust, self-contained rendering environment that can be deployed across your render farm.

"""


openjd_prompt = """

Please skip to the openjd_agent with the following query:
Package Details:
- original_package_url: https://github.com/appleseedhq/appleseed/releases/download/2.1.0-beta/appleseed-2.1.0-beta-0-g015adb503-linux64-gcc74.zip
- package_archive: conda_recipes/archive_files/appleseed-2.1.0-beta-0-g015adb503-linux64-gcc74.zip
- package_archive_unzipped: conda_recipes/archive_files/appleseed-2.1.0-beta-0-g015adb503-linux64-gcc74
- sample_url: https://github.com/appleseedhq/appleseed-scenes/releases/download/2.1.0-beta/rose_1.4.zip
- sample_archive: conda_recipes/archive_files/rose_1.4.zip
- sample_archive_unzipped: conda_recipes/archive_files/rose_1.4/
- software_name: appleseed
- version: 2.1.0
- platform: Linux 64-bit
- queue_name: CondaQueue
- binary_test: appleseed.cli --version
- binary_render: appleseed.cli -o output.exr scene.appleseed

Job Template Requirements:
- Create job template in directory: job_bundles/appleseed-2.1/
- Use conda package name: appleseed (version 2.1.0) that was successfully built
- Main rendering command: appleseed.cli -o output.exr scene.appleseed
- CPU-based renderer with multi-threading support
- Outputs EXR format images
- Place sample scene data in: job_bundles/appleseed-2.1/sample/

Template Features Needed:
- Support for scene file input parameter
- Output file path parameter
- Thread count parameter for multi-threading
- Frame range support if applicable
- Proper file path handling for input/output
- Integration with the conda package environment

The conda package has been successfully created and is available in the CondaQueue conda channel.

"""
