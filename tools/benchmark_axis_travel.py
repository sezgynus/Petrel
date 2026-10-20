#!/usr/bin/env python3
"""CI-only real Klipper trapq integration and synthetic extra/API cost comparison.

Not a Raspberry Pi timing-safety acceptance test. No local printer required.
"""
import argparse
import ctypes as C
import importlib.util
import json
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import time
from types import SimpleNamespace as NS

ROOT=Path(__file__).resolve().parents[1]


class Pull(C.Structure):
    _fields_=[(k,C.c_double) for k in ('print_time','move_t','start_v','accel',
              'start_x','start_y','start_z','x_r','y_r','z_r')]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--klipper-source',type=Path,required=True)
    args=parser.parse_args()
    sys.modules['chelper']=NS()
    spec=importlib.util.spec_from_file_location('petrel_axis_travel',ROOT/'klipper_extras/petrel_axis_travel.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    with tempfile.TemporaryDirectory() as folder:
        library=Path(folder)/'trapq.so'
        subprocess.run(['gcc','-O2','-shared','-fPIC','-I',str(args.klipper_source/'klippy/chelper'),
                        str(args.klipper_source/'klippy/chelper/trapq.c'),'-lm','-o',str(library)],check=True)
        lib=C.CDLL(str(library))
        lib.trapq_alloc.restype=C.c_void_p
        lib.trapq_free.argtypes=[C.c_void_p]
        lib.trapq_append.argtypes=[C.c_void_p]+[C.c_double]*13
        lib.trapq_set_position.argtypes=[C.c_void_p]+[C.c_double]*4
        lib.trapq_extract_old.argtypes=[C.c_void_p,C.POINTER(Pull),C.c_int,C.c_double,C.c_double]
        # Real native queue: acceleration + cruise + deceleration, negative Y.
        queue=lib.trapq_alloc();buffer=(Pull*128)()
        try:
            lib.trapq_append(queue,1.,1.,1.,1.,0.,0.,0.,.6,-.8,0.,0.,10.,10.)
            total=[0.,0.,0.]
            for start,end in ((0.,1.5),(1.5,2.),(2.,2.5),(2.5,3.5),(3.5,4.)):
                n=lib.trapq_extract_old(queue,buffer,128,start,end)
                for i in range(n):
                    for axis,value in enumerate(module.distances(buffer[i],start,end)):
                        total[axis]+=value
            assert all(abs(a-b)<1e-8 for a,b in zip(total,(12.,16.,0.))),total
            lib.trapq_set_position(queue,4.,1000.,1000.,0.)
            assert lib.trapq_extract_old(queue,buffer,128,4.,5.)==0,'Coordinate reset counted as motion'
        finally:
            lib.trapq_free(queue)
        print('Native trapq integration: PASS (partial intervals, acceleration, reverse Y, coordinate reset)')
        print('Fixed native buffer: %d bytes; one extraction/tick, interval %.1fs' % (C.sizeof(buffer),module.INTERVAL))
        for rate in (20,100,200,2000):
            queue=lib.trapq_alloc();count=int(rate*.5)
            try:
                for i in range(count):
                    lib.trapq_append(queue,(i+.01)/rate,0.,1./rate,0.,float(i),0.,0.,1.,0.,0.,10.,10.,100.)
                collector=module.PetrelAxisTravel(NS(get_printer=lambda:NS(get_reactor=lambda:None,
                    register_event_handler=lambda *a:None)))
                collector.reactor=NS(NEVER=1e30);collector.mcu=NS(estimated_print_time=lambda t:.5)
                collector.trapq=queue;collector.lib=lib;collector.buffer=buffer;collector.state='tracking'
                durations=[];payload=0
                for _ in range(500):
                    collector.last_time=0.;begin=time.perf_counter_ns();collector._tick(.5)
                    durations.append(time.perf_counter_ns()-begin)
                # API-like export comparison includes extraction/list/JSON/parse/
                # integration, not sockets or the actual Klipper bulk API wrapper.
                bulk=(Pull*(count+1))();api_times=[]
                for _ in range(100):
                    begin=time.perf_counter_ns()
                    n=lib.trapq_extract_old(queue,bulk,len(bulk),0.,.5)
                    data=[(m.print_time,m.move_t,m.start_v,m.accel,
                           (m.start_x,m.start_y,m.start_z),(m.x_r,m.y_r,m.z_r)) for m in bulk[:n]]
                    raw=json.dumps(data);decoded=json.loads(raw);value=0.
                    for row in decoded:
                        value+=abs(row[5][0]*(row[2]+.5*row[3]*row[1])*row[1])
                    api_times.append(time.perf_counter_ns()-begin);payload=len(raw)
                print(json.dumps(dict(segments_per_second=rate,
                    extra_median_us=round(statistics.median(durations)/1000,2),
                    extra_max_us=round(max(durations)/1000,2),
                    dropped_batches=collector.dropped_batches,
                    api_like_median_us=round(statistics.median(api_times)/1000,2),
                    api_like_bytes_per_half_second=payload)))
            finally:
                lib.trapq_free(queue)
        print('Synthetic runner measurements only; physical low-end SBC latency acceptance remains required.')


if __name__=='__main__': main()
