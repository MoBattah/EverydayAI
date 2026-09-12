# aws-session

A bash helper for AWS credentials across several accounts, written for coding agents (Claude Code,
Codex, Gemini CLI) that run AWS commands on a developer's machine. It uses IAM Identity Center
(SSO) first and accepts pasted credentials as a fallback.

This is a working example to adapt. Copy the script, change the defaults, and remove what you do
not need.

## What it guards against

| Failure | Without a guard | What aws-session does |
|---|---|---|
| Ambient credentials | `AWS_ACCESS_KEY_ID` and `AWS_SESSION_TOKEN` in the environment take precedence over the `AWS_PROFILE` variable. A shell that sourced one account's credentials answers for that account while the command names another | Every AWS call runs with the `AWS_*` variables cleared, and `exec` clears them before loading the alias |
| Wrong account | A profile copied or edited incorrectly points at a different account, and nothing reports it until a deploy lands there | Each alias is pinned to one account id. A mismatch exits non-zero with `WRONG ACCOUNT` |
| Sandboxed shells | Some agent sandboxes refuse `source "$(...)" && cmd`, because substitution and chaining cannot be inspected before they run. Claude Code's worktree isolation is one | `aws-session exec <alias> -- <cmd>` is one plain command, and the credentials never appear on a command line |
| Concurrent agents | Two sessions share one credentials file, and the second overwrites pasted credentials the first is still using | `save` refuses to replace pasted credentials that still work unless given `--force`. SSO cache files are regenerated freely |
| Truncated pastes | A session token copied by hand loses a chunk and fails later with a signature error | `save` checks the token length and calls STS before it writes anything |

## Requirements

- AWS CLI v2.9.0 or later, for `aws configure export-credentials` and `aws sso login --sso-session`
- bash 3.2 or later, `perl` and `awk`, all present on a stock macOS or Linux install

## Install

```bash
install -m 755 aws-session ~/.local/bin/aws-session
mkdir -p ~/.config/aws-session && chmod 700 ~/.config/aws-session
install -m 600 sessions.conf.example ~/.config/aws-session/sessions.conf
```

Edit the registry, then give each SSO alias a profile of the same name in `~/.aws/config`:

```ini
[sso-session example]
sso_start_url = https://example.awsapps.com/start
sso_region = us-east-1
sso_registration_scopes = sso:account:access

[profile staging]
sso_session = example
sso_account_id = 111111111111
sso_role_name = AdministratorAccess
region = us-east-1
```

```bash
aws-session login staging     # one browser login covers every alias on that sso-session
aws-session list
```

## Commands

| Command | Does |
|---|---|
| `list` | Every alias with its account, region, source and status |
| `login <alias>` | Browser login for the alias's SSO session |
| `check <alias>` | Exit 0 and print the account id if the credentials work |
| `sso-ok <alias>` | Exit 0 if the SSO token is alive. Ignores pasted credentials |
| `path <alias>` | Print the path of a sourceable env file, regenerating it from SSO |
| `exec <alias> -- <cmd>` | Run a command with the alias's credentials in its environment |
| `save <alias> [--file F] [--region R] [--force]` | Install pasted credentials, from stdin or a file |

```bash
aws-session exec prod-read -- aws s3 ls
source "$(aws-session path staging)"          # in a shell that allows it
pbpaste | aws-session save vendor             # break-glass: bash, ini, PowerShell or assume-role JSON
```

`list` statuses: `valid` is usable, `login` needs `aws-session login`, `paste-bg` means SSO has
expired and pasted break-glass credentials are in use, `missing` and `expired` apply to paste-only
aliases, and `MISMATCH` means the credentials belong to an account other than the pinned one.

## Using it from an agent

A paragraph for `CLAUDE.md`, `AGENTS.md` or an equivalent file:

```markdown
AWS access goes through `aws-session`. Run commands as `aws-session exec <alias> -- <command>`;
`aws-session list` shows the aliases. If it reports that the SSO session expired, stop and ask
for `aws-session login <alias>` to be run; do not look for credentials anywhere else. A
WRONG ACCOUNT error means stop.
```

A launcher that refreshes SSO before starting the agent:

```bash
#!/usr/bin/env bash
if [[ -t 1 ]] && ! aws-session sso-ok staging >/dev/null 2>&1; then
  aws-session login staging || echo "continuing without AWS credentials" >&2
fi
exec claude "$@"
```

## Configuration

| Variable | Default |
|---|---|
| `AWS_SESSION_CONF` | `$XDG_CONFIG_HOME/aws-session/sessions.conf`, or `~/.config/aws-session/sessions.conf` |
| `AWS_SESSION_DIR` | The registry's directory. Env files are written here as `aws-session-env-<alias>.sh` |
| `AWS_SESSION_MIN_TOKEN_LEN` | `400`. Lower it if your session tokens are shorter |

The registry format is documented in `sessions.conf.example`.

## Security notes

- Env files hold short-lived credentials in plaintext, mode 600, in a directory created as 700.
  The AWS CLI keeps SSO role credentials in `~/.aws/cli/cache` in a similar form.
- For an SSO alias the file is rebuilt from the SSO token on every `path` and `exec`, and a file
  carrying the generated marker is never treated as pasted credentials.
- Pasted credentials last as long as they were issued for. `list` reports them as `expired` once
  STS rejects them.
- The registry holds account ids and no secrets. Keep it out of public repositories anyway.
- Temp files are created inside the credentials directory and removed on exit.

## Compared with aws-vault and Granted

Both cover more ground: encrypted credential storage, role chaining, console login. aws-session is
smaller and covers one case: an agent's shell that needs SSO credentials, pinned to the correct
account, through a single command a sandbox will run. It is about 400 lines of bash, so it can be
read in full before it is trusted.

## Tests

```bash
python3 test_aws_session.py
```

Standard library only. A stub `aws` stands in for the CLI, so no AWS account or network is needed.
The suite runs under every bash it finds, including `/bin/bash` 3.2 on macOS.

## License

MIT. See `LICENSE` at the repository root.
