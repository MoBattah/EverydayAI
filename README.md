# EverydayAI

Working systems for context engineering and AI-assisted operations.

This repository holds small, tested tools that show how an AI assistant can be given durable
context, constrained behavior, and recoverable state. Each project runs from a clean clone with
synthetic data, and each documents the failure modes it was built to handle.

The through-line is a four-stage pipeline. The stages are useful because each one has a failure
mode that the next stage cannot repair.

| Stage | Question it answers | Failure when skipped |
|---|---|---|
| **Inception** | How does a thought become a structured asset? | The context exists only in a conversation that will be lost |
| **Storage** | Where does a fact live, and what else is generated from it? | The same fact is copied into five files and four of them go stale |
| **Refinement** | How is raw material verified and reduced? | A transcript or a status report is trusted past what the evidence supports |
| **Assembly** | What context does this task, and only this task, receive? | Every session starts with everything, and the agent drowns |

## Engineering projects

Each project has a README with a problem statement, architecture, quick start, a failure
demonstration, and test commands.

| Project | Stage | What it demonstrates | Runtime | Dependencies | Quick start |
|---|---|---|---|---|---|
| [`tools/aws-session`](tools/aws-session/) | Assembly | Account-pinned AWS credentials for agent shells; refuses to answer for the wrong account | Bash, Python test suite | AWS CLI v2.9+ | `python3 tools/aws-session/test_aws_session.py` |
| [`tools/quarto-batch-edit`](tools/quarto-batch-edit/) | Assembly | Transactional batch editing of Quarto sources with heading-aware placement and all-or-nothing writes | Python 3.10+ | None (Quarto optional) | `python3 tools/quarto-batch-edit/test_quarto_batch_edit.py` |
| [`tools/agent-continuity`](tools/agent-continuity/) | Inception | Reconstruct a repository's working state in one read-only call: worktrees, unmerged branches, landed commits, open pull requests | Python 3.10+ | Git (`gh` optional) | `python3 tools/agent-continuity/test_agent_continuity.py` |

A project appears here only when its tests pass and its README documents a reproducible
demonstration.

## Context engineering demos

`demos/` holds the original presentation work and a self-contained storage demonstration.

- **[Presentation](demos/alpine-ai/presentation/)**: "Automating the Mundane", the four-stage
  argument in slide form. Quarto source, Beamer PDF, and the tracked output.
- **[Report generation](demos/alpine-ai/report-generation/)**: a Quarto and LaTeX pipeline that
  turns analysis into a typeset PDF. The `.qmd` source is the artifact; `build.sh` renders it.
- **[Resume system](demos/alpine-ai/resume-system/)**: documentation as code. Shared content
  fragments, per-variant LaTeX templates, and two built PDFs from one content base.
- **Wardrobe database**: a machine-readable inventory used for outfit generation experiments.
- **[Deterministic context](demos/deterministic-context/)**: one JSON record per workspace, every
  Markdown view generated from it, and a check that fails when a copy drifts.

## Prompts and skills

Prompts are the smallest unit in the repository and the easiest to copy. They are kept because they
show the input side of the pipeline.

- **[`prompts/linguistics-prompts/`](prompts/linguistics-prompts/)**: vocabulary coaching from call
  transcripts.
- **[`prompts/osint/`](prompts/osint/)**: reputation research and technical due diligence.
- **[`prompts/claude-code/`](prompts/claude-code/)**: codebase audits, performance review, and
  transcription instructions.
- **[`skills/socratic-tutor/`](skills/socratic-tutor/)**: a structured tutoring skill with diagnostic
  placement and spaced review. MIT licensed, adapted from Jane Street's `agent_skills`.

## Repository layout

```text
.
├── demos/                  Reproducible context engineering demonstrations
│   ├── alpine-ai/          Presentation, report generation, resume system
│   └── deterministic-context/  Records as data, views generated, drift checked
├── prompts/                Prompt libraries by domain
├── skills/                 Agent skills with their own licenses
├── tools/                  Standalone command-line utilities
│   ├── aws-session/        AWS credential helper for agent shells
│   ├── agent-continuity/   Read-only repository state reconstruction
│   └── quarto-batch-edit/  Transactional Quarto edit batches
├── CLAUDE.md               Guide for coding agents working in this repository
└── LICENSE                 MIT
```

## Running the tests

Every project is self-contained and uses only the Python standard library unless its README says
otherwise. There is no root-level test runner and no shared virtual environment to create.

```bash
python3 tools/aws-session/test_aws_session.py
python3 tools/agent-continuity/test_agent_continuity.py
python3 tools/quarto-batch-edit/test_quarto_batch_edit.py
python3 demos/deterministic-context/test_context_registry.py
```

Tests that touch Git build temporary repositories under the system temp directory. Tests that touch
GitHub use a stub `gh` on `PATH`, so no account or network access is required.

## Design rules

These rules are what make the projects reproducible, and they are enforced by review.

1. **Standard library first.** A tool that needs a package manager to demonstrate a filesystem
   invariant is harder to trust and harder to run.
2. **Synthetic inputs.** No project depends on a private repository, a client dataset, or a live
   account. Fixtures are checked in.
3. **Failure is a first-class output.** Ambiguity stops the operation and names the candidates.
   Partial application is refused as a whole. A command that cannot answer says so and exits
   non-zero.
4. **One fact, one home.** Where a fact is projected into Markdown, the projection is generated and
   the drift is detected.
5. **Read-only means read-only.** Inspection tools do not fetch, write refs, or touch an index.

## License and attribution

MIT. See [LICENSE](LICENSE).

`skills/socratic-tutor/` carries its own MIT license from Jane Street Group, LLC; see
[`skills/socratic-tutor/LICENSE.md`](skills/socratic-tutor/LICENSE.md).
