#!/usr/bin/env python3
"""Offers the client at the current commit to every installed computer (they update at their next daily sync).

  python3 scripts/release.py --dry-run     show what would be released
  python3 scripts/release.py               release it

Refuses unless: client/ and skill/ have no uncommitted changes, the commit is on GitHub (origin/main), GitHub serves
exactly these files at that commit, and the version in client/relay.py is newer than the one released now.
The server URL and admin key come from admin/config.json (or SESSION_RELAY_SERVER / SESSION_RELAY_ADMIN_KEY).
"""
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW = "https://raw.githubusercontent.com/hack-vibe-x/hack-session-relay/"
RELEASE_FILE = re.compile(r"^(client/[a-z_]+\.(?:py|json)|skill/SKILL\.md)$")


def git(*args, binary=False):
    out = subprocess.run(["git", "-C", ROOT] + list(args), capture_output=True, check=True)
    return out.stdout if binary else out.stdout.decode().strip()


def config():
    try:
        with open(os.path.join(ROOT, "admin", "config.json"), encoding="utf-8") as f:
            cfg = json.load(f)
    except (OSError, ValueError):
        cfg = {}
    server = (os.environ.get("SESSION_RELAY_SERVER") or cfg.get("server_url") or "").rstrip("/")
    key = os.environ.get("SESSION_RELAY_ADMIN_KEY") or cfg.get("admin_key") or ""
    if not server or not key:
        sys.exit("admin/config.json needs server_url and admin_key.")
    return server, key


def admin(server, key, method, body=None):
    req = urllib.request.Request(server + "/admin/client", data=json.dumps(body).encode() if body else None,
                                 method=method, headers={"Authorization": "Bearer " + key,
                                                         "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as res:
        return json.loads(res.read()).get("client")


def version_tuple(text):
    return tuple(int(x) for x in text.split("."))


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--force", action="store_true", help="release even if the version is not newer")
    args = parser.parse_args()

    if git("status", "--porcelain", "--", "client", "skill"):
        sys.exit("client/ or skill/ has uncommitted changes. Commit and push first.")
    git("fetch", "-q", "origin", "main")
    ref = git("rev-parse", "HEAD")
    if subprocess.run(["git", "-C", ROOT, "merge-base", "--is-ancestor", ref, "origin/main"]).returncode != 0:
        sys.exit("HEAD %s is not on origin/main. Push first." % ref[:12])
    source = git("show", "%s:client/relay.py" % ref)
    found = re.search(r'^VERSION = "([0-9.]+)"', source, re.M)
    if not found:
        sys.exit("No VERSION in client/relay.py.")
    version = found.group(1)

    files = {}
    for rel in git("ls-tree", "-r", "--name-only", ref, "--", "client", "skill").splitlines():
        if not RELEASE_FILE.match(rel):
            continue
        data = git("show", "%s:%s" % (ref, rel), binary=True)
        digest = hashlib.sha256(data).hexdigest()
        with urllib.request.urlopen(RAW + ref + "/" + rel, timeout=60) as res:
            if hashlib.sha256(res.read()).hexdigest() != digest:
                sys.exit("GitHub serves a different %s at %s." % (rel, ref[:12]))
        files[rel] = digest

    server, key = config()
    current = admin(server, key, "GET")
    print("now released: %s" % ("%s (%s)" % (current["version"], current["ref"][:12]) if current else "nothing"))
    print("to release:   %s (%s), %d files: %s" % (version, ref[:12], len(files), ", ".join(sorted(files))))
    if current and version_tuple(version) <= version_tuple(current["version"]) and not args.force:
        sys.exit("Version %s is not newer than %s. Raise VERSION in client/relay.py." % (version, current["version"]))
    if args.dry_run:
        print("dry run: nothing released.")
        return 0
    released = admin(server, key, "PUT", {"version": version, "ref": ref, "files": files})
    print("released %s. Installed computers update at their next daily sync." % released["version"])
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except urllib.error.HTTPError as e:
        sys.exit("server refused: %s %s" % (e.code, e.read()[:200].decode("utf-8", "replace")))
    except subprocess.CalledProcessError as e:
        sys.exit("git failed: %s" % (e.stderr or b"").decode().strip())
