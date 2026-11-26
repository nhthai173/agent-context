# agent-context

Kho instructions / skills / memories dùng chung cho Claude Code và Codex. Script `agentctx.py` (chỉ dùng stdlib, chạy bằng `uv run`) render nội dung đó ra định dạng riêng của từng agent.

## Hai repo: công cụ (repo này) và dữ liệu của bạn

Repo này chỉ chứa công cụ và `layers/global` (skill + instructions dùng chung). **Memories, instructions cá nhân và project của bạn nằm ở một repo riêng** (nên để private). Đừng bỏ qua bước này: nếu không khai `repo` trong profile, `agentctx` mặc định ghi memory vào chính bản clone này, tức vào repo public.

## Cài đặt

```bash
git clone https://github.com/nhthai173/agent-context.git ~/code/agent-context   # công cụ (repo này)
mkdir ~/code/my-context-data && git -C ~/code/my-context-data init              # dữ liệu riêng của bạn
```

Tạo `~/.agentctx/profile.toml`, rồi xem trước và chạy sync:

```bash
uv run ~/code/agent-context/agentctx.py sync --dry-run
uv run ~/code/agent-context/agentctx.py sync
```

## Dùng

1. `~/.agentctx/profile.toml` (không commit):
   ```toml
   user = "me"
   repo = "~/code/my-context-data"          # repo riêng của bạn: memories, inbox, users/, teams/ (nơi duy nhất được ghi)
   shared = ["~/code/agent-context"]        # repo công cụ này: layers/global dùng chung, chỉ đọc
   agents = ["claude", "codex"]
   teams = ["acme"]          # skill của team này được cài ở user-level
   scan = ["~/Desktop"]          # tìm checkout của project đã đăng ký (sâu 2 cấp)
   write_user_level = true       # false = sync chỉ đọc, không ghi ~/.claude/CLAUDE.md hay ~/.codex/AGENTS.md
   ```
2. Đăng ký project (nhận diện bằng git remote, mọi clone/worktree đều khớp):
   `uv run agentctx.py project add ~/Desktop/acme/app --owner teams/acme`
3. Thêm nội dung vào `layers/<layer>/{instructions,skills,memories}/` (repo dữ liệu riêng chứa layer của bạn; repo này chỉ giữ `layers/global`).
4. `uv run agentctx.py sync --dry-run`, rồi `uv run agentctx.py sync`. Commit file sinh ra trong repo project.

| Lệnh | Việc |
| --- | --- |
| `sync [--dry-run] [--agent X] [--force]` | Ghi managed block + skills + memories. Dừng nếu lint lỗi hoặc block bị sửa tay (`--force` để ghi đè) |
| `status` | Block nào drift, inbox có bao nhiêu memory, skill `custom` nào lệch so với claude.ai |
| `lint` | Frontmatter, secret, memory trùng, `review_by` quá hạn |
| `project add [path...] --owner teams/T\|users/U` | Đăng ký repo vào `layers/<owner>/projects/<repo>/project.toml` |
| `project list [--registered]` | Repo git trong `scan`: layer đã đăng ký, có `CLAUDE.md`(`C@` = đã import AGENTS.md)/`AGENTS.md` chưa |
| `propose --to L --type T --reason R "text"` | Tạo memory trong `inbox/` |
| `remember --to L --type T --reason R "text" [--name slug \| --new]` | Agent tự ghi: approve + commit riêng file memory + `sync`, không hỏi. Gần trùng (≥0.3) thì exit 2 kèm `similar:`, gộp bằng `--name`. Review qua `git log`. Một lần chỉ một `remember` (khoá `.remember.lock`); kẻ đến sau chờ ≤15s rồi exit 3 (`BUSY`, chưa ghi gì) |
| `harvest` | Copy memory native của Claude (`~/.claude/projects/*/memory/*.md`) chưa có trong repo vào `inbox/` |
| `review` | Liệt kê inbox kèm scope gợi ý (`⚠ scope?` khi lệch với `proposed_layer`) |
| `review approve <slug>... [--to L]` / `review reject <slug>...` (hoặc `--all`) | Duyệt (chuyển sang `layers/<L>/memories/`, `--all` theo `proposed_layer`) hoặc xoá; slug bị reject ghi vào `inbox/.rejected` để `harvest` không kéo lại |
| `import-claudeai [--to L]` | Copy skill `custom` từ `~/.claude/skills/synced/` vào repo (mặc định `users/<user>`) |
| `mcp list [--agent X] [--project P] [--json]` | Liệt kê MCP server (env/header/token che thành `***`) |

Secret: không ghi vào repo; lưu bằng `uvx keyring set <service> <user>` (Keychain / Windows Credential Manager / Secret Service), tham chiếu bằng `uvx keyring get <service> <user>`.

Test: `uv run test_agentctx.py`. Chưa làm: xác minh path skills Codex, chạy thử trên Windows/Linux, sync MCP.

Hook PreCompact nhắc agent chạy `remember` trước khi context bị nén: `layers/global/hooks/precompact-propose-memory.json` có snippet, merge key `PreCompact` vào `~/.claude/settings.json` `hooks`. `sync` không tự áp (hook chưa phải loại nội dung của layer).

## Windows

Đã chạy `test_agentctx.py` trên Windows 11 (Python 3.13, Git for Windows) và pass. Lưu ý:

- Trong `profile.toml` viết đường dẫn bằng dấu `/` hoặc dấu nháy đơn (`'C:\Users\me\data'`). Dấu `\` trong nháy kép bị TOML hiểu là escape và báo lỗi.
- Nhập memory gốc của Claude (`import`) chưa hỗ trợ đường dẫn có ổ đĩa; các lệnh còn lại không bị ảnh hưởng.
- Chưa có `uv` thì chạy thẳng `python agentctx.py ...` (chỉ cần Python >= 3.11).
