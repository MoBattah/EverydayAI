#!/usr/bin/env python3
"""Checks for aws-session. Stdlib only: no AWS account and no network.

A stub `aws` on PATH stands in for the AWS CLI, and every file the tool reads or writes
lives in a temp dir. The suite runs once per bash found, because macOS ships bash 3.2 at
/bin/bash and most other systems ship 5.x.

    python3 test_aws_session.py
"""
import json, os, shutil, stat, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
SCRIPT = HERE / "aws-session"

fails = []
def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"  {detail}" if not cond and detail else ""))
    if not cond:
        fails.append(name)

# Fake credential values are assembled at runtime, so no line in this file looks like a key
# to a secret scanner.
SECRET = "s" * 40
TOKEN = "t" * 600
def kid(name):
    return "TESTKEY" + name.upper()

# The stub answers the four AWS CLI calls aws-session makes. State lives in $AWS_STUB_STATE:
#   sso/<profile>  line 1 the account the profile resolves to, line 2 the key id it exports.
#                  No file means the SSO token has expired.
#   keys/<key id>  the account those static credentials belong to. No file means invalid.
#   log            every invocation, plus a LEAK line if a --profile call saw ambient creds.
STUB = r'''#!/bin/sh
state="$AWS_STUB_STATE"
printf '%s\n' "$*" >> "$state/log"
profile=""; prev=""
for a in "$@"; do
  [ "$prev" = "--profile" ] && profile="$a"
  prev="$a"
done
if [ -n "$profile" ] && [ -n "${AWS_ACCESS_KEY_ID:-}${AWS_SESSION_TOKEN:-}${AWS_PROFILE:-}" ]; then
  printf 'LEAK %s\n' "$profile" >> "$state/log"
fi
case "$1 $2" in
  "sts get-caller-identity")
    if [ -n "$profile" ]; then
      [ -f "$state/sso/$profile" ] || { echo "token expired" >&2; exit 255; }
      sed -n 1p "$state/sso/$profile"; exit 0
    fi
    k="${AWS_ACCESS_KEY_ID:-}"
    if [ -n "$k" ] && [ -n "${AWS_SECRET_ACCESS_KEY:-}" ] && [ -n "${AWS_SESSION_TOKEN:-}" ] \
       && [ -f "$state/keys/$k" ]; then
      cat "$state/keys/$k"; exit 0
    fi
    echo "invalid credentials" >&2; exit 255 ;;
  "configure export-credentials")
    [ -f "$state/sso/$profile" ] || exit 255
    printf 'export AWS_ACCESS_KEY_ID=%s\n' "$(sed -n 2p "$state/sso/$profile")"
    printf 'export AWS_SECRET_ACCESS_KEY=stubsecret\nexport AWS_SESSION_TOKEN=stubtoken\n'
    exit 0 ;;
  "sso login") exit 0 ;;
esac
echo "stub: unhandled: $*" >&2
exit 2
'''

REGISTRY = """# alias | account_id | region | sso_session | description
alpha | 111111111111 | us-east-1 | corp | SSO, token alive
beta  | 222222222222 | us-west-2 | corp | SSO, token expired
gamma | 333333333333 | eu-west-1 |      | paste-only, working credentials
delta | 444444444444 | us-east-2 |      | paste-only, nothing saved
eps   | 555555555555 | us-east-1 |      | paste-only, expired credentials
zeta  | 666666666666 | us-east-1 | corp | SSO, resolves to the wrong account
"""


class Fixture:
    def __init__(self, bash):
        self.bash = bash
        self.root = Path(tempfile.mkdtemp(prefix="aws-session-test-"))
        self.bin = self.root / "bin"
        self.state = self.root / "state"
        self.cfg = self.root / "cfg"
        for d in (self.bin, self.state / "sso", self.state / "keys", self.cfg):
            d.mkdir(parents=True)
        stub = self.bin / "aws"
        stub.write_text(STUB)
        stub.chmod(0o755)
        (self.cfg / "sessions.conf").write_text(REGISTRY)
        self.sso("alpha", "111111111111")
        self.sso("zeta", "999999999999")
        for name, acct in (("alpha", "111111111111"), ("beta", "222222222222"),
                           ("gamma", "333333333333"), ("delta", "444444444444"),
                           ("wrong", "333333333333")):
            (self.state / "keys" / kid(name)).write_text(acct + "\n")
        self.pasted("gamma", kid("gamma"))
        self.pasted("eps", kid("expired"))

    def sso(self, profile, acct):
        (self.state / "sso" / profile).write_text(f"{acct}\n{kid(profile)}\n")

    def envfile(self, alias):
        return self.cfg / f"aws-session-env-{alias}.sh"

    def pasted(self, alias, key):
        p = self.envfile(alias)
        p.write_text(f"export AWS_ACCESS_KEY_ID={key}\nexport AWS_SECRET_ACCESS_KEY={SECRET}\n"
                     f"export AWS_SESSION_TOKEN={TOKEN}\nexport AWS_REGION=us-east-1\n")
        p.chmod(0o600)
        return p

    def env(self, **extra):
        e = {"PATH": f"{self.bin}:/usr/bin:/bin", "HOME": str(self.root),
             "AWS_STUB_STATE": str(self.state),
             "AWS_SESSION_CONF": str(self.cfg / "sessions.conf"),
             "AWS_SESSION_DIR": str(self.cfg)}
        e.update(extra)
        return {k: v for k, v in e.items() if v is not None}

    def run(self, *args, stdin="", env=None, timeout=20):
        return subprocess.run([self.bash, str(SCRIPT), *args], input=stdin, text=True,
                              capture_output=True, env=env or self.env(), timeout=timeout)

    def log(self):
        p = self.state / "log"
        return p.read_text() if p.exists() else ""

    def temps_left(self):
        return list(self.cfg.glob(".aws-session.*"))

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)


def paste_bash(key, token=TOKEN):
    return (f"export AWS_ACCESS_KEY_ID={key}\nexport AWS_SECRET_ACCESS_KEY={SECRET}\n"
            f"export AWS_SESSION_TOKEN={token}\n")

PASTE_FORMATS = {
    "bash exports": paste_bash,
    "ini": lambda k: (f"[default]\naws_access_key_id = {k}\naws_secret_access_key = {SECRET}\n"
                      f"aws_session_token = {TOKEN}\n"),
    "PowerShell": lambda k: (f'$Env:AWS_ACCESS_KEY_ID="{k}"\n$Env:AWS_SECRET_ACCESS_KEY="{SECRET}"\n'
                             f'$Env:AWS_SESSION_TOKEN="{TOKEN}"\n'),
    "assume-role JSON": lambda k: json.dumps({"Credentials": {
        "AccessKeyId": k, "SecretAccessKey": SECRET, "SessionToken": TOKEN,
        "Expiration": "2030-01-01T00:00:00Z"}}, indent=2),
}


def suite(bash):
    version = subprocess.run([bash, "-c", "echo $BASH_VERSION"], capture_output=True,
                             text=True).stdout.strip()
    tag = f"[bash {version}]"
    print(f"\n{bash} ({version})")
    t = Fixture(bash)
    def c(name, cond, detail=""):
        check(f"{tag} {name}", cond, detail)

    try:
        # --- help ---
        r = t.run("--help")
        c("help exits 0", r.returncode == 0, r.stderr)
        cmds = ("list", "login", "check", "sso-ok", "path", "exec", "save")
        c("help lists all seven commands", all(f"aws-session {x}" in r.stdout for x in cmds), r.stdout)
        c("help stops before the implementation notes", "WHY" not in r.stdout, r.stdout)
        c("unknown command exits non-zero", t.run("bogus").returncode != 0)

        # --- list ---
        r = t.run("list", env=t.env(AWS_ACCESS_KEY_ID=kid("gamma"), AWS_SECRET_ACCESS_KEY=SECRET,
                                    AWS_SESSION_TOKEN=TOKEN, AWS_PROFILE="elsewhere"))
        rows = {ln.split()[0]: ln.split() for ln in r.stdout.splitlines()[1:]
                if ln.strip() and not ln.startswith("status:")}
        expected = {"alpha": "valid", "beta": "login", "gamma": "valid",
                    "delta": "missing", "eps": "expired", "zeta": "MISMATCH"}
        for alias, status in expected.items():
            got = rows.get(alias, [None] * 5)[4]
            c(f"list: {alias} is {status}", got == status, f"got {got}; {r.stderr}")
        c("list: profile calls never see ambient credentials", "LEAK" not in t.log(), t.log())

        # --- check ---
        r = t.run("check", "alpha")
        c("check: live SSO alias prints its account",
          r.returncode == 0 and r.stdout.strip() == "111111111111", r.stdout + r.stderr)
        r = t.run("check", "zeta")
        c("check: wrong account exits non-zero", r.returncode != 0 and "WRONG ACCOUNT" in r.stderr, r.stderr)
        r = t.run("check", "beta")
        c("check: expired SSO says how to log in",
          r.returncode != 0 and "aws-session login beta" in r.stderr, r.stderr)
        r = t.run("check", "gamma")
        c("check: working pasted credentials",
          r.returncode == 0 and r.stdout.strip() == "333333333333", r.stdout + r.stderr)
        r = t.run("check", "eps")
        c("check: expired pasted credentials", r.returncode != 0 and "expired" in r.stderr, r.stderr)
        r = t.run("check", "nope")
        c("check: unknown alias", r.returncode != 0 and "unknown alias" in r.stderr, r.stderr)
        r = t.run("check", "../gamma")
        c("check: alias with a path separator is refused", r.returncode != 0 and "invalid alias" in r.stderr, r.stderr)

        # --- path ---
        r = t.run("path", "alpha")
        p = t.envfile("alpha")
        body = p.read_text() if p.exists() else ""
        c("path: prints the env file", r.returncode == 0 and r.stdout.strip() == str(p), r.stdout + r.stderr)
        c("path: file starts with the generated marker", body.startswith("# generated-by: aws-session"), body[:80])
        c("path: file is mode 600", p.exists() and stat.S_IMODE(p.stat().st_mode) == 0o600)
        c("path: credentials come from the SSO export", f"AWS_ACCESS_KEY_ID={kid('alpha')}" in body, body)
        c("path: registry region is appended",
          "export AWS_REGION=us-east-1" in body and "export AWS_DEFAULT_REGION=us-east-1" in body, body)
        c("path: no temp files left behind", not t.temps_left(), str(t.temps_left()))
        r = t.run("path", "zeta")
        c("path: wrong account writes nothing",
          r.returncode != 0 and "WRONG ACCOUNT" in r.stderr and not t.envfile("zeta").exists(), r.stderr)
        c("path: failed run leaves no temp files", not t.temps_left(), str(t.temps_left()))
        r = t.run("path", "beta")
        c("path: expired SSO with nothing pasted exits non-zero", r.returncode != 0 and "login" in r.stderr, r.stderr)
        t.pasted("beta", kid("beta"))
        r = t.run("path", "beta")
        c("path: expired SSO falls back to working pasted credentials",
          r.returncode == 0 and "break-glass" in r.stderr, r.stdout + r.stderr)
        t.pasted("beta", kid("wrong"))
        r = t.run("path", "beta")
        c("path: the pasted fallback is held to the pinned account",
          r.returncode != 0 and "WRONG ACCOUNT" in r.stderr, r.stderr)
        t.envfile("beta").unlink()
        r = t.run("path", "delta")
        c("path: paste-only alias with nothing saved", r.returncode != 0 and "aws-session save delta" in r.stderr, r.stderr)
        fresh = t.root / "fresh" / "creds"
        r = t.run("path", "alpha", env=t.env(AWS_SESSION_DIR=str(fresh)))
        c("path: creates a missing credentials dir as 700",
          r.returncode == 0 and fresh.is_dir() and stat.S_IMODE(fresh.stat().st_mode) == 0o700, r.stderr)

        # --- exec ---
        r = t.run("exec", "alpha", "--", "env",
                  env=t.env(AWS_PROFILE="elsewhere", AWS_REGION="ap-south-1", AWS_ACCESS_KEY_ID="AMBIENT"))
        lines = set(r.stdout.splitlines())
        c("exec: runs the command with the alias's credentials",
          r.returncode == 0 and f"AWS_ACCESS_KEY_ID={kid('alpha')}" in lines, r.stderr)
        c("exec: the registry region replaces the ambient one", "AWS_REGION=us-east-1" in lines)
        c("exec: ambient AWS_PROFILE is removed", not any(ln.startswith("AWS_PROFILE=") for ln in lines))
        r = t.run("exec", "gamma", "env")
        c("exec: '--' is optional", r.returncode == 0 and f"AWS_ACCESS_KEY_ID={kid('gamma')}" in r.stdout, r.stderr)
        r = t.run("exec", "alpha", "--")
        c("exec: no command is a usage error", r.returncode != 0 and "usage" in r.stderr, r.stderr)
        r = t.run("exec", "zeta", "--", "env")
        c("exec: wrong account never runs the command",
          r.returncode != 0 and "AWS_ACCESS_KEY_ID" not in r.stdout, r.stdout)

        # --- save ---
        d = t.envfile("delta")
        for name, fmt in PASTE_FORMATS.items():
            if d.exists():
                d.unlink()
            r = t.run("save", "delta", stdin=fmt(kid("delta")))
            body = d.read_text() if d.exists() else ""
            c(f"save: parses {name}",
              r.returncode == 0 and f"AWS_ACCESS_KEY_ID={kid('delta')}" in body
              and f"AWS_SESSION_TOKEN={TOKEN}" in body and "AWS_REGION=us-east-2" in body, r.stderr)
        c("save: file is mode 600", d.exists() and stat.S_IMODE(d.stat().st_mode) == 0o600)
        r = t.run("save", "delta", stdin=paste_bash(kid("gamma")))
        c("save: refuses credentials for another account",
          r.returncode != 0 and "refusing" in r.stderr and f"AWS_ACCESS_KEY_ID={kid('delta')}" in d.read_text(), r.stderr)
        r = t.run("save", "delta", stdin=paste_bash(kid("delta")))
        c("save: will not replace working pasted credentials", r.returncode != 0 and "--force" in r.stderr, r.stderr)
        r = t.run("save", "delta", "--force", stdin=paste_bash(kid("delta")))
        c("save: --force replaces them", r.returncode == 0, r.stderr)
        r = t.run("save", "delta", "--force", stdin=paste_bash(kid("delta"), token=TOKEN[:50]))
        c("save: refuses a truncated token", r.returncode != 0 and "truncated" in r.stderr, r.stderr)
        r = t.run("save", "delta", "--force", stdin=paste_bash(kid("delta")),
                  env=t.env(AWS_SESSION_MIN_TOKEN_LEN="1000"))
        c("save: the token length floor is configurable", r.returncode != 0 and "truncated" in r.stderr, r.stderr)
        r = t.run("save", "delta", "--force", stdin=paste_bash("TESTKEYUNKNOWN"))
        c("save: refuses credentials STS rejects", r.returncode != 0 and "not valid" in r.stderr, r.stderr)
        r = t.run("save", "delta", "--force", stdin="nothing useful here\n")
        c("save: refuses a paste missing a value", r.returncode != 0 and "could not parse" in r.stderr, r.stderr)
        r = t.run("save", "nope", stdin=paste_bash(kid("delta")))
        c("save: unknown alias", r.returncode != 0 and "unknown alias" in r.stderr, r.stderr)
        paste_file = t.root / "paste.txt"
        paste_file.write_text(paste_bash(kid("delta")))
        r = t.run("save", "delta", "--force", "--file", str(paste_file))
        c("save: --file reads the paste from a file", r.returncode == 0, r.stderr)
        for opt in ("--file", "-f", "--region"):
            name = f"save: {opt} with no value exits non-zero"
            try:
                r = t.run("save", "delta", opt, stdin=paste_bash(kid("delta")), timeout=10)
                c(name, r.returncode != 0 and "needs" in r.stderr, r.stderr)
            except subprocess.TimeoutExpired:
                c(name, False, "hung until the 10s timeout")
        t.run("path", "alpha")
        r = t.run("save", "alpha", stdin=paste_bash(kid("alpha")))
        c("save: a generated SSO cache is replaced without --force",
          r.returncode == 0 and not t.envfile("alpha").read_text().startswith("# generated-by"), r.stderr)
        c("save: no temp files left behind", not t.temps_left(), str(t.temps_left()))

        # --- sso-ok ---
        c("sso-ok: live token", t.run("sso-ok", "alpha").returncode == 0)
        c("sso-ok: expired token", t.run("sso-ok", "beta").returncode == 1)
        c("sso-ok: paste-only alias", t.run("sso-ok", "gamma").returncode == 1)
        r = t.run("sso-ok", "zeta")
        c("sso-ok: wrong account fails", r.returncode != 0 and "WRONG ACCOUNT" in r.stderr, r.stderr)
        t.pasted("beta", kid("beta"))
        c("sso-ok: working pasted credentials do not count as SSO", t.run("sso-ok", "beta").returncode == 1)

        # --- login ---
        r = t.run("login", "alpha")
        c("login: opens the alias's SSO session",
          r.returncode == 0 and "sso login --sso-session corp" in t.log(), r.stderr)
        c("login: reports every alias on that session",
          all(a in r.stderr for a in ("alpha", "beta", "zeta")), r.stderr)
        r = t.run("login", "gamma")
        c("login: paste-only alias is refused", r.returncode != 0 and "paste-only" in r.stderr, r.stderr)

        # --- defaults ---
        home = t.root / "home"
        (home / ".config" / "aws-session").mkdir(parents=True)
        (home / ".config" / "aws-session" / "sessions.conf").write_text(REGISTRY)
        defaults = t.env(HOME=str(home), AWS_SESSION_CONF=None, AWS_SESSION_DIR=None)
        r = t.run("list", env=defaults)
        c("defaults: registry is read from ~/.config/aws-session", r.returncode == 0 and "alpha" in r.stdout, r.stderr)
        r = t.run("path", "alpha", env=defaults)
        c("defaults: env files are written beside the registry",
          r.returncode == 0 and (home / ".config" / "aws-session" / "aws-session-env-alpha.sh").exists(), r.stderr)
        xdg = t.root / "xdg"
        (xdg / "aws-session").mkdir(parents=True)
        (xdg / "aws-session" / "sessions.conf").write_text(REGISTRY)
        r = t.run("list", env=t.env(HOME=str(t.root / "empty-home"), XDG_CONFIG_HOME=str(xdg),
                                    AWS_SESSION_CONF=None, AWS_SESSION_DIR=None))
        c("defaults: XDG_CONFIG_HOME is honoured", r.returncode == 0 and "alpha" in r.stdout, r.stderr)
        r = t.run("list", env=t.env(AWS_SESSION_CONF=str(t.root / "absent.conf")))
        c("defaults: a missing registry is named", r.returncode != 0 and "absent.conf" in r.stderr, r.stderr)
    finally:
        t.close()


def bashes():
    found, seen = [], set()
    for cand in ("/bin/bash", shutil.which("bash")):
        if cand and os.path.exists(cand) and os.path.realpath(cand) not in seen:
            seen.add(os.path.realpath(cand))
            found.append(cand)
    return found


if __name__ == "__main__":
    if not shutil.which("perl"):
        print("perl is required")
        sys.exit(1)
    for b in bashes():
        suite(b)
    if fails:
        print(f"\n{len(fails)} check(s) failed")
        sys.exit(1)
    print("\nall checks passed")
