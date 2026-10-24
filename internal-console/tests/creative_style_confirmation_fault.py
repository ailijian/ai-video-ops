"""Crash only after real Native publication; no Gate or source is substituted."""
import os
from pathlib import Path
import runpy
import socket
import sys

point, script = sys.argv[1], Path(sys.argv[2])
sys.argv = sys.argv[2:]
sys.path.insert(0,str(script.parent))
socket.socket.connect=lambda *a,**k: (_ for _ in ()).throw(RuntimeError('Network forbidden in confirmation fault test'))
import creative_style_v1 as style
original=style.write_once
def publish(path,value):
    result=original(path,value)
    if Path(path).name==point:os._exit(91)
    return result
style.write_once=publish
runpy.run_path(str(script),run_name='__main__')
