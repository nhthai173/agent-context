---
name: writing
description: Apply whenever you write or rewrite prose that a person will read - documents, READMEs, changelogs, design docs, reports, proposals, thesis or paper sections, emails, messages, commit and PR descriptions, long explanations. Also use when the user says a sentence sounds unnatural, asks to rewrite, polish or unify terminology, or asks whether text sounds machine-written. Picks a tone (technical, thesis, report, correspondence), grounds claims in the real source, and lints for stock AI phrasing. Not for code, commands or one-line answers.
---

# Writing

Distilled from a real thesis-writing session and from public research on "machine voice" (see `references/ai-tells.md`). Goal: natural, correct prose at a low token cost. Write in the user's language; language-specific notes live in `references/` (Vietnamese: `references/vietnamese.md`).

## Choose a tone (load exactly one file)

| Tone | Use for | File |
|---|---|---|
| Thesis | thesis, dissertation, academic paper | `references/tones/thesis.md` |
| Technical | README, design doc, changelog, runbook, system description | `references/tones/technical.md` |
| Report | status report, proposal, summary for a decision maker | `references/tones/report.md` |
| Correspondence | email, chat message, note to a colleague | `references/tones/correspondence.md` |

If the user does not say, infer it from where the text will live and who reads it; if still unclear, ask one short question. For mixed documents use the tone of the main reader.

## Workflow

1. **Pin down the job.** Outline and draft, evaluate and rewrite, or fix one sentence? If two readings are plausible, ask one short question. "No need to create/update the file" means answer in chat only.
2. **Ground in facts before writing.** If the text describes a system, read the relevant code or docs first (grep names, read the key function). Anything you cannot verify is dropped or marked "needs checking"; never invent detail to fill a gap.
3. **Evaluate before rewriting** (when there is a draft). List concrete numbered problems: contradictions, items present in the code but missing in the text, ambiguous statements, inconsistent terms, explanatory sentences that repeat. Praise what works, briefly.
4. **Rewrite in the author's voice and meaning.** No new facts, no changed meaning. If the draft is only reference material, rewrite to the standard of the chosen tone instead of patching sentence by sentence.
5. **"Sounds unnatural".** Find the cause (often a word-for-word calque of English), give 2 to 3 options with trade-offs, recommend one with a reason. Once a term is chosen, grep the whole file and replace it everywhere (`references/terminology.md`).
6. **Lint mechanically, not by feel:** `python scripts/lint.py <file> --tone <thesis|technical|report|correspondence> [--terms "a|b"]`. Pattern list and fixes: `references/ai-tells.md`. The lint only points at passages to reread; never use it (or any detector) to conclude who wrote a text.
7. **Report briefly.** What changed, why, and what the user must verify. Do not replay the whole text.

## Orchestration: quality versus tokens

- **Default: do it inline, no subagent.** Fixing a sentence, offering options, "rewrite this line" is one turn. Load only this file plus one tone file.
- **Gather facts with a cheap, read-only helper when many files must be read** (a fast model or subagent: Claude Explore/Haiku, or a small Codex model). Ask for a short fact table with `file:line`; the strong model drafts from that table, so raw greps stay out of the main context.
- **Mechanical work goes to the script:** terminology consistency, long sentences, stock phrases, em dashes. Zero reasoning tokens.
- **Never give a small model the job of judging "was this written by AI".** In tests, a small model and a heuristic detector both failed to separate AI paragraphs in technical Vietnamese text.
- **Use the strong model at two points only:** the first draft and the final polish. Small revision rounds in between happen inline, one sentence or paragraph at a time.
- **Keep a short project glossary file** (for example `glossary.md`) and read it instead of rereading the whole document.
