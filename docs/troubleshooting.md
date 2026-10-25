# Troubleshooting

## The sidebar is empty after restore

By far the most common outcome when something goes wrong, and it has one dominant cause.

### Zen was force killed

Killing the process registers as a crash. The next launch discards the previous session
instead of restoring it, and your migration goes with it. Zen then rewrites both session
files from its empty in-memory state, so the data is gone from disk too.

Check `prefs.js`:

```sh
grep toolkit.startup.recent_crashes prefs.js
```

A non-zero value means at least one unclean exit. Recover by restoring from the
`arc2zen-backup-<timestamp>/` folder, quitting Zen properly, and running `--apply` again.
On Windows that means `taskkill /IM zen.exe` with no `/F`, or just using Zen's own menu.

### A stale file earlier in the fallback chain

Zen reads the first file it finds, in roughly this order:

```
sessionstore.jsonlz4
sessionstore-backups/recovery.jsonlz4
sessionstore-backups/previous.jsonlz4
```

If you write `sessionstore.jsonlz4` but leave an older `recovery.jsonlz4` in place, which
file wins depends on timing. The script moves the others into the backup folder for this
reason. If you are writing these files by hand, do the same.

### The two stores disagree

`zen-sessions.jsonlz4` and `sessionstore.jsonlz4` are matched per tab by `zenSyncId`, and
Zen keeps the intersection. Writing one and not the other prunes everything on the next
start. Write both, with identical tab objects.

### A string `userContextId`

If a single tab has `"userContextId": "1"` instead of `1`, `getEssentialsSection` throws
and the entire restore aborts
([zen-browser/desktop#15917](https://github.com/zen-browser/desktop/issues/15917)). The
script asserts on this before writing. If you hand-edit, decompress and check.

## How to tell whether Zen accepted the migration

Do not rely on a glance at the sidebar. Let Zen run for a minute, then decompress
`zen-sessions.jsonlz4` and count what it contains. Zen rewrites that file from its live
in-memory model, so if the counts match what the script reported, Zen genuinely parsed and
accepted the state.

```python
import json, lz4.block
from pathlib import Path

raw = Path("zen-sessions.jsonlz4").read_bytes()
size = int.from_bytes(raw[8:12], "little")
d = json.loads(lz4.block.decompress(raw[12:], uncompressed_size=size))

print(len(d["spaces"]), "spaces", len(d["folders"]), "folders", len(d["tabs"]), "tabs")
```

A `tabs` count of 0 is diagnostic rather than merely bad. A fresh window always holds at
least one tab, so zero means the UI failed to initialise rather than that it started
clean.

## Isolate the harness before blaming your data

If a restore comes back empty, resist the urge to start editing the generated session.
Restore your original, pre-migration session files and launch Zen.

- Original restores fine: the harness works, so the problem is in the generated data.
- Original also comes back empty: something about the profile or the procedure is broken,
  and no amount of editing the payload will help.

This single check separates the two cases quickly and is worth doing before any other
debugging.

## Essentials appear in every space

Expected with `--no-containers`, since Essentials are filtered by container.

With containers on, confirm that
`zen.workspaces.container-specific-essentials-enabled` is `true` in `prefs.js` and that
each space has a distinct non-zero `containerTabId`. Toggling the preference needs a
restart.

Per-space Essentials have a history of bugs worth checking against your version:
[#13526](https://github.com/zen-browser/desktop/issues/13526) and
[#12313](https://github.com/zen-browser/desktop/issues/12313).

A related quirk: leaving the preference **off** on 1.23b causes the space name to overlap
the first Essential tile
([#15699](https://github.com/zen-browser/desktop/issues/15699)).

## A preference I set disappeared

`prefs.js` only persists values that differ from the default. Writing a preference that
already matches its default is a no-op and the line vanishes on the next shutdown. If a
line disappears, the value was already in effect.

`browser.startup.page` is the usual source of confusion here. Zen already defaults it to
`3`, so setting it changes nothing.

## Wrong or outdated tabs got migrated

Arc keeps historical snapshots of its sidebar in the same container list. Select the live
one by item count, not by position:

```python
main = max(usable_containers, key=lambda c: len(c["items"]))
```

Taking the first match can migrate a sidebar from weeks ago.

## Rolling back

Quit Zen, then copy `sessionstore.jsonlz4` and `zen-sessions.jsonlz4` out of
`arc2zen-backup-<timestamp>/` back into the profile root, and delete anything left in
`sessionstore-backups/`. Start Zen.

Arc is never modified, so its data remains a valid source for another attempt.
