"""Existing PrinterData methods grouped by responsibility."""
import logging
import math
import sys
import time
from urllib.parse import quote
from collections.abc import Mapping
from petrel.printer.background_reads import ReadPending
from petrel.moonraker.client import MoonrakerError


class FilePrinterMixin:
    def _invalidate_files(self):
        """Release all owners of file data together across backend sessions."""
        self._files_generation += 1
        self.files = []
        self._files_paths_snapshot = ()
        self._file_thumbnail_keys = {}
        self._file_thumbnail_list = None
        self._files_loaded = self._files_loading = self._directory_loading = False
        self._file_retry_at = 0.
        self._directory_cache.clear()
        self._directory_retry_at.clear()
        self._directory_revision_key = None
        self._root_prefetch_unretained = None
        for name in ('_directory_cache_sizes', '_directory_orders'):
            getattr(self, name, {}).clear()
        pending, self._file_sort_pending = self._file_sort_pending, None
        if pending is not None:
            pending[2].cancel()
        for key in tuple(self._read_jobs):
            if key == 'files' or isinstance(key, tuple) and key[0] in ('directory', 'directory_sort'):
                self._read_jobs.pop(key)[1].cancel()

    def _file_sort_identity(self):
        return (self.state.epoch, self.state.file_revision, id(self.files), self.file_sort_revision)

    def _poll_file_sort(self, now):
        identity, preference, future = self._file_sort_pending
        if identity != self._file_sort_identity():
            future.cancel()
            self._file_sort_pending = None
            self._file_sort_refresh_at = 0.
            return False
        if not future.done():
            return False
        self._file_sort_pending = None
        self._file_sort_refresh_at = now + 5.
        try:
            files, paths = future.result()
        except Exception as error:
            logging.debug('File resort unavailable: %s', type(error).__name__)
            return False
        old_files = self.files
        self.files = files
        self._files_paths_snapshot = paths
        if self._file_thumbnail_list is old_files:
            self._file_thumbnail_list = files
        self.file_sort = preference
        self.file_sort_revision += 1
        return True

    def refresh_file_sort(self, force=False):
        now = time.monotonic()
        if self._file_sort_pending is not None:
            return self._poll_file_sort(now)
        if not force and now < self._file_sort_refresh_at:
            return False
        try:
            response = self._read('file_sort', lambda: self.client.get('/server/database/item?namespace=mainsail&key=view.gcodefiles'))
            self._file_sort_refresh_at = now + 5.0
            values = response.get('result', {}).get('value', {})
            if not isinstance(values, Mapping):
                raise ValueError('Invalid file sort settings')
            field = values.get('sortBy', 'modified')
            descending = values.get('sortDesc', True)
            if field not in ('filename', 'modified', 'size') or not isinstance(descending, bool):
                field, descending = 'modified', True
            preference = (field, descending)
        except ReadPending:
            return False
        except (MoonrakerError, KeyError, TypeError, ValueError, AttributeError):
            self._file_sort_refresh_at = now + 5.0
            preference = ('modified', True)
        if preference == self.file_sort:
            return False
        # Work on a private copy; queued results bind to this exact list/session.
        source = self.files
        identity = self._file_sort_identity()
        def resort():
            files = list(source)
            self._sort_files(files, preference=preference)
            return files, tuple(item['path'] for item in files)
        self._file_sort_pending = (identity, preference, self._read_worker.submit(resort))
        return self._poll_file_sort(now)

    def _sort_files(self, entries=None, preference=None):
        items = self.files if entries is None else entries
        field, descending = self.file_sort if preference is None else preference
        # Deterministic ties and full paths preserve distinct nested files.
        items.sort(key=lambda item: (item['path'].casefold(), item['path']))
        def value(item):
            if field == 'filename':
                return item['path'].rstrip('/').rsplit('/', 1)[-1].casefold()
            number = item.get(field)
            if isinstance(number, (int, float)) and not isinstance(number, bool) and math.isfinite(number):
                return (True, number)
            return (False, 0)
        items.sort(key=value, reverse=descending)

    def GetFiles(self, refresh=False):
        self.refresh_file_sort()
        if not self._files_loaded or refresh:
            if time.monotonic() < self._file_retry_at and not refresh:
                return self._files_paths_snapshot
            self._files_loaded = False
            self._files_loading = True
            try:
                preference = self.file_sort
                revision = self.state.file_revision
                def prepare():
                    files = self.getREST('/server/files/list')['result']
                    if not isinstance(files, list) or not all(
                            isinstance(item, dict) and isinstance(item.get('path'), str)
                            and item['path'] for item in files):
                        raise ValueError('Invalid file list')
                    paths = {item['path'] for item in files}
                    if len(paths) != len(files):
                        raise ValueError('Duplicate file paths')
                    self._sort_files(files, preference=preference)
                    keys = {item['path']: (item['path'], item.get('modified'), item.get('size'),
                            revision if item.get('modified') is None else None) for item in files}
                    return files, tuple(item['path'] for item in files), keys
                files, paths, keys = self._read('files', prepare,
                    (self.state.epoch, revision, self.file_sort_revision))
                self.files = files
                self._files_paths_snapshot = paths
                self._file_thumbnail_keys = keys
                self._file_thumbnail_list = files
                self.file_error = None
                self._files_loaded = True
                self._files_loading = False
                self._file_retry_at = 0.0
            except ReadPending:
                pass
            except (MoonrakerError, KeyError, TypeError, ValueError) as exc:
                self.file_error = str(exc)
                self._files_loaded = False
                self._files_loading = False
                self._file_retry_at = time.monotonic() + 5
        return getattr(self, '_files_paths_snapshot', tuple())

    def prefetch_files(self):
        """Warm the root browser cache using the existing nonblocking read worker."""
        if not self.state.ready:
            return
        key = (self.state.epoch, self.state.file_revision, '')
        if not self._files_loaded or (key not in self._directory_cache
                                     and key != self._root_prefetch_unretained):
            self.GetDirectory('')

    @staticmethod
    def _directory_size(entries):
        # Include Python container/string overhead, not just serialized JSON bytes.
        pending = [entries]
        size = 0
        while pending:
            value = pending.pop()
            size += sys.getsizeof(value)
            if isinstance(value, dict):
                pending.extend(value.keys())
                pending.extend(value.values())
            elif isinstance(value, (list, tuple)):
                pending.extend(value)
        return size

    def GetDirectory(self, directory=''):
        # A snapshot stays unresolved through read failures and retry backoff.
        # Only a successful directory result (including empty) may clear this.
        self._directory_loading = True
        self.GetFiles()
        if self.file_error or self._files_loading:
            return ()
        if directory and any(part in ('', '.', '..') for part in directory.split('/')):
            raise ValueError('Invalid directory path')
        key = (self.state.epoch, self.state.file_revision, directory)
        orders = getattr(self, '_directory_orders', {})
        self._directory_orders = orders
        sizes = getattr(self, '_directory_cache_sizes', {})
        self._directory_cache_sizes = sizes
        for old in tuple(sizes):
            if old not in self._directory_cache:
                del sizes[old]
                orders.pop(old, None)
        if self._directory_revision_key != key[:2]:
            self._directory_cache.clear()
            sizes.clear()
            orders.clear()
            self._directory_retry_at.clear()
            self._directory_revision_key = key[:2]
            self._root_prefetch_unretained = None
        try:
            if key not in self._directory_cache:
                if time.monotonic() < self._directory_retry_at.get(key, 0):
                    return ()
                self._directory_loading = True
                preference = self.file_sort
                def prepare_directory():
                    data = self.getREST('/server/files/directory?path=' + quote('gcodes/' + directory, safe=''))['result']
                    entries = []
                    for group, name_key, is_dir in (('dirs', 'dirname', True), ('files', 'filename', False)):
                        for item in data[group]:
                            name = item[name_key]
                            if not isinstance(name, str) or not name or '/' in name or name in ('.', '..'):
                                raise ValueError('Invalid directory entry')
                            if name.startswith('.') or (not is_dir and not name.lower().endswith('.gcode')):
                                continue
                            path = (directory + '/' if directory else '') + name
                            entries.append(dict(item, path=path + ('/' if is_dir else ''), isDirectory=is_dir))
                    if len({item['path'] for item in entries}) != len(entries):
                        raise ValueError('Duplicate directory entries')
                    size = self._directory_size(entries)
                    self._sort_files(entries, preference=preference)
                    entries.sort(key=lambda item: not item['isDirectory'])
                    return entries, size, tuple(item['path'] for item in entries)
                entries, size, paths = self._read(('directory', directory), prepare_directory,
                    (key, preference))
                if size <= self.DIRECTORY_CACHE_BYTES:
                    self._directory_cache[key] = entries
                    sizes[key] = size
                    orders[key] = (preference, paths)
                if not directory:
                    # A successful oversized root needs no further automatic
                    # prefetch in this revision. Keep only its identity, not data.
                    # Explicit GetDirectory calls still fetch and return paths.
                    self._root_prefetch_unretained = (
                        key if size > self.DIRECTORY_CACHE_BYTES else None)
                self._directory_loading = False
                self._directory_retry_at.pop(key, None)
            # Insertion-ordered cache: keep the root and current parent available
            # while bounding memory during long sessions with many folders.
            if key in self._directory_cache:
                entries = self._directory_cache.pop(key)
                self._directory_cache[key] = entries
            parent = directory.rpartition('/')[0]
            retained = sum(sizes.values())
            while len(self._directory_cache) > 64 or retained > self.DIRECTORY_CACHE_BYTES:
                victim = next((k for k in self._directory_cache
                               if k[2] not in ('', directory, parent)), None)
                if victim is None:
                    # Byte limit wins even when only root/current/parent remain.
                    victim = next(iter(self._directory_cache))
                del self._directory_cache[victim]
                retained -= sizes.pop(victim, 0)
                orders.pop(victim, None)
            order = orders.get(key)
            if order is not None and order[0] != self.file_sort:
                preference = self.file_sort
                source = entries
                def resort():
                    items = list(source)
                    self._sort_files(items, preference=preference)
                    items.sort(key=lambda item: not item['isDirectory'])
                    return items, tuple(item['path'] for item in items)
                self._directory_loading = True
                entries, paths = self._read(('directory_sort', directory), resort, (key, preference))
                self._directory_loading = False
                self._directory_cache[key] = entries
                orders[key] = (preference, paths)
            self._directory_loading = False
            return orders[key][1] if key in orders else paths
        except ReadPending:
            return ()
        except (MoonrakerError, KeyError, TypeError, ValueError) as error:
            self._directory_loading = True
            self._directory_retry_at[key] = time.monotonic() + 5
            # Only the newest retry deadlines may survive in the current revision.
            for old in list(self._directory_retry_at)[:-64]:
                del self._directory_retry_at[old]
            self.file_error = str(error)
            self._files_loaded = False
            return ()
