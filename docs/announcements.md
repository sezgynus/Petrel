# Online project announcements

[English](announcements.md) · [Türkçe](announcements_TR.md) · [Documentation](README.md)

Petrel can show messages from the project maintainers on your printer’s display, such as release news and notices that affect Petrel users. Online announcements are enabled by default.

## Receiving and reading announcements

Petrel downloads the public [announcement feed](https://raw.githubusercontent.com/sezgynus/Petrel/master/announcements.json) from the project's `master` branch on GitHub at startup and every five minutes while the feature is enabled. A new announcement with no scheduled time appears after a successful download. Scheduled announcements use the local date and time of the Linux host running Petrel. If the announcement has already been downloaded, it appears when the scheduled time arrives. If Petrel starts or first downloads the announcement after that time, it appears after the download.

Open the bell in the top bar to read an announcement. Select the announcement and press the encoder to mark it as read and remove it from the list. Petrel remembers that choice across restarts, so the same announcement does not reappear while it remains in the feed. Unread announcements also survive restarts.

A new announcement plays the notification chime when **Device → Event sounds → New notification** is enabled. That switch controls the sound. **Device settings → Announcements** controls delivery.

## Network access and privacy

Petrel makes an HTTPS request to GitHub for the same public file on every installation. The request requires no GitHub account and sends no printer data, device identifier, or read status. GitHub receives standard connection information such as the public IP address and request time. The read history stays on the Linux host running Petrel.

## Turning online announcements off

On the display, open **Device settings → Announcements** and turn it off. Petrel stops checking GitHub for announcements and pauses delivery of scheduled announcements. Previously received announcements and their read history are kept. The setting is saved on the Linux host and persists across restarts. Turn it back on in the same menu to resume checks.
