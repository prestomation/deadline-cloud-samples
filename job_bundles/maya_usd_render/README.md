# Maya USD Render

## Background

The [Maya USD plugin (maya-usd)](https://github.com/Autodesk/maya-usd) enables working with Universal Scene Description (USD) files in Autodesk Maya. This job bundle renders USD scenes by importing them into Maya and rendering with Maya's software renderer.

## Job Summary

This job bundle renders a USD scene using Maya with the Maya USD plugin (`mayaUsdPlugin`).

To run it, you will need Maya and the Maya USD plugin available in the PATH in one of the following ways:

* As conda packages when your queue has a conda queue environment set up to provide virtual environments for jobs.
  * For more information see the developer guide section [Provide applications for your jobs.](https://docs.aws.amazon.com/deadline-cloud/latest/developerguide/provide-applications.html)
* Installed on the worker hosts that run the job. You can customize your Deadline Cloud queues, fleets, and this job to fit your own production pipeline.

The job uses `mayapy` (Maya's standalone Python interpreter) to:
1. Load the Maya USD plugin
2. Import the USD scene
3. Render each frame using Maya's software renderer

The step expands to a task per frame by defining a parameter space using the Frames job parameter. It limits the fleets it will run on by including host requirements for Linux.

## Conda Packages

This job bundle uses the `maya-usd` conda package by default. To build this package, see the [maya-usd-2026 conda recipe](../../conda_recipes/maya-usd-2026/).

## Sample Asset

`sample.usda` is a simple scene containing basic geometry with a camera and lighting. This scene contains no external assets and can be rendered without attaching any other files.

This work by the Deadline Cloud team is marked with [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/?ref=chooser-v1)
