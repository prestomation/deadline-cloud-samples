# tmate Shell

Get an interactive shell on a Deadline Cloud service-managed fleet (SMF) worker
using [tmate](https://tmate.io/), with no additional infrastructure required.

## How it works

1. The `submit.sh` script generates an ephemeral SSH keypair
2. The public key is sent as a job parameter
3. The worker installs tmate from conda-forge, writes the public key to an
   `authorized_keys` file, and starts a key-restricted tmate session
4. The SSH connection string appears in the job logs
5. You connect from your local machine using the ephemeral private key

Only the holder of the private key can connect — even if someone reads the
connection string from the logs, they cannot access the session.

## Prerequisites

- [Deadline Cloud CLI](https://github.com/aws-deadline/deadline-cloud) installed
  and configured with a default farm and queue
- The queue must have a Conda queue environment configured (standard for SMF queues)
- `ssh-keygen` available locally (included with Git on Windows)

## Usage

```bash
# Submit with default 1-hour timeout
python submit.py

# Submit with custom timeout (seconds)
python submit.py 7200
```

The script will poll the job logs and print the SSH command when the session is
ready:

```
=== TMATE SESSION READY ===

Connect with:
  ssh -i /path/to/tmate_shell/.tmate_key XYZ123@nyc1.tmate.io
```

## Security

- An ephemeral ed25519 keypair is generated per-use (stored as `.tmate_key`)
- The tmate session is started with `-a authorized_keys`, restricting access to
  the holder of the matching private key
- The `.tmate_key` and `.tmate_key.pub` files are gitignored
- The session automatically terminates after the configured timeout
