# Arc to Zen

> I built this because I moved my own Arc setup to Zen before Arc shuts down, and found
> that Zen's importer rebuilt almost none of it.

Move your Arc setup into [Zen Browser](https://zen-browser.app): spaces, nested folders,
pinned tabs, Essentials and open tabs. Zen's importer only reads bookmark HTML, so it
rebuilds none of that. This writes Zen's session stores directly.

> **Arc shuts down 22 December 2026.** Export your data before 15 December.
> [Announcement](https://techcrunch.com/2026/10/22/arc-browser-sunsets-december-22-as-the-browser-company-doubles-down-on-dia/)

## Platform support

| | Status | |
| --- | --- | --- |
| **Windows** | Tested, this is what I migrated on | [notes](docs/windows.md) |
| **macOS** | Implemented, untested. Arc's original platform, so probably most of you: reports welcome | [notes](docs/macos.md) |
| **Linux** | Arc never shipped a Linux build. Copy `StorableSidebar.json` off a Mac or Windows machine and pass `--arc` | |

The data model is identical everywhere. Only paths and the way you quit Zen differ, so
non-Windows breakage should be shallow. Issues and fixes welcome.

## Quickstart

Needs Python 3.11+, [uv](https://docs.astral.sh/uv/), and Zen 1.18+ launched at least once.

```sh
uv run arc2zen.py          # preview, writes nothing
# quit Zen from its own menu, then:
uv run arc2zen.py --apply
```

Start Zen. Done.

## What you get

| Arc | Zen |
| --- | --- |
| Space | Space, with its emoji and a theme |
| Pinned tab tree | Pinned tabs, folders nested to any depth |
| Favorites | Essentials, per space |
| Unpinned tabs | Open tabs |
| Space profile | Container, so each space keeps its own cookie jar |

**You will be logged out of everything.** Cookies cannot be migrated between Chromium and
Firefox. Keep your 2FA handy. [Full limitations](docs/limitations.md)

## Two rules

1. **Quit Zen from its menu.** Force killing it registers as a crash and the next launch
   throws your migration away. This is the one mistake that wastes an afternoon.
2. Dry run first. `--apply` is the only path that writes, and it backs up what it replaces
   to `arc2zen-backup-<timestamp>/` inside the profile.

## Docs

- [Limitations](docs/limitations.md): cookies, passwords, history, extensions.
- [How it works](docs/how-it-works.md): Arc and Zen data models, platform independent.
- [macOS notes](docs/macos.md): paths, and why closing the window is not quitting.
- [Windows notes](docs/windows.md): paths, clean shutdown, Arc's MSIX package.
- [Troubleshooting](docs/troubleshooting.md): empty sidebar, and how to diagnose it.

<details>
<summary>Options</summary>

| Flag | Effect |
| --- | --- |
| `--apply` | Write to the profile. Without it, report only. |
| `--no-containers` | One shared container. Single login, but all Essentials show in every space. |
| `--arc PATH` | Point at a specific `StorableSidebar.json`. |
| `--profile PATH` | Point at a specific Zen profile directory. |

By default each space after the first gets its own container, mirroring Arc's per-space
profiles. That is what makes Essentials differ per space, at the cost of signing in
separately per space. A fresh profile has four stock containers; spaces beyond that share
the default one.

</details>

<details>
<summary>Why this exists</summary>

The Browser Company is sunsetting Arc and pointing everyone at Dia. I wanted Zen instead,
migrated my own setup on Windows, and found that almost nothing carried over: three
spaces, their nested folders, their pinned tabs and their open tabs all had to be
reconstructed by writing Zen's session stores by hand.

This is that work, generalised and documented so nobody else has to reverse engineer the
file formats. Since I only had Windows to test on, that is the only platform I can
vouch for. The data model is identical everywhere, so the other platforms should be a
matter of paths; issues and fixes welcome.

</details>

<details>
<summary>Rolling back</summary>

Quit Zen, copy `sessionstore.jsonlz4` and `zen-sessions.jsonlz4` out of
`arc2zen-backup-<timestamp>/` back into the profile root, clear
`sessionstore-backups/`, start Zen.

Arc is only ever read, so it stays a valid source for another attempt.

</details>

## Credits

[rafcabezas/arc2zen](https://github.com/rafcabezas/arc2zen) covers similar ground with a
larger toolset, including a sync mode.

MIT licensed. See [LICENSE](LICENSE).
