# Tone: technical (README, design doc, changelog, runbook, system description)

**Reader:** a developer or coding agent who must act on it or continue the work. **Goal:** after reading, they know what to do and where.

- Short, active sentences. Result or decision first, reason after.
- Be concrete: paths, function names, environment variables, commands, defaults. Not "improved the experience" but which file, which function, what changed.
- Identifiers in backticks, verbatim. Do not mix whole sentences of another language into the text.
- Commands in their own code block, one command per block when the reader runs them one by one.
- Order by what the reader does (prepare, run, verify, troubleshoot), not by how you discovered it.
- Explain "why" only when there is a real cause the reader cannot infer; no filler benefit sentences.
- Markdown: one line per paragraph or bullet; no manual wrapping.
- No first-person storytelling ("I tried...") in reference docs.

Before/after:
- Before: "The system allows configuring various parameters to optimize performance."
- After: "Set `API_CACHE_TTL` (seconds, default 60) to change cache time; 0 disables it."
