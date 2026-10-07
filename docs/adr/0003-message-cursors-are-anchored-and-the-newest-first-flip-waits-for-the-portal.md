# Message cursors are anchored, and the newest-first flip waits for the portal

A message cursor is a message id. `before` returns the page adjacent to that message on the older side and `after` the page adjacent on the newer side, in whichever order was requested, executed as a `(created_at, id)` keyset after one primary-key lookup. The read requires `order` explicitly; the HTTP route keeps today's oldest-first default until the portal's reader is changed to open at the newest messages, at which point the default flips in one place.

Today's route compares raw ids against an oldest-first list, so `before=<id>` returns the channel's oldest page instead of the page next to the cursor. That is the "Load older loads newer" defect. The portal currently sends only `after`, for which anchored and raw semantics coincide, so this change is invisible until the flip.

## Considered options

- **Flip the default to newest-first in the same change and edit the portal pages with it.** Rejected: it couples a backend change to Svelte edits that belong to the portal rework's first phase.
- **Keep raw id comparison and fix only the ordering.** Rejected: `before` would still return the far end of the list.

## Consequences

- The response keeps `before_id` and `after_id`, set to the oldest and newest id on the page, so they keep meaning "pass this as `before` / `after`" after the flip.
- An unknown cursor id falls back to the first page rather than erroring.
- Every ORDER BY in the module ends in a tie-break that makes the order total: the primary key, or for a grouped read (such as `reactions`, grouped by emoji name) the group key, so pages are stable when timestamps or counts collide.
- `has_more` points away from the cursor: after `before` it says whether older messages remain, after `after` whether newer ones do, and on a first page whether more follow in the requested order. With both cursors it says whether older messages remain that are still newer than `after`.
