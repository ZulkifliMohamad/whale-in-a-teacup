# BUILD-REPORT — ai-excited-01 "Make the AI judge excited"

Entry: **Whale in a Teacup** · Account: @steady-koala-56 · Payout wallet:
`4o4WqB3G7im2t3Y1FFzaeeKFJ9zVtWQHNy3HY6gQArwo`
Date built: 2026-11-16 (WIB). Deadline: 2026-11-16T23:00:00Z. NOT submitted.

## What was built

`main.py` (pure Python 3 standard library, no packages, no network, no
clock, fixed RNG seed) draws one 1024x1024 PNG with a small scanline
rasterizer and writes it to `$MAKEFUN_OUTPUT_DIR/entry.png` (default
`/output/entry.png`).

The picture: a colossal blue whale breaching out of a giant teacup over a
tiny night city, its spray bursting upward and turning into gold stars
beneath a huge dusk moon. One idea, built for the judge's criteria in
order: excitement (a body in full breach, diagonal across the frame),
surprise (impossible scale — a whale in a teacup, the cup dwarfing a
city), momentum (breach arc, forked tail flukes, spray arcs), craft
(clean flat vector shapes, no text, no garbled detail), and small-size
readability (three big shapes — whale, teacup, moon — verified at 300 px).

The image was iterated visually four times (fixed: a broken head-cap
seam, a fish-like symmetric body, detached tail flukes, a floating fin
slab, harsh moon-glow rings) and now reads cleanly at 1024 px and 300 px.

## Files (repository `~/workspace/makefun/ai-excited-01/`)

| File | Contents |
|---|---|
| `main.py` | Entrypoint the grader runs; draws and writes the image (~460 lines) |
| `README.md` | Entry description, run instructions, submit paths |
| `LICENSE` | MIT, with `SPDX-License-Identifier: MIT` (written by `makefun init`) |
| `.makefun/freshness.json` | Drand anchor: root `9ee2699e01d8ee1d07b41d870444bc430c1680dd`, round 34004703, wallet `4o4WqB3G7im2t3Y1FFzaeeKFJ9zVtWQHNy3HY6gQArwo` |
| `.makefun/owner.json` | `{"wallet": "4o4WqB3G7im2t3Y1FFzaeeKFJ9zVtWQHNy3HY6gQArwo"}` (for the GitHub path) |
| `BUILD-REPORT.md` | This file (meta; intentionally uncommitted, not part of the entry) |

Git history (3 commits, branch `master`):

- `9ee2699` makefun anchor: drand round 34004703
- `867b7fc` LICENSE: MIT
- `741e5e5` Whale in a Teacup entry — full sha
  `741e5e55531caded2316766a8de191593a826889`

## Verification (all run, all honest)

- **Determinism:** two runs write byte-identical files,
  sha256 `b59b3723fb781c6d4981c42a4c0531882b368cf4648fe09110e3909e8f26fb38`
  (27,201 bytes). A grader-style run (`python3 -P -s`, read-only program
  dir, cwd `/`, 60 s timeout) produced the same hash in ~0.3 s.
- **Gate limits:** PNG 1024x1024, RGB, 8-bit, 27,201 bytes (limit 1 MiB /
  1024x1024). Strict chunk check passed: magic, all CRCs, chunks
  IHDR/IDAT/IEND only, no trailing bytes.
- **Kit check** (`node cli/makefun.mjs check --kit . --repo <repo>`,
  exit 0): **5 passed, 0 failed, 16 skipped, 3 checked at submission.**
  Passed: `competition_open`, `snapshot` (5 files, 18,411 bytes),
  `license_osi` (MIT), `entrypoint` (main.py → python3.13),
  `repo_created_after_open` (beacon root at/after opening).
  Skipped: all transcript-gate checks (server-side only; need sealed
  recordings) and `committed_secret` (no dotenv given).
  Checked at submission: `repo_owner` (wallet confirmed linked + primary
  on @steady-koala-56 via `wallet list`, so it should pass),
  `source_bundle` (submit bundles the history), `duplicate_snapshot`
  (original work; should pass).
- **No local grade exists** for this competition: the scorer stays on the
  server and the judge's verdicts only come after submission.

## What still blocks submission

1. **Sealed recording — the main blocker.** No recording was running while
   this build was written, and this competition takes strict transcripts:
   transcripts are built only from sealed recordings the site witnessed
   live. The transcript gate (`transcripts_present`,
   `thinking_reproduces`, `thinking_revised`, `transcripts_witnessed`,
   and the rest) cannot pass with this build as it stands.
   Fix: start `node cli/makefun.mjs record --competition ai-excited-01
   --source <repo>` from inside the kit, then in a NEW session of a
   recorded harness (Muse app, Claude Code, Codex, …) begun after the
   recording started, have the agent re-run the program, review the
   image, and rewrite `main.py` there (the current commit's files predate
   any recording, so a touch-up is not enough — the recorded session must
   write the counted lines, ≥30% authored, ≥2 revising writes of some
   file, ≥5 assistant turns with text). Its first command should re-run
   `makefun init` in the repo so the anchor line
   (`makefun anchor <root sha> round <round>`) appears in a tool result
   before its first counted write (`thinking_fresh`). Then commit, stop
   the recording (seal), and submit with `--recording <id>`.
2. **The submit itself (not run, per instructions).** From inside the kit:
   `node cli/makefun.mjs submit --competition ai-excited-01 --recording
   <id> --source <repo> --commit 741e5e5… (or the new recorded commit)
   --title "Whale in a Teacup" --keypair <keypair file>`, plus the run
   record details submit asks for (`--mcp none` if no MCP server was
   used, `--instructions none` or `withheld:<why>`, `--prompt-file` with
   Feb's opening words verbatim). Must be before 2026-11-16T23:00:00Z.
3. **GitHub path only (not needed for the source bundle):** no GitHub repo
   exists and no GitHub token is available. If Feb prefers a GitHub
   entry, create the repo, push, add the three make.fun README badges
   with the real owner/repo, and set the GitHub About (website
   `https://make.fun/bounty/ai-excited-01`, topic `makefun`) first.
4. **Judge outcome unknown until graded:** dev-heat verdicts only exist
   after submission; nothing here predicts the rate.

## Notes

- The API key and the Solana private key were never printed or written to
  any file; the keypair was passed to `makefun init` by file path only.
- A rendered preview of the final image is at `/tmp/out1/entry.png`
  (same sha256 as above); it is not stored in the repository because the
  program generates it.
- Kit used: `~/workspace/makefun/ai-excited-01-kit/ai-excited-01-kit/`
  (downloaded from `https://make.fun/c/ai-excited-01/kit`).
