# How it works

Everything here is platform independent. For file locations and shell specifics, see
[windows.md](windows.md).

## The short version

Arc keeps its entire sidebar in one JSON file. Zen keeps its sidebar in two compressed
JSON files. Both describe the same shapes: spaces holding folders holding tabs. The
migration reads the first and rewrites the second.

```
StorableSidebar.json  ->  zen-sessions.jsonlz4
                      ->  sessionstore.jsonlz4
```

## Arc's data model

A single file, `StorableSidebar.json`, holds everything.

### Containers

`sidebar.containers` is a list of snapshots. Arc keeps historical copies, so most entries
are stale. The live one is simply the entry with the most items. Picking the first match
instead gives you a sidebar from weeks ago, which is a quiet way to migrate the wrong
data.

```python
usable = [c for c in containers if "spaces" in c and "items" in c]
main = max(usable, key=lambda c: len(c["items"]))
```

### Spaces

`main["spaces"]` alternates between a plain id string and the space object it belongs to,
so filter for dicts. Each space object carries:

- `title`: the display name. `None` for the default personal space, which Arc shows
  without a label.
- `customInfo.iconType.emoji_v2`: the emoji, as a string. `emoji` holds the same thing as
  a codepoint integer.
- `containerIDs`: a flat list in the shape `["pinned", <id>, "unpinned", <id>]`. Decode it
  pairwise.
- `profile`: which Arc profile the space belongs to. Either `{"default": true}` or a
  custom entry naming a directory such as `Profile 1`.

### Items

`main["items"]` is a flat list of every node in every tree. Nodes reference each other by
`parentID` and `childrenIds`; `childrenIds` holds the visual order. Three kinds matter,
distinguished by the key inside `data`:

| `data` key | Meaning | Useful fields |
| --- | --- | --- |
| `tab` | A tab | `savedURL`, `savedTitle` |
| `list` | A folder | `title`, `childrenIds` |
| `itemContainer` | A tree root | `childrenIds` |

Folders nest arbitrarily. Walking a pinned container recursively reproduces the hierarchy.

### Favorites

`main["topAppsContainerIDs"]` alternates a profile descriptor with a container id. These
are Arc's Favorites, the icon row at the top of the sidebar. They are keyed **per profile,
not per space**, so resolve a space's favorites by looking up its `profile` value. Spaces
sharing a profile share favorites.

## Zen's data model

Zen stores state in two mozlz4 files inside the profile.

| File | Role |
| --- | --- |
| `zen-sessions.jsonlz4` | Zen's own store. Authoritative for spaces, folders and pinned tabs on 1.18+. |
| `sessionstore.jsonlz4` | Firefox's session store, written on a clean quit. Holds the same data under `windows[0]`. |

A third file, `sessionstore-backups/recovery.jsonlz4`, is the crash-recovery copy written
every few seconds while running. It sits earlier in the restore fallback chain, so a stale
one overrides what you wrote. Move it aside.

Both files must agree. Tabs are matched across them by `zenSyncId`, and Zen effectively
keeps the intersection: a tab present in only one file is pruned on the next start.

### mozlz4

Not plain lz4. The framing is:

```
bytes 0..8    b"mozLz40\0"
bytes 8..12   uncompressed size, little endian uint32
bytes 12..    raw lz4 block
```

Decompressing needs that size up front:

```python
lz4.block.decompress(raw[12:], uncompressed_size=int.from_bytes(raw[8:12], "little"))
```

### Spaces

```json
{
  "uuid": "{...}",
  "name": "Work",
  "icon": "🏢",
  "theme": { "type": "gradient", "gradientColors": [...], "opacity": 0.62, "texture": 0 },
  "containerTabId": 2,
  "hasCollapsedPinnedTabs": false
}
```

`uuid` includes the braces. `containerTabId` is a Firefox container identity and drives
Essentials filtering.

### Folders

A folder is stored twice, once in `folders[]` and once in `groups[]`, sharing an `id`.
Both must exist or the folder does not render.

```json
// folders[]
{ "id": "...", "name": "Clients", "parentId": null, "workspaceId": "{...}",
  "emptyTabIds": ["..."], "collapsed": true, "pinned": true,
  "splitViewGroup": false, "saveOnWindowClose": true, "prevSiblingInfo": null, "userIcon": "" }

// groups[]
{ "id": "...", "name": "Clients", "color": "zen-workspace-color",
  "collapsed": true, "pinned": true, "splitView": false, "saveOnWindowClose": true }
```

`parentId` gives nesting. Each folder also needs one placeholder tab, an `about:blank` with
`zenIsEmpty: true` and `groupId` set to the folder, whose `zenSyncId` is listed in
`emptyTabIds`. It is the anchor an otherwise empty folder keeps in the tab strip.

### Tabs

One flat array covers every kind. The distinguishing fields:

| Kind | `pinned` | `zenEssential` | `zenWorkspace` | `groupId` |
| --- | --- | --- | --- | --- |
| Essential | `true` | `true` | `null` | absent |
| Pinned, loose | `true` | `false` | space uuid | absent |
| Pinned, in folder | `true` | `false` | space uuid | folder id |
| Open | `false` | `false` | space uuid | absent |
| Folder placeholder | `true` | `false` | space uuid | folder id, plus `zenIsEmpty` |

Essentials carry `zenWorkspace: null` because they are scoped by container, not by space.

Two fields are load bearing:

- **`userContextId` must be an integer.** A string throws in `getEssentialsSection` and
  aborts the entire session restore, leaving an empty sidebar
  ([zen-browser/desktop#15917](https://github.com/zen-browser/desktop/issues/15917)).
- **Entries want `triggeringPrincipal_base64`.** Zen writes `{"3":{}}`, the system
  principal. Entries lacking it can be dropped on restore.

## The mapping

| Arc | Zen |
| --- | --- |
| Space | Entry in `spaces[]` |
| Space title, or a generated name if `None` | `name` |
| `customInfo.iconType.emoji_v2` | `icon` |
| Space profile | `containerTabId` |
| `containerIDs["pinned"]` tree | Pinned tabs plus `folders[]` and `groups[]` |
| `data.list` node | Folder pair, `parentId` from the walk |
| `containerIDs["unpinned"]` children | Tabs with `pinned: false` |
| `topAppsContainerIDs` for the space's profile | Tabs with `zenEssential: true` |
| `savedTitle` | `entries[0].title` |
| `savedURL` | `entries[0].url` |

### Essentials scoping

Zen filters Essentials by the container of the active space. With
`zen.workspaces.container-specific-essentials-enabled` on and distinct `containerTabId`
values per space, each space shows only its own. Without containers, every Essential
appears everywhere.

This mirrors Arc, where favorites are per profile and spaces map onto profiles. The
tradeoff is cookie isolation, so logins do not carry across spaces.

## Why not import an HTML bookmark file

Zen accepts Netscape bookmark HTML, and Firefox's importer writes it into
`places.sqlite`. That store has nothing to do with the sidebar. The result is a bookmark
folder per space and an otherwise untouched Zen. Spaces, pinned tabs, Essentials and open
tabs all live in the session stores described above, which no import path writes.
