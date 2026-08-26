# OpenDroneMap simple job

This job bundle runs a CPU-only
[OpenDroneMap (ODM) 3.6.1](https://github.com/OpenDroneMap/ODM/tree/v3.6.1)
survey reconstruction on AWS Deadline Cloud. One task downloads a pinned public
18-image Brighton Beach survey, verifies it, runs ODM in Docker, and returns
standard geospatial and 3D deliverables through job attachments.

Use this sample to evaluate photogrammetry on a Linux service-managed fleet
without packaging ODM or managing a separate application cluster. Version 1
processes one survey per job; distributed split/merge processing is outside its
scope.

## Prerequisites

- A Deadline Cloud farm and queue with a Linux service-managed fleet.
- The [Docker Engine host configuration](../../host_configuration_scripts/docker_engine/)
  applied to newly launched workers. Configure the fleet with the custom
  attribute `attr.OpenDroneMap=docker_3_6_1`; the job requires that capability
  to prevent scheduling on Linux workers without Docker.
- Fleet capabilities of at least 2 vCPUs and 8 GiB RAM. The step requests these
  amounts from the scheduler.
- At least 20 GiB free worker disk for the image layers, source archive,
  processing scratch data, and packaged outputs. The task checks this before
  downloading.
- Outbound HTTPS access to GitHub and Docker Hub.
- The [Deadline Cloud CLI](https://github.com/aws-deadline/deadline-cloud)
  configured with a default farm and queue, or explicit farm and queue IDs.

The pinned ODM image is a multi-architecture manifest for Linux x86_64 and
ARM64. A worker still needs enough memory and disk; architecture support alone
does not establish that a given instance size meets the baseline. As of the
validation date below, Deadline Cloud service-managed fleets accept only
`x86_64`; ARM64 image compatibility was therefore tested locally with Docker,
not on a service-managed fleet.

### Create a compatible fleet

This repository does not create Deadline infrastructure. If starting without a
fleet, use the
[Docker Engine setup checklist](../../host_configuration_scripts/docker_engine/):

1. Create or select a farm and a queue with job attachments in the Deadline
   Cloud console.
2. Create a Linux `x86_64` service-managed fleet with a zero minimum, a bounded
   maximum, and worker capacity meeting the 2-vCPU, 8-GiB RAM, and 20-GiB free
   disk baseline.
3. Add `attr.OpenDroneMap=docker_3_6_1`, then paste
   [`linux.sh`](../../host_configuration_scripts/docker_engine/linux.sh) into
   the fleet's **Host configuration** field.
4. Associate the fleet with the queue, launch one worker, and confirm its host
   configuration log ends with `Docker Engine setup complete`.
5. Return the fleet minimum to zero before submitting the job.

### Configure the Deadline CLI

Install or update the client, then set the profile, region, farm, and queue
created above:

```console
pip install --upgrade deadline
deadline config set defaults.aws_profile_name my-profile
deadline config set defaults.farm_region us-west-2
deadline config set defaults.farm_id farm-0123456789abcdef0123456789abcdef
deadline config set defaults.queue_id queue-0123456789abcdef0123456789abcdef
```

You can instead select a farm and queue for each submission. The job's
`attr.OpenDroneMap=docker_3_6_1` host requirement prevents it from using a
generic Linux fleet that does not advertise the Docker configuration.

## Submit

From the repository root, review the parameters in the GUI:

```console
deadline bundle gui-submit job_bundles/opendronemap_simple_job
```

Or submit the defaults from the command line:

```console
deadline bundle submit job_bundles/opendronemap_simple_job \
    -p OutputDir="$(pwd)/odm-output"
```

The bundle creates `open_drone_map/` inside `OutputDir`. Use a new or dedicated
output directory because a retry replaces that sample-owned subdirectory.

## Parameters

| Parameter | Default | Description |
|---|---:|---|
| `OutputDir` | `./output` | Job-attachment output directory. |
| `OrthophotoResolution` | `10` | Orthophoto resolution in centimeters per pixel. |
| `FeatureQuality` | `low` | ODM feature extraction quality: `ultra`, `high`, `medium`, `low`, or `lowest`. |
| `PointCloudQuality` | `lowest` | ODM dense point cloud quality using the same quality levels. |
| `GenerateDsm` | `True` | Generate a digital surface model. |
| `GenerateDtm` | `False` | Classify ground points and generate a digital terrain model. |
| `MaxConcurrency` | `2` | Positive integer limiting concurrent ODM processes. ODM estimates roughly 1 GiB per process for 2-megapixel images. |

The image, dataset URL, commit, and checksums are constants in the execution
script. The job does not accept additional shell arguments or mutable download
locations.

## Data flow and progress

The task uses the OpenJD session working directory for all downloads,
extraction, and ODM intermediates:

1. Check Docker and verify at least 20 GiB free disk.
2. Download the immutable commit archive for
   [`pierotofy/drone_dataset_brighton_beach`](https://github.com/pierotofy/drone_dataset_brighton_beach/tree/9506a9bf09c9678b7d0b80b014af5b606c8a7255).
3. Verify SHA-256
   `4ec7c469ae9242bd7a08eec46bb5b2442bcae904e43c3b7c9d48d5de2fb538a7`
   and stage only the 18 JPEGs in `images/`. The repository's precomputed
   preview, DSM, and point cloud are not used.
4. Pull
   `opendronemap/odm:3.6.1@sha256:b5fda2c0f02308c1a7fb7a07b4405aa051cf509bcc8c46eb12d10af9cbfbaf8d`.
5. Run the container without network access and stream every ODM log line to
   Deadline Cloud.
6. Translate ODM's stage messages into `openjd_status` and `openjd_progress`
   updates for the Monitor.
7. Copy only deliverables to `OutputDir/open_drone_map`, verify every required
   artifact, and write a checksummed JSON manifest.

The task uses OpenJD's notify-then-terminate cancellation mode. On cancellation,
the script asks Docker to stop ODM, waits up to 20 seconds, removes the named
container, packages any partial log/results, and returns the container status.
Normal nonzero ODM exits are also returned unchanged.

## Outputs

Successful defaults produce:

```text
open_drone_map/
|-- manifest.json
|-- odm.log
|-- odm_dem/
|   `-- dsm.tif
|-- odm_georeferencing/
|   `-- odm_georeferenced_model.laz
|-- odm_orthophoto/
|   `-- odm_orthophoto.tif
|-- odm_report/
|   `-- report.pdf
`-- odm_texturing/
    |-- odm_textured_model_geo.obj
    |-- odm_textured_model_geo.mtl
    `-- ... texture images and supporting model files
```

Enabling `GenerateDtm` also requires and returns `odm_dem/dtm.tif`. The
manifest records the ODM version and image digest, dataset license/commit/hash,
all processing parameters, timestamps, duration, exit status, host
architecture, and the size and SHA-256 of every returned artifact.

Use a geospatial application such as QGIS for the GeoTIFF, CloudCompare for
LAZ, and MeshLab for OBJ. The OBJ, material file, and textures must remain
together in `odm_texturing/`.

## Security, cost, and cleanup

The Brighton Beach dataset is Copyright 2017 Piero Toffanin and licensed
[BSD-2-Clause](https://github.com/pierotofy/drone_dataset_brighton_beach/blob/9506a9bf09c9678b7d0b80b014af5b606c8a7255/LICENSE).
ODM is distributed under AGPL-3.0-only; this sample runs its unmodified official
container.

The Docker host configuration adds `job-user` to the `docker` group. That group
has root-equivalent host access, so route only trusted jobs to this fleet.
The task container receives only the session dataset volume and has networking
disabled after the image pull.

Deadline Cloud charges for worker time and job-attachment storage/transfer.
Approximate worker cost is the service-managed fleet rate for the selected
instance multiplied by the worker's billed runtime; consult
[AWS Deadline Cloud pricing](https://aws.amazon.com/deadline-cloud/pricing/)
and the Monitor usage explorer for the actual job estimate.

### Baseline validation record

Validated on 2026-08-04 using an Amazon Linux 2023 service-managed Spot fleet
in `us-west-2`. The worker was a `t3.large` constrained to 2 vCPUs and 8 GiB,
with a 100-GiB root volume. A test-only wrapper sampled Docker memory and
filesystem use once per second; it did not change the sample's parameters or
outputs.

| Measurement | 2-vCPU / 8-GiB x86_64 | 2-vCPU / 8-GiB ARM64 |
|---|---:|---:|
| Cold ODM image download | 28 seconds; 1.55 GiB image | Service-managed fleets unsupported |
| End-to-end runtime | 5 minutes 42 seconds | Service-managed fleets unsupported |
| Peak memory | 1.27 GiB container RSS | Service-managed fleets unsupported |
| Peak worker disk use | 2.35 GiB delta; 0.53 GiB session scratch | Service-managed fleets unsupported |
| Approximate Deadline cost | USD 0.0095 on-demand upper bound | Service-managed fleets unsupported |

The cost estimate multiplies 342 seconds by the 2026-08-04 on-demand
`t3.large` Deadline rate of USD 0.09984 per hour. The validation fleet used
Spot capacity, whose actual rate varies and should be checked in the Deadline
usage explorer. Worker startup, idle timeout, attachment storage, and transfer
can add cost outside the task interval.

After validation, restore the fleet minimum worker count to zero and confirm the
worker terminates. Download job outputs before deleting the job if they are
needed later.

## Validate and troubleshoot

Static validation from the bundle directory:

```console
bash -n scripts/run_open_drone_map.sh
shellcheck scripts/run_open_drone_map.sh
tests/test_run_open_drone_map.sh
openjd check template.yaml
openjd summary template.yaml
```

Run locally only on a Linux host with Docker and at least 20 GiB free:

```console
mkdir -p output
openjd run template.yaml -p OutputDir="$(pwd)/output"
```

Common failures:

- **Docker permission denied:** confirm the worker was launched after applying
  the host configuration and its log verified Docker as `job-user`.
- **Checksum mismatch:** the task rejects the archive before extraction. Check
  for a proxy or upstream archive change; do not update the hash without
  reviewing the pinned contents.
- **Exit 137:** ODM exhausted memory. Increase fleet memory or lower quality and
  concurrency.
- **Missing expected artifact:** ODM returned zero but did not produce the
  declared result set. The task fails and lists the missing relative path; use
  `odm.log` and partial outputs for diagnosis.
- **Pull/download failure:** verify outbound DNS and HTTPS access to Docker Hub
  and GitHub.

The script tests under `tests/` use command shims to cover checksum rejection,
download and pull failures, nonzero ODM exit propagation, cancellation cleanup,
and missing artifact rejection without downloading the image.
