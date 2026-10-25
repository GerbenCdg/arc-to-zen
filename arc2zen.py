# /// script
# requires-python = ">=3.11"
# dependencies = ["lz4"]
# ///
"""Migrate Arc spaces, folders, pinned tabs and open tabs into Zen Browser.

Reads Arc's StorableSidebar.json and rewrites Zen's session stores so that every Arc
space becomes a Zen space with the same folders, pinned tabs, Essentials and open tabs.

Dry run by default. Nothing is written without --apply, and Zen must be fully quit
through its own menu (a force kill corrupts the clean-shutdown handshake Zen relies on).

    uv run arc2zen.py                 # inspect and preview
    uv run arc2zen.py --apply         # write into the Zen profile

See docs/how-it-works.md for the data model and docs/troubleshooting.md when a run
produces an empty sidebar.
"""

from __future__ import annotations

import argparse
import configparser
import json
import os
import platform
import shutil
import sys
import time
import uuid
from pathlib import Path

import lz4.block

MAGIC = b"mozLz40\0"

# Zen reuses Firefox's container identities. 0 is the default (no container); 1 to 4 ship
# with a stock profile. Spaces beyond that fall back to sharing the default container.
STOCK_CONTAINER_IDS = [1, 2, 3, 4]

PALETTE = [
    {"c": [139, 107, 250], "algorithm": "floating", "lightness": "70", "opacity": 0.524},
    {"c": [87, 105, 219], "algorithm": "complementary", "lightness": "60", "opacity": 0.624},
    {"c": [89, 196, 126], "algorithm": "floating", "lightness": "60", "opacity": 0.556},
    {"c": [233, 134, 92], "algorithm": "complementary", "lightness": "65", "opacity": 0.58},
    {"c": [214, 93, 151], "algorithm": "floating", "lightness": "65", "opacity": 0.58},
]


# --------------------------------------------------------------------- mozlz4
def read_mozlz4(path: Path):
    raw = path.read_bytes()
    if raw[:8] != MAGIC:
        raise ValueError(f"{path} is not a mozlz4 file (magic {raw[:8]!r})")
    size = int.from_bytes(raw[8:12], "little")
    return json.loads(lz4.block.decompress(raw[12:], uncompressed_size=size))


def write_mozlz4(path: Path, obj) -> None:
    data = json.dumps(obj, separators=(",", ":")).encode("utf-8")
    payload = lz4.block.compress(data, store_size=False)
    path.write_bytes(MAGIC + len(data).to_bytes(4, "little") + payload)


# ------------------------------------------------------------------ discovery
def arc_sidebar_path() -> Path:
    """Locate Arc's StorableSidebar.json for the current platform."""
    if platform.system() == "Windows":
        base = Path(os.environ["LOCALAPPDATA"]) / "Packages"
        for pkg in base.glob("TheBrowserCompany.Arc_*"):
            candidate = pkg / "LocalCache" / "Local" / "Arc" / "StorableSidebar.json"
            if candidate.exists():
                return candidate
    else:  # macOS
        candidate = Path.home() / "Library/Application Support/Arc/StorableSidebar.json"
        if candidate.exists():
            return candidate
    raise SystemExit("Arc data not found. Is Arc installed for this user?")


def zen_profile_dir() -> Path:
    """Resolve the Zen profile the installed build actually launches."""
    if platform.system() == "Windows":
        root = Path(os.environ["APPDATA"]) / "zen"
    elif platform.system() == "Darwin":
        root = Path.home() / "Library/Application Support/zen"
    else:
        root = Path.home() / ".zen"
    if not root.exists():
        raise SystemExit(f"Zen data directory not found at {root}. Run Zen once first.")

    # installs.ini names the profile tied to this installation and wins over the
    # Default=1 flag in profiles.ini, which can point at an unused profile.
    installs = root / "installs.ini"
    if installs.exists():
        cfg = configparser.ConfigParser()
        cfg.read(installs, encoding="utf-8")
        for section in cfg.sections():
            rel = cfg[section].get("Default")
            if rel and (root / rel).exists():
                return root / rel

    profiles = root / "profiles.ini"
    if profiles.exists():
        cfg = configparser.ConfigParser()
        cfg.read(profiles, encoding="utf-8")
        for section in cfg.sections():
            if section.startswith("Profile") and cfg[section].get("Default") == "1":
                rel = cfg[section].get("Path")
                if rel and (root / rel).exists():
                    return root / rel
    raise SystemExit("Could not determine which Zen profile to use.")


def zen_is_running(profile: Path) -> bool:
    """A live Zen holds the profile lock; writing underneath it loses the changes."""
    if platform.system() == "Windows":
        out = os.popen("tasklist").read().lower()
        return "zen.exe" in out
    return bool(os.popen("pgrep -x zen 2>/dev/null").read().strip())


# ------------------------------------------------------------------ Arc model
def load_arc(path: Path):
    """Return (items_by_id, spaces, topapps_by_profile) from Arc's sidebar."""
    data = json.loads(path.read_text(encoding="utf-8"))
    containers = data["sidebar"]["containers"]
    # Arc keeps historical container snapshots; the live one holds the most items.
    usable = [c for c in containers if isinstance(c, dict) and "spaces" in c and "items" in c]
    if not usable:
        raise SystemExit("No usable container found in StorableSidebar.json")
    main = max(usable, key=lambda c: len(c["items"]))

    items = {it["id"]: it for it in main["items"] if isinstance(it, dict)}
    spaces = [s for s in main["spaces"] if isinstance(s, dict)]

    tops = main.get("topAppsContainerIDs", [])
    topapps: dict[str, str] = {}
    for i in range(0, len(tops) - 1, 2):
        desc, cid = tops[i], tops[i + 1]
        if isinstance(desc, dict) and isinstance(cid, str):
            if desc.get("default"):
                topapps["default"] = cid
            else:
                name = desc.get("custom", {}).get("_0", {}).get("directoryBasename")
                if name:
                    topapps[name] = cid
    return items, spaces, topapps


def decode_pairs(flat: list) -> dict:
    """Arc stores ['pinned', <id>, 'unpinned', <id>] as a flat list."""
    return {
        flat[i]: flat[i + 1]
        for i in range(0, len(flat) - 1, 2)
        if isinstance(flat[i], str) and isinstance(flat[i + 1], str)
    }


def arc_profile_key(space: dict) -> str:
    prof = space.get("profile")
    if isinstance(prof, dict) and not prof.get("default"):
        return prof.get("custom", {}).get("_0", {}).get("directoryBasename", "default")
    return "default"


def arc_space_name(space: dict, index: int) -> str:
    title = space.get("title")
    return title.strip() if isinstance(title, str) and title.strip() else f"Space {index + 1}"


def arc_space_icon(space: dict) -> str:
    icon = space.get("customInfo", {}).get("iconType", {})
    emoji = icon.get("emoji_v2")
    if isinstance(emoji, str) and emoji:
        return emoji
    code = icon.get("emoji")
    if isinstance(code, int):
        return chr(code)
    return ""


def item_kind(item: dict) -> str:
    data = item.get("data", {})
    if "tab" in data:
        return "tab"
    if "list" in data:
        return "folder"
    if "itemContainer" in data:
        return "container"
    return "unknown"


# ------------------------------------------------------------------ Zen model
class IdFactory:
    """Zen ids look like '<epoch_ms>-<n>'; sync ids embed a uuid."""

    def __init__(self) -> None:
        self.base = int(time.time() * 1000)
        self.n = 0

    def next(self) -> str:
        self.n += 1
        return f"{self.base + self.n}-{self.n}"

    def sync(self) -> str:
        self.n += 1
        return f"{self.base + self.n}-{uuid.uuid4()}"


class SessionBuilder:
    def __init__(self, items: dict, ids: IdFactory) -> None:
        self.items = items
        self.ids = ids
        self.tabs: list[dict] = []
        self.folders: list[dict] = []
        self.groups: list[dict] = []
        self.spaces: list[dict] = []

    # -- tabs ---------------------------------------------------------------
    def make_tab(self, url, title, *, workspace, ctx, pinned, essential=False,
                 group_id=None, empty=False):
        # Entries without a serialized triggering principal can be dropped on restore.
        # '{"3":{}}' is the system principal, which is what Zen writes itself.
        entry = {"url": url, "triggeringPrincipal_base64": '{"3":{}}'}
        if title:
            entry["title"] = title
        tab = {
            "entries": [entry],
            "lastAccessed": self.ids.base,
            "pinned": pinned,
            "hidden": False,
            "zenWorkspace": None if essential else workspace,
            "zenSyncId": self.ids.sync(),
            "zenEssential": essential,
            "zenDefaultUserContextId": "true" if not empty else None,
            "zenPinnedIcon": None,
            "zenIsEmpty": empty,
            "zenHasStaticIcon": False,
            "zenGlanceId": None,
            "zenIsGlance": False,
            "zenLiveFolderItemId": None,
            "searchMode": None,
            # Must stay an int. A string here throws in getEssentialsSection and
            # aborts the whole session restore (zen-browser/desktop#15917).
            "userContextId": int(ctx),
            "attributes": {},
            "index": 1,
            "userTypedValue": "",
            "userTypedClear": 0,
            "image": None,
        }
        if group_id:
            tab["groupId"] = group_id
        if pinned:
            tab["_zenPinnedInitialState"] = {"entry": {"url": url}, "image": None}
        self.tabs.append(tab)
        return tab

    # -- folders ------------------------------------------------------------
    def add_folder(self, name, *, workspace, parent_id, ctx):
        """Zen models a folder twice: an entry in folders[] and one in groups[]."""
        folder_id = self.ids.next()
        folder = {
            "pinned": True,
            "splitViewGroup": False,
            "id": folder_id,
            "name": name or "Folder",
            "collapsed": True,
            "saveOnWindowClose": True,
            "parentId": parent_id,
            "prevSiblingInfo": None,
            "emptyTabIds": [],
            "userIcon": "",
            "workspaceId": workspace,
        }
        self.folders.append(folder)
        self.groups.append({
            "pinned": True,
            "splitView": False,
            "id": folder_id,
            "name": name or "Folder",
            "color": "zen-workspace-color",
            "collapsed": True,
            "saveOnWindowClose": True,
        })
        # Every folder carries one hidden placeholder tab so an empty folder still
        # has an anchor in the tab strip.
        placeholder = self.make_tab("about:blank", None, workspace=workspace, ctx=ctx,
                                    pinned=True, group_id=folder_id, empty=True)
        folder["emptyTabIds"] = [placeholder["zenSyncId"]]
        return folder_id

    # -- walkers ------------------------------------------------------------
    def walk_pinned(self, container_id, *, workspace, ctx, parent_folder=None):
        node = self.items.get(container_id)
        if not node:
            return
        for child_id in node.get("childrenIds", []):
            child = self.items.get(child_id)
            if not child:
                continue
            kind = item_kind(child)
            if kind == "tab":
                tab = child["data"]["tab"]
                if tab.get("savedURL"):
                    self.make_tab(tab["savedURL"], tab.get("savedTitle"),
                                  workspace=workspace, ctx=ctx, pinned=True,
                                  group_id=parent_folder)
            elif kind in ("folder", "container"):
                folder_id = self.add_folder(child.get("title"), workspace=workspace,
                                            parent_id=parent_folder, ctx=ctx)
                self.walk_pinned(child_id, workspace=workspace, ctx=ctx,
                                 parent_folder=folder_id)

    def walk_flat(self, container_id, *, workspace, ctx, pinned, essential):
        """Open tabs and Essentials are flat lists, with no folder nesting."""
        node = self.items.get(container_id)
        if not node:
            return
        for child_id in node.get("childrenIds", []):
            child = self.items.get(child_id)
            if not child or item_kind(child) != "tab":
                continue
            tab = child["data"]["tab"]
            if tab.get("savedURL"):
                self.make_tab(tab["savedURL"], tab.get("savedTitle"),
                              workspace=workspace, ctx=ctx, pinned=pinned,
                              essential=essential)


# ------------------------------------------------------------------- mapping
def plan_spaces(arc_spaces, existing_spaces, use_containers: bool):
    """Map each Arc space to a Zen space, reusing existing uuids when names match."""
    by_name = {s.get("name"): s for s in existing_spaces}
    plan, used_ctx = [], set()
    for index, space in enumerate(arc_spaces):
        name = arc_space_name(space, index)
        existing = by_name.get(name)
        if existing:
            space_uuid = existing["uuid"]
            ctx = existing.get("containerTabId", 0)
        else:
            space_uuid = "{" + str(uuid.uuid4()) + "}"
            ctx = 0
        if use_containers and index > 0 and ctx == 0:
            free = [c for c in STOCK_CONTAINER_IDS if c not in used_ctx]
            ctx = free[0] if free else 0
        used_ctx.add(ctx)
        plan.append({
            "arc_id": space["id"],
            "name": name,
            "icon": arc_space_icon(space),
            "uuid": space_uuid,
            "containerTabId": int(ctx) if use_containers else 0,
            "theme": PALETTE[index % len(PALETTE)],
        })
    return plan


def build(arc_path: Path, existing_spaces: list, use_containers: bool):
    items, arc_spaces, topapps = load_arc(arc_path)
    ids = IdFactory()
    builder = SessionBuilder(items, ids)
    plan = plan_spaces(arc_spaces, existing_spaces, use_containers)
    by_arc_id = {p["arc_id"]: p for p in plan}
    stats: dict[str, dict] = {}

    # Essentials lead the tab array, matching how Zen orders its own file.
    for space in arc_spaces:
        target = by_arc_id.get(space["id"])
        if not target:
            continue
        container = topapps.get(arc_profile_key(space))
        before = len(builder.tabs)
        if container:
            builder.walk_flat(container, workspace=target["uuid"],
                              ctx=target["containerTabId"], pinned=True, essential=True)
        stats.setdefault(target["name"], {})["essentials"] = len(builder.tabs) - before

    for space in arc_spaces:
        target = by_arc_id.get(space["id"])
        if not target:
            continue
        containers = decode_pairs(space.get("containerIDs", []))
        ctx = target["containerTabId"]
        row = stats.setdefault(target["name"], {})

        before_tabs, before_folders = len(builder.tabs), len(builder.folders)
        if containers.get("pinned"):
            builder.walk_pinned(containers["pinned"], workspace=target["uuid"], ctx=ctx)
        row["folders"] = len(builder.folders) - before_folders
        row["pinned"] = len(builder.tabs) - before_tabs - row["folders"]

        before_tabs = len(builder.tabs)
        if containers.get("unpinned"):
            builder.walk_flat(containers["unpinned"], workspace=target["uuid"], ctx=ctx,
                              pinned=False, essential=False)
        row["open"] = len(builder.tabs) - before_tabs

        theme = target["theme"]
        entry = {
            "uuid": target["uuid"],
            "name": target["name"],
            "theme": {
                "type": "gradient",
                "gradientColors": [{
                    "c": theme["c"],
                    "isCustom": False,
                    "algorithm": theme["algorithm"],
                    "isPrimary": True,
                    "lightness": theme["lightness"],
                    "position": {"x": 150, "y": 150},
                    "type": "explicit-lightness",
                }],
                "opacity": theme["opacity"],
                "texture": 0,
            },
            "containerTabId": ctx,
            "hasCollapsedPinnedTabs": False,
        }
        if target["icon"]:
            entry["icon"] = target["icon"]
        builder.spaces.append(entry)

    return builder, plan, stats


# --------------------------------------------------------------------- apply
def apply(builder: SessionBuilder, profile: Path, template: dict, active_uuid: str):
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = profile / f"arc2zen-backup-{stamp}"
    backup.mkdir(exist_ok=True)

    clean_path = profile / "sessionstore.jsonlz4"
    zen_path = profile / "zen-sessions.jsonlz4"
    for path in (clean_path, zen_path):
        if path.exists():
            shutil.copy2(path, backup / path.name)

    first_open = next((t for t in builder.tabs if not t["pinned"]), None)
    if first_open:
        first_open["_zenIsActiveTab"] = True

    window = template["windows"][0]
    window["tabs"] = builder.tabs
    window["folders"] = builder.folders
    window["groups"] = builder.groups
    window["spaces"] = builder.spaces
    window["splitViewData"] = []
    window["splitViews"] = []
    window["closedGroups"] = []
    window["_closedTabs"] = []
    window["activeZenSpace"] = active_uuid
    window["workspaceID"] = active_uuid
    window["selected"] = (builder.tabs.index(first_open) + 1) if first_open else 1
    template["_closedWindows"] = []
    template["savedGroups"] = []
    template["selectedWindow"] = 1

    zen_state = read_mozlz4(zen_path) if zen_path.exists() else {}
    zen_state["tabs"] = builder.tabs
    zen_state["folders"] = builder.folders
    zen_state["groups"] = builder.groups
    zen_state["spaces"] = builder.spaces
    zen_state["splitViewData"] = []
    zen_state["lastCollected"] = builder.ids.base

    write_mozlz4(zen_path, zen_state)
    write_mozlz4(clean_path, template)
    # Anything earlier in the restore fallback chain would otherwise win.
    for name in ("recovery.jsonlz4", "previous.jsonlz4", "recovery.baklz4"):
        stale = profile / "sessionstore-backups" / name
        if stale.exists():
            shutil.move(str(stale), str(backup / name))
    return backup


def session_template(profile: Path) -> dict:
    """Prefer the clean-shutdown file; its closed-window markers are expected by Zen."""
    for rel in ("sessionstore.jsonlz4", "sessionstore-backups/recovery.jsonlz4"):
        path = profile / rel
        if path.exists():
            return read_mozlz4(path)
    raise SystemExit("No Zen session file found. Launch Zen once and quit it cleanly.")


# ---------------------------------------------------------------------- main
def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate Arc spaces into Zen Browser.")
    parser.add_argument("--apply", action="store_true",
                        help="write into the Zen profile (default is a dry run)")
    parser.add_argument("--no-containers", action="store_true",
                        help="put every space in the default container and share Essentials")
    parser.add_argument("--arc", type=Path, help="path to StorableSidebar.json")
    parser.add_argument("--profile", type=Path, help="path to the Zen profile directory")
    args = parser.parse_args()

    arc_path = args.arc or arc_sidebar_path()
    profile = args.profile or zen_profile_dir()
    use_containers = not args.no_containers

    print(f"Arc sidebar : {arc_path}")
    print(f"Zen profile : {profile}")

    template = session_template(profile)
    existing = template["windows"][0].get("spaces", []) if template.get("windows") else []

    builder, plan, stats = build(arc_path, existing, use_containers)

    print()
    print(f"{'space':<22}{'icon':<6}{'ctx':>4}{'essentials':>12}{'folders':>9}{'pinned':>8}{'open':>6}")
    for target in plan:
        row = stats.get(target["name"], {})
        print(f"{target['name'][:21]:<22}{target['icon'] or '-':<6}{target['containerTabId']:>4}"
              f"{row.get('essentials', 0):>12}{row.get('folders', 0):>9}"
              f"{row.get('pinned', 0):>8}{row.get('open', 0):>6}")

    placeholders = sum(1 for t in builder.tabs if t["zenIsEmpty"])
    print(f"\n{len(builder.spaces)} spaces, {len(builder.folders)} folders, "
          f"{len(builder.tabs)} tab records "
          f"({sum(1 for t in builder.tabs if t['zenEssential'])} essential, "
          f"{sum(1 for t in builder.tabs if t['pinned'] and not t['zenEssential'] and not t['zenIsEmpty'])} pinned, "
          f"{placeholders} folder placeholders, "
          f"{sum(1 for t in builder.tabs if not t['pinned'])} open)")

    bad = [t for t in builder.tabs if not isinstance(t["userContextId"], int)]
    if bad:
        raise SystemExit(f"refusing to write: {len(bad)} tabs have a non-int userContextId")

    if not args.apply:
        print("\nDry run. Re-run with --apply to write. Quit Zen first.")
        return 0

    if zen_is_running(profile):
        print("\nZen is running. Quit it from its own menu, then re-run with --apply.",
              file=sys.stderr)
        print("Do not force kill it: that registers as a crash and the next launch "
              "discards the session.", file=sys.stderr)
        return 1

    backup = apply(builder, profile, template, plan[0]["uuid"])
    print(f"\nWritten. Previous session files copied to:\n  {backup}")
    print("Start Zen normally to verify.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
