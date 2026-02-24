# Maya USD 2026 conda build recipe

This recipe packages the [Autodesk Maya USD plugin](https://github.com/Autodesk/maya-usd)
(maya-usd 0.32.0) for Maya 2026 as a conda package for use with AWS Deadline Cloud.

Note: MayaUSD 0.32.0 is used instead of newer versions because it was built for Maya 2026.1,
which is ABI-compatible with the Maya 2026.0 conda package in the deadline-cloud channel.
Newer MayaUSD versions (0.33+) require Maya 2026.2+ and use a dual-USD installation that
is not compatible with Maya 2026.0.

## Prerequisites

- The [Maya 2026 conda package](../maya-2026) must be built first, as this recipe depends on it.

## Downloading the source archive

Download the Maya USD installer from the GitHub releases page:

```
https://github.com/Autodesk/maya-usd/releases/download/v0.32.0/MayaUSD_0.32.0_Maya2026.1_Linux.run
```

Place the downloaded `MayaUSD_0.32.0_Maya2026.1_Linux.run` file in the `archive_files/` directory
used by the `submit-package-job` command.

## Building the package

From the `conda_recipes` directory, run:

```
./submit-package-job maya-usd-2026
```

## How it works

The build script extracts the self-extracting `.run` installer and installs the Maya USD
plugin files into the conda environment. A Maya module file is copied to a location on
Maya's default `MAYA_MODULE_PATH`, and an activation script sets `LD_LIBRARY_PATH` so
the plugin's shared libraries can be found at runtime.

## Version compatibility

| MayaUSD | Maya required | USD versions | Notes |
|---------|--------------|--------------|-------|
| 0.32.0  | 2026.0/2026.1 | 24.11 (single) | ✅ Compatible with deadline-cloud Maya 2026.0 |
| 0.33.0+ | 2026.2+       | 24.11 + 25.05 (dual) | ❌ Requires `MULTI_USD_VERSION` env var (Maya 2026.2+ only) |
| 0.35.0  | 2026.3        | 24.11 + 25.05 (dual) | ❌ Ufe ABI mismatch with Maya 2026.0 (`undefined symbol: _ZNK6Ufe_v614TypedAttributeIjE4typeB5cxx11Ev`) |

To use MayaUSD 0.33+, the `maya` conda package in the `deadline-cloud` channel must first
be updated to Maya 2026.3.
