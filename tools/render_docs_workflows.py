#!/usr/bin/env python3
"""Render short, reproducible real-UI example workflows; no printer connection."""
from pathlib import Path
import logging
import sys
import time
from unittest.mock import patch
from PIL import Image
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from tools.render_docs_screenshots import ROOT, canvas, sample, finish, workflow_view
from dwin_emulator.presentation import with_frame


def save(name, frames, durations):
    destination=ROOT/'docs/assets'/name
    frames[0].save(destination,save_all=True,append_images=frames[1:],duration=durations,loop=0,disposal=2)
    destination=ROOT/'docs/assets/framed'/name;destination.parent.mkdir(exist_ok=True)
    framed=[with_frame(frame) for frame in frames]
    framed[0].save(destination,save_all=True,append_images=framed[1:],duration=durations,loop=0,disposal=2)
    print(destination)


def mmu_error_scroll_frames():
    """Scroll the real error reader, return to header Back, then to Print."""
    view = workflow_view('error-long')
    frames, durations = [finish(view, False)], [1400]
    view._rotation_steps = 1
    maximum = max(0, len(view._focus_error_lines) - 15)
    view.get_encoder_state.return_value = view.ENCODER_DIFF_CW
    for index in range(maximum + 1):
        view._focus_error_input()
        if index % 4 == 0:
            frames.append(finish(view, False))
            durations.append(650)
    # CW selects MMU recovery. Returning requires real CCW input all the way
    # past the first text position; do not assign the selection directly.
    view.get_encoder_state.return_value = view.ENCODER_DIFF_CCW
    for index in range(maximum + 2):
        view._focus_error_input()
        if index % 4 == 0 or view._focus_error_choice:
            frames.append(finish(view, False))
            durations.append(650)
        if view._focus_error_choice:
            break
    if view._focus_error_scroll != 0 or view._focus_error_choice != 1:
        raise RuntimeError('Error-reader walkthrough did not select header Back')
    view.get_encoder_state.return_value = view.ENCODER_DIFF_ENTER
    view._focus_error_input()
    if view.checkkey != view.PrintProcess:
        raise RuntimeError('Error-reader Back did not return to Print')
    frames.append(finish(view))
    durations.append(1800)
    return frames, durations


def main():
    logging.getLogger().setLevel(logging.ERROR)
    with patch.object(time,'strftime',return_value='12:34'),patch.object(time,'monotonic',return_value=0):
        # Hold progression, then release-to-confirm and incomplete-hold cancellation.
        names=['hold-start','hold-progress','hold-ready','power-idle','hold-progress','hold-cancel','tune-hold-cancel','power-blocked']
        save('power-shortcut-demo.gif',[finish(workflow_view(n),False) for n in names],
             [450,350,900,1800,600,1400,1600,1800])
        # Two red blinks from the real quiet-edit reconciliation path.
        frames=[];durations=[]
        for kind in ('tune-rejected','tune-switch-rejected','pause-rejected'):
            v=workflow_view(kind, pending_rejection=True)
            frames.append(finish(v,False));durations.append(900)
            next(iter(v._quiet_edits.values()))['future'].set_exception(RuntimeError('Example rejected command'))
            for tick in (0,.2,.4,.6,.8):
                with patch.object(time,'monotonic',return_value=tick):
                    if kind=='pause-rejected': v._focus_print_tick()
                    else: v._focus_tune_tick()
                    frames.append(finish(v,False));durations.append(200 if tick<.8 else 1600)
        save('rejected-controls-demo.gif',frames,durations)
        frames,durations = mmu_error_scroll_frames()
        save('mmu-error-scroll-demo.gif',frames,durations)
        # Native animation channel is sampled at elapsed times, not hand-drawn frames.
        v=canvas(sample());v.Goto_MainMenu();frames=[];durations=[];elapsed=0
        for percent in (0,1,50,100):
            v.pd.thermalManager['fan_speed'][0]=percent
            with patch.object(time,'monotonic',return_value=elapsed):v.Draw_Status_Area(False);v.lcd.update()
            for _ in range(12):
                elapsed+=.1
                with patch.object(time,'monotonic',return_value=elapsed):frames.append(v.framebuffer.snapshot()[0])
                durations.append(100)
        save('fan-animation-demo.gif',frames,durations)


if __name__=='__main__':main()
