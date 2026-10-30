"""Existing display methods grouped by responsibility."""
from petrel.ui.theme import show_icon as show_theme_icon
import time
from petrel.artwork.resources import ICON_FOLDER


class FileBrowserMixin:
    def _refresh_file_snapshot(self):
        self._sync_file_lifecycle()
        paths = self.pd.GetDirectory(getattr(self, '_file_directory', ''))
        if self.pd.file_error or self.pd._files_loading or self.pd._directory_loading:
            return False
        previous = getattr(self, '_file_paths', ())
        selected = (previous[self.select_file.now - 1]
                    if 0 < self.select_file.now <= len(previous) else None)
        self._file_paths = paths
        self.select_file.set(paths.index(selected) + 1 if selected in paths else 0)
        self.index_file = max(self.MROWS, self.select_file.now)
        self._file_view_epoch = self.pd.state.epoch
        self._file_view_revision = self.pd.state.file_revision
        self._file_view_sort_revision = self.pd.file_sort_revision
        self._sync_thumbnail_cache()
        if hasattr(self, '_loop'):
            self._loop.set_interval(.02)
        return True

    def _enter_file_directory(self, directory, select=None):
        self._file_directory = directory
        self._file_paths = ()
        self.select_file.reset()
        self.index_file = self.MROWS
        if self._refresh_file_snapshot() and select in self._file_paths:
            self.select_file.set(self._file_paths.index(select) + 1)
            self.index_file = max(self.MROWS, self.select_file.now)
        self.Draw_Print_File_Menu()
        self.lcd.update()

    def HMI_SelectFile(self):
        event = self.get_encoder_state()
        if event == self.ENCODER_DIFF_NO or getattr(self, '_pending_start', None):
            return
        if event == self.ENCODER_DIFF_ENTER and self.select_file.now == 0:
            directory = getattr(self, '_file_directory', '')
            if directory:
                self._enter_file_directory(directory.rpartition('/')[0], directory + '/')
            else:
                self.Goto_MainMenu()
            return
        if (self.pd.state.epoch != getattr(self, '_file_view_epoch', -1)
                or self.pd.state.file_revision != getattr(self, '_file_view_revision', -1)
                or self.pd.file_sort_revision != getattr(self, '_file_view_sort_revision', -1)):
            self._refresh_file_snapshot()
            self.Redraw_SD_List()
            # Do not apply an Enter captured against the previous list.
            return
        count = len(getattr(self, '_file_paths', ()))
        if event == self.ENCODER_DIFF_CW:
            self.select_file.inc(count + 1)
        elif event == self.ENCODER_DIFF_CCW:
            self.select_file.dec()
        elif event == self.ENCODER_DIFF_ENTER:
            path = self._file_paths[self.select_file.now - 1]
            if path.endswith('/'):
                self._enter_file_directory(path[:-1])
                return
            self._open_file_preview(path)
            return
        self.index_file = max(self.MROWS, self.select_file.now,
                              min(self.index_file, self.select_file.now + self.MROWS))
        self.Redraw_SD_List()
        self.lcd.update()

    def _poll_print_start(self):
        pending = getattr(self, '_pending_start', None)
        if not pending:
            return False
        future, epoch, started = pending
        error = None
        if epoch != self.pd.state.epoch:
            error = 'Connection changed; check printer'
        elif future.done():
            if future.cancelled():
                error = 'Print start cancelled'
            elif future.exception():
                error = 'Print start failed; check log'
            elif self.pd.status in ('printing', 'paused', 'error'):
                self._pending_start = None
                self._present_print_state()
                return False
            elif time.monotonic() - started > 30:
                error = 'Start unconfirmed; check printer'
        if not error and time.monotonic() - started > 30:
            future.cancel()  # Only cancels work that has not started.
            error = 'Start unconfirmed; check printer'
        if error:
            self._pending_start = None
            self.pd.last_command_error = None
            self._show_message(error)
            self._start_error_visible = True
        return True

    def Draw_SDItem(self, item, row=0):
        path = self._file_paths[item]
        is_dir = path.endswith('/')
        label = path.rstrip('/').rsplit('/', 1)[-1]
        self.Draw_Menu_Line(row, False if is_dir else self.ICON_File, label)
        if is_dir:
            show_theme_icon(self.lcd, self.ICON, ICON_FOLDER, 26, self.MBASE(row) - 7)

    def Draw_Print_File_Menu(self):
        self.Redraw_SD_List()

    def Redraw_SD_List(self):
        if not hasattr(self, '_file_paths'):
            self._refresh_file_snapshot()
        entries = [('Back', self.ICON_Back, None, None)]
        for index, path in enumerate(self._file_paths):
            entries.append(('', False, path,
                lambda row, index=index: self.Draw_SDItem(index, row)))
        directory = getattr(self, '_file_directory', '')
        self._draw_list_menu(('Print: /' + directory)[-32:] if directory else 'Print file',
                             entries, self.select_file.now, max(0, self.index_file - self.MROWS))
        message = ('File list unavailable' if self.pd.file_error else 'No files') if (
            len(entries) == 1 and (self.pd.file_error or not (self.pd._files_loading or self.pd._directory_loading))) else ''
        if message != getattr(self, '_file_drawn_message', None):
            if getattr(self, '_file_drawn_message', None):
                self.lcd.draw_rectangle(1, self.lcd.Color_Bg_Black, 20, self.MBASE(2), 271, self.MBASE(2) + 16)
            if message:
                self._draw_menu_text(message, 20, self.MBASE(2))
            self._file_drawn_message = message
