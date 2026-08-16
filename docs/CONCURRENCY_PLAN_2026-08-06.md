# WAL and `--workers` — measurements and recommendation

**Status: recommendation only. Nothing in `render.yaml`, `app/db.py` or
`app/database/` has been changed.**

`CLAUDE.md` has carried this as one open decision: production is a single
synchronous Gunicorn worker, there is no `PRAGMA journal_mode=WAL` anywhere, and
"adding workers without enabling WAL first trades that latency for lock errors;
treat the pair as one decision." This document measures the pair.

Everything below was measured against a copy of the live `routing_system.db`
(323 `fuel_log` rows, 36 vehicles) on `sqlite3 3.37.2 / Python 3.10`.

---

## First, a correction to the audit

`docs/AUDIT_2026-08-06.md` §2 said the geofence bug's uncommitted write "holds a
`RESERVED` lock across N network round trips… concurrent requests block on it."
The lock part is right. **The "concurrent requests block" part is wrong**, and
the distinction changes what WAL is for.

A held `RESERVED` lock does **not** block readers. SQLite allows readers
throughout; only the brief `EXCLUSIVE` phase at commit excludes them. Measured,
with a writer holding a transaction open and four readers arriving mid-hold:

| journal_mode | writer holds | reads OK | reads locked | max read wait |
|---|---|---|---|---|
| delete | 2s | 4 | 0 | 2 ms |
| delete | 7s | 4 | 0 | 1 ms |
| wal | 2s | 4 | 0 | 0 ms |
| wal | 7s | 4 | 0 | 4 ms |

What *does* fail is a **second writer**. Python's `sqlite3` has a default busy
timeout of 5 seconds, so a competing write waits that long and then raises:

| journal_mode | writer holds | competing write | waited |
|---|---|---|---|
| delete | 2s | **OK** | 2055 ms |
| delete | 7s | **`database is locked`** | 5018 ms |
| wal | 2s | **OK** | 2039 ms |
| wal | 7s | **`database is locked`** | 5012 ms |

**WAL does not help here.** SQLite serialises writers in both modes. So:

> The fix for `database is locked` in this codebase was the geofence
> transaction fix, not WAL. The hold is now one loop iteration instead of N
> OpenRouteService round trips, which is the difference between comfortably
> under the 5-second timeout and comfortably over it.

That reframes the decision. WAL is not the safety prerequisite `CLAUDE.md`
implies — it is a throughput improvement, and it should be argued for on those
terms.

---

## What WAL actually buys

Six reader threads running the fuel-log query plus one writer imitating the
background refresher, six seconds, default busy timeout:

| journal_mode | reads completed | read p50 | read p95 | writes | write p50 | write p95 | lock errors |
|---|---|---|---|---|---|---|---|
| delete | 924 | 28.5 ms | 81.0 ms | 166 | 24.1 ms | 43.0 ms | 0 |
| **wal** | **2128** | **14.0 ms** | **29.5 ms** | **511** | **0.8 ms** | **4.0 ms** | 0 |

2.3× the read throughput, read p95 cut by 64%, and writes go from 24 ms to
under 1 ms because a WAL commit is an append rather than a rollback-journal
dance. Zero lock errors in *both* modes at this concurrency — again, the errors
come from long-held transactions, not from contention as such.

---

## Recommendation

### 1. Enable WAL — worth doing, low risk

`journal_mode` is a **persistent property of the database file**, not a
per-connection pragma (unlike `foreign_keys`, which `app/db.py` correctly sets on
every connection). Verified: set once, a fresh connection reports `wal`. So this
is one line at startup in `init_db()`, not a change to every call site or to
`DatabaseManager`.

```python
conn.execute("PRAGMA journal_mode=WAL")
```

**Three caveats worth knowing before you say yes:**

- **Backups get a footgun.** Under WAL, copying just `routing_system.db` while
  the server is running silently loses everything not yet checkpointed.
  Measured: a live database with 373 rows produced a 323-row copy — 50 committed
  rows gone, no error. Use `sqlite3 .dump`, `.backup`, or Python's
  `conn.backup()`, all of which go through SQLite and are correct. Your existing
  `database.sql` is a `.dump`, so **it is already safe**; the risk is anyone who
  downloads the `.db` file off the Render disk directly.
- **Two sidecar files appear** next to the database (`-wal`, `-shm`). They live
  on the persistent disk, are removed on clean shutdown, and are small. Anything
  that enumerates or syncs the data directory should expect them.
- **WAL needs real shared memory**, so the database must sit on a local
  filesystem rather than a network mount. Render's persistent disk qualifies.

### 2. Set `busy_timeout` explicitly

Today the 5-second timeout is Python's default, arrived at by accident rather
than decision — and it is the line between "waited" and "`database is locked`"
in the table above. Making it explicit in `app/db.py` and at the raw
`sqlite3.connect()` call sites documents the intent and lets it be tuned:

```python
conn.execute("PRAGMA busy_timeout = 10000")   # ms
```

Raising it to 10-15s converts the remaining rare lock error into a slow request,
which for a dispatch board is the better failure.

### 3. `--workers` — yes, but that is a *different* problem

Workers do not fix lock contention; they fix **head-of-line blocking**, which is
this system's actual latency complaint. `/api/execution/dashboard` does a
blocking TTAS fetch (15s timeout) inside the request, and `/api/eta` issues one
ORS call per remaining stop serially at 30s each. On one synchronous worker,
every other request queues behind those.

```yaml
startCommand: "gunicorn wsgi:app --workers 2 --threads 4 --worker-class gthread --timeout 120"
```

Notes on that line specifically:

- **`--threads` is ignored by the default `sync` worker class.** It needs
  `--worker-class gthread`, or the flag silently does nothing.
- **Start at 2 workers, not 4.** More workers means more concurrent *writers*,
  which is the one axis WAL does not help. Now that writes are short this is
  much safer than it was, but it is still the thing to watch.
- **`app/state.py` becomes per-worker.** The route cache, the TTAS session and
  `known_locations` are process-global. With 2 workers you get two independent
  caches and two TTAS sessions, and `state.sync_lock` / `state.oil_fetch_lock`
  **stop being mutual exclusion** — they only guard threads within one process.
  `/api/fuel/sync`'s "Sync already in progress" 429 would no longer be reliable.
  **This is the real cost of adding workers, and it is not a database problem.**
  It wants its own look before the flag is set.
- The Render disk limits the service to **one instance**, but multiple workers
  inside that instance are fine. Zero-downtime deploys are already given up.

### Suggested order

1. **WAL + explicit `busy_timeout`.** Self-contained, measurable, no
   application-logic implications. Do this first and confirm the latency change
   in production.
2. **Then** the `app/state.py` audit — decide what a second process does to the
   route cache, the TTAS session, and the two locks.
3. **Then** `--workers 2 --worker-class gthread`, once step 2 has an answer.

Steps 1 and 3 are genuinely separable now. They were not before the geofence
fix, which is what `CLAUDE.md`'s "treat the pair as one decision" was protecting
against.

---

## How to reproduce

The three benchmarks are straightforward to re-run: copy `routing_system.db` to
a scratch path, set `journal_mode`, then (a) run N reader threads and one writer
for a fixed interval and compare percentiles, (b) hold a write transaction open
for longer than the busy timeout and have a reader arrive mid-hold, (c) same but
with a competing *writer*. The numbers above came from exactly that, and (c) is
the one that reproduces `database is locked`.
