# Maya USD 2026 conda build recipe

This recipe packages the [Autodesk Maya USD plugin](https://github.com/Autodesk/maya-usd)
(maya-usd 0.35.0) for Maya 2026 as a conda package for use with AWS Deadline Cloud.

## Prerequisites

- The [Maya 2026 conda package](../maya-2026) must be built first, as this recipe depends on it.

## Downloading the source archive

Download the Maya USD installer from the GitHub releases page:

```
https://github.com/Autodesk/maya-usd/releases/download/v0.35.0/MayaUSD_0.35.0_Maya2026.3_Linux.run
```

Place the downloaded `MayaUSD_0.35.0_Maya2026.3_Linux.run` file in the `archive_files/` directory
used by the `submit-package-job` command.

## Building the package

From the `conda_recipes` directory, run:

```
./submit-package-job maya-usd-2026
```

## How it works

The build script extracts the self-extracting `.run` installer and installs the Maya USD
plugin files into the conda environment. A Maya module file (`maya-usd.mod`) is created
so that Maya automatically loads the plugin.
