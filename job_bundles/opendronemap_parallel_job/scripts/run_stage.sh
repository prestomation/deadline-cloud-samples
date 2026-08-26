#!/usr/bin/env bash

set -euo pipefail

readonly ODM_IMAGE_REF="opendronemap/odm:3.6.1@sha256:b5fda2c0f02308c1a7fb7a07b4405aa051cf509bcc8c46eb12d10af9cbfbaf8d"
readonly ODM_IMAGE_DIGEST="sha256:b5fda2c0f02308c1a7fb7a07b4405aa051cf509bcc8c46eb12d10af9cbfbaf8d"
readonly MINIMUM_FREE_KIB=$((20 * 1024 * 1024))

STAGE=""
INPUT_IMAGES=""
INTERMEDIATE_DIR=""
OUTPUT_DIR=""
SCRIPT_DIR=""
SESSION_WORKING_DIR=""
CONTAINER_NAME=""
CONTAINER_STARTED=0
CANCEL_REQUESTED=0
MONITOR_PID=""
STATS_PID=""
FIFO_PATH=""
LOG_PATH=""
METRICS_PATH=""

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

require_commands() {
    local command_name
    for command_name in docker python3 df awk grep tee mkfifo du date; do
        if ! command -v "$command_name" >/dev/null 2>&1; then
            fail "Required command is unavailable: $command_name" 69
            return $?
        fi
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
    emit_status "Cancellation requested; stopping ${STAGE} container"
    stop_container
}

handle_exit() {
    local status=$?
    trap - EXIT TERM INT
    set +e
    stop_container
    docker rm -f "$CONTAINER_NAME" >/dev/null 2>&1 || true
    if [[ -n "$STATS_PID" ]]; then
        kill "$STATS_PID" >/dev/null 2>&1 || true
        wait "$STATS_PID" >/dev/null 2>&1 || true
    fi
    if [[ -n "$MONITOR_PID" ]]; then
        wait "$MONITOR_PID" >/dev/null 2>&1 || true
    fi
    if [[ -n "$FIFO_PATH" ]]; then
        rm -f -- "$FIFO_PATH"
    fi
    if [[ "$CANCEL_REQUESTED" -eq 1 && "$status" -eq 0 ]]; then
        status=130
    fi
    exit "$status"
}

monitor_resources() {
    local timestamp
    local stats
    local scratch_kib
    printf 'timestamp_utc,memory_usage,cpu_percent,scratch_kib\n' >"$METRICS_PATH"
    while docker container inspect "$CONTAINER_NAME" >/dev/null 2>&1; do
        timestamp="$(date -u +%FT%TZ)"
        stats="$(docker stats --no-stream --format '{{.MemUsage}},{{.CPUPerc}}' "$CONTAINER_NAME" 2>/dev/null || true)"
        if [[ -z "$stats" ]]; then
            stats=","
        fi
        scratch_kib="$(du -sk "$INTERMEDIATE_DIR" 2>/dev/null | awk '{print $1}')"
        printf '%s,%s,%s\n' "$timestamp" "$stats" "${scratch_kib:-0}" >>"$METRICS_PATH"
        sleep 1
    done
}

pull_and_verify_image() {
    local repo_digests
    emit_status "Pulling pinned OpenDroneMap 3.6.1 image"
    emit_progress 1
    docker pull "$ODM_IMAGE_REF"
    repo_digests="$(docker image inspect --format '{{json .RepoDigests}}' "$ODM_IMAGE_REF")"
    if ! grep -Fq "$ODM_IMAGE_DIGEST" <<<"$repo_digests"; then
        fail "Pulled ODM image does not expose the pinned manifest digest" 69
        return $?
    fi
}

run_container() {
    local uid_gid
    local docker_pid
    local docker_status
    local -a wrapper_args=("$@")

    mkdir -p "$INTERMEDIATE_DIR/logs" "$INTERMEDIATE_DIR/metrics" "$OUTPUT_DIR"
    LOG_PATH="$INTERMEDIATE_DIR/logs/${STAGE}.log"
    if [[ "$STAGE" == "reconstruct" || "$STAGE" == "process" ]]; then
        LOG_PATH="$INTERMEDIATE_DIR/logs/${STAGE}_$(printf '%04d' "${wrapper_args[2]}").log"
    fi
    METRICS_PATH="${LOG_PATH%.log}.metrics.csv"
    FIFO_PATH="${SESSION_WORKING_DIR}/odm-${STAGE}-$$.fifo"
    mkfifo "$FIFO_PATH"
    tee -a "$LOG_PATH" <"$FIFO_PATH" &
    MONITOR_PID=$!

    uid_gid="$(id -u):$(id -g)"
    docker create \
        --name "$CONTAINER_NAME" \
        --rm \
        --init \
        --network none \
        --stop-timeout 20 \
        --user "$uid_gid" \
        --env HOME=/tmp \
        --env PYTHONPATH=/code:/code/SuperBuild/install/local/lib/python3.12/dist-packages:/code/SuperBuild/install/lib/python3.12/dist-packages:/code/SuperBuild/install/bin/opensfm \
        --volume "$INTERMEDIATE_DIR:/work" \
        --volume "$OUTPUT_DIR:/output" \
        --volume "$SCRIPT_DIR:/scripts:ro" \
        --workdir /work \
        --entrypoint python3 \
        "$ODM_IMAGE_REF" \
        /scripts/stage_wrapper.py "${wrapper_args[@]}" >/dev/null
    CONTAINER_STARTED=1
    monitor_resources &
    STATS_PID=$!
    docker start --attach "$CONTAINER_NAME" >"$FIFO_PATH" 2>&1 &
    docker_pid=$!

    set +e
    wait_for_child "$docker_pid"
    docker_status=$?
    set -e
    wait "$MONITOR_PID" || true
    MONITOR_PID=""
    kill "$STATS_PID" >/dev/null 2>&1 || true
    wait "$STATS_PID" >/dev/null 2>&1 || true
    STATS_PID=""
    rm -f -- "$FIFO_PATH"
    FIFO_PATH=""
    return "$docker_status"
}

main() {
    local available_kib
    local submodel_index
    local expected_submodels
    local max_concurrency

    if [[ "$#" -lt 6 ]]; then
        fail "Expected stage and five path arguments" 64
        return $?
    fi
    STAGE="$1"
    INPUT_IMAGES="$2"
    INTERMEDIATE_DIR="$3"
    OUTPUT_DIR="$4"
    SCRIPT_DIR="$5"
    SESSION_WORKING_DIR="$6"
    shift 6
    CONTAINER_NAME="deadline-odm-parallel-${STAGE}-$$"

    require_commands
    docker info >/dev/null
    mkdir -p "$INTERMEDIATE_DIR" "$OUTPUT_DIR" "$SESSION_WORKING_DIR"
    available_kib="$(df -Pk "$SESSION_WORKING_DIR" | awk 'NR == 2 {print $4}')"
    if [[ ! "$available_kib" =~ ^[0-9]+$ || "$available_kib" -lt "$MINIMUM_FREE_KIB" ]]; then
        fail "At least 20 GiB of free worker disk is required" 69
        return $?
    fi

    case "$STAGE" in
        prepare)
            if [[ "$#" -ne 14 ]]; then
                fail "Prepare received an unexpected parameter count" 64
                return $?
            fi
            emit_status "Validating and staging the attached survey"
            emit_progress 0
            python3 "$SCRIPT_DIR/worker_input.py" \
                --input-images "$INPUT_IMAGES" \
                --intermediate-dir "$INTERMEDIATE_DIR" \
                --expected-count "$1" \
                --expected-submodels "$2" \
                --expected-bytes "$3" \
                --expected-megapixels "$4"
            pull_and_verify_image
            run_container \
                prepare \
                --project-root /work/survey \
                --expected-images "$1" \
                --expected-submodels "$2" \
                --target-images "$5" \
                --split-overlap "$6" \
                --minimum-shared-images "$7" \
                --orthophoto-resolution "$8" \
                --feature-quality "$9" \
                --point-cloud-quality "${10}" \
                --generate-dsm "${11}" \
                --generate-dtm "${12}" \
                --max-concurrency "${13}"
            ;;
        reconstruct)
            if [[ "$#" -ne 3 ]]; then
                fail "Reconstruct received an unexpected parameter count" 64
                return $?
            fi
            submodel_index="$1"
            expected_submodels="$2"
            max_concurrency="$3"
            pull_and_verify_image
            run_container \
                reconstruct \
                --submodel-index "$submodel_index" \
                --project-root /work/survey \
                --expected-submodels "$expected_submodels" \
                --max-concurrency "$max_concurrency"
            ;;
        align)
            if [[ "$#" -ne 2 ]]; then
                fail "Align received an unexpected parameter count" 64
                return $?
            fi
            pull_and_verify_image
            run_container \
                align \
                --project-root /work/survey \
                --expected-submodels "$1" \
                --max-concurrency "$2"
            ;;
        process)
            if [[ "$#" -ne 8 ]]; then
                fail "Process received an unexpected parameter count" 64
                return $?
            fi
            submodel_index="$1"
            expected_submodels="$2"
            pull_and_verify_image
            run_container \
                process \
                --submodel-index "$submodel_index" \
                --project-root /work/survey \
                --expected-submodels "$expected_submodels" \
                --orthophoto-resolution "$3" \
                --feature-quality "$4" \
                --point-cloud-quality "$5" \
                --generate-dsm "$6" \
                --generate-dtm "$7" \
                --max-concurrency "$8"
            ;;
        merge)
            if [[ "$#" -ne 11 ]]; then
                fail "Merge received an unexpected parameter count" 64
                return $?
            fi
            pull_and_verify_image
            run_container \
                merge \
                --project-root /work/survey \
                --output-dir /output \
                --expected-images "$1" \
                --expected-submodels "$2" \
                --target-images "$3" \
                --split-overlap "$4" \
                --orthophoto-resolution "$5" \
                --feature-quality "$6" \
                --point-cloud-quality "$7" \
                --generate-dsm "$8" \
                --generate-dtm "$9" \
                --max-concurrency "${10}" \
                --retain-intermediates "${11}"
            ;;
        *)
            fail "Unsupported ODM parallel stage: $STAGE" 64
            return $?
            ;;
    esac
}

trap handle_cancel TERM INT
trap handle_exit EXIT
main "$@"
