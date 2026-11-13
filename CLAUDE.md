# Working in EverydayAI

Guide for coding agents and contributors. The repository is public and MIT licensed. Everything
committed here is published.

## What this repository is

A collection of self-contained demonstrations of context engineering and AI-assisted operations.
Each project should be runnable from a clean clone, with synthetic inputs and no private
infrastructure.

## Layout

| Path | Holds |
|---|---|
| `demos/alpine-ai/` | The original presentation, report-generation and resume-system demos |
| `prompts/` | Prompt libraries by domain |
| `skills/` | Agent skills, each with its own license where adapted |
| `tools/` | Standalone command-line utilities |

Every directory under `tools/` and `demos/` has a `README.md`. The root `README.md` indexes the
projects and is updated when a project is added.

## Conventions

- **Python standard library only** unless a README states otherwise. No `requirements.txt` is
  needed for the current projects.
- **Tests live beside the code**, named `test_<module>.py`, and run directly:
  `python3 tools/<name>/test_<name>.py`.
- **Temporary Git repositories** are built inside the test's temp directory. Tests must not touch
  the contributor's checkout.
- **Stub external commands** on `PATH` rather than requiring an account. `gh` and `quarto` are the
  two commands treated this way.
- **Exit codes are part of the interface.** Document them in the README and test them.
- **Failure paths are tested.** A tool that reports ambiguity or refuses a partial write needs a
  test that proves it.

## Commands

```bash
python3 tools/aws-session/test_aws_session.py
python3 tools/agent-continuity/test_agent_continuity.py
python3 tools/quarto-batch-edit/test_quarto_batch_edit.py
python3 demos/deterministic-context/test_context_registry.py
```

There is no root-level runner. Each suite prints its own tally and exits non-zero on failure.

## Publication rules

Before committing, check the diff for:

- credentials, tokens, account identifiers, email addresses and phone numbers
- client names, private repository links, internal hostnames and absolute home-directory paths
- fixtures derived from confidential communications or business records
- third-party code without a compatible license and attribution

Use synthetic names (`Alpha`, `Beta`, `acme`, `example.com`) and synthetic data. When adapting
third-party material, keep its license file beside it and record the source in the README.

## Writing

Prose in this repository follows a plain style: no em dashes, no "X, not Y" antithesis slogans, no
authenticity intensifiers (`real`, `actually`, `truly`, `genuinely`, `literally`, `honestly`), and
no claims beyond what the tests or evidence support. Prefer a concrete command and its output over
an adjective.
