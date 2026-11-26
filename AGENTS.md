# agent-context: làm việc trong repo này

Cách dùng: [README.md](README.md).

## Dùng CLI, đừng viết shell ad-hoc

| Muốn biết / làm | Lệnh |
| --- | --- |
| Repo nào trên máy đã/chưa đăng ký, có `CLAUDE.md`/`AGENTS.md` chưa | `uv run agentctx.py project list [--registered]` |
| Đăng ký repo (nhiều path một lúc) | `uv run agentctx.py project add <path>... --owner teams/<t>\|users/<u>` |
| Layer nào đang có hiệu lực, file nào drift, inbox còn bao nhiêu | `uv run agentctx.py status` |
| Nội dung có lỗi / secret không | `uv run agentctx.py lint` |
| Sẽ ghi gì ra máy | `uv run agentctx.py sync --dry-run` |

- Chạy file bằng `uv run agentctx.py` hoặc `uv run test_agentctx.py` (script header ép Python ≥3.11).
  `uv run python -c "import agentctx"` sẽ lấy Python hệ thống và lỗi `tomllib`.
- Thiếu lệnh cho việc đang làm tay lần thứ hai thì thêm subcommand vào `agentctx.py` kèm assert trong
  `test_agentctx.py`, đừng lặp lại shell.
- `sync` không dry-run ghi vào `~/.claude`, `~/.codex` và các repo project: hỏi người dùng trước. Ngoại lệ: `remember` tự
  approve + commit file memory + `sync` không hỏi (giống native memory của harness), người dùng review qua `git log`.

## Test

`uv run test_agentctx.py` — chạy trong HOME sandbox, an toàn. Mọi thay đổi logic phải có assert ở đây.

`uv run bench_remember.py [reps] [arms] [base_ref]` — A/B chi phí ghi memory (native vs `remember`) bằng `claude -p` trong sandbox; chạy lại khi sửa block `propose-memory.md` hoặc output của `remember`. Tốn token thật (~$0.06/run).

## Secrets

- Không bao giờ in giá trị secret ra output. `uvx keyring get` ghi giá trị ra stdout; muốn kiểm tra thì so sánh
  (`[ "$(uvx keyring get s u)" = "$(…)" ] && echo ok`) hoặc đếm độ dài, đừng redirect stderr/stdout lung tung.
- Ghi vào keyring (`uvx keyring set`) là việc của người dùng.
- `lint` báo secret thì thay giá trị bằng tham chiếu (`uvx keyring get <service> <user>`, tên biến trong `.env`).
  Báo nhầm thì sửa `SECRET_RE` và thêm assert, đừng tắt lint.

## Hook watermarks-remover

Hook này báo nhầm các file memory (`scope_reason`, `author` là field bắt buộc của schema). Không chạy
`clean_file.py` lên `inbox/` hay `layers/`, vì sẽ làm hỏng frontmatter.
