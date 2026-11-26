# /// script
# requires-python = ">=3.11"
# ///
"""Self-check: `uv run test_agentctx.py`. Runs sync in a sandboxed HOME."""
import json, os, subprocess, sys, tempfile
from pathlib import Path

tmp = Path(tempfile.mkdtemp())
os.environ.update(HOME=str(tmp / "home"), CODEX_HOME=str(tmp / "home/.codex"),
                  AGENTCTX_HOME=str(tmp / "home/.agentctx"), AGENTCTX_PROFILE=str(tmp / "profile.toml"))
import agentctx as A  # noqa: E402  (after env so HOME is the sandbox)
A.HOME = tmp / "home"

repo = tmp / "repo"
def w(rel, text):
    p = repo / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)
w("layers/global/instructions/a.md", "---\ntitle: A\n---\nglobal rule")
w("layers/users/me/instructions/a.md", "---\ntitle: B\nagents: [claude]\n---\nuser rule")
w("layers/global/memories/m.md", "---\nname: m\ndescription: d\ntype: user\n---\nfact")
w("layers/global/skills/s/SKILL.md", "---\nname: s\ndescription: x\n---\nbody")
w("layers/teams/t/instructions/a.md", "---\ntitle: T\n---\nteam rule")
w("layers/teams/t/memories/tm.md", "---\nname: tm\ndescription: d\ntype: project\n---\nteam fact")
w("layers/teams/t/projects/p/project.toml", 'remote = "https://github.com/X/P.git"\n')
w("layers/teams/t/projects/p/instructions/a.md", "---\ntitle: P\n---\nproj rule")
w("layers/teams/t/projects/p/memories/pm.md", "---\nname: pm\ndescription: d\ntype: project\n---\nproj fact")

def git(cwd, *args):
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)
ws = tmp / "ws"                                   # scan root: two clones (https + ssh remote) + one worktree
proj, clone2 = ws / "proj", ws / "nested/proj-codex"
for d, url in ((proj, "https://github.com/x/p"), (clone2, "git@github.com:X/P.git")):
    d.mkdir(parents=True); git(d, "init", "-q"); git(d, "remote", "add", "origin", url)
    git(d, "-c", "user.name=t", "-c", "user.email=t@t", "commit", "-q", "--allow-empty", "-m", "i")
git(proj, "worktree", "add", "-q", str(ws / "proj-wt"))
(clone2 / "CLAUDE.md").write_text("# own notes\n")
other_repo = ws / "unrelated"; other_repo.mkdir(); git(other_repo, "init", "-q")
(tmp / "profile.toml").write_text(f'user="me"\nrepo="{repo.as_posix()}"\nteams=["t"]\nscan=["{ws.as_posix()}"]\n')

claude = A.HOME / ".claude/CLAUDE.md"
codex = A.HOME / ".codex/AGENTS.md"
claude.parent.mkdir(parents=True); claude.write_text("my own notes\n")

assert A.main(["sync"]) == 0
c, x = claude.read_text(), codex.read_text()
assert "my own notes" in c and c.index("global rule") < c.index("user rule"), "precedence/preserve"
assert "user rule" not in x, "agents: filter"
long = "từ " * 60
assert A.short("ngắn") == "ngắn" and len(A.short(long)) <= A.DESC_MAX + 1 and A.short(long).endswith("…"), "short cắt mô tả dài ở ranh giới từ"
assert "[m](global/m.md)" in c and (A.HOME / ".agentctx/rendered/memories/global/m.md").exists()
assert (A.HOME / ".claude/skills/s/.agentctx").exists() and (A.HOME / ".agents/skills/s/SKILL.md").exists()
assert "team rule" not in c and "[tm](" not in c, "team context stays out of user-level files"
for d in (proj, clone2):                                  # same project via either remote spelling
    ag = (d / "AGENTS.md").read_text()
    assert "team rule" in ag and ag.index("team rule") < ag.index("proj rule") and "global rule" not in ag
    assert "](.agentctx/memories/teams/t/projects/p/pm.md)" in ag, "relative link, resolves on any clone"
    assert (d / ".agentctx/memories/teams/t/tm.md").exists() and (d / ".agentctx/memories/teams/t/projects/p/pm.md").exists()
assert (proj / "CLAUDE.md").read_text() == "@AGENTS.md\n"
assert (clone2 / "CLAUDE.md").read_text() == "# own notes\n\n@AGENTS.md\n", "import appended, notes kept"
assert not (ws / "proj-wt/AGENTS.md").exists(), "worktrees skipped (get it via git)"
assert not (other_repo / "AGENTS.md").exists(), "unregistered repo untouched"

import io, contextlib
w("layers/global/instructions/b.md", "---\ntitle: B2\n---\nnew rule")      # repo changed, not synced yet
with contextlib.redirect_stdout(io.StringIO()) as buf:
    A.main(["status"])
assert f"stale   {claude}" in buf.getvalue()
(repo / "layers/global/instructions/b.md").unlink()

claude.write_text(c.replace("global rule", "hand edited"))           # drift
assert A.main(["sync"]) == 1 and "hand edited" in claude.read_text()
assert A.main(["sync", "--force"]) == 0 and "global rule" in claude.read_text()

(A.HOME / ".claude/skills/s/.agentctx").unlink()                  # identical unmarked copy -> adopted
assert A.main(["sync"]) == 0 and (A.HOME / ".claude/skills/s/.agentctx").exists()

other = A.HOME / ".claude/skills/own"; other.mkdir(); (other / "SKILL.md").write_text("mine")
(repo / "layers/global/skills/s/SKILL.md").unlink(); (repo / "layers/global/skills/s").rmdir()
A.main(["sync"])
assert not (A.HOME / ".claude/skills/s").exists() and other.exists(), "remove stale, keep unmarked"

w("layers/global/instructions/bad.md", "password: hunter2xyz")        # lint blocks sync
assert A.main(["sync"]) == 1

cj = {"mcpServers": {"x": {"command": "npx", "args": ["a"], "env": {"K": "secret"}},
                     "y": {"url": "https://h/mcp?api_key=SECRET", "headers": {"Authorization": "Bearer T"}}}}
(A.HOME / ".claude.json").write_text(json.dumps(cj))
import io, contextlib
buf = io.StringIO()
with contextlib.redirect_stdout(buf):
    A.main(["mcp", "list", "--json"])
assert "SECRET" not in buf.getvalue() and "Bearer" not in buf.getvalue() and "secret" not in buf.getvalue()

# --- propose / review / harvest / import-claudeai (Phase 2) ---
assert A.main(["propose", "--to", "teams/t", "--type", "feedback", "--reason", "r", "Dùng pnpm"]) == 0
inbox = list((repo / "inbox").glob("*.md"))
assert len(inbox) == 1 and "proposed_layer: teams/t" in inbox[0].read_text()

with contextlib.redirect_stdout(io.StringIO()) as buf:
    A.main(["review"])
assert inbox[0].stem in buf.getvalue()

slug = inbox[0].stem
assert A.main(["review", "approve", slug]) == 0
approved = repo / "layers/teams/t/memories" / f"{slug}.md"
assert approved.exists() and not inbox[0].exists() and "proposed_layer" not in approved.read_text()

assert A.slugify("Build docker trên host acmecorp qua SSH fail", set()) == "build-docker-tren-host-acmecorp-qua-ssh", "bỏ dấu, không '-' cuối"
assert A.slugify("Đường dẫn", set()) == "duong-dan"

w("layers/teams/t/memories/quoting.md", "---\nname: ssh-quoting\ndescription: lệnh ssh tới host acmecorp đi vào cmd\n"
  "type: reference\ncreated: 2020-01-01\n---\ncmd nuốt > nên pipe file qua stdin")
with contextlib.redirect_stdout(io.StringIO()) as buf:
    A.main(["propose", "--to", "teams/t", "--type", "reference", "--reason", "r",
            "Build docker trên host acmecorp qua ssh: tạo config qua stdin vì cmd nuốt >"])
assert "similar: ssh-quoting" in buf.getvalue(), "gợi ý memory liên quan"
A.main(["review", "reject", "build-docker-tren-host-acmecorp-qua-ssh"])

with contextlib.redirect_stdout(io.StringIO()) as buf:   # --name existing: update, layer + created kept
    assert A.main(["propose", "--name", "ssh-quoting", "--type", "reference", "--reason", "gộp", "cmd nuốt > và |"]) == 0
upd = (repo / "inbox/ssh-quoting.md").read_text()
assert buf.getvalue().startswith("update ssh-quoting (teams/t)") and "proposed_layer: teams/t" in upd and "created: 2020-01-01" in upd
assert A.main(["review", "approve", "ssh-quoting", "--to", "users/me"]) == 0
assert not (repo / "layers/teams/t/memories/quoting.md").exists(), "approve moves, never duplicates a name"
assert "cmd nuốt > và |" in (repo / "layers/users/me/memories/ssh-quoting.md").read_text()
try:
    A.main(["propose", "--type", "user", "--reason", "r", "no layer"]); raise AssertionError("--to required for new")
except SystemExit:
    pass

# --- remember: agent tự approve + commit + sync, user review qua git ---
bad = repo / "layers/global/instructions/bad.md"; bad.rename(tmp / "bad.md")  # lint lỗi chặn sync
git(repo, "init", "-q"); git(repo, "config", "user.name", "t"); git(repo, "config", "user.email", "t@t")
git(repo, "add", "-A"); git(repo, "commit", "-q", "-m", "base")
w("layers/global/instructions/wip.md", "---\ntitle: W\n---\nwip"); git(repo, "add", "layers/global/instructions/wip.md")
log = lambda: subprocess.run(["git", "-C", str(repo), "log", "--name-status", "-1", "--format=%s"],
                             capture_output=True, text=True).stdout
import contextlib, io  # noqa: E402
_o = io.StringIO()
with contextlib.redirect_stdout(_o):
    rc = A.main(["remember", "--to", "users/me", "--type", "feedback", "--reason", "r1", "Luôn chạy uv cho Python"])
assert rc == 0 and "sync ok" in _o.getvalue() and not any(l.startswith("ok") for l in _o.getvalue().splitlines()), "output của remember phải gọn"
assert log().startswith("memory: add luon-chay-uv-cho-python -> users/me") and "wip.md" not in log(), "commit chỉ file memory"
assert "luon-chay-uv-cho-python" in claude.read_text(), "đã sync ra ~/.claude"
assert A.main(["remember", "--to", "users/me", "--type", "feedback", "--reason", "r", "Luôn chạy uv cho Python nhé"]) == 2
assert not list((repo / "inbox").glob("luon-chay-uv*")), "gần trùng: dừng trước khi ghi gì"
assert A.main(["remember", "--name", "luon-chay-uv-cho-python", "--to", "teams/t", "--type", "feedback", "--reason", "gộp",
               "Luôn chạy uv cho Python, kể cả script"]) == 0
assert log().startswith("memory: update luon-chay-uv-cho-python -> teams/t") and "layers/users/me/memories/luon-chay-uv-cho-python.md" in log(), "move commit gồm cả file cũ"
assert not (repo / "layers/users/me/memories/luon-chay-uv-cho-python.md").exists()
lk = repo / ".remember.lock"; lk.touch()  # remember khác đang giữ khoá: chờ rồi exit 3, không ghi gì
A.LOCK_WAIT = 1
assert A.main(["remember", "--to", "global", "--type", "user", "--reason", "r", "fact bị khoá"]) == 3
assert not list((repo / "inbox").glob("fact-bi-khoa*")) and lk.exists(), "không ghi gì, không xoá khoá của người khác"
os.utime(lk, (1, 1))  # khoá mồ côi (quá LOCK_STALE) thì bị chiếm
assert A.main(["remember", "--to", "global", "--type", "user", "--reason", "r", "fact sau khoá mồ côi"]) == 0 and not lk.exists()
try:
    A.main(["remember", "--to", "global", "--type", "reference", "--reason", "r", "password: hunter2xyz"]); raise AssertionError
except SystemExit:
    pass
git(repo, "reset", "-q", "layers/global/instructions/wip.md"); (repo / "layers/global/instructions/wip.md").unlink()
(tmp / "bad.md").rename(bad)

w("layers/global/instructions/p.md", "---\ntitle: P\n---\nrun `uv run {{repo}}/agentctx.py`")
assert f"uv run {repo.as_posix()}/agentctx.py" in A.render_block(repo, ["global"], "claude", tmp), "{{repo}} rendered"
(repo / "layers/global/instructions/p.md").unlink()

native = A.HOME / ".claude/projects/-x/memory"
native.mkdir(parents=True)
(native / "feedback_demo.md").write_text(
    "---\nname: feedback-demo\ndescription: d\nmetadata:\n  type: feedback\n---\n\nbody text")
(native / "MEMORY.md").write_text("- index, not a memory")
assert A.main(["harvest"]) == 0
harvested = repo / "inbox/feedback-demo.md"
assert harvested.exists() and "type: feedback" in harvested.read_text()
assert A.main(["review", "reject", "feedback-demo"]) == 0 and not harvested.exists()
assert A.main(["harvest"]) == 0 and not harvested.exists(), "rejected stays rejected"

native = A.HOME / ".claude/projects/-ws-proj-wt"          # session ran inside a worktree of p
(native / "memory").mkdir(parents=True)
(native / "s.jsonl").write_text('{"type":"x"}\n' + json.dumps({"cwd": str(ws / "proj-wt")}) + "\n")
(native / "memory/gotcha.md").write_text("---\nname: gotcha\ndescription: d\ntype: project\n---\nbuild quirk")
assert A.main(["harvest"]) == 0
assert "proposed_layer: teams/t/projects/p" in (repo / "inbox/gotcha.md").read_text(), "harvest maps via git remote"

(repo / "layers/global/instructions/bad.md").unlink()
tracked = proj / ".claude/skills/kept"; tracked.mkdir(parents=True)  # committed skill w/ stray marker
(tracked / "SKILL.md").write_text("---\nname: kept\ndescription: d\n---\nx"); (tracked / ".agentctx").write_text("{}")
git(proj, "add", ".claude/skills/kept/SKILL.md")
assert A.main(["sync"]) == 0 and (tracked / "SKILL.md").exists() and not (tracked / ".agentctx").exists()

w("layers/global/skills/kept/SKILL.md", "---\nname: kept\ndescription: d\n---\nother")  # user symlinked it
(A.HOME / ".claude/skills/kept").symlink_to(tracked)
assert A.main(["sync"]) == 0 and not (tracked / ".agentctx").exists() and (tracked / "SKILL.md").read_text().endswith("x")
(repo / "layers/global/skills/kept/SKILL.md").unlink(); (repo / "layers/global/skills/kept").rmdir()

if sys.platform != "win32":  # decode_project_dir is POSIX-only (ponytail note in agentctx.py)
    spaced = tmp / "App Scripts/Smart Wallet"; spaced.mkdir(parents=True)  # no transcript: decode dir name
    (tmp / "App-Scripts").mkdir()                                           # decoy that encodes the same prefix
    enc = "-" + "-".join(__import__("re").sub(r"[^A-Za-z0-9]", "-", p) for p in spaced.resolve().parts[1:])
    assert A.decode_project_dir(enc) == spaced.resolve(), "decodes dir names containing spaces"

assert A.main(["project", "add", str(other_repo), "--owner", "users/me"]) == 0
assert (repo / "layers/users/me/projects/unrelated/project.toml").exists()
(other_repo / "AGENTS.md").write_text("hand written\n")
assert A.main(["sync"]) == 0 and (other_repo / "AGENTS.md").read_text() == "hand written\n", "no content -> no empty block"
w("layers/users/me/projects/unrelated/instructions/a.md", "---\ntitle: U\n---\nmine")
assert A.main(["sync"]) == 0 and "mine" in (other_repo / "AGENTS.md").read_text(), "no-remote repo matched by dir name"
assert A.main(["project", "add", str(clone2), "--owner", "teams/t"]) == 1, "dup rejected"
with contextlib.redirect_stdout(io.StringIO()) as buf:
    A.main(["project", "list"])
assert "teams/t/projects/p" in buf.getvalue() and "users/me/projects/unrelated" in buf.getvalue()

assert A.SECRET_RE.search("password: `SuperAdmin@123`") and not A.SECRET_RE.search("token: `EDGELINK_TOKEN`")
assert not A.SECRET_RE.search("password: <from .env>")

synced = A.HOME / ".claude/skills/synced/bucket1"
(synced / "mine/refs").mkdir(parents=True)
(synced / "mine/SKILL.md").write_text("---\nname: mine\ndescription: d\n---\nbody")
(synced / "mine-plugin/refs").mkdir(parents=True)
(synced / "mine-plugin/SKILL.md").write_text("---\nname: mine-plugin\ndescription: d\n---\nbody")
(synced / "vendor-plugin").mkdir(parents=True)
(synced / "vendor-plugin/SKILL.md").write_text("---\nname: vendor-plugin\ndescription: d\n---\nbody")
(synced / "manifest.json").write_text(json.dumps({"skills": [
    {"skillId": "x", "name": "mine", "source": "custom", "updatedAt": "now"},
    {"skillId": "y", "name": "mine-plugin", "source": "plugin", "backingPluginId": "plugin_private", "updatedAt": "now"},
    {"skillId": "z", "name": "vendor-plugin", "source": "plugin", "backingPluginId": "plugin_marketplace", "updatedAt": "now"}]}))
plugins_synced = A.HOME / ".claude/plugins/synced/bucket1"
plugins_synced.mkdir(parents=True)
(plugins_synced / "manifest.json").write_text(json.dumps({"plugins": [
    {"pluginId": "plugin_marketplace", "name": "vendor-plugin"}]}))
assert A.main(["import-claudeai", "--to", "users/me"]) == 0
assert (repo / "layers/users/me/skills/mine/SKILL.md").exists()
assert (repo / "layers/users/me/skills/mine-plugin/SKILL.md").exists(), "plugin-backed skill not in any marketplace is still 'created by you'"
assert not (repo / "layers/users/me/skills/vendor-plugin").exists(), "marketplace plugin skill stays out of the repo"
with contextlib.redirect_stdout(io.StringIO()) as buf:
    A.main(["status"])
assert "skill-drift" not in buf.getvalue()
(synced / "mine/SKILL.md").write_text("---\nname: mine\ndescription: d\n---\nchanged upstream")
with contextlib.redirect_stdout(io.StringIO()) as buf:
    A.main(["status"])
assert "skill-drift" in buf.getvalue()

(tmp / "profile.toml").write_text(f'user="me"\nrepo="{repo.as_posix()}"\nteams=["t"]\nscan=["{ws.as_posix()}"]\nwrite_user_level=false\n')
assert A.main(["sync"]) == 0
assert "global rule" not in claude.read_text() and "global rule" not in codex.read_text(), "write_user_level=false clears user-level files"
assert f"{A.BEGIN}\n{A.END}" in claude.read_text() and codex.read_text() == f"{A.BEGIN}\n{A.END}\n", "block cleared, hand-written content around it kept"
assert (proj / "AGENTS.md").read_text().count("team rule") == 1, "project files keep writing regardless of write_user_level"
with contextlib.redirect_stdout(io.StringIO()) as buf:
    A.main(["status"])
out = buf.getvalue()
assert "CHỈ ĐỌC" in out and f"ok      {claude}" in out, "status reports read-only mode, no false drift/stale"

vz = tmp / "viz.html"
assert A.main(["viz", "-o", str(vz)]) == 0
h = vz.read_text()
assert '"name": "pm"' in h and '"layer": "teams/t/projects/p"' in h and "/*DATA*/" not in h, "viz embeds memories with their layer"
pv = proj / ".agentctx/viz.html"
assert pv.exists() and '"name": "pm"' in pv.read_text() and '"name": "m"' not in pv.read_text(), "project viz = project layers only"
assert (proj / ".agentctx/.ignore").read_text() == "viz.html\n" and "viz.html" not in (proj / "AGENTS.md").read_text(), "agent never pointed at viz"

# shared source: extra read-only layers; main repo wins on same skill name, memories stay main-only
shared = tmp / "shared"
for rel, t in (("layers/global/skills/sh/SKILL.md", "---\nname: sh\ndescription: x\n---\nb"),
               ("layers/global/skills/s/SKILL.md", "---\nname: s\ndescription: x\n---\nshared copy"),
               ("layers/global/instructions/z.md", "---\ntitle: Z\n---\nshared rule")):
    p = shared / rel; p.parent.mkdir(parents=True, exist_ok=True); p.write_text(t)
(tmp / "profile.toml").write_text(f'user="me"\nrepo="{repo.as_posix()}"\nshared=["{shared.as_posix()}"]\nteams=["t"]\nscan=["{ws.as_posix()}"]\n')
w("layers/global/skills/s/SKILL.md", "---\nname: s\ndescription: x\n---\nmain copy")
prof = A.load_profile()
sk = dict(A.layer_skills(repo, "global", "claude"))
assert set(sk) == {"s", "sh"} and sk["s"].resolve() == (repo / "layers/global/skills/s").resolve(), "shared skill added, main repo wins on same name"
assert any(t == "Z" for t, _ in A.layer_instructions(repo, "global", "claude")), "shared instructions are read"
assert not A.layer_memories(shared, "global"), "shared repo has no memories"

# log mỗi lệnh gọi: ghi dòng JSON, không lộ nội dung text
A.main(["lint"])
logf = tmp / "home/.agentctx/log.jsonl"
row = json.loads(logf.read_text().splitlines()[-1])
assert row["args"]["cmd"] == "lint" and row["rc"] in (0, 1) and "ms" in row and "cwd" in row, "lint is logged"
try:
    A.main(["remember", "SECRET-FACT-XYZ", "--type", "user", "--reason", "r", "--to", "nowhere/x"])
except BaseException:
    pass
assert "SECRET-FACT-XYZ" not in logf.read_text(), "fact text never logged, only its length"

print("ok")
