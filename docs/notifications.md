# Notification infrastructure

PetrelDisplay owns the NotificationStore. Features can publish Notification
records without calling panel methods. Identity is
the pair (source, key); use a stable key for each active condition, and a new
key for each separate one-shot event. Identical publications are no-ops.
New entries appear first. The persistence field defaults to PERSISTENT.
These records are restored from Petrel/notifications.json under XDG_CONFIG_HOME
(normally ~/.config) after a service restart or power cycle. VOLATILE records
only live in memory. Both policies can be combined with either retention
policy below. Dismissal and resolution update the on-disk copy of a persistent
record before it leaves the live feed. A storage failure leaves the live
persistent record unchanged.

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
