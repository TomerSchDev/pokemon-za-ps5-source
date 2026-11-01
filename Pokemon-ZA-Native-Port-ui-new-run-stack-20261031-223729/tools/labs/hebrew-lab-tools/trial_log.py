"""Capture task-scoped console logs until the local stop file is created."""
from pathlib import Path
import sys
import time
LAB=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(LAB.parent/'Pokemon-ZA-Native-Port'))
from run_r3 import KlogCapture
root=LAB/'trial/console-r1';root.mkdir(parents=True,exist_ok=True)
cap=KlogCapture(root/'hardware.klog.log');cap.start()
print('Hebrew trial console logger started',flush=True)
try:
    while not (root/'stop-logger').exists() and cap.is_alive():time.sleep(.5)
finally:
    cap.stop()
    print(dict(lines=cap.lines,error=cap.error),flush=True)
