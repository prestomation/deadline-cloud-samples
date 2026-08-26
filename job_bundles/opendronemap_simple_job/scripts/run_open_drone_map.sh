#!/usr/bin/env bash

set -euo pipefail

readonly ODM_VERSION="3.6.1"
readonly ODM_IMAGE_REF="opendronemap/odm:3.6.1@sha256:b5fda2c0f02308c1a7fb7a07b4405aa051cf509bcc8c46eb12d10af9cbfbaf8d"
readonly DATASET_COMMIT="9506a9bf09c9678b7d0b80b014af5b606c8a7255"
readonly DATASET_URL="https://github.com/pierotofy/drone_dataset_brighton_beach/archive/${DATASET_COMMIT}.tar.gz"
readonly DATASET_SHA256="4ec7c469ae9242bd7a08eec46bb5b2442bcae904e43c3b7c9d48d5de2fb538a7"
readonly DATASET_ROOT="drone_dataset_brighton_beach-${DATASET_COMMIT}"
readonly PROJECT_NAME="brighton_beach"
readonly EXPECTED_IMAGE_COUNT=18
readonly MINIMUM_FREE_KIB=$((20 * 1024 * 1024))

SCRIPT_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
START_EPOCH="$(date +%s)"
STARTED_AT="$(date -u +%FT%TZ)"
WORK_ROOT=""
DATASETS_DIR=""
SURVEY_DIR=""
RESULT_DIR=""
ODM_LOG=""
OUTPUT_DIR=""
ORTHOPHOTO_RESOLUTION=""
FEATURE_QUALITY=""
POINT_CLOUD_QUALITY=""
GENERATE_DSM=""
GENERATE_DTM=""
MAX_CONCURRENCY=""
CONTAINER_NAME="deadline-odm-$$"
CONTAINER_STARTED=0
CANCEL_REQUESTED=0
MONITOR_PID=""
ODM_EXIT_CODE=""

emit_status() {
    printf 'openjd_status: %s\n' "$1"
}

emit_progress() {
    printf 'openjd_progress: %s\n' "$1"
}

fail() {
    local message="$1"
    local status="${2:-1}"
    printf 'openjd_fail: %s\n' "$message" >&2
    return "$status"
}

read_parameter() {
    local path="$1"
    if [[ ! -f "$path" ]]; then
        fail "Parameter file is missing: $path" 64
        return $?
    fi
    cat -- "$path"
}

validate_parameters() {
    if [[ ! "$ORTHOPHOTO_RESOLUTION" =~ ^[1-9][0-9]*$ ]]; then
        fail "OrthophotoResolution must be a positive integer" 64
        return $?
    fi
    if [[ ! "$MAX_CONCURRENCY" =~ ^[1-9][0-9]*$ ]]; then
        fail "MaxConcurrency must be a positive integer" 64
        return $?
    fi
    case "$FEATURE_QUALITY" in
        ultra | high | medium | low | lowest) ;;
        *)
            fail "FeatureQuality has an unsupported value" 64
            return $?
            ;;
    esac
    case "$POINT_CLOUD_QUALITY" in
        ultra | high | medium | low | lowest) ;;
        *)
            fail "PointCloudQuality has an unsupported value" 64
            return $?
            ;;
    esac
    case "$GENERATE_DSM" in
        True | False) ;;
        *)
            fail "GenerateDsm must be True or False" 64
            return $?
            ;;
    esac
    case "$GENERATE_DTM" in
        True | False) ;;
        *)
            fail "GenerateDtm must be True or False" 64
            return $?
            ;;
    esac
}

require_commands() {
    local command_name
    for command_name in curl tar sha256sum docker python3 find awk cp; do
        if ! command -v "$command_name" >/dev/null 2>&1; then
            fail "Required command is unavailable: $command_name" 69
            return $?
        fi
    done
}

monitor_odm_output() {
    local line
    while IFS= read -r line || [[ -n "$line" ]]; do
        printf '%s\n' "$line"
        case "$line" in
            *"Running dataset stage"*)
                emit_status "ODM: loading the aerial images"
                emit_progress 22
                ;;
            *"Running split stage"*)
                emit_status "ODM: preparing the reconstruction"
                emit_progress 24
                ;;
            *"Running merge stage"*)
                emit_status "ODM: preparing the reconstruction"
                emit_progress 26
                ;;
            *"Running opensfm stage"*)
                emit_status "ODM: matching images and solving camera poses"
                emit_progress 30
                ;;
            *"Running openmvs stage"*)
                emit_status "ODM: building the dense point cloud"
                emit_progress 45
                ;;
            *"Running odm_filterpoints stage"*)
                emit_status "ODM: filtering the point cloud"
                emit_progress 58
                ;;
            *"Running odm_meshing stage"*)
                emit_status "ODM: generating the mesh"
                emit_progress 65
                ;;
            *"Running mvs_texturing stage"*)
                emit_status "ODM: texturing the 3D model"
                emit_progress 73
                ;;
            *"Running odm_georeferencing stage"*)
                emit_status "ODM: georeferencing outputs"
                emit_progress 80
                ;;
            *"Running odm_dem stage"*)
                emit_status "ODM: generating elevation models"
                emit_progress 87
                ;;
            *"Running odm_orthophoto stage"*)
                emit_status "ODM: rendering the orthophoto"
                emit_progress 93
                ;;
            *"Running odm_report stage"*)
                emit_status "ODM: creating the processing report"
                emit_progress 96
                ;;
            *"Running odm_postprocess stage"*)
                emit_status "ODM: finalizing results"
                emit_progress 98
                ;;
        esac
    done
}

wait_for_child() {
    local pid="$1"
    local status
    while true; do
        set +e
        wait "$pid"
        status=$?
        set -e
        if ! kill -0 "$pid" 2>/dev/null; then
            return "$status"
        fi
    done
}

stop_container() {
    if [[ "$CONTAINER_STARTED" -eq 1 ]] &&
        docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
        docker stop --time 20 "$CONTAINER_NAME" >/dev/null 2>&1 || true
    fi
}

handle_cancel() {
    CANCEL_REQUESTED=1
    emit_status "Cancellation requested; stopping the ODM container"
    stop_container
}

copy_results() {
    local directory
    local status=0
    mkdir -p "$RESULT_DIR" || return $?
    for directory in odm_orthophoto odm_georeferencing odm_dem odm_texturing odm_report; do
        if [[ -d "$SURVEY_DIR/$directory" ]]; then
            cp -a -- "$SURVEY_DIR/$directory" "$RESULT_DIR/" || status=$?
        fi
    done
    if [[ -f "$ODM_LOG" ]]; then
        cp -a -- "$ODM_LOG" "$RESULT_DIR/odm.log" || status=$?
    fi
    return "$status"
}

require_nonempty_file() {
    local relative_path="$1"
    if [[ ! -s "$RESULT_DIR/$relative_path" ]]; then
        printf 'Missing expected artifact: %s\n' "$relative_path" >&2
        return 1
    fi
}

validate_results() {
    local missing=0
    local texture_count
    require_nonempty_file "odm_orthophoto/odm_orthophoto.tif" || missing=1
    require_nonempty_file "odm_georeferencing/odm_georeferenced_model.laz" || missing=1
    require_nonempty_file "odm_texturing/odm_textured_model_geo.obj" || missing=1
    require_nonempty_file "odm_texturing/odm_textured_model_geo.mtl" || missing=1
    require_nonempty_file "odm_report/report.pdf" || missing=1
    require_nonempty_file "odm.log" || missing=1

    if [[ "$GENERATE_DSM" == "True" ]]; then
        require_nonempty_file "odm_dem/dsm.tif" || missing=1
    fi
    if [[ "$GENERATE_DTM" == "True" ]]; then
        require_nonempty_file "odm_dem/dtm.tif" || missing=1
    fi

    texture_count="$(
        find "$RESULT_DIR/odm_texturing" -maxdepth 1 -type f \
            \( -iname '*.jpg' -o -iname '*.jpeg' -o -iname '*.png' -o -iname '*.tif' \) \
            2>/dev/null | awk 'END { print NR }'
    )"
    if [[ "$texture_count" -lt 1 ]]; then
        echo "Missing expected textured-model image" >&2
        missing=1
    fi

    if [[ "$missing" -ne 0 ]]; then
        fail "ODM exited successfully but required output artifacts are missing" 66
        return $?
    fi
}

write_manifest() {
    local exit_status="$1"
    local run_status="$2"
    local finished_epoch
    local finished_at
    local container_exit_code="${ODM_EXIT_CODE:-}"

    finished_epoch="$(date +%s)"
    finished_at="$(date -u +%FT%TZ)"
    python3 "$SCRIPT_DIR/write_manifest.py" \
        --result-dir "$RESULT_DIR" \
        --status "$run_status" \
        --exit-code "$exit_status" \
        --container-exit-code "$container_exit_code" \
        --started-at "$STARTED_AT" \
        --finished-at "$finished_at" \
        --duration-seconds "$((finished_epoch - START_EPOCH))" \
        --orthophoto-resolution "$ORTHOPHOTO_RESOLUTION" \
        --feature-quality "$FEATURE_QUALITY" \
        --point-cloud-quality "$POINT_CLOUD_QUALITY" \
        --generate-dsm "$GENERATE_DSM" \
        --generate-dtm "$GENERATE_DTM" \
        --max-concurrency "$MAX_CONCURRENCY"
}

handle_exit() {
    local exit_status=$?
    local collect_status=0
    local validation_status=0
    local manifest_status=0
    local run_status="failed"

    trap - EXIT TERM INT
    set +e
    stop_container
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    if [[ -n "$MONITOR_PID" ]]; then
        wait "$MONITOR_PID" >/dev/null 2>&1 || true
    fi

    if [[ -n "$RESULT_DIR" && -n "$SURVEY_DIR" ]]; then
        copy_results
        collect_status=$?
    fi
    if [[ "$exit_status" -eq 0 && "$collect_status" -eq 0 ]]; then
        validate_results
        validation_status=$?
    fi

    if [[ "$CANCEL_REQUESTED" -eq 1 ]]; then
        run_status="canceled"
        if [[ "$exit_status" -eq 0 ]]; then
            exit_status=130
        fi
    elif [[ "$exit_status" -eq 0 && "$collect_status" -eq 0 && "$validation_status" -eq 0 ]]; then
        run_status="success"
    fi

    if [[ "$exit_status" -eq 0 && "$collect_status" -ne 0 ]]; then
        exit_status="$collect_status"
    fi
    if [[ "$exit_status" -eq 0 && "$validation_status" -ne 0 ]]; then
        exit_status="$validation_status"
    fi

    if [[ -n "$RESULT_DIR" && -n "$ORTHOPHOTO_RESOLUTION" ]]; then
        write_manifest "$exit_status" "$run_status"
        manifest_status=$?
        if [[ "$exit_status" -eq 0 && "$manifest_status" -ne 0 ]]; then
            exit_status="$manifest_status"
            run_status="failed"
        fi
    fi

    if [[ "$run_status" == "success" ]]; then
        emit_status "OpenDroneMap processing complete"
        emit_progress 100
    elif [[ "$run_status" == "canceled" ]]; then
        printf 'openjd_fail: OpenDroneMap processing was canceled\n' >&2
    else
        printf 'openjd_fail: OpenDroneMap processing failed with exit code %s\n' "$exit_status" >&2
    fi
    exit "$exit_status"
}

main() {
    local available_kib
    local archive_path
    local extract_dir
    local actual_sha256
    local curl_status
    local docker_pull_status
    local docker_run_status
    local fifo_path
    local docker_pid
    local uid_gid
    local -a source_images
    local -a odm_args

    if [[ "$#" -ne 7 ]]; then
        fail "Expected seven parameter files, received $#" 64
        return $?
    fi

    OUTPUT_DIR="$(read_parameter "$1")"
    ORTHOPHOTO_RESOLUTION="$(read_parameter "$2")"
    FEATURE_QUALITY="$(read_parameter "$3")"
    POINT_CLOUD_QUALITY="$(read_parameter "$4")"
    GENERATE_DSM="$(read_parameter "$5")"
    GENERATE_DTM="$(read_parameter "$6")"
    MAX_CONCURRENCY="$(read_parameter "$7")"
    validate_parameters
    require_commands

    WORK_ROOT="${OPENJD_SESSION_WORKING_DIR:-$(pwd)}/open_drone_map"
    DATASETS_DIR="$WORK_ROOT/datasets"
    SURVEY_DIR="$DATASETS_DIR/$PROJECT_NAME"
    RESULT_DIR="$OUTPUT_DIR/open_drone_map"
    ODM_LOG="$WORK_ROOT/odm.log"
    archive_path="$WORK_ROOT/dataset.tar.gz"
    extract_dir="$WORK_ROOT/dataset"

    rm -rf -- "$WORK_ROOT" "$RESULT_DIR"
    mkdir -p "$SURVEY_DIR/images" "$extract_dir" "$RESULT_DIR"
    : >"$ODM_LOG"

    emit_status "Checking the worker and Docker daemon"
    emit_progress 1
    docker info >/dev/null
    available_kib="$(df -Pk "$WORK_ROOT" | awk 'NR == 2 { print $4 }')"
    if [[ ! "$available_kib" =~ ^[0-9]+$ || "$available_kib" -lt "$MINIMUM_FREE_KIB" ]]; then
        fail "At least 20 GiB of free session disk is required" 69
        return $?
    fi

    emit_status "Downloading the pinned Brighton Beach dataset"
    emit_progress 5
    set +e
    curl --fail --location --retry 3 --retry-all-errors --connect-timeout 30 \
        --output "$archive_path" "$DATASET_URL"
    curl_status=$?
    set -e
    if [[ "$curl_status" -ne 0 ]]; then
        fail "Dataset download failed" "$curl_status"
        return $?
    fi

    emit_status "Verifying the dataset checksum"
    emit_progress 10
    actual_sha256="$(sha256sum "$archive_path" | awk '{ print $1 }')"
    if [[ "$actual_sha256" != "$DATASET_SHA256" ]]; then
        fail "Dataset checksum mismatch: expected $DATASET_SHA256, got $actual_sha256" 65
        return $?
    fi

    emit_status "Staging the 18 source images"
    emit_progress 13
    tar -xzf "$archive_path" -C "$extract_dir"
    shopt -s nullglob
    source_images=("$extract_dir/$DATASET_ROOT/images/"*.JPG)
    shopt -u nullglob
    if [[ "${#source_images[@]}" -ne "$EXPECTED_IMAGE_COUNT" ]]; then
        fail "Expected 18 source images, found ${#source_images[@]}" 65
        return $?
    fi
    cp -- "${source_images[@]}" "$SURVEY_DIR/images/"

    emit_status "Pulling OpenDroneMap ${ODM_VERSION}"
    emit_progress 15
    set +e
    docker pull "$ODM_IMAGE_REF"
    docker_pull_status=$?
    set -e
    if [[ "$docker_pull_status" -ne 0 ]]; then
        fail "Docker image pull failed" "$docker_pull_status"
        return $?
    fi

    odm_args=(
        --project-path /datasets
        "$PROJECT_NAME"
        --orthophoto-resolution "$ORTHOPHOTO_RESOLUTION"
        --feature-quality "$FEATURE_QUALITY"
        --pc-quality "$POINT_CLOUD_QUALITY"
        --max-concurrency "$MAX_CONCURRENCY"
    )
    if [[ "$GENERATE_DSM" == "True" ]]; then
        odm_args+=(--dsm)
    fi
    if [[ "$GENERATE_DTM" == "True" ]]; then
        odm_args+=(--dtm)
    fi

    emit_status "Starting OpenDroneMap"
    emit_progress 20
    fifo_path="$WORK_ROOT/odm-output.fifo"
    mkfifo "$fifo_path"
    monitor_odm_output <"$fifo_path" | tee -a "$ODM_LOG" &
    MONITOR_PID=$!

    uid_gid="$(id -u):$(id -g)"
    CONTAINER_STARTED=1
    docker run \
        --name "$CONTAINER_NAME" \
        --rm \
        --init \
        --network none \
        --stop-timeout 20 \
        --user "$uid_gid" \
        --env HOME=/tmp \
        --volume "$DATASETS_DIR:/datasets" \
        --workdir "/datasets/$PROJECT_NAME" \
        "$ODM_IMAGE_REF" \
        "${odm_args[@]}" >"$fifo_path" 2>&1 &
    docker_pid=$!

    set +e
    wait_for_child "$docker_pid"
    docker_run_status=$?
    set -e
    ODM_EXIT_CODE="$docker_run_status"
    wait "$MONITOR_PID" || true
    MONITOR_PID=""
    rm -f "$fifo_path"
    return "$docker_run_status"
}

trap handle_cancel TERM INT
trap handle_exit EXIT
main "$@"
