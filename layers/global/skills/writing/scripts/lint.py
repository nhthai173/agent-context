#!/usr/bin/env python3
"""Mechanical review of Vietnamese or English prose: long sentences, stock phrases, term consistency. Stdlib only, no model tokens.

  python lint.py file.txt [--tone thesis|technical|report|correspondence] [--terms "old term|new term"] [--long N]

Prints compact line-numbered hints. They are prompts to reread, not evidence about authorship.
"""
import argparse, re, sys

SET_PHRASES = ["trong bối cảnh", "trong thời đại", "điều quan trọng là", "cần lưu ý", "đóng vai trò quan trọng",
               "đóng vai trò then chốt", "một cách toàn diện", "mở ra nhiều cơ hội", "tương lai tươi sáng",
               "không thể thiếu", "nhiều khía cạnh", "nhiều lĩnh vực", "các yếu tố khác nhau",
               "it is important to note", "it's important to note", "plays a key role", "plays a crucial role",
               "in today's", "in the realm of", "a testament to", "at its core", "delve", "tapestry"]
CONNECT = ["hơn nữa", "ngoài ra", "bên cạnh đó", "tóm lại", "nhìn chung", "kết luận lại", "furthermore",
           "moreover", "additionally", "in conclusion", "overall", "ultimately"]
CALQUE = {"vị trí ứng viên": "calque of 'candidate position': try 'các vị trí cần xét' / 'vị trí dự kiến'",
          "đối tượng chủ trì": "try 'thành phần trực tiếp thực thi'",
          "cài đặt": "in a thesis prefer 'hiện thực' / 'triển khai' (stay consistent)"}
RESIDUE = re.compile(r"hy vọng (?:điều|thông tin) này|bạn có muốn tôi|as an ai|i hope this helps|oaicite|utm_source=chatgpt", re.I)
REFRAME = re.compile(r"không (?:chỉ|phải)\b[^.;]{0,80}\bmà\b|\bnot (?:just|only)\b[^.;]{0,80}\bbut\b", re.I)
LONG = {"thesis": 40, "technical": 35, "report": 30, "correspondence": 25}   # long-sentence threshold per tone


def sentences(line):
    return [s.strip() for s in re.split(r"(?<=[.!?…])\s+", line) if s.strip()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("file"); ap.add_argument("--terms", default="")
    ap.add_argument("--tone", choices=list(LONG), default="thesis"); ap.add_argument("--long", type=int)
    a = ap.parse_args()
    a.long = a.long or LONG[a.tone]
    lines = open(a.file, encoding="utf-8").read().splitlines()
    lens, hits = [], []
    for n, line in enumerate(lines, 1):
        low = line.lower()
        for s in sentences(line):
            w = len(s.split()); lens.append(w)
            if w > a.long:
                hits.append((n, f"long sentence ({w} words): {s[:60]}..."))
        for p in SET_PHRASES:
            if p in low: hits.append((n, f"stock phrase: '{p}'"))
        for c in CONNECT:
            if re.search(rf"(?:^|[.!?]\s+){re.escape(c)}\b", low): hits.append((n, f"connector opener: '{c}'"))
        for k, why in (CALQUE.items() if a.tone == "thesis" else ()):
            if k in low: hits.append((n, f"possible calque '{k}': {why}"))
        if REFRAME.search(line): hits.append((n, "'not X but Y' construction"))
        if RESIDUE.search(line): hits.append((n, "chatbot residue"))
        if "—" in line or " -- " in line: hits.append((n, "em dash"))
    for n, msg in hits:
        print(f"{n}: {msg}")
    if lens:
        m = sum(lens) / len(lens); sd = (sum((x - m) ** 2 for x in lens) / len(lens)) ** 0.5
        print(f"-- {len(lens)} sentences, mean {m:.1f} words, sd {sd:.1f} (coefficient of variation {sd / m:.2f}; below 0.3 is a very even rhythm)")
    for t in (x for x in a.terms.split("|") if x):
        print(f"-- term '{t}': {sum(l.lower().count(t.lower()) for l in lines)} occurrences")


if __name__ == "__main__":
    sys.exit(main())
