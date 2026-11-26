---
title: Secrets
order: 20
---
Không bao giờ ghi password, token hay key vào file (memory, instructions, code, commit).
Secret nằm trong keyring của OS, dùng chung một lệnh trên Mac/Windows/Linux:

- Đọc: `uvx keyring get <service> <user>`. Dùng thẳng trong lệnh (`$(uvx keyring get …)`), không in giá trị ra output.
- Lưu: người dùng tự chạy `uvx keyring set <service> <user>` (lệnh sẽ hỏi giá trị).
- Đặt tên service: `<hệ thống>-<loại>`, ví dụ `myhost-ssh`, `site-mqtt`.

Thứ gì đã có trong `.env` của repo thì chỉ ghi tham chiếu tới tên biến, không chép giá trị.
