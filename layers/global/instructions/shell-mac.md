---
title: Shell trên Mac
order: 30
---
Lệnh Bash chạy trong zsh + BSD, hay vấp những chỗ sau (đã đo trên transcript):

- Cwd bị reset sau mỗi lệnh: dùng đường dẫn tuyệt đối, đừng dựa vào `cd` của lệnh trước.
- Sửa file bằng Edit, không dùng `sed -i`. Nếu cần sed thì `sed -i ''` (BSD) hoặc `gsed`.
- Chờ một việc xong: dùng Monitor hoặc `run_in_background`. `sleep N; lệnh` bị harness chặn.
- Python: `uv run`, không gọi `python` hệ thống.
- Biến chứa lệnh kèm đối số (`R="ssh -p 22"`) chỉ chạy được khi shell đã bật `shwordsplit`; không chắc thì viết hàm hoặc gõ thẳng.
- ssh tới host Windows: không để `|`, `>`, `'` trong lệnh từ xa (cmd nuốt). Đẩy script lên rồi chạy file.
- Không bao giờ `sshpass -p '<mật khẩu>'`: dùng `SSHPASS=$(uvx keyring get <service> <user>) sshpass -e ssh ...`.
