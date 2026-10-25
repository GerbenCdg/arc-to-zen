# macOS notes

Platform specifics only. The data model is in [how-it-works.md](how-it-works.md).

> **Untested.** The paths below are implemented in the script and match where Arc and Zen
> document their data, but I migrated on Windows and have no Mac to verify against. If you
> run it, an issue confirming success or failure is genuinely useful.

macOS is Arc's original platform, so this is likely the common case. The data model is
identical to Windows; only the locations and the way you quit differ.

## Where the files live

### Arc

```
~/Library/Application Support/Arc/StorableSidebar.json
```

No package indirection, unlike Windows. Alongside it sit dated snapshots such as
`StorableSidebar.2026-10-24-17-12-43.json`. Use the undated one.

`~/Library` is hidden in Finder. Open it with `Cmd+Shift+G` or reach it from a terminal,
which is what the script does.

### Zen

```
~/Library/Application Support/zen/profiles.ini
~/Library/Application Support/zen/installs.ini
~/Library/Application Support/zen/Profiles/<id>.<name>/
```

Pick the profile from `installs.ini`, not `profiles.ini`. A Zen install commonly has more
than one profile, and the `Default=1` flag in `profiles.ini` can point at one the browser
never launches.

Files of interest inside the profile are the same as everywhere else:

```
zen-sessions.jsonlz4                      Zen's own store
sessionstore.jsonlz4                      written on a clean quit
sessionstore-backups/recovery.jsonlz4     crash-recovery copy, written while running
prefs.js                                  preferences
containers.json                           container identities
```

## Quitting Zen cleanly

This matters more than anything else on this page, and macOS makes it easier to get wrong
than Windows does.

**Closing the window is not quitting.** On macOS the application keeps running with no
window, it still holds the profile, and it will overwrite your migrated files when it
finally exits. Use `Cmd+Q`, or Zen's menu, and confirm nothing is left:

```sh
pgrep -x zen || echo "stopped"
```

Do not `kill -9`. A forced kill registers as a crash, and the next launch discards the
previous session rather than restoring it, taking the migration with it. The symptom is an
empty sidebar. See [troubleshooting.md](troubleshooting.md).

Confirm the shutdown was clean before writing:

- `sessionstore.jsonlz4` exists in the profile root. It is only written on a clean quit.
- `prefs.js` has no `toolkit.startup.recent_crashes` line, or it reads `0`.

## Running the script

```sh
uv run arc2zen.py
# Cmd+Q Zen, then:
uv run arc2zen.py --apply
```

If auto-detection misses, pass the paths explicitly. Quote them, since the profile
directory name contains a space:

```sh
uv run arc2zen.py --apply \
  --arc ~/Library/Application\ Support/Arc/StorableSidebar.json \
  --profile ~/Library/Application\ Support/zen/Profiles/xxxxxxxx.Default\ \(release\)
```

## Terminal permissions

Reading `~/Library/Application Support` normally needs no special permission. If your
terminal returns "Operation not permitted", grant it Full Disk Access under System
Settings, Privacy and Security, then restart the terminal.
