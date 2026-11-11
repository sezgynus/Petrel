"""Sideband operation notifications; never dispatch hardware or printer commands."""
import logging


def contains_homing(script):
    return isinstance(script, str) and any(
        line.split(';', 1)[0].strip().upper().split()[:1] == ['G28']
        for line in script.splitlines())


def emit_operation(printer, name, epoch):
    try:
        callback = getattr(printer.subscription, 'emit_operation_melody', None)
        if callable(callback):
            callback(name, epoch)
    except Exception:
        logging.exception('Operation sound notification failed')


def confirmed_command_failure(future):
    """A server-reported command error, never timeout, cancellation or read failure."""
    return (future is not None and future.done() and not future.cancelled()
            and getattr(future, 'dispatch_stage', None) == 'server_error'
            and future.exception() is not None)
