# Notification infrastructure

PetrelDisplay owns an initially empty, in-memory NotificationStore. Features
can publish Notification records without calling panel methods. Identity is
the pair (source, key); use a stable key for each active condition, and a new
key for each separate one-shot event. Identical publications are no-ops.
New entries appear first. Unresolved conditions can be published again by
their owning feature when it initializes.

- DISMISSIBLE entries without an action leave the panel when pressed.
- UNTIL_RESOLVED entries remain until their owner calls resolve(source, key).
  A press on an entry without an action leaves its state intact.
- Actions are optional identifiers mapped to UI-thread handlers in
  PetrelDisplay.notification_actions. Handlers receive the selected record.
  Return False if a dismissible action could not be accepted. A persistent
  entry is resolved separately by its owner when its condition clears.

The bell precedes the first encoder target on Home, Info and the shared
Prepare, Control, Move, Temperature and Motion menus. Rotate one step back
from the first target to focus it. The popup keeps the originating screen,
starts with Back selected and scrolls all rows, including read-only ones.
The bell is hidden and absent from the encoder order whenever the feed is
empty. No producers, action registrations or network checks are installed.

Both panel families use the shared icon library for the bell, badge and row
glyphs. The badge count uses panel text. Cached rendering updates the
changed control, rows and scroll gutter. Closing restores the menu underneath
the overlay through the existing view renderer.
