# Windows notes

Platform specifics only. The data model is in [how-it-works.md](how-it-works.md).

## Where the files live

### Arc

Arc ships on Windows as an MSIX package, so its data sits under `Packages`, not in a
normal `AppData\Local\Arc` folder:

```
%LOCALAPPDATA%\Packages\TheBrowserCompany.Arc_<hash>\LocalCache\Local\Arc\StorableSidebar.json
```

The hash suffix varies per install, so glob for it rather than hardcoding. Alongside the
live file you will find dated snapshots such as `StorableSidebar.2026-10-24-17-12-43.json`.
Use the undated one.

Resolve the install location from PowerShell:

```powershell
(Get-AppxPackage -Name 'TheBrowserCompany.Arc').InstallLocation
```

### Zen

```
%APPDATA%\zen\profiles.ini
%APPDATA%\zen\installs.ini
%APPDATA%\zen\Profiles\<id>.<name>\
```

Pick the profile from `installs.ini`, not `profiles.ini`. A Zen install commonly has two
profiles, and the `Default=1` flag in `profiles.ini` can point at one the browser never
launches:

```ini
# installs.ini, the one that matters
[F0DC299D809B9700]
Default=Profiles/xxxxxxxx.Default (release)
Locked=1
```

Files of interest inside the profile:

```
zen-sessions.jsonlz4                      Zen's own store
sessionstore.jsonlz4                      written on a clean quit
sessionstore-backups\recovery.jsonlz4     crash-recovery copy, written while running
sessionstore-backups\previous.jsonlz4     last session
prefs.js                                  preferences
containers.json                           container identities
```

## Quitting Zen cleanly

This matters more than anything else on this page.

Zen must be fully stopped before writing, because a running instance holds the session in
memory and overwrites your files on exit. But **how** you stop it decides whether the
migration survives.

```sh
# Correct. Sends a close request, Zen shuts down cleanly.
taskkill /IM zen.exe

# Wrong. Registers as a crash.
taskkill /IM zen.exe /F
```

A forced kill increments `toolkit.startup.recent_crashes` in `prefs.js`, and the next
launch discards the previous session rather than restoring it. Your migrated spaces go
with it. The symptom is an empty sidebar and session files rewritten to zero tabs.

`taskkill` without `/F` prints an error for processes that refuse a polite close:

```
ERROR: The process "zen.exe" with PID 54916 could not be terminated.
Reason: This process can only be terminated forcefully (with /F option).
```

Ignore it. That is a child process declining; the parent still exits. Poll until nothing
is left rather than trusting the exit code:

```sh
taskkill //IM zen.exe
for i in $(seq 1 15); do
  sleep 2
  tasklist | grep -qi zen.exe || break
done
```

Confirm the shutdown was clean before writing:

- `sessionstore.jsonlz4` exists in the profile root. It is only written on a clean quit.
- `prefs.js` has no `toolkit.startup.recent_crashes` line, or it reads `0`.

Quitting from Zen's own menu is always safe and is what the script tells you to do.

## Git Bash notes

These examples assume Git Bash. Two quirks:

- MSYS rewrites arguments that look like paths, so `taskkill /IM` becomes a mangled
  filesystem path. Double the slash: `taskkill //IM zen.exe`.
- The console defaults to cp1252 and chokes on space emoji when printing. Set
  `PYTHONUTF8=1`, otherwise a report containing an emoji dies with:

  ```
  UnicodeEncodeError: 'charmap' codec can't encode character '\U0001f3e2'
  ```

## Reading Arc's assets

Files inside `C:\Program Files\WindowsApps` are not listable with normal tooling because
of their ACLs, but they are readable once you resolve the path through PowerShell. Arc's
icons live in the package's `Assets` folder:

```powershell
$arc = (Get-AppxPackage -Name 'TheBrowserCompany.Arc').InstallLocation
Get-ChildItem (Join-Path $arc 'Assets')
```

`AppList.targetsize-256_altform-unplated.png` is the 256px logo with no plated
background, which is the one to use if you want to build an `.ico`.

## Using Arc's icon for Zen

Shortcuts are easy and reversible. Build a multi-resolution `.ico` with Pillow:

```python
from PIL import Image
img = Image.open("arc-256.png").convert("RGBA")
img.save("arc.ico", sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])
```

Then set it on a shortcut:

```powershell
$sh = New-Object -ComObject WScript.Shell
$lnk = $sh.CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Zen.lnk")
$lnk.TargetPath = 'C:\Program Files\Zen Browser\zen.exe'
$lnk.IconLocation = "$env:LOCALAPPDATA\ZenArcIcon\arc.ico"
$lnk.Save()
```

Two limits worth knowing before you start:

- Shortcuts under `C:\ProgramData\Microsoft\Windows\Start Menu` need admin rights. Create
  copies under `%APPDATA%\Microsoft\Windows\Start Menu\Programs` instead, which needs
  none.
- The icon shown on the window and on the taskbar while the browser runs comes from the
  resources compiled into `zen.exe`, not from the shortcut. Changing it means patching a
  signed binary, which invalidates its Authenticode signature and is overwritten on every
  Zen update.
