# Master AI Music Autonomously

Automation system for Suno music creation, mastering, and export using a hybrid architecture:
- deterministic browser skills for reliable execution
- planner-driven orchestration for autonomous runs
- optional AI-assisted spec generation

## Current Focus (Build Now)

We are actively building and hardening the **in-repo hybrid autopilot**:
- input: high-level `music_type`
- auto-generate: lyrics, styles, weirdness, style influence
- execute: create -> wait -> master -> export
- resilience: retries, checkpoint/resume, phase artifacts

Example:

```bash
cd suno_mastering_agent
source venv/bin/activate
python main.py autopilot --music-type "edm" --count 3
```

Phase 2 planning mode (parallel candidates + artifacts):

```bash
python main.py autopilot \
  --music-type "edm" \
  --count 3 \
  --phase2 \
  --candidate-count 4 \
  --phase2-artifact-log /tmp/suno_phase2_artifacts.jsonl
```

Resumable robust mode:

```bash
python main.py autopilot \
  --music-type "edm" \
  --count 20 \
  --step-retries 3 \
  --checkpoint-file /tmp/suno_autopilot_checkpoint.json \
  --resume \
  --continue-on-error
```

## Future Features (Not Active Dependencies Yet)

These are tracked as future enhancements, not required for the current build:

- **LangChain DeepAgents integration** (optional planner backend migration once executor reliability is stable)
  - Ref: https://github.com/langchain-ai/deepagents
- **BMAD Method integration** (process/workflow templates for planning discipline)
  - Ref: https://github.com/bmad-code-org/BMAD-METHOD
- **Gastown-style orchestration** (larger multi-agent workspace lifecycle management)
  - Ref: https://github.com/steveyegge/gastown

Decision: we will keep using lightweight in-repo equivalents first, then consider full external adoption once execution reliability is consistently strong.

## Project Layout

- `suno_mastering_agent/main.py` - CLI entry point (`autopilot`, `autocreate`, `agent`, etc.)
- `suno_mastering_agent/src/skills/` - deterministic browser action primitives
- `suno_mastering_agent/src/agents/` - composed automation runners
- `suno_mastering_agent/src/agent/` - LLM/tool workflows
- `suno_mastering_agent/src/ui/` - Gradio UI
