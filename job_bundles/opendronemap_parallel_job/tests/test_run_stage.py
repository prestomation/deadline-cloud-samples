#!/usr/bin/env python3
"""Regression tests for the host-side stage runner."""

from __future__ import annotations

import os
import subprocess
import tempfile
import textwrap
import unittest
from pathlib import Path

BUNDLE_DIR = Path(__file__).resolve().parents[1]
RUN_STAGE = BUNDLE_DIR / "scripts" / "run_stage.sh"


class TestRunStage(unittest.TestCase):
    def test_scratch_check_uses_local_session_filesystem(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            fake_bin = root / "bin"
            fake_bin.mkdir()
            attachment = root / "attachment"
            output = root / "output"
            session = root / "session"
            for path in (attachment, output, session):
                path.mkdir()

            docker = fake_bin / "docker"
            docker.write_text(
                "#!/usr/bin/env bash\n"
                "[[ \"${1:-}\" == info ]]\n",
                encoding="utf-8",
            )
            docker.chmod(0o755)

            df = fake_bin / "df"
            df.write_text(
                textwrap.dedent(
                    """\
                    #!/usr/bin/env bash
                    printf 'Filesystem 1024-blocks Used Available Capacity Mounted on\\n'
                    if [[ "${@: -1}" == "$EXPECTED_SESSION" ]]; then
                        printf 'local 50000000 0 50000000 0%% /local\\n'
                    else
                        printf 'attachment 10 9 1 90%% /attachment\\n'
                    fi
                    """
                ),
                encoding="utf-8",
            )
            df.chmod(0o755)

            environment = os.environ.copy()
            environment["PATH"] = f"{fake_bin}{os.pathsep}{environment['PATH']}"
            environment["EXPECTED_SESSION"] = str(session)
            result = subprocess.run(
                [
                    "bash",
                    str(RUN_STAGE),
                    "unsupported",
                    str(root / "images"),
                    str(attachment),
                    str(output),
                    str(BUNDLE_DIR / "scripts"),
                    str(session),
                ],
                text=True,
                capture_output=True,
                env=environment,
                check=False,
            )

            self.assertEqual(result.returncode, 64, result.stderr)
            self.assertIn("Unsupported ODM parallel stage", result.stderr)
            self.assertNotIn("free worker disk", result.stderr)


if __name__ == "__main__":
    unittest.main()
