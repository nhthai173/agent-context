#!/usr/bin/env python3
"""A/B ghi memory: A = native (CLAUDE.md không có agentctx), B = agentctx remember.
Sandbox hoàn toàn: repo copy, HOME giả cho lệnh remember, 25 repo giả để sync tốn công như thật.
B0 = bản trước tối ưu (git ref, mặc định HEAD), B1 = working tree hiện tại. Chỉ tốn token (haiku low mặc định; đổi bằng BENCH_MODEL/BENCH_EFFORT), không đụng repo/HOME thật.
Usage: uv run bench_remember.py [reps=2] [arms=A,B0,B1] [base_ref=HEAD]   (cần `claude` đã đăng nhập, và ~/.claude/CLAUDE.md để lấy ngữ cảnh thật)"""
import json, os, re, shutil, statistics as st, subprocess, sys, tempfile
from pathlib import Path

S = Path(tempfile.mkdtemp(prefix="bench_remember_"))
HERE = Path(__file__).resolve().parent
SRCS = {"B0": S / "src0", "B1": HERE, "A": HERE}
ARMS = sys.argv[2].split(",") if len(sys.argv) > 2 else ["A", "B0", "B1"]
if "B0" in ARMS:
    SRCS["B0"].mkdir()
    subprocess.run(f"git -C {HERE} archive {sys.argv[3] if len(sys.argv) > 3 else 'HEAD'} | tar -x -C {SRCS['B0']}", shell=True, check=True)
NATIVE = ("Persistent memory dir: {mem}. Save a durable fact as one file there with frontmatter (name, description, metadata.type) "
          "plus a one-line pointer in MEMORY.md in the same dir. Use this for things worth remembering across sessions.")
REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 2
FACTS = [
    "Thái muốn đặt tên branch theo dạng feat/<ticket>-<mô-tả-ngắn>, toàn chữ thường.",
    "Broker MQTT của site demo-lab chạy cổng 18830, không phải 1883 mặc định.",
    "Khi Thái nói 'chốt' nghĩa là commit luôn, đừng hỏi xác nhận lại.",
]
DUPS = [  # đã có trong Shared memories: ghi lại là phí token
    "Luôn dùng pnpm thay npm cho Node.js.",
    "Trả lời Thái bằng tiếng Việt.",
]
FACTS += DUPS
USER_MD = (Path.home() / ".claude/CLAUDE.md").read_text()
# A = bỏ block "Remember via agent-context" (từ heading tới hết đoạn "Mention in one line..." + đoạn PreCompact)
A_MD = re.sub(r"## Remember via agent-context.*?(?=\n## |\Z)", "", USER_MD, flags=re.S)
PROJ = "<!-- agentctx:begin -->\n## Project\nRepo test.\n<!-- agentctx:end -->\n"


def sh(*a, **k):
    return subprocess.run(a, check=True, capture_output=True, text=True, **k)


def sandbox(tag, SRC):
    B = S / f"sb_{tag}"
    shutil.rmtree(B, ignore_errors=True)
    (B / "home").mkdir(parents=True)
    shutil.copytree(SRC, B / "repo", ignore=shutil.ignore_patterns("__pycache__", ".remember.lock", "fsmonitor*"), symlinks=True)
    g = lambda *a: sh("git", "-C", str(B / "repo"), "-c", "user.name=b", "-c", "user.email=b@b", *a)
    if not (B / "repo/.git").exists(): g("init", "-q")
    g("add", "-A"); g("commit", "-qm", "base", "--allow-empty"); g("tag", "-f", "base")
    scan = B / "scan"
    for i in range(25):
        d = scan / f"proj{i}"; d.mkdir(parents=True)
        sh("git", "-C", str(d), "init", "-q"); sh("git", "-C", str(d), "remote", "add", "origin", f"https://x/p{i}.git")
        (d / "AGENTS.md").write_text("x")
    (B / "profile.toml").write_text(f'user = "me"\nrepo = "{B/"repo"}"\nagents = ["claude"]\nteams = []\nscan = ["{scan}"]\n')
    env = dict(os.environ, HOME=str(B / "home"), AGENTCTX_HOME=str(B / "home/.agentctx"),
               AGENTCTX_PROFILE=str(B / "profile.toml"), UV_CACHE_DIR=str(Path.home() / ".cache/uv"))
    sh("uv", "run", str(B / "repo/agentctx.py"), "project", "add", *[str(p) for p in scan.iterdir()], "--owner", "users/me", env=env)
    sh("uv", "run", str(B / "repo/agentctx.py"), "sync", env=env)
    (B / "ws").mkdir(); (B / "mem").mkdir()
    return B


def block(src):
    t = (src / "layers/global/instructions/propose-memory.md").read_text().split("---\n", 2)[2].strip()
    return "## Remember via agent-context\n\n" + t.replace("{{repo}}", str(src)) + "\n\n"


def run(arm, B, fact):
    md = A_MD
    if arm != "A":
        md = A_MD + "\n" + block(SRCS[arm])
        md = md.replace(str(SRCS[arm]) + "/agentctx.py", "AGENTCTX_PLACEHOLDER")
    if arm != "A":
        pre = (f"env HOME={B/'home'} AGENTCTX_HOME={B/'home/.agentctx'} AGENTCTX_PROFILE={B/'profile.toml'} "
               f"UV_CACHE_DIR={Path.home()/'.cache/uv'} uv run {B/'repo/agentctx.py'}")
        md = md.replace("uv run AGENTCTX_PLACEHOLDER", pre)
    (B / "ws/CLAUDE.md").write_text(md + "\n" + PROJ)
    r = subprocess.run(["claude", "-p", "--no-session-persistence", "--output-format", "json",
                        "--permission-mode", "bypassPermissions",
                        "--model", os.environ.get("BENCH_MODEL", "haiku"), "--effort", os.environ.get("BENCH_EFFORT", "low"), "--setting-sources", "project,local",
                        "--append-system-prompt", NATIVE.format(mem=B / "mem"),
                        f"Hãy ghi nhớ: {fact}"], cwd=B / "ws", capture_output=True, text=True)
    try:
        d = json.loads(r.stdout)
    except Exception:
        return None
    u = d["usage"]
    wrote = bool(list((B / "mem").glob("*"))) if arm == "A" else sh("git", "-C", str(B / "repo"), "rev-list", "--count", "base..HEAD").stdout.strip() != "0"
    return dict(wrote=wrote, cc=u.get("cache_creation_input_tokens",0), cr=u.get("cache_read_input_tokens",0), fresh=u["input_tokens"], cost=d["total_cost_usd"], turns=d["num_turns"], out=u["output_tokens"],
                inp=u["input_tokens"] + u.get("cache_creation_input_tokens", 0) + u.get("cache_read_input_tokens", 0),
                result=d.get("result", "")[:160])


res = {a: [] for a in ARMS}
dup_wrote = {a: [] for a in ARMS}
for rep in range(REPS):
    for fi, fact in enumerate(FACTS):
        for arm in ARMS:
            B = sandbox(arm, SRCS[arm])  # path cố định theo arm: prefix giống nhau -> cache hit như session thật
            m = run(arm, B, fact)
            print(arm, rep, fi, {k: v for k, v in (m or {}).items() if k != "result"}, flush=True)
            if m and m["cost"] > 0 and not (rep == 0 and fi == 0):  # bỏ run đầu = warm-up cache
                res[arm].append(m)
                if FACTS[fi] in DUPS:
                    dup_wrote[arm].append(m["wrote"])
            shutil.rmtree(B, ignore_errors=True)
print("\narm n cost turns fresh cache_create cache_read out")
for arm, r in res.items():
    if r:
        print(arm, len(r), *[f"{st.mean(x[k] for x in r):.4g}" for k in ("cost", "turns", "fresh", "cc", "cr", "out")])
print("fact trùng vẫn bị ghi lại:", {a: f"{sum(v)}/{len(v)}" for a, v in dup_wrote.items()})
shutil.rmtree(S, ignore_errors=True)
