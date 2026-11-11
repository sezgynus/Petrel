"""Positive native-command contract checks for bounded Maintenance protocols."""
from collections.abc import Mapping


def require_native(settings, commands):
    if not isinstance(settings, Mapping):
        raise ValueError('maintenance_command_settings_unknown')
    macros = {name.casefold().partition(' ')[2] for name in settings
              if isinstance(name,str) and name.casefold().startswith('gcode_macro ')}
    if macros.intersection(str(command).casefold() for command in commands):
        raise ValueError('maintenance_command_overridden')


def require_native_script(settings, script):
    commands = {line.split()[0] for line in script.splitlines() if line.split()}
    require_native(settings,commands)
