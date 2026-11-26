#!/usr/bin/env -S uv run
# /// script
# requires-python = ">=3.11"
# ///
"""agentctx: sync instructions/skills/memories from layers into coding agents. Stdlib only."""
import contextlib, io, argparse, hashlib, json, math, os, re, shutil, subprocess, sys, time, tomllib, unicodedata
from datetime import date
from pathlib import Path

REPO = Path(__file__).resolve().parent
HOME = Path.home()
BEGIN = "<!-- agentctx:begin (generated — đừng sửa tay, sửa trong agent-context) -->"
END = "<!-- agentctx:end -->"
BLOCK_RE = re.compile(re.escape(BEGIN) + r".*?" + re.escape(END), re.S)
MARK = ".agentctx"
PROJ_MEM = Path(".agentctx/memories")  # committed copy of memories inside a project repo
SECRET_RE = re.compile(
    r"(password|passwd|token|secret|api[_-]?key)\s*[:=]\s*(?![\"'`]?([$<]|(?-i:[A-Z_]{3,})`))\S{4,}"  # $VAR, <placeholder>, `ENV_NAME` are references
    r"|-----BEGIN [A-Z ]*PRIVATE KEY"
    r"|\b(sk-[A-Za-z0-9]{20,}|ghp_[A-Za-z0-9]{30,}|AKIA[0-9A-Z]{16})\b", re.I)


def codex_home():
    return Path(os.environ.get("CODEX_HOME", HOME / ".codex"))


# ponytail: adapters are plain data; a new agent = a new entry. project_skills None = unsupported.
ADAPTERS = {
    "claude": dict(
        instr=lambda: HOME / ".claude/CLAUDE.md", skills=lambda: HOME / ".claude/skills",
        proj_instr="CLAUDE.md", proj_skills=".claude/skills", limit=None),
    "codex": dict(
        # Codex scans user skills in ~/.agents/skills; ~/.codex/skills is where older agentctx put them
        instr=lambda: codex_home() / "AGENTS.md", skills=lambda: HOME / ".agents/skills",
        legacy_skills=lambda: codex_home() / "skills",
        proj_instr="AGENTS.md", proj_skills=None, limit=32 * 1024),
}

# ---------- parsing ----------

def parse_md(path):
    """-> (meta dict, body). Minimal frontmatter: `key: value`, `key: [a, b]`."""
    text = Path(path).read_text(encoding="utf-8").replace("\r\n", "\n")
    meta, body = {}, text
    m = re.match(r"---\n(.*?)\n---\n?(.*)", text, re.S)
    if m:
        body = m.group(2)
        for line in m.group(1).splitlines():
            if ":" not in line or line.startswith((" ", "#")):
                continue
            k, v = line.split(":", 1)
            v = re.sub(r"\s+#.*$", "", v).strip()
            if v.startswith("[") and v.endswith("]"):
                v = [x.strip() for x in v[1:-1].split(",") if x.strip()]
            if isinstance(v, str) and len(v) > 1 and v[0] == v[-1] == '"':
                v = v[1:-1].replace('\\"', '"')  # YAML double-quoted scalar
            meta[k.strip()] = v.strip("\"'").replace('\\"', '"') if isinstance(v, str) else v
    return meta, body.strip()


def dump_md(meta, body):
    lines = ["---"]
    for k, v in meta.items():
        lines.append(f"{k}: [{', '.join(v)}]" if isinstance(v, list) else f"{k}: {v}")
    lines.append("---")
    return "\n".join(lines) + "\n\n" + body.strip() + "\n"


def fold(text):
    """Bỏ dấu tiếng Việt: 'Đường trên' -> 'duong tren' (NFKD không tách được đ)."""
    t = unicodedata.normalize("NFKD", text.lower().replace("đ", "d").replace("Đ", "d"))
    return "".join(c for c in t if not unicodedata.combining(c))


def slugify(text, existing):
    base = re.sub(r"[^a-z0-9]+", "-", fold(text))[:40].strip("-") or "memory"
    slug, i = base, 2
    while slug in existing:
        slug, i = f"{base}-{i}", i + 1
    return slug


def existing_slugs(repo):
    """Dedup key is the memory's `name:` field, not the filename — a memory can be
    approved under a filename that differs from its slug (git mv by hand, etc)."""
    files = list(repo.glob("inbox/*.md")) + list(repo.glob("layers/**/memories/*.md"))
    out = set()
    for f in files:
        meta, _ = parse_md(f)
        out.add(meta.get("name", f.stem))
    return out


def suggest_scope(meta, body, prof):
    """§5.2 heuristic: suggestion only, người duyệt quyết định cuối cùng."""
    text = f"{body} {meta.get('description', '')}".lower()
    personal_kw = ("~/", "mình thích", "tôi thích", "máy cá nhân", "account cá nhân")
    if meta.get("type") == "user" or any(k in text for k in personal_kw):
        return f"users/{meta.get('author', prof['user'])}"
    for pr in projects(prof["repo"]):
        if pr["name"].lower() in text:
            return pr["layer"]
    if "mọi team" in text or "mọi project" in text:
        return "global"
    return f"teams/{prof['teams'][0]}" if prof["teams"] else "global"


def sha(data):
    return hashlib.sha256(data if isinstance(data, bytes) else data.encode()).hexdigest()[:16]


def dir_hash(d):
    h = hashlib.sha256()
    for p in sorted(x for x in Path(d).rglob("*") if x.is_file() and x.name != MARK):
        h.update(str(p.relative_to(d)).replace("\\", "/").encode() + p.read_bytes())
    return h.hexdigest()[:16]

# ---------- profile / layers ----------

SHARED = []  # filled by load_profile; searched before the main repo so the main repo wins on same name


def layer_dirs(repo, layer, kind):
    return [r / "layers" / layer / kind for r in (*SHARED, repo)]

def load_profile():
    p = Path(os.environ.get("AGENTCTX_PROFILE", HOME / ".agentctx/profile.toml"))
    if not p.exists():
        sys.exit(f"thiếu profile: {p} (xem README)")
    prof = tomllib.loads(p.read_text(encoding="utf-8"))
    prof["repo"] = Path(os.path.expanduser(prof.get("repo", REPO))).resolve()
    # shared = read-only repos with extra layers (instructions/skills); prof["repo"] stays the only one written to.
    prof["shared"] = [Path(os.path.expanduser(p)).resolve() for p in prof.get("shared", [])]
    SHARED[:] = [p for p in prof["shared"] if p != prof["repo"]]
    prof.setdefault("agents", list(ADAPTERS))
    prof.setdefault("teams", [])
    prof.setdefault("scan", [])
    prof.setdefault("user", os.environ.get("USER", "me"))
    prof.setdefault("write_user_level", True)  # false = chỉ đọc, không ghi vào ~/.claude, ~/.codex
    # User-level files get only global + me; team instructions/memories go into the team's repos.
    prof["layers"] = ["global", f"users/{prof['user']}"]
    # Skills load on demand (only the description sits in context), and Codex has no project
    # skills dir, so the teams' skills stay user-level.
    prof["skill_layers"] = ["global", *(f"teams/{t}" for t in prof["teams"]), f"users/{prof['user']}"]
    return prof

# ---------- projects: identity = git remote, owner = folder it sits under ----------

def git(path, *args):
    r = subprocess.run(["git", "-C", str(path), *args], capture_output=True, text=True)
    return r.stdout.strip() if r.returncode == 0 else ""


def norm_remote(url):
    """git@github.com:A/b.git, https://github.com/A/b/ -> github.com/a/b"""
    u = re.sub(r"^[a-z+]+://", "", url.strip().lower())
    u = re.sub(r"^[^@/]*@", "", u).replace(":", "/", 1)
    return u.rstrip("/").removesuffix(".git")


def project_id(path):
    """-> (remote, repo dir name), identical for every clone/worktree of a repo; None if not a repo.
    ponytail: remote = origin only; no remote -> match by the main checkout's dir name."""
    common = git(path, "rev-parse", "--path-format=absolute", "--git-common-dir")
    if not common:
        return None
    remote = git(path, "remote", "get-url", "origin")
    return norm_remote(remote) if remote else "", Path(common).parent.name


def projects(repo):
    """Registry: layers/{teams,users}/<owner>/projects/<name>/project.toml (`remote = "..."`)."""
    out = []
    for f in sorted(repo.glob("layers/*/*/projects/*/project.toml")):
        meta = tomllib.loads(f.read_text(encoding="utf-8"))
        layer = f.parent.relative_to(repo / "layers").as_posix()
        out.append(dict(layer=layer, owner=layer.split("/projects/")[0], name=f.parent.name,
                        remote=norm_remote(meta["remote"]) if meta.get("remote") else ""))
    return out


def match_project(projs, pid):
    if pid:
        for p in projs:
            if (p["remote"] and p["remote"] == pid[0]) or (not p["remote"] and p["name"] == pid[1]):
                return p


def scan_repos(prof):
    """Git checkouts in cwd + `scan` roots (2 levels deep). Worktrees are skipped unless they're
    the cwd: they get the committed files through git anyway."""
    cwd = Path.cwd()
    cands = [cwd]
    for root in prof["scan"]:
        r = Path(os.path.expanduser(root))
        cands += [g.parent for pat in (".git", "*/.git", "*/*/.git") for g in r.glob(pat)]
    seen = set()
    for c in cands:
        top = git(c, "rev-parse", "--show-toplevel")
        if top and top not in seen and (c == cwd or (Path(top) / ".git").is_dir()):
            seen.add(top)
            yield Path(top)


def checkouts(prof):
    projs = projects(prof["repo"])
    if not projs:
        return []
    return [(p, top) for top in scan_repos(prof) if (p := match_project(projs, project_id(top)))]


def state_path():
    return Path(os.environ.get("AGENTCTX_HOME", HOME / ".agentctx")) / "state.json"


def load_state():
    p = state_path()
    return json.loads(p.read_text()) if p.exists() else {}


def save_state(s):
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(s, indent=1))


def for_agent(meta, agent):
    a = meta.get("agents")
    return not a or agent in a


def layer_instructions(repo, layer, agent):
    items = []
    for f in (f for d in layer_dirs(repo, layer, "instructions") for f in d.glob("*.md")):
        meta, body = parse_md(f)
        if for_agent(meta, agent):
            items.append((int(meta.get("order", 50)), f.name, meta.get("title", f.stem), body))
    return [(t, b) for _, _, t, b in sorted(items)]


def layer_memories(repo, layer):
    out = []
    for f in sorted((repo / "layers" / layer / "memories").glob("*.md")):
        meta, _ = parse_md(f)
        out.append((meta.get("name", f.stem), meta.get("description", ""), f))
    return out


def layer_skills(repo, layer, agent):
    out = {}  # name -> dir; later dir (main repo) overrides shared
    for base in layer_dirs(repo, layer, "skills"):
        for d in sorted(base.glob("*/SKILL.md")):
            meta, _ = parse_md(d)
            if for_agent(meta, agent):
                out[d.parent.name] = d.parent
    return sorted(out.items())

# ---------- rendering ----------

DESC_MAX = 80  # mô tả trong index Shared memories chỉ để nhận diện; chi tiết nằm trong file


def short(desc):
    if len(desc) <= DESC_MAX:
        return desc
    return desc[:DESC_MAX].rsplit(" ", 1)[0].rstrip(",;:—-") + "…"


def render_block(repo, layers, agent, rendered_dir):
    parts, index = [], []
    for layer in layers:
        for title, body in layer_instructions(repo, layer, agent):
            parts.append(f"## {title}\n\n{body.replace('{{repo}}', repo.as_posix()).replace('{{tool}}', REPO.as_posix())}")
        for name, desc, f in layer_memories(repo, layer):
            index.append(f"- [{name}]({(rendered_dir / layer / f.name).as_posix()}) — {short(desc)}")
    if index:
        head = ""
        if rendered_dir.is_absolute():  # ghi base một lần, link còn lại tương đối (đỡ token)
            base = rendered_dir.as_posix() + "/"
            index = [i.replace(f"]({base}", "](") for i in index]
            head = f"Đường dẫn dưới đây tương đối so với `{base}`.\n\n"
        parts.append("## Shared memories\n\n" + head + "\n".join(index))
    return f"{BEGIN}\n" + "\n\n".join(parts) + f"\n{END}"


def user_block(repo, layers, agent, rendered, prof):
    """render_block cho file user-level, nhưng rỗng khi write_user_level=false (§write_user_level)."""
    return render_block(repo, layers, agent, rendered) if prof["write_user_level"] else f"{BEGIN}\n{END}"


def copy_memories(repo, layers, rendered_dir, dry):
    if dry:
        return
    for layer in layers:
        dst = rendered_dir / layer
        shutil.rmtree(dst, ignore_errors=True)
        for _, _, f in layer_memories(repo, layer):
            dst.mkdir(parents=True, exist_ok=True)
            shutil.copy2(f, dst / f.name)


def write_block(path, block, state, force, dry, log):
    """Replace managed block in path. Refuses if the block was edited by hand since last sync."""
    key = str(path)
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    m = BLOCK_RE.search(text)
    if m and key in state and sha(m.group(0)) != state[key] and not force:
        log(f"DRIFT  {path} (block bị sửa tay; chuyển thay đổi vào agent-context rồi --force)")
        return False
    new = text[:m.start()] + block + text[m.end():] if m else (text.rstrip("\n") + "\n\n" if text else "") + block + "\n"
    if new == text:
        log(f"ok     {path}")
    else:
        log(f"write  {path}")
        if not dry:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(new, encoding="utf-8", newline="\n")
    state[key] = sha(block)
    return True


def sync_skills(skills, dest, label, dry, log):
    """Copy skills into dest, tagging each with a marker; remove stale tagged ones; never touch unmarked."""
    want = {}
    for name, src, layer in skills:
        want[name] = (src, layer)  # later layer wins
    for name, (src, layer) in want.items():
        d = dest / name
        h = dir_hash(src)
        if d.is_symlink():  # user linked it to some other source on purpose
            log(f"skip   {d} (symlink)")
            continue
        if d.exists() and not (d / MARK).exists():
            if dir_hash(d) == h:  # identical hand-installed copy: adopt it
                log(f"adopt  {d}")
                if not dry:
                    (d / MARK).write_text(json.dumps({"layer": layer, "hash": h}))
            else:
                log(f"skip   {d} (không do agentctx quản lý)")
            continue
        if (d / MARK).exists() and json.loads((d / MARK).read_text()).get("hash") == h:
            continue
        log(f"skill  {d}")
        if not dry:
            shutil.rmtree(d, ignore_errors=True)
            shutil.copytree(src, d)
            (d / MARK).write_text(json.dumps({"layer": layer, "hash": h}))
    if dest.exists():
        for d in dest.iterdir():
            if not d.is_symlink() and (d / MARK).exists() and d.name not in want:
                if git(d, "ls-files", "."):  # committed in some repo: that copy is the source, never delete
                    log(f"unmanage {d} (git track, chỉ gỡ marker)")
                    if not dry:
                        (d / MARK).unlink()
                    continue
                log(f"remove {d}")
                if not dry:
                    shutil.rmtree(d)


def project_layers(pr):
    return ([pr["owner"]] if pr["owner"].startswith("teams/") else []) + [pr["layer"]]


def has_content(repo, layers):
    """Anything sync would write into the project repo (team skills stay user-level, so only the last)."""
    return bool(layer_skills(repo, layers[-1], "claude")) or any(
        layer_instructions(repo, l, "codex") or layer_memories(repo, l) for l in layers)


def has_block(path):
    return path.exists() and BEGIN in path.read_text(encoding="utf-8")


def cmd_sync(a):
    prof, state = load_profile(), load_state()
    repo = prof["repo"]
    errs = [i for i in lint_issues(repo) if i.startswith("ERROR")]
    if errs:
        print("\n".join(errs) + "\nsync dừng vì lint lỗi", file=sys.stderr)
        return 1
    log = print if not a.dry_run else lambda m: print("[dry] " + m)
    rendered = Path(os.environ.get("AGENTCTX_HOME", HOME / ".agentctx")) / "rendered/memories"
    layers = prof["layers"]
    copy_memories(repo, layers, rendered, a.dry_run)
    rc = 0
    for agent in prof["agents"]:
        if a.agent and agent != a.agent:
            continue
        ad = ADAPTERS[agent]
        block = user_block(repo, layers, agent, rendered, prof)
        if ad["limit"] and len(block.encode()) > ad["limit"]:
            log(f"ERROR  {agent}: block {len(block.encode())}B vượt giới hạn {ad['limit']}B")
            rc = 1
            continue
        rc |= not write_block(ad["instr"](), block, state, a.force, a.dry_run, log)
        skills = [(n, p, l) for l in prof["skill_layers"] for n, p in layer_skills(repo, l, agent)]
        sync_skills(skills, ad["skills"](), agent, a.dry_run, log)
        if "legacy_skills" in ad:  # migrate: drop our tagged copies from the old location (unmarked ones stay)
            sync_skills([], ad["legacy_skills"](), agent, a.dry_run, log)
    # Project scope: owning team + project go into the (committed) project files, memories
    # copied into the repo and linked relatively so they resolve on any clone/machine.
    for pr, root in checkouts(prof):
        players = project_layers(pr)
        if not has_content(repo, players) and not has_block(root / "AGENTS.md"):
            log(f"empty  {root} (chưa có nội dung cho {pr['layer']})")
            continue
        if not a.dry_run:
            shutil.rmtree(root / PROJ_MEM, ignore_errors=True)
        copy_memories(repo, players, root / PROJ_MEM, a.dry_run)
        write_viz(root, repo, players, a.dry_run)
        block = render_block(repo, players, "codex", PROJ_MEM)  # agent-neutral content
        rc |= not write_block(root / "AGENTS.md", block, state, a.force, a.dry_run, log)
        cl = root / "CLAUDE.md"
        text = cl.read_text(encoding="utf-8") if cl.exists() else ""
        if "@AGENTS.md" not in text:
            log(f"write  {cl} (+@AGENTS.md)")
            if not a.dry_run:
                cl.write_text((text.rstrip("\n") + "\n\n" if text.strip() else "") + "@AGENTS.md\n",
                              encoding="utf-8", newline="\n")
        for agent, ad in ADAPTERS.items():
            if ad["proj_skills"] and agent in prof["agents"]:
                sk = [(n, p, pr["layer"]) for n, p in layer_skills(repo, pr["layer"], agent)]
                sync_skills(sk, root / ad["proj_skills"], agent, a.dry_run, log)
    if not a.dry_run:
        save_state(state)
    return rc

# ---------- lint ----------

def lint_issues(repo):
    out, seen = [], {}
    files = [f for f in repo.rglob("*.md") if ".git" not in f.parts and f.name not in ("PLAN.md", "README.md")]
    for f in files:
        rel = f.relative_to(repo)
        text = f.read_text(encoding="utf-8", errors="replace")
        if any(SECRET_RE.search(l) for l in text.splitlines() if "$(" not in l):  # ponytail: lines with $(...) are shell lookups, not literals
            out.append(f"ERROR  {rel}: nghi có secret")
        parts = rel.parts
        if parts[0] == "inbox" or "memories" in parts:
            meta, _ = parse_md(f)
            for k in ("name", "description", "type"):
                if not meta.get(k):
                    out.append(f"ERROR  {rel}: thiếu '{k}'")
            if parts[0] == "inbox" and not (meta.get("proposed_layer") and meta.get("scope_reason")):
                out.append(f"ERROR  {rel}: inbox thiếu proposed_layer/scope_reason")
            if parts[0] != "inbox":
                seen.setdefault(meta.get("name"), []).append(str(rel))
                if meta.get("review_by", "9999") < date.today().isoformat():
                    out.append(f"WARN   {rel}: quá review_by {meta['review_by']}")
        elif f.name == "SKILL.md":
            meta, _ = parse_md(f)
            for k in ("name", "description"):
                if not meta.get(k):
                    out.append(f"ERROR  {rel}: thiếu '{k}'")
    for name, paths in seen.items():
        if len(paths) > 1:
            out.append(f"WARN   memory trùng '{name}': {', '.join(paths)}")
    return out


def size_issues(repo):
    """Block-size check needs a profile (which layers/agents apply); skip quietly if none."""
    try:
        prof = load_profile()
    except SystemExit:
        return []
    layers = prof["layers"]
    out = []
    for agent in prof["agents"]:
        ad = ADAPTERS[agent]
        if not ad["limit"]:
            continue
        block = render_block(repo, layers, agent, Path("rendered/memories"))
        size = len(block.encode())
        if size > ad["limit"]:
            out.append(f"ERROR  {agent}: block {size}B vượt giới hạn {ad['limit']}B")
    return out


def cmd_lint(a):
    prof = load_profile()
    issues = [i for r in dict.fromkeys([prof["repo"], *SHARED]) for i in lint_issues(r)] + size_issues(prof["repo"])
    print("\n".join(issues) or "lint ok")
    return any(i.startswith("ERROR") for i in issues)

# ---------- status ----------

def cmd_status(a):
    prof, state = load_profile(), load_state()
    repo = prof["repo"]
    mode = "ghi" if prof["write_user_level"] else "CHỈ ĐỌC (write_user_level=false)"
    print(f"user-level: {' + '.join(prof['layers'])}  (skills: {' + '.join(prof['skill_layers'])})  [{mode}]")
    rendered = Path(os.environ.get("AGENTCTX_HOME", HOME / ".agentctx")) / "rendered/memories"
    files = [(ADAPTERS[g]["instr"](), user_block(repo, prof["layers"], g, rendered, prof)) for g in prof["agents"]]
    files += [(root / "AGENTS.md", render_block(repo, project_layers(pr), "codex", PROJ_MEM))
              for pr, root in checkouts(prof)
              if has_content(repo, project_layers(pr)) or has_block(root / "AGENTS.md")]
    for path, want in files:
        m = BLOCK_RE.search(path.read_text(encoding="utf-8")) if path.exists() else None
        if not m:
            print(f"missing {path}")
        elif str(path) in state and sha(m.group(0)) != state[str(path)]:
            print(f"DRIFT   {path} (sửa tay)")
        elif m.group(0) != want:
            print(f"stale   {path} (repo đã đổi, cần sync)")
        else:
            print(f"ok      {path}")
    inbox = list((repo / "inbox").glob("*.md"))
    print(f"inbox: {len(inbox)} memory chờ duyệt")
    for s, src in claudeai_custom_skills():
        matches = list(repo.glob(f"layers/**/skills/{s['name']}"))
        for m in matches:
            if dir_hash(m) != dir_hash(src):
                print(f"skill-drift {m} khác bản trên claude.ai (sửa trong repo? upload lại tay)")
    return 0

# ---------- memory: propose / harvest / review ----------

def find_memory(repo, name):
    """Approved memory có `name:` này -> (path, layer), hoặc (None, None)."""
    for f in (repo / "layers").glob("**/memories/*.md"):
        if parse_md(f)[0].get("name", f.stem) == name:
            return f, f.parent.parent.relative_to(repo / "layers").as_posix()
    return None, None


def words(text):
    return set(re.findall(r"[a-z0-9]{3,}", fold(text)))


def similar(repo, text, skip=None, n=3, floor=0.1):
    """Memory gần giống nhất -> [(score, name, where)]. Jaccard có trọng số IDF trên từ đã bỏ dấu,
    để từ phổ biến (the, dùng, project...) không kéo điểm các cặp không liên quan lên."""
    # ponytail: quét O(n) mọi memory mỗi lần propose, đổi sang index khi layers lên hàng nghìn file
    docs = []
    for f in list(repo.glob("inbox/*.md")) + list(repo.glob("layers/**/memories/*.md")):
        meta, body = parse_md(f)
        where = "inbox" if f.parent.name == "inbox" else f.parent.parent.relative_to(repo / "layers").as_posix()
        docs.append((meta.get("name", f.stem), where, words(f"{meta.get('description', '')} {body}")))
    df = {}
    for _, _, ws in docs:
        for x in ws:
            df[x] = df.get(x, 0) + 1
    idf = lambda x: math.log((len(docs) + 1) / (df.get(x, 0) + 1)) + 0.1
    mine, out = words(text), []
    for name, where, theirs in docs:
        if name != skip and mine and theirs:
            score = sum(map(idf, mine & theirs)) / sum(map(idf, mine | theirs))
            if score >= floor:
                out.append((round(score, 2), name, where))
    return sorted(out, reverse=True)[:n]


def cmd_propose(a):
    propose(a, load_profile())
    return 0


def propose(a, prof):
    repo = prof["repo"]
    old, old_layer = find_memory(repo, a.name) if a.name else (None, None)
    layer = a.to or old_layer
    if not layer:
        sys.exit("thiếu --to (chỉ được bỏ khi --name trỏ tới memory đã có)")
    slug = a.name or slugify(a.text, existing_slugs(repo))
    created = parse_md(old)[0].get("created") if old else None
    meta = dict(name=slug, description=a.text.splitlines()[0][:120], type=a.type, author=prof["user"],
                created=created or date.today().isoformat(), updated=date.today().isoformat(),
                proposed_layer=layer, scope_reason=a.reason)
    dst = repo / "inbox" / f"{slug}.md"
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(dump_md(meta, a.text), encoding="utf-8", newline="\n")
    print(f"update {slug} ({old_layer}) -> {dst}" if old else f"propose {dst}")
    for score, name, where in similar(repo, a.text, skip=slug):
        print(f"similar: {name} ({score}, {where})")
    return slug, layer


MERGE_SCORE = 0.3  # từ dữ liệu thật: cặp cùng fact 0.33–0.41, cặp liên quan/nhiễu ≤ 0.17


LOCK_WAIT, LOCK_STALE = 15, 300  # giây: chờ khoá tối đa / khoá cũ hơn thì coi là của tiến trình đã chết


def cmd_remember(a):
    """Một remember tại một thời điểm (propose+approve+git+sync đụng chung inbox/, index git, ~/.claude).
    Ai chiếm khoá (O_EXCL, chạy được cả Windows) thì làm; kẻ đến sau chờ ≤ LOCK_WAIT rồi exit 3."""
    repo = load_profile()["repo"]
    lock = repo / ".remember.lock"
    end = time.monotonic() + LOCK_WAIT
    while True:
        try:
            os.close(os.open(lock, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            break
        except FileExistsError:
            try:
                if time.time() - lock.stat().st_mtime > LOCK_STALE:
                    lock.unlink(missing_ok=True)
                    continue
            except FileNotFoundError:
                continue
            if time.monotonic() > end:
                print(f"BUSY   remember khác đang chạy ({lock}) quá {LOCK_WAIT}s; chưa ghi gì. "
                      "Đợi vài giây chạy lại đúng lệnh này một lần; vẫn BUSY thì đừng lặp: làm việc khác rồi báo người dùng, "
                      "hoặc nhờ họ tự chạy.", file=sys.stderr)
                return 3
            time.sleep(0.5)
    try:
        return _remember(a)
    finally:
        lock.unlink(missing_ok=True)


def _remember(a):
    prof = load_profile()
    repo = prof["repo"]
    if SECRET_RE.search(a.text):
        sys.exit("text trông như chứa secret, thay bằng tham chiếu (uvx keyring get ..., tên biến .env)")
    dup = [s for s in similar(repo, a.text) if s[0] >= MERGE_SCORE]
    if dup and not a.name and not a.new:
        for score, name, where in dup:
            print(f"similar: {name} ({score}, {where})")
        print(f"gần trùng memory đã có: viết lại bản gộp rồi chạy lại với --name {dup[0][1]}, "
              "hoặc --new nếu thật sự là fact khác (liên quan nhưng khác: giữ riêng, thêm [[<slug>]] vào fact)", file=sys.stderr)
        return 2
    slug, layer = propose(a, prof)
    paths = approve(repo, slug, layer)
    if git(repo, "rev-parse", "--git-dir"):
        rel = [p.relative_to(repo).as_posix() for p in paths
               if p.exists() or git(repo, "ls-files", p.relative_to(repo).as_posix())]
        verb = "update" if len(paths) > 1 or git(repo, "ls-files", rel[0]) else "add"
        subprocess.run(["git", "-C", str(repo), "add", "-A", "--", *rel], check=True)
        # `commit -- paths` = --only: chỉ commit file memory này, không cuốn theo thứ người dùng đang stage
        subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", f"memory: {verb} {slug} -> {layer}\n\n{a.reason}",
                        "--", *rel], check=True)
        print(f"commit memory: {verb} {slug}")
    else:
        print(f"WARN   {repo} không phải git repo, không commit được", file=sys.stderr)
    # agent chỉ cần biết sync có lỗi không: bỏ các dòng "ok" (mỗi project một dòng, tốn token)
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = cmd_sync(argparse.Namespace(dry_run=False, agent=None, force=False))
    lines = buf.getvalue().splitlines()
    print("\n".join(l for l in lines if not l.startswith("ok")))
    print(f"sync ok: {sum(l.startswith('ok') for l in lines)} file không đổi" if rc == 0 else
          "sync LỖI: memory đã commit và sẽ ship ở lần sync sau; báo người dùng nội dung lỗi ở trên")
    return rc


def cmd_project(a):
    prof = load_profile()
    if a.sub == "list":
        projs = projects(prof["repo"])
        for top in scan_repos(prof):
            pid = project_id(top)
            p = match_project(projs, pid)
            cl = top / "CLAUDE.md"
            files = ("C@" if "@AGENTS.md" in cl.read_text(encoding="utf-8") else "C ") if cl.exists() else "- "
            files += "A" if (top / "AGENTS.md").exists() else "-"
            if p or not a.registered:
                print(f"{p['layer'] if p else '-':45} {files}  {top}  {pid[0] or '(no remote)'}")
        return 0
    if not re.fullmatch(r"(teams|users)/[^/]+", a.owner):
        sys.exit("--owner phải là teams/<team> hoặc users/<user>")
    rc = 0
    for path in a.paths:
        pid = project_id(Path(path).expanduser())
        hit = pid and match_project(projects(prof["repo"]), pid)
        if not pid or hit:
            print(f"skip    {path}: " + (f"đã đăng ký layers/{hit['layer']}" if hit else "không phải git repo"))
            rc = 1
            continue
        d = prof["repo"] / "layers" / a.owner / "projects" / pid[1]
        d.mkdir(parents=True, exist_ok=True)
        (d / "project.toml").write_text(
            f'remote = "{pid[0]}"\n' if pid[0] else "# không có remote: nhận diện bằng tên thư mục repo\n",
            encoding="utf-8", newline="\n")
        print(f"project {d.relative_to(prof['repo']).as_posix()}")
    return rc


def decode_project_dir(enc, base=Path("/")):
    """Claude names ~/.claude/projects/<enc> by replacing every non-alphanumeric char of the cwd with
    '-', so `App Scripts` and `App-Scripts` collide. Walk the filesystem for a dir that encodes to enc.
    ponytail: POSIX paths only; Windows drive prefixes fall back to None."""
    if not enc:
        return base
    try:
        children = sorted(c for c in base.iterdir() if c.is_dir())
    except OSError:
        return None
    for c in children:
        e = "-" + re.sub(r"[^A-Za-z0-9]", "-", c.name)
        if enc == e or enc.startswith(e + "-"):
            hit = decode_project_dir(enc[len(e):], c)
            if hit:
                return hit


def native_cwd(proj_dir, cache={}):
    """Claude's encoded project dir -> the real cwd, read from a session transcript
    (or decoded from the dir name when no transcript is left)."""
    if proj_dir not in cache:
        cache[proj_dir] = None
        for j in proj_dir.glob("*.jsonl"):
            with j.open(encoding="utf-8", errors="replace") as fh:
                m = next((m for line in fh if (m := re.search(r'"cwd":\s*("(?:[^"\\]|\\.)*")', line))), None)
            if m:
                cache[proj_dir] = Path(json.loads(m.group(1)))
                break
        else:
            cache[proj_dir] = decode_project_dir(proj_dir.name)
    return cache[proj_dir]


def native_memories():
    for f in (HOME / ".claude/projects").glob("*/memory/*.md"):
        if f.name != "MEMORY.md":
            yield f


def project_tag(src):
    """Encoded Claude-project dirname -> short disambiguator, e.g.
    -Users-me-Desktop-acme-app -> acme-app."""
    enc = src.parent.parent.name
    return re.sub(r"^-Users-[^-]+-(Desktop-|Downloads-)?", "", enc).lower()


def cmd_harvest(a):
    prof = load_profile()
    repo = prof["repo"]
    known = existing_slugs(repo) | rejected(repo)
    batch_slugs, n, projs = set(), 0, projects(repo)
    for src in native_memories():
        meta, body = parse_md(src)
        name = meta.get("name", src.stem)
        if name in known or f"{name}--{project_tag(src)}" in known:
            continue  # already proposed/approved/rejected under this canonical name
        slug = name
        if slug in batch_slugs:  # two different projects independently used the same name
            slug = f"{name}--{project_tag(src)}"
            if slug in batch_slugs:
                slug = slugify(slug, batch_slugs)
        batch_slugs.add(slug)
        mtype = re.search(r"\n\s*type:\s*(\S+)", src.read_text(encoding="utf-8"))
        mtype = (mtype.group(1) if mtype else "project").rstrip(",")
        new = dict(name=slug, description=meta.get("description", ""), type=mtype, author=prof["user"],
                   created=date.today().isoformat(), updated=date.today().isoformat())
        cwd = native_cwd(src.parent.parent)
        pr = mtype != "user" and cwd and cwd.exists() and match_project(projs, project_id(cwd))
        new["proposed_layer"] = pr["layer"] if pr else suggest_scope(new, body, prof)
        new["scope_reason"] = (f"harvest từ session trong {cwd} (project đã đăng ký)" if pr else
                               "harvest từ native memory của Claude, người duyệt xác nhận lại scope")
        dst = repo / "inbox" / f"{slug}.md"
        dst.parent.mkdir(parents=True, exist_ok=True)
        dst.write_text(dump_md(new, body), encoding="utf-8", newline="\n")
        print(f"harvest {src} -> inbox/{slug}.md")
        n += 1
    print(f"{n} memory mới trong inbox")
    return 0


def rejected(repo):
    """inbox/.rejected: one slug per line, so harvest doesn't bring rejected memories back."""
    p = repo / "inbox/.rejected"
    return set(p.read_text(encoding="utf-8").split()) if p.exists() else set()


def approve(repo, s, layer):
    """inbox/<s>.md -> layers/<layer>/memories/. -> các path đã đổi (để commit)."""
    src = repo / "inbox" / f"{s}.md"
    meta, body = parse_md(src)
    meta.pop("proposed_layer", None); meta.pop("scope_reason", None)
    meta["updated"] = date.today().isoformat()
    dst = repo / "layers" / layer / "memories" / f"{s}.md"
    old, _ = find_memory(repo, s)
    if old and old != dst:  # same name = same memory: moved layer or renamed file, don't keep two
        old.unlink()
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(dump_md(meta, body), encoding="utf-8", newline="\n")
    src.unlink()
    print(f"approve {s} -> layers/{layer}")
    return [dst] + ([old] if old and old != dst else [])


def cmd_review(a):
    prof = load_profile()
    repo = prof["repo"]
    if a.action in ("approve", "reject"):
        slugs = [f.stem for f in sorted(repo.glob("inbox/*.md"))] if a.all else a.slugs
        if not slugs:
            sys.exit("thiếu slug (hoặc --all)")
        missing = [s for s in slugs if not (repo / "inbox" / f"{s}.md").exists()]
        if missing:
            sys.exit(f"không thấy trong inbox: {', '.join(missing)}")
        if a.action == "reject":
            with open(repo / "inbox/.rejected", "a", encoding="utf-8", newline="\n") as fh:
                fh.writelines(f"{s}\n" for s in slugs)
            for s in slugs:
                (repo / "inbox" / f"{s}.md").unlink()
                print(f"reject {s}")
            return 0
        for s in slugs:
            layer = a.to or parse_md(repo / "inbox" / f"{s}.md")[0].get("proposed_layer")
            if not layer:
                sys.exit(f"{s}: thiếu layer đích (--to hoặc proposed_layer)")
            approve(repo, s, layer)
        return 0
    for f in sorted(repo.glob("inbox/*.md")):
        meta, body = parse_md(f)
        suggested = suggest_scope(meta, body, prof)
        flag = " ⚠ scope?" if meta.get("proposed_layer") != suggested else ""
        print(f"{meta.get('name', f.stem):30} proposed={meta.get('proposed_layer', '?'):20} suggested={suggested}{flag}")
        print(f"  {meta.get('scope_reason', '')}")
    return 0

# ---------- claude.ai skills ----------

def claudeai_manifest_entries():
    for mf in (HOME / ".claude/skills/synced").glob("*/manifest.json"):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        for s in data.get("skills", []):
            yield s, mf.parent / s["name"]


def installed_plugin_ids():
    ids = set()
    for mf in (HOME / ".claude/plugins/synced").glob("*/manifest.json"):
        try:
            data = json.loads(mf.read_text(encoding="utf-8"))
        except Exception:
            continue
        ids.update(p["pluginId"] for p in data.get("plugins", []))
    return ids


def claudeai_custom_skills():
    """source=custom, or source=plugin backed by a private plugin (not in installed_plugins.json
    i.e. not from any marketplace) — claude.ai buckets some self-made skills as 'plugin' too."""
    known = installed_plugin_ids()
    for s, src in claudeai_manifest_entries():
        is_custom = s.get("source") == "custom"
        is_private_plugin = s.get("source") == "plugin" and s.get("backingPluginId") not in known
        if (is_custom or is_private_plugin) and (src / "SKILL.md").exists():
            yield s, src


def cmd_import_claudeai(a):
    prof = load_profile()
    dest_root = prof["repo"] / "layers" / (a.to or f"users/{prof['user']}") / "skills"
    n = 0
    for s, src in claudeai_custom_skills():
        dst = dest_root / s["name"]
        print(f"import {s['name']} -> {dst}")
        shutil.rmtree(dst, ignore_errors=True)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(src, dst)
        n += 1
    print(f"{n} skill đã import, nhớ commit (sửa trong repo thì phải upload lại tay lên claude.ai).")
    return 0

# ---------- mcp list ----------

def mask_url(u):
    return re.sub(r"([?&][^=&]*(?:key|token|secret|auth)[^=&]*=)[^&]*", r"\1***", re.sub(r"//[^/@]*@", "//***@", u), flags=re.I)


def mcp_rows(servers, agent, scope, src):
    for name, c in (servers or {}).items():
        cmd = c.get("url") and mask_url(c["url"]) or " ".join([c.get("command", ""), *map(str, c.get("args", []))]).strip()
        extra = [f"{k}[{','.join(c[k])}]=***" for k in ("env", "headers", "http_headers", "env_http_headers") if c.get(k)]
        transport = c.get("type") or ("http" if c.get("url") else "stdio")
        yield dict(agent=agent, scope=scope, name=name, transport=transport,
                   target=" ".join([cmd, *extra]), source=str(src))


def managed_mcp_path():
    if sys.platform == "darwin":
        return Path("/Library/Application Support/ClaudeCode/managed-mcp.json")
    if sys.platform == "win32":
        return Path(os.environ.get("ProgramData", r"C:\ProgramData")) / "ClaudeCode/managed-mcp.json"
    return Path("/etc/claude-code/managed-mcp.json")


def claude_cli_rows():
    """plugin + claude.ai connector scopes: shell out to `claude mcp list` (already resolves
    plugin-provided servers and connector health without printing secrets); skip if CLI missing."""
    exe = shutil.which("claude")
    if not exe:
        return
    try:
        out = subprocess.run([exe, "mcp", "list"], capture_output=True, text=True, timeout=30).stdout
    except Exception:
        return
    for line in out.splitlines():
        name, sep, rest = line.partition(": ")
        if not sep:
            continue
        scope = "claude.ai connector" if name.startswith("claude.ai ") else "plugin" if name.startswith("plugin:") else None
        if not scope:
            continue
        target = rest.rsplit(" - ", 1)[0].strip()
        yield dict(agent="claude", scope=scope, name=name, transport="-", target=mask_url(target), source="claude mcp list")


def cmd_mcp(a):
    rows, projects = [], [Path(a.project).expanduser()] if a.project else [Path.cwd()]
    try:
        projects += [root for _, root in checkouts(load_profile())]
    except SystemExit:
        pass

    def read(path, loader):
        try:
            return loader(path) if path.exists() else None
        except Exception as e:  # ponytail: warn + continue, as planned
            print(f"warn: không đọc được {path}: {e}", file=sys.stderr)

    jl = lambda p: json.loads(p.read_text(encoding="utf-8"))
    tl = lambda p: tomllib.loads(p.read_text(encoding="utf-8"))
    cj = read(HOME / ".claude.json", jl) or {}
    rows += mcp_rows(cj.get("mcpServers"), "claude", "user", HOME / ".claude.json")
    for pp, v in cj.get("projects", {}).items():
        if Path(pp) in projects:
            rows += mcp_rows(v.get("mcpServers"), "claude", "local", HOME / ".claude.json")
    for pr in projects:
        j = read(pr / ".mcp.json", jl) or {}
        rows += mcp_rows(j.get("mcpServers"), "claude", "project", pr / ".mcp.json")
        t = read(pr / ".codex/config.toml", tl) or {}
        rows += mcp_rows(t.get("mcp_servers"), "codex", "project", pr / ".codex/config.toml")
    t = read(codex_home() / "config.toml", tl) or {}
    rows += mcp_rows(t.get("mcp_servers"), "codex", "user", codex_home() / "config.toml")
    mp = managed_mcp_path()
    if mp.exists():
        j = read(mp, jl) or {}
        rows += mcp_rows(j.get("mcpServers"), "claude", "managed", mp)
    rows += claude_cli_rows()
    rows = [r for r in rows if not a.agent or r["agent"] == a.agent]
    if a.json:
        print(json.dumps(rows, indent=1))
    else:
        for r in rows:
            print(" | ".join(r[k] for k in ("agent", "scope", "name", "transport", "target", "source")))
    return 0

def viz_html(repo, files):
    """viz.html template + memory files as JSON -> one self-contained HTML string."""
    mems = []
    for f in sorted(files):
        meta, body = parse_md(f)
        rel = f.relative_to(repo)
        layer = "inbox" if rel.parts[0] == "inbox" else f.parent.parent.relative_to(repo / "layers").as_posix()
        mems.append({**{k: v if isinstance(v, str) else ", ".join(v) for k, v in meta.items()},
                     "name": meta.get("name", f.stem), "layer": layer, "file": rel.as_posix(), "body": body})
    layers = sorted({m["layer"] for m in mems})
    data = json.dumps(dict(memories=mems, layers=layers, generated=time.strftime("%Y-%m-%d %H:%M")), ensure_ascii=False)
    return (REPO / "viz.html").read_text(encoding="utf-8").replace("/*DATA*/null", data.replace("</", "<\\/"))


def write_viz(root, repo, players, dry):
    """Project copy for humans: .agentctx/viz.html. Not linked from AGENTS.md, and hidden from rg/Grep
    via .agentctx/.ignore, so agents never spend tokens on it."""
    if dry:
        return
    (root / PROJ_MEM.parent).mkdir(parents=True, exist_ok=True)
    (root / PROJ_MEM.parent / "viz.html").write_text(
        viz_html(repo, [f for l in players for _, _, f in layer_memories(repo, l)]), encoding="utf-8", newline="\n")
    (root / PROJ_MEM.parent / ".ignore").write_text("viz.html\n", encoding="utf-8", newline="\n")


def cmd_viz(a):
    repo = load_profile()["repo"]
    html = viz_html(repo, [*(repo / "layers").glob("**/memories/*.md"), *(repo / "inbox").glob("*.md")])
    out = Path(a.out) if a.out else Path(os.environ.get("AGENTCTX_HOME", HOME / ".agentctx")) / "viz.html"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(html, encoding="utf-8")
    print(f"-> {out}")
    if a.open:
        import webbrowser
        webbrowser.open(out.as_uri())

# ---------- main ----------

def main(argv=None):
    p = argparse.ArgumentParser(prog="agentctx")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("sync")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--agent")
    s.add_argument("--force", action="store_true")
    s.set_defaults(fn=cmd_sync)
    sub.add_parser("status").set_defaults(fn=cmd_status)
    sub.add_parser("lint").set_defaults(fn=cmd_lint)
    pr = sub.add_parser("propose")
    pr.add_argument("text")
    pr.add_argument("--to", help="bắt buộc, trừ khi --name trỏ tới memory đã có (mặc định layer của nó)")
    pr.add_argument("--type", required=True, choices=["user", "feedback", "project", "reference"])
    pr.add_argument("--reason", required=True)
    pr.add_argument("--name")
    pr.set_defaults(fn=cmd_propose)
    rm = sub.add_parser("remember", help="propose + approve + commit + sync, không hỏi")
    rm.add_argument("text")
    rm.add_argument("--to")
    rm.add_argument("--type", required=True, choices=["user", "feedback", "project", "reference"])
    rm.add_argument("--reason", required=True)
    rm.add_argument("--name", help="slug memory đã có: ghi đè (gộp)")
    rm.add_argument("--new", action="store_true", help="vẫn tạo mới dù gần trùng")
    rm.set_defaults(fn=cmd_remember)
    pj = sub.add_parser("project")
    pjs = pj.add_subparsers(dest="sub", required=True)
    pa = pjs.add_parser("add")
    pa.add_argument("paths", nargs="*", default=["."])
    pa.add_argument("--owner", required=True)
    pa.set_defaults(fn=cmd_project)
    pl = pjs.add_parser("list")
    pl.add_argument("--registered", action="store_true")
    pl.set_defaults(fn=cmd_project)
    sub.add_parser("harvest").set_defaults(fn=cmd_harvest)
    rv = sub.add_parser("review")
    rvs = rv.add_subparsers(dest="action")
    for name in ("approve", "reject"):
        x = rvs.add_parser(name)
        x.add_argument("slugs", nargs="*")
        x.add_argument("--all", action="store_true", help="mọi memory trong inbox (approve: theo proposed_layer)")
        if name == "approve":
            x.add_argument("--to")
    rv.set_defaults(fn=cmd_review)
    ic = sub.add_parser("import-claudeai")
    ic.add_argument("--to")
    ic.set_defaults(fn=cmd_import_claudeai)
    m = sub.add_parser("mcp")
    ms = m.add_subparsers(dest="sub", required=True)
    ml = ms.add_parser("list")
    ml.add_argument("--agent")
    ml.add_argument("--project")
    ml.add_argument("--json", action="store_true")
    ml.set_defaults(fn=cmd_mcp)
    v = sub.add_parser("viz", help="build memory thành 1 file HTML để xem")
    v.add_argument("-o", "--out")
    v.add_argument("--open", action="store_true")
    v.set_defaults(fn=cmd_viz)
    a = p.parse_args(argv)
    return int(a.fn(a) or 0)


if __name__ == "__main__":
    sys.exit(main())
