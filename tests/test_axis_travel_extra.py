"""CI regressions for bounded extra processing, with no printer hardware."""
import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch


def extra_module():
    spec=importlib.util.spec_from_file_location('petrel_travel_test',
        Path(__file__).resolve().parents[1]/'klipper_extras/petrel_axis_travel.py')
    module=importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules,{'chelper':Mock()}): spec.loader.exec_module(module)
    return module


def move(start=0.,duration=2.,velocity=10.,accel=0.,direction=(1.,0.,0.)):
    return NS(print_time=start,move_t=duration,start_v=velocity,accel=accel,
              x_r=direction[0],y_r=direction[1],z_r=direction[2])


class AxisExtraTests(unittest.TestCase):
    def collector(self, moves):
        module=extra_module()
        obj=module.PetrelAxisTravel(NS(get_printer=lambda:Mock()))
        obj.reactor=NS(NEVER=1e30)
        obj.mcu=NS(estimated_print_time=lambda eventtime:eventtime)
        obj.last_time=0.;obj.trapq=object();obj.state='tracking'
        obj.buffer=moves
        obj.lib=NS(trapq_extract_old=Mock(return_value=len(moves)))
        return module,obj

    def test_integrates_acceleration_diagonal_and_reverse_without_offsets(self):
        m=extra_module()
        self.assertEqual(m.distances(move(velocity=0,accel=10,direction=(.6,-.8,0)),0,2),(12.,16.,0.))
        self.assertEqual(m.distances(move(direction=(-1,0,0)),0,2),(20.,0.,0.))
        self.assertEqual(m.distances(move(),3,4),(0.,0.,0.))

    def test_partial_move_is_not_double_counted_and_future_is_excluded(self):
        m,obj=self.collector([move()])
        for t in (.5,1.,1.5,2.): obj._tick(t)
        self.assertEqual(obj.totals,[20.,0.,0.])
        self.assertEqual(m.distances(move(start=100),0,1),(0.,0.,0.))

    def test_one_extraction_per_tick_capacity_and_stall_drop_without_catchup(self):
        m,obj=self.collector([move()]*128)
        obj._tick(.5)
        self.assertEqual(obj.totals,[0.,0.,0.])
        self.assertEqual(obj.dropped_batches,1)
        obj.lib.trapq_extract_old.assert_called_once()
        obj._tick(5.)
        self.assertEqual(obj.dropped_batches,2)
        obj.lib.trapq_extract_old.assert_called_once()

    def test_homing_and_probe_moves_are_excluded_and_tracking_resumes(self):
        m,obj=self.collector([move()])
        obj.reactor=NS(NEVER=1e30,monotonic=lambda:1.)
        obj._homing_begin(None);obj._tick(.5);obj._homing_end(None)
        self.assertEqual(obj.totals,[0.,0.,0.])
        obj._tick(1.5)
        self.assertEqual(obj.totals,[5.,0.,0.])

    def test_optional_failure_stops_only_collector_and_status_has_no_io(self):
        m,obj=self.collector([])
        obj.lib.trapq_extract_old.side_effect=RuntimeError('incompatible helper')
        self.assertEqual(obj._tick(.5),obj.reactor.NEVER)
        self.assertEqual(obj.get_status(1)['state'],'unavailable')
        self.assertEqual(obj.get_status(1)['coverage'],'recorded_lower_bound')
        obj.printer.invoke_shutdown.assert_not_called()

    def test_ready_uses_fixed_buffer_and_shutdown_stops_timer(self):
        m=extra_module();reactor=Mock();reactor.monotonic.return_value=10.
        printer=Mock();printer.get_reactor.return_value=reactor
        printer.lookup_object.return_value=NS(estimated_print_time=lambda t:1.,get_trapq=lambda:object())
        ffi=Mock();m.chelper.get_ffi.return_value=(ffi,Mock())
        obj=m.PetrelAxisTravel(NS(get_printer=lambda:printer));obj._ready()
        self.assertEqual(obj.state,'tracking')
        ffi.new.assert_called_once_with('struct pull_move[128]')
        self.assertEqual(reactor.register_timer.call_args.args[1],10.1)
        obj._stop();reactor.update_timer.assert_called_with(obj.timer,reactor.NEVER)

    def test_homing_callback_failure_does_not_escape_into_motion(self):
        m,obj=self.collector([])
        obj.mcu=NS(estimated_print_time=Mock(side_effect=RuntimeError('disconnected')))
        obj.reactor=NS(NEVER=1e30,monotonic=lambda:1.)
        obj._homing_begin();obj._homing_end()
        self.assertEqual(obj.state,'unavailable')
        obj.printer.invoke_shutdown.assert_not_called()
