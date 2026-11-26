---
name: git-history-cleanup
description: Purge a heavy path's git history (repeatedly-overwritten exports, PDFs, build output) down to just its latest snapshot, without losing current content. Use when .git is bloated, when the user asks to "dọn git history", "xoá lịch sử git", "giảm dung lượng repo", "chỉ giữ bản mới nhất" for a specific folder, or before adding a heavy path to .gitignore that already has history baggage.
---

# Git history cleanup (purge history, keep latest snapshot)

Rewrites every commit's SHA in the target repo. **Hard to reverse** — always
confirm scope with the user first (which paths, which repo) before running
anything past step 2. This is not for removing a file going forward
(that's just `.gitignore` + `git rm --cached`) — it's for shrinking `.git`
because old revisions of a heavy path are baked into history.

## When it's worth doing

Check the actual bloat before touching anything:

```bash
git rev-list --objects --all -- <path> | git cat-file --batch-check='%(objecttype) %(objectname) %(objectsize) %(rest)' \
  | awk '$1=="blob"{sum+=$3; n++} END{printf "%d blobs, %.1f MB across history\n", n, sum/1024/1024}'
du -sh "$(git rev-parse --git-dir)"
```

If that number is small relative to `.git`, this isn't the win — look
elsewhere first.

## Procedure

1. **Install once**: `brew install git-filter-repo` (the current
   Git-recommended tool — not BFG, not `filter-branch`).

2. **Backup before anything else** — this is the only safety net, since the
   rewrite that follows cannot be undone once pushed:
   ```bash
   git clone --mirror <remote-url> /path/to/scratch/backup.git
   ```

3. **Check every ref on the remote, not just the branch you're cleaning**:
   ```bash
   git ls-remote --heads origin
   for b in <other-branches>; do
     git merge-base --is-ancestor origin/$b origin/main \
       && echo "$b: merged, safe to ignore/delete" \
       || echo "$b: diverged — decide before rewriting (ahead: $(git rev-list --count origin/main..origin/$b), behind: $(git rev-list --count origin/$b..origin/main))"
   done
   ```
   Any ref (branch or tag) still pointing at old history keeps the heavy
   blobs reachable on the server — rewriting `main` alone does not shrink
   the repo if a stale branch still references the old tree. A branch fully
   merged into main (0 ahead) can be deleted with nothing lost. A diverged
   branch needs an explicit decision (leave it, delete it, or rewrite it
   too) — ask the user, don't default.
   ```bash
   git push origin --delete <branch>   # only for branches the user confirmed
   ```

4. **Save the current content of the target paths** — the rewrite removes
   them from the final checkout too, not just old commits:
   ```bash
   SNAP=/path/to/scratch/snapshot
   mkdir -p "$SNAP"
   cp -R <path1> "$SNAP/"
   cp -R <path2> "$SNAP/"
   ```

5. **Run the rewrite**:
   ```bash
   git filter-repo --path <path1> --path <path2> --invert-paths --force
   ```
   This drops `origin` remote as a safety feature (a rewritten history must
   never be silently pushed to the same remote without a deliberate step).

6. **Restore the latest snapshot as one new commit**:
   ```bash
   cp -R "$SNAP"/* .
   find <path1> <path2> -name ".DS_Store" -delete   # cruft left on disk pre-rewrite
   git add <path1> <path2>
   git commit -m "chore(history): purge <path> history, keep latest snapshot"
   ```
   Verify it's byte-identical to what was there before rewriting:
   `diff -rq "$SNAP/<path>" <path>` should print nothing.

7. **Actually reclaim the space locally**:
   ```bash
   git reflog expire --all --expire=now
   git gc --prune=now --aggressive
   du -sh "$(git rev-parse --git-dir)"   # compare to the number from step 0
   ```

8. **Push** — every SHA changed, so this is unavoidably a force-push.
   Never use a bare `--force`; fetch first and lease against the exact SHA
   you last saw, so a push that happened in between gets rejected instead of
   silently overwritten:
   ```bash
   git remote add origin <remote-url>
   git fetch origin main
   git rev-parse origin/main   # confirm it's still the SHA you expect
   git push origin main --force-with-lease=main:<that-sha>
   ```

9. **Fix anything that pointed at the old SHAs.** A submodule pointer in
   another repo, a deploy pin, a CI config referencing a specific commit —
   all of those 404 once the old commits become unreachable and GitHub GCs
   them. Bump those pointers in the same session.

## Common mistakes

- Deleting the target path's history without checking other branches first
  (step 3) — the "cleanup" then does nothing for actual repo size on the
  server.
- Force-pushing without confirming `origin/main` hasn't moved — use
  `--force-with-lease=<branch>:<sha>`, not `--force`.
- Forgetting step 4/6 — `--invert-paths` deletes the path from HEAD too, not
  just history. Losing the current files is not the goal.
- Not re-adding `origin` after `git filter-repo` runs (it removes the remote
  on purpose) and then being confused why `git push` fails.
