# Kiro Agent Job Bundle

Run [Kiro CLI](https://kiro.dev) as an AI agent on AWS Deadline Cloud workers.

## Overview

This job bundle enables running Kiro as an autonomous AI agent within Deadline Cloud. The agent can:
- Debug failed Deadline Cloud jobs
- Create OpenJD job bundles
- Investigate worker environments
- Write scripts, code, and documentation

## Structure

```
kiro_agent/
├── template.yaml           # OpenJD job template
├── agent_context/          # Agent prompts (customize these)
│   ├── system_prompt.txt   # System instructions for the agent
│   └── user_prompt.txt     # Task prompt for the agent
└── kiro_output/            # Output directory (gitignored)
```

## Parameters

| Parameter | Type | Description |
|-----------|------|-------------|
| `AgentContext` | PATH (IN) | Folder containing `system_prompt.txt` and `user_prompt.txt` |
| `OutputDir` | PATH (OUT) | Directory where the agent writes output |
| `KiroAuthFile` | PATH (IN) | Path to your `~/.local/share/kiro-cli/data.sqlite3` auth file |

## Usage

### Submit a job

```bash
deadline bundle submit ./kiro_agent \
  --farm-id <farm-id> \
  --queue-id <queue-id> \
  -p "KiroAuthFile=$HOME/.local/share/kiro-cli/data.sqlite3" \
  --yes
```

### Customize the agent task

Edit `agent_context/user_prompt.txt` with your task, or create a new context folder:

```bash
mkdir my_context
echo "Your system prompt" > my_context/system_prompt.txt
echo "Your task" > my_context/user_prompt.txt

deadline bundle submit ./kiro_agent \
  -p "AgentContext=./my_context" \
  -p "KiroAuthFile=$HOME/.local/share/kiro-cli/data.sqlite3" \
  --yes
```

### Wait and get results

```bash
# Wait for completion
deadline job wait --job-id <job-id> --timeout 600

# View logs
deadline job logs --job-id <job-id>

# Download output
deadline job download-output --job-id <job-id> --yes
```

## System Prompt Variables

The system prompt supports these placeholders (replaced at runtime):
- `${SESSION_DIR}` - Worker session directory
- `${OUTPUT_DIR}` - Output directory path

## Requirements

- Linux worker (uses `attr.worker.os.family: linux`)
- Internet access to install kiro-cli via `curl -fsSL https://cli.kiro.dev/install | bash`
- Valid Kiro CLI authentication (data.sqlite3 file)
