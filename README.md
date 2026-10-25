# Arc to Zen

Migrate [Arc](https://arc.net) spaces into [Zen Browser](https://zen-browser.app), with
folders, pinned tabs, Essentials and open tabs intact.

Zen's built-in import only reads an HTML bookmark file. That gives you a bookmark folder
per space and nothing else: no spaces, no pinned tabs, no open tabs. This project writes
Zen's session stores directly instead, so the sidebar comes out looking like Arc's.

## Why this exists

On 22 October 2026, The Browser Company
[announced that Arc is being sunset](https://techcrunch.com/2026/10/22/arc-browser-sunsets-december-22-as-the-browser-company-doubles-down-on-dia/).
Arc stops working entirely on 22 December 2026, accounts are deactivated, and after that
date Spaces, tabs and locally stored browsing data are no longer reachable from the
browser. The official migration path points at Dia.

I wanted Zen instead, so I migrated my own setup and wrote down what it took. Zen's
importer handled almost none of it: three spaces, their nested folders, their pinned tabs
and their open tabs all had to be reconstructed by writing Zen's session stores by hand.
This repository is that work, generalised and documented so the next person does not have
to reverse engineer the file formats.

If you are leaving Arc for Zen before December, this should save you a weekend.

## What gets migrated

| Arc | Zen |
| --- | --- |
| Space | Space, with its emoji icon and a gradient theme |
| Space profile | Container, so each space keeps its own cookie jar |
| Pinned tab tree | Pinned tabs, with folders nested to any depth |
| Favorites (top apps) | Essentials, scoped per space when containers are on |
| Unpinned tabs | Open tabs in the matching space |
| Page titles | Preserved, read from Arc's `savedTitle` |

## Limitations

This tool migrates the **structure** of your browsing: spaces, folders, tabs and their
titles. It does not migrate the state that makes those tabs useful on first open.

### Cookies and sessions are not migrated

This is the gap you will feel first. **You will be logged out of everything** and will
have to sign in again on every site, in every space.

Arc on Windows is Chromium based and stores cookies in a SQLite database encrypted with a
key that DPAPI binds to your Windows account. Zen is Firefox based and uses a different
database with a different schema and different encryption. There is no supported path
between the two, and no safe way to translate one into the other. Anything claiming
otherwise is reimplementing both browsers' crypto, which is not something to trust with
live session tokens.

Practical consequences, worth planning for before Arc shuts down:

- Sites protected by two-factor authentication need a full sign-in, so have your second
  factor available.
- "Remember this device" trust is per browser and resets.
- Anything you are only still logged into because the session never expired, and whose
  password you do not actually remember, should be recovered **while Arc still runs**.

If containers are enabled, this applies per space: signing in inside Work does not sign
you in inside Personal. That matches how Arc's per-space profiles already behaved.

### Also not migrated

| Not covered | Where to get it instead |
| --- | --- |
| Passwords | Export from Arc, then import into Zen. Zen can also read a Chromium password CSV. |
| History | Firefox's own import, or accept the loss. |
| Extensions | Reinstall from addons.mozilla.org. Chrome extensions are not compatible. |
| Open tab scroll position and form state | Not recoverable. Tabs restore at the top of the page. |
| Arc Boosts, Easels, Split View layouts | No Zen equivalent. |

Export your Arc data before 15 December 2026, which is the last day The Browser Company
accepts data requests. Recent Arc builds include an export option.

## Requirements

- Zen Browser 1.18 or newer. Tested on 1.23.4b.
- Arc installed, with the data still on disk. Arc does not need to run.
- Python 3.11+. [uv](https://docs.astral.sh/uv/) is the easiest way to get the `lz4`
  dependency, and the script carries a PEP 723 header so `uv run` resolves it for you.

## Usage

Launch Zen once and quit it, so the profile has a session file to use as a template.

```sh
# Preview. Reads Arc, writes nothing.
uv run arc2zen.py

# Quit Zen from its own menu first, then:
uv run arc2zen.py --apply
```

Start Zen normally to verify.

The preview prints one row per space:

```
space                 icon   ctx  essentials  folders  pinned  open
Personal              planet   0           5        0       7     6
Work                  office   2          12       22      92    55
Dev                   laptop   3           1        1      15     1
```

### Options

| Flag | Effect |
| --- | --- |
| `--apply` | Write to the profile. Without it the script only reports. |
| `--no-containers` | Put every space in the default container. One shared login, but all Essentials show in every space. |
| `--arc PATH` | Point at a specific `StorableSidebar.json`. |
| `--profile PATH` | Point at a specific Zen profile directory. |

### Containers and logins

By default each space after the first gets its own Firefox container, mirroring Arc's
per-space profiles. This is what makes Essentials differ per space. The cost is that
cookies are isolated, so you sign in to each service separately per space, exactly as Arc
required. Use `--no-containers` if you would rather sign in once.

Only four stock container identities exist in a fresh profile. Spaces beyond that fall
back to the default container and share Essentials with it.

## Safety

- Dry run by default. `--apply` is the only path that writes.
- Every file it replaces is copied to `arc2zen-backup-<timestamp>/` inside the profile
  first. To roll back, quit Zen and copy `sessionstore.jsonlz4` and
  `zen-sessions.jsonlz4` back out of that folder.
- Arc's own data is only ever read.
- The script refuses to run with `--apply` while Zen is running.

**Quit Zen through its own menu.** Killing the process registers as a crash and the next
launch throws the session away, migration included. This is the single most common way to
end up with an empty sidebar. See [docs/troubleshooting.md](docs/troubleshooting.md).

## Documentation

- [How it works](docs/how-it-works.md): Arc's and Zen's data models, and the mapping
  between them. Platform independent.
- [Windows notes](docs/windows.md): paths, quitting Zen cleanly, and reading Arc's data
  out of its MSIX package.
- [Troubleshooting](docs/troubleshooting.md): empty sidebar after restore, and the
  failure modes worth knowing about.

## Credits

[rafcabezas/arc2zen](https://github.com/rafcabezas/arc2zen) covers the same ground with a
larger toolset, including a sync mode. Worth a look if this one does not fit.

## License

MIT. See [LICENSE](LICENSE).
