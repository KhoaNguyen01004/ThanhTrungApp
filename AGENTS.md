# Agent Instructions

**Read `CLAUDE.md` first.** It is the primary context file for this repository and carries
the architecture notes, the DB-access and frontend conventions, the Scope Control rules,
and the Definition of Done. This file only adds the graphify rules on top of it.

**Who reads what.** Claude Code and Cowork read `CLAUDE.md` and ignore this file; OpenCode
reads this one. That is why both exist. Keep them consistent: anything that belongs to both
goes in `CLAUDE.md` and is referenced from here, never duplicated.

## graphify

**Standing instruction: query the knowledge graph at `graphify-out/` before grepping or
opening files** for any question about how this codebase fits together. `CLAUDE.md`
§ graphify carries the full command table, the two silent-failure modes (no
per-subcommand `--help`; substring matching with no stemming), and the confidence-tag
rules. Read that section rather than relying on the summary below.

Quick reference: the package is `graphifyy` (three y's), the command is `graphify`.
`query` / `path` / `explain` / `affected` / `god-nodes` read the graph; `graphify update .`
rebuilds it by AST with no LLM cost.

The graph currently holds 3,131 nodes, 5,997 edges and 200 communities over 137 files.
**As of 2026-08-15 it is behind HEAD** — `built_at_commit` is `569c0fe`, five commits back,
with uncommitted work on top of that. Run `graphify update .` before trusting a result
about `app/routes/trips.py` or `app/state.py` in particular.

When the user types `/graphify`, use the installed graphify skill or instructions before
doing anything else.

Rules:

- For codebase questions, first run `graphify query "<question>"` when
  `graphify-out/graph.json` exists. Use `graphify path "<A>" "<B>"` for relationships and
  `graphify explain "<concept>"` for focused concepts. These return a scoped subgraph,
  usually much smaller than `GRAPH_REPORT.md` or raw grep output.
- Dirty `graphify-out/` files are expected after hooks or incremental updates; that is not
  a reason to skip graphify. Only skip it if the task is about stale or incorrect graph
  output, or the user says not to use it.
- Read `graphify-out/GRAPH_REPORT.md` only for broad architecture review, or when
  query/path/explain do not surface enough. `graphify-out/wiki/index.md` does not exist in
  this repo.
- After modifying code, run `graphify update .` to keep the graph current (AST-only, no API
  cost). Use `--force` after a refactor that deletes code — the rebuild otherwise refuses
  to shrink the graph.
- `.sql` files are effectively absent from the graph. `database.sql` is UTF-16LE, which
  tree-sitter-sql cannot parse, so it contributes one bare file node and zero edges.
  Installing the `[sql]` extra will not fix it.
