"""Existing PrinterData methods grouped by responsibility."""
import time
from petrel.moonraker.client import MoonrakerError


class SpoolmanPrinterMixin:
    @staticmethod
    def _spool_remaining_percent(spool):
        from petrel.features.spoolman.tags import remaining_percent
        return remaining_percent(spool)

    def _poll_spoolman_percentages(self, spool_ids):
        now = time.monotonic()
        changed = False
        valid_ids = {int(sid) for sid in spool_ids
                     if isinstance(sid, (int, float)) and int(sid) > 0}

        for sid, future in list(self._spoolman_futures.items()):
            if not future.done():
                continue
            del self._spoolman_futures[sid]
            self._spoolman_refresh_at[sid] = now + 15.0
            try:
                response = future.result()
                spool = response['result']
                percent = self._spool_remaining_percent(spool)
            except (KeyError, TypeError, ValueError, MoonrakerError):
                percent = None
            if percent is None:
                # Never present an old percentage as current after a failed refresh.
                if sid in self._spoolman_percentages:
                    del self._spoolman_percentages[sid]
                    changed = True
            elif self._spoolman_percentages.get(sid) != percent:
                self._spoolman_percentages[sid] = percent
                changed = True

        for sid in list(self._spoolman_percentages):
            if sid not in valid_ids:
                del self._spoolman_percentages[sid]
                changed = True
        for sid in list(self._spoolman_refresh_at):
            if sid not in valid_ids:
                del self._spoolman_refresh_at[sid]

        for sid in valid_ids:
            if sid in self._spoolman_futures or now < self._spoolman_refresh_at.get(sid, 0):
                continue
            self._spoolman_futures[sid] = self.spoolman_client.post(
                '/server/spoolman/proxy',
                {'request_method': 'GET', 'path': '/v1/spool/%d' % sid},
                report_error=False)
        return changed
