# Limitations

This tool migrates the **structure** of your browsing: spaces, folders, tabs and their
titles. It does not migrate the state that makes those tabs useful the moment they open.

## Cookies and sessions

The gap you will feel first. **You will be logged out of everything** and will have to
sign in again on every site, in every space.

Arc on Windows is Chromium based and keeps cookies in a SQLite database encrypted with a
key that DPAPI binds to your Windows account. Zen is Firefox based and uses a different
database, a different schema and different encryption. There is no supported path between
the two and no safe way to translate one into the other. Anything claiming otherwise is
reimplementing both browsers' crypto, which is not something to trust with live session
tokens.

Plan for this **before** Arc shuts down:

- Sites behind two-factor authentication need a full sign-in. Have your second factor
  ready.
- "Remember this device" trust is per browser and resets.
- Anything you are still logged into only because the session never expired, and whose
  password you do not actually remember, should be recovered while Arc still runs.

With containers enabled this applies per space: signing in inside Work does not sign you
in inside Personal. That matches how Arc's per-space profiles already behaved.

## Everything else

| Not covered | Where to get it instead |
| --- | --- |
| Passwords | Export from Arc, import into Zen. Zen also reads a Chromium password CSV. |
| History | Firefox's own import, or accept the loss. |
| Extensions | Reinstall from addons.mozilla.org. Chrome extensions are not compatible. |
| Scroll position, form state | Not recoverable. Tabs restore at the top of the page. |
| Boosts, Easels, Split View layouts | No Zen equivalent. |

## Deadlines

| Date | What happens |
| --- | --- |
| 23 November 2026 | Arc Search loses AI features and sync. Desktop starts showing sunset reminders. |
| 15 December 2026 | Last day to request a copy of your Arc account data, or ask for deletion. |
| 22 December 2026 | Arc stops working. Accounts deactivated, data deleted within 30 days. |

Recent Arc builds include an export option. Use it before the December dates, since after
the shutdown the browser can no longer open your Spaces, tabs or locally stored data.
