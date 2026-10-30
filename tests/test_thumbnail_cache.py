from concurrent.futures import Future
import unittest
from unittest.mock import Mock
from unittest.mock import patch

from petrel.features.files.thumbnail_cache import ThumbnailCache


def key(name):
    return (name+'.gcode',1,100,None)


def completed(data=b'x'*300):
    future=Future();future.set_result(data);return future


class CacheTests(unittest.TestCase):
    def make(self, count=8, size=300):
        keys=tuple(key(str(index)) for index in range(count))
        cache=ThumbnailCache(Mock(),loader=Mock(side_effect=lambda k: completed(b'x'*size)))
        cache.sync((1,1),keys,keys[:5])
        return cache,keys,Mock()

    def fill(self,cache,lcd):
        for _ in range(100):cache.tick(lcd,chunks=8)

    def test_first_five_preload_in_order_without_duplicate_requests(self):
        cache,keys,lcd=self.make();self.fill(cache,lcd)
        self.assertEqual([c.args[0] for c in cache.loader.call_args_list],list(keys[:5]))
        self.assertEqual(tuple(cache.entries),keys[:5])
        addresses=sorted(cache.entries.values())
        self.assertTrue(all(a+n<=b for (a,n),(b,m) in zip(addresses,addresses[1:])))
        lcd.show_sram_jpeg.assert_not_called()

    def test_background_packets_are_bounded_and_partial_upload_is_not_a_hit(self):
        cache,keys,lcd=self.make(size=600)
        cache.tick(lcd);cache.tick(lcd)
        self.assertEqual(lcd.write_sram.call_count,2)
        self.assertIsNone(cache.address(keys[0]))
        cache.tick(lcd);cache.tick(lcd)
        self.assertEqual(cache.address(keys[0]),0)
        self.assertEqual(b''.join(call.args[1] for call in lcd.write_sram.call_args_list),b'x'*600)

    def test_reordering_retains_entries_and_only_downloads_new_priority(self):
        cache,keys,lcd=self.make();self.fill(cache,lcd)
        previous=dict(cache.entries)
        cache.sync((1,1),keys,(keys[7],keys[4],keys[3],keys[2],keys[1]))
        self.fill(cache,lcd)
        self.assertEqual(cache.loader.call_count,6)
        self.assertTrue(all(cache.entries[k]==v for k,v in previous.items()))
        cache.sync((1,1),keys,(keys[7],keys[6],keys[5],keys[4],keys[3]))
        self.fill(cache,lcd)
        self.assertEqual(cache.loader.call_count,8)

    def test_lru_eviction_preserves_priority_and_recently_opened_extra(self):
        cache,keys,lcd=self.make();cache.capacity=2400;self.fill(cache,lcd)
        # Five protected and three extra images fill memory exactly.
        for k in keys[5:]:
            for _ in range(4):cache.tick(lcd,foreground=k,chunks=8)
        cache.address(keys[5],touch=True)
        extra=key('new');cache.sync((1,1),keys+(extra,),keys[:5])
        for _ in range(4):cache.tick(lcd,foreground=extra,chunks=8)
        self.assertIn(keys[5],cache.entries)
        self.assertNotIn(keys[6],cache.entries)
        self.assertTrue(all(k in cache.entries for k in keys[:5]))
        self.assertLessEqual(sum(n for a,n in cache.entries.values()),cache.capacity)

    def test_capacity_prioritizes_earlier_files_and_foreground_can_still_open(self):
        cache,keys,lcd=self.make(size=600);cache.capacity=1000
        self.fill(cache,lcd)
        self.assertEqual(tuple(cache.entries),(keys[0],))
        self.assertEqual(cache.errors[keys[1]],'LCD cache full')
        cache.errors.pop(keys[1])
        for _ in range(6):cache.tick(lcd,foreground=keys[1],chunks=8)
        self.assertIsNotNone(cache.address(keys[1]))
        self.assertIsNone(cache.address(keys[0]))

    def test_deleted_replaced_files_and_late_result_cannot_be_published(self):
        cache,keys,lcd=self.make();future=Future();cache.loader.return_value=future;cache.loader.side_effect=None
        cache.tick(lcd)
        replacement=(keys[0][0],2,200,None)
        cache.sync((1,1),(replacement,)+keys[1:],(replacement,)+keys[1:5])
        future.set_result(b'x'*300);cache.tick(lcd)
        lcd.write_sram.assert_not_called()
        self.assertNotIn(keys[0],cache.entries)
        self.assertEqual(cache.job[0],replacement)

    def test_epoch_change_discards_even_same_file_pending_result(self):
        cache,keys,lcd=self.make();future=Future();cache.loader.side_effect=None;cache.loader.return_value=future
        cache.tick(lcd);cache.entries[keys[1]]=(1000,300)
        cache.sync((2,1),keys,keys[:5]);self.assertFalse(cache.entries)
        future.set_result(b'x'*300);cache.tick(lcd)
        lcd.write_sram.assert_not_called()

    def test_foreground_preempts_unrelated_partial_preload(self):
        cache,keys,lcd=self.make(size=2000)
        cache.tick(lcd);cache.tick(lcd);lcd.reset_mock()
        cache.tick(lcd,foreground=keys[7],chunks=8)
        self.assertEqual(cache.job[0],keys[7])
        self.assertIsNone(cache.address(keys[0]))
        lcd.write_sram.assert_not_called()
        for _ in range(3):cache.tick(lcd,foreground=keys[7],chunks=8)
        self.assertIsNotNone(cache.address(keys[7]))

    def test_error_is_not_retried_each_tick_but_replacement_is(self):
        cache,keys,lcd=self.make();future=Future();future.set_exception(ValueError('No thumbnail'))
        cache.loader.side_effect=lambda k: future if k==keys[0] else completed()
        self.fill(cache,lcd)
        self.assertEqual(cache.loader.call_count,5)
        self.assertIn(keys[0],cache.errors)
        replacement=(keys[0][0],2,200,None)
        cache.sync((1,1),(replacement,)+keys[1:],(replacement,)+keys[1:5]);self.fill(cache,lcd)
        self.assertEqual(cache.loader.call_count,6)
        self.assertNotIn(keys[0],cache.errors)

    def test_write_failure_never_publishes_partial_entry(self):
        cache,keys,lcd=self.make(size=600)
        cache.tick(lcd);lcd.write_sram.side_effect=OSError('disconnected')
        with self.assertRaises(OSError):cache.tick(lcd)
        self.assertFalse(cache.entries)
        cache.sync((2,1),keys,keys[:5])
        self.assertIsNone(cache.upload)

    def test_invalid_size_is_rejected_before_uart_write(self):
        for data in (b'',b'x'*32769,()):
            cache,keys,lcd=self.make();cache.loader.side_effect=lambda k:completed(data)
            cache.tick(lcd);cache.tick(lcd)
            lcd.write_sram.assert_not_called()
            self.assertIn(keys[0],cache.errors)

    def test_temporary_metadata_failure_retries_after_backoff(self):
        cache,keys,lcd=self.make();future=Future();future.set_exception(ValueError('No thumbnail'))
        cache.loader.side_effect=lambda k:future
        with patch('petrel.features.files.thumbnail_cache.time.monotonic',return_value=10):
            cache.tick(lcd,foreground=keys[0]);cache.tick(lcd,foreground=keys[0])
            cache.tick(lcd,foreground=keys[0])
            self.assertEqual(cache.loader.call_count,1)
        cache.loader.side_effect=lambda k:completed()
        with patch('petrel.features.files.thumbnail_cache.time.monotonic',return_value=21):
            cache.tick(lcd,foreground=keys[0]);cache.tick(lcd,foreground=keys[0],chunks=8)
        self.assertIsNotNone(cache.address(keys[0]))
        self.assertNotIn(keys[0],cache.errors)

    def test_folder_change_drops_partial_preload_but_keeps_completed_images(self):
        cache,keys,lcd=self.make(size=600)
        cache.tick(lcd);cache.tick(lcd);cache.tick(lcd);cache.tick(lcd)
        cache.tick(lcd);cache.tick(lcd)
        cache.sync((1,1),keys,keys[5:])
        lcd.reset_mock();cache.tick(lcd)
        self.assertIsNone(cache.address(keys[1]))
        self.assertIsNotNone(cache.address(keys[0]))
        self.assertEqual(cache.job[0],keys[5])
        lcd.write_sram.assert_not_called()
