#!/usr/bin/env bash

set -euo pipefail

TEST_DIR="$(cd -- "$(dirname -- "$0")" && pwd)"
readonly TEST_DIR
BUNDLE_DIR="$(cd -- "$TEST_DIR/.." && pwd)"
readonly BUNDLE_DIR
readonly RUN_SCRIPT="$BUNDLE_DIR/scripts/run_open_drone_map.sh"
readonly EXPECTED_DATASET_SHA="4ec7c469ae9242bd7a08eec46bb5b2442bcae904e43c3b7c9d48d5de2fb538a7"
readonly DATASET_ROOT="drone_dataset_brighton_beach-9506a9bf09c9678b7d0b80b014af5b606c8a7255"

TEST_ROOT="$(mktemp -d)"
trap 'rm -rf "$TEST_ROOT"' EXIT

fail() {
    echo "FAIL: $*" >&2
    exit 1
}

make_shims() {
    local bin_dir="$1"
    mkdir -p "$bin_dir"

    cat >"$bin_dir/curl" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
if [[ "${MOCK_MODE}" == "download_failure" ]]; then
    exit 22
fi
output=""
while [[ "$#" -gt 0 ]]; do
    if [[ "$1" == "--output" ]]; then
        output="$2"
        shift 2
    else
        shift
    fi
done
printf 'mock archive\n' >"$output"
EOF

    cat >"$bin_dir/sha256sum" <<EOF
#!/usr/bin/env bash
set -euo pipefail
if [[ "\${MOCK_MODE}" == "checksum_failure" ]]; then
    printf '%064d  %s\\n' 0 "\$1"
else
    printf '%s  %s\\n' "$EXPECTED_DATASET_SHA" "\$1"
fi
EOF

    cat >"$bin_dir/tar" <<EOF
#!/usr/bin/env bash
set -euo pipefail
destination=""
while [[ "\$#" -gt 0 ]]; do
    if [[ "\$1" == "-C" ]]; then
        destination="\$2"
        shift 2
    else
        shift
    fi
done
image_dir="\$destination/$DATASET_ROOT/images"
mkdir -p "\$image_dir"
index=18
while [[ "\$index" -le 35 ]]; do
    printf 'image %s\\n' "\$index" >"\$image_dir/DJI_00\${index}.JPG"
    index=\$((index + 1))
done
EOF

    cat >"$bin_dir/df" <<'EOF'
#!/usr/bin/env bash
cat <<'OUTPUT'
Filesystem 1024-blocks Used Available Capacity Mounted on
mock       100000000   100  99999900       1% /mock
OUTPUT
EOF

    cat >"$bin_dir/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"$MOCK_DOCKER_LOG"

write_success_outputs() {
    local dataset_mount="$1"
    local project_dir="$dataset_mount/brighton_beach"
    mkdir -p \
        "$project_dir/odm_orthophoto" \
        "$project_dir/odm_georeferencing" \
        "$project_dir/odm_dem" \
        "$project_dir/odm_texturing" \
        "$project_dir/odm_report"
    printf 'orthophoto\n' >"$project_dir/odm_orthophoto/odm_orthophoto.tif"
    printf 'point cloud\n' >"$project_dir/odm_georeferencing/odm_georeferenced_model.laz"
    printf 'dsm\n' >"$project_dir/odm_dem/dsm.tif"
    printf 'obj\n' >"$project_dir/odm_texturing/odm_textured_model_geo.obj"
    printf 'map_Kd texture.jpg\n' >"$project_dir/odm_texturing/odm_textured_model_geo.mtl"
    printf 'texture\n' >"$project_dir/odm_texturing/texture.jpg"
    printf 'report\n' >"$project_dir/odm_report/report.pdf"
}

case "${1:-}" in
    info | pull)
        if [[ "$1" == "pull" && "$MOCK_MODE" == "pull_failure" ]]; then
            exit 17
        fi
        exit 0
        ;;
    container)
        if [[ "${2:-}" == "inspect" && -f "$MOCK_CONTAINER_PID" ]]; then
            exit 0
        fi
        exit 1
        ;;
    stop)
        if [[ -f "$MOCK_CONTAINER_PID" ]]; then
            kill -TERM "$(cat "$MOCK_CONTAINER_PID")" 2>/dev/null || true
        fi
        exit 0
        ;;
    rm)
        if [[ -f "$MOCK_CONTAINER_PID" ]]; then
            kill -KILL "$(cat "$MOCK_CONTAINER_PID")" 2>/dev/null || true
            rm -f "$MOCK_CONTAINER_PID"
        fi
        exit 0
        ;;
    run)
        echo "$$" >"$MOCK_CONTAINER_PID"
        trap 'exit 143' TERM INT
        if [[ "$MOCK_MODE" == "cancellation" ]]; then
            while true; do
                sleep 1
            done
        fi

        dataset_mount=""
        while [[ "$#" -gt 0 ]]; do
            if [[ "$1" == "--volume" ]]; then
                dataset_mount="${2%%:*}"
                shift 2
            else
                shift
            fi
        done

        echo "[INFO] Running dataset stage"
        echo "[INFO] Running opensfm stage"
        if [[ "$MOCK_MODE" == "odm_failure" ]]; then
            exit 42
        fi
        write_success_outputs "$dataset_mount"
        if [[ "$MOCK_MODE" == "missing_artifact" ]]; then
            rm -f "$dataset_mount/brighton_beach/odm_georeferencing/odm_georeferenced_model.laz"
        fi
        echo "[INFO] Running odm_postprocess stage"
        exit 0
        ;;
esac

exit 1
EOF

    chmod +x "$bin_dir/curl" "$bin_dir/sha256sum" "$bin_dir/tar" \
        "$bin_dir/df" "$bin_dir/docker"
}

make_parameters() {
    local parameter_dir="$1"
    local output_dir="$2"
    mkdir -p "$parameter_dir" "$output_dir"
    printf '%s\n' "$output_dir" >"$parameter_dir/output"
    printf '10\n' >"$parameter_dir/resolution"
    printf 'low\n' >"$parameter_dir/feature_quality"
    printf 'lowest\n' >"$parameter_dir/point_cloud_quality"
    printf 'True\n' >"$parameter_dir/generate_dsm"
    printf 'False\n' >"$parameter_dir/generate_dtm"
    printf '2\n' >"$parameter_dir/max_concurrency"
}

invoke_script() {
    local case_dir="$1"
    local mode="$2"
    local parameter_dir="$case_dir/parameters"
    local output_dir="$case_dir/output"
    local status

    mkdir -p "$case_dir/session"
    make_parameters "$parameter_dir" "$output_dir"

    PATH="$case_dir/bin:$PATH" \
        MOCK_MODE="$mode" \
        MOCK_DOCKER_LOG="$case_dir/docker.log" \
        MOCK_CONTAINER_PID="$case_dir/container.pid" \
        OPENJD_SESSION_WORKING_DIR="$case_dir/session" \
        bash "$RUN_SCRIPT" \
        "$parameter_dir/output" \
        "$parameter_dir/resolution" \
        "$parameter_dir/feature_quality" \
        "$parameter_dir/point_cloud_quality" \
        "$parameter_dir/generate_dsm" \
        "$parameter_dir/generate_dtm" \
        "$parameter_dir/max_concurrency" \
        >"$case_dir/stdout.log" 2>"$case_dir/stderr.log"
    status=$?
    return "$status"
}

run_case() {
    local name="$1"
    local mode="$2"
    local expected_status="$3"
    local case_dir="$TEST_ROOT/$name"
    local status

    make_shims "$case_dir/bin"
    set +e
    invoke_script "$case_dir" "$mode"
    status=$?
    set -e
    if [[ "$status" -ne "$expected_status" ]]; then
        cat "$case_dir/stdout.log" "$case_dir/stderr.log" >&2
        fail "$name returned $status; expected $expected_status"
    fi
    printf 'PASS: %s\n' "$name"
}

run_cancellation_case() {
    local case_dir="$TEST_ROOT/cancellation"
    local parameter_dir="$case_dir/parameters"
    local output_dir="$case_dir/output"
    local script_pid
    local status
    local attempts=0

    make_shims "$case_dir/bin"
    mkdir -p "$case_dir/session"
    make_parameters "$parameter_dir" "$output_dir"

    PATH="$case_dir/bin:$PATH" \
        MOCK_MODE="cancellation" \
        MOCK_DOCKER_LOG="$case_dir/docker.log" \
        MOCK_CONTAINER_PID="$case_dir/container.pid" \
        OPENJD_SESSION_WORKING_DIR="$case_dir/session" \
        bash "$RUN_SCRIPT" \
        "$parameter_dir/output" \
        "$parameter_dir/resolution" \
        "$parameter_dir/feature_quality" \
        "$parameter_dir/point_cloud_quality" \
        "$parameter_dir/generate_dsm" \
        "$parameter_dir/generate_dtm" \
        "$parameter_dir/max_concurrency" \
        >"$case_dir/stdout.log" 2>"$case_dir/stderr.log" &
    script_pid=$!

    while [[ ! -f "$case_dir/container.pid" && "$attempts" -lt 100 ]]; do
        sleep 0.05
        attempts=$((attempts + 1))
    done
    [[ -f "$case_dir/container.pid" ]] || fail "cancellation container did not start"

    kill -TERM "$script_pid"
    set +e
    wait "$script_pid"
    status=$?
    set -e

    [[ "$status" -eq 143 ]] || fail "cancellation returned $status; expected 143"
    grep -q '^stop --time 20 ' "$case_dir/docker.log" ||
        fail "cancellation did not stop the container"
    grep -q '^rm -f ' "$case_dir/docker.log" ||
        fail "cancellation did not remove the container"
    [[ ! -f "$case_dir/container.pid" ]] ||
        fail "cancellation left the mock container state behind"
    printf 'PASS: cancellation cleanup\n'
}

run_case "checksum rejection" checksum_failure 65
run_case "download failure" download_failure 22
run_case "Docker pull failure" pull_failure 17
run_case "nonzero ODM exit" odm_failure 42
run_cancellation_case
run_case "missing expected artifact" missing_artifact 66
run_case "successful packaging" success 0

grep -q -- '--workdir /datasets/brighton_beach' \
    "$TEST_ROOT/successful packaging/docker.log" ||
    fail "container does not use the writable survey directory as its working directory"
printf 'PASS: writable container working directory\n'

SUCCESS_MANIFEST="$TEST_ROOT/successful packaging/output/open_drone_map/manifest.json"
python3 - "$SUCCESS_MANIFEST" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as stream:
    manifest = json.load(stream)
assert manifest["runtime"]["status"] == "success"
assert manifest["dataset"]["sourceImageCount"] == 18
assert manifest["application"]["version"] == "3.6.1"
assert any(item["role"] == "orthophoto" for item in manifest["artifacts"])
PY
printf 'PASS: success manifest\n'
