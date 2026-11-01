"""The scripted PC sessions for the r28a texfix: many scene transitions, as LARECOMP_INPUT and capture frames.

    py -3 session_inputs.py [--cycles N]     -> prints JSON {input, shot_at, frames}

A run boots, loads the save (title -> Continue) and repeats a cycle (frames are presented frames, ~25-30 a second):
  walking with camera turns and sprinting (city blocks streamed in and out), A now and then to close tutorials and
  dialogs (the Wild Zone tutorial does not close with B), into the Wild Zone ahead and back;
  the main menu (X) - pages left / right, a page opened and closed - the map (PLUS), MINUS, Y, each closed again;
  lock-on / attack / throw (ZL, A, X, ZR) at whatever is ahead (a battle when a wild Pokemon is there);
  an in-game save (X, R, A, A, B - the save sequence of the r28 ITEMS PC proof).
A second run started from the first run's saved file loads it (save -> load). The PC runtime's in-place reboot
(LARECOMP_REBOOT_AT) is not used: it ends the process with heap corruption right after the textures are released,
with the original runtime as well (runs orig-reboot-01 / texfix-session-01), so it can't stand for a reload here.
"""
import argparse
import json


def run_inputs(cycles):
    ev, shots = [], []

    def press(f, b, n=8):
        ev.append('%d:%s:%d' % (f, b, n))

    for f in (240, 420, 600, 780):  # title, Continue, the load's prompts
        press(f, 'A')
    for f in (1500, 1560):
        press(f, 'B')
    t = 1700
    for c in range(cycles):
        shots.append(t + 100)
        for d, hold in (('STICK_UP', 300), ('RSTICK_LEFT', 45), ('STICK_UP', 240), ('RSTICK_RIGHT', 90),
                        ('STICK_UP', 300), ('STICK_LEFT', 150), ('RSTICK_LEFT', 60), ('STICK_UP', 240),
                        ('STICK_DOWN', 300), ('STICK_RIGHT', 150)):
            press(t, d, hold)
            if hold >= 240:
                press(t + 30, 'B', hold - 90)  # (run)
            for k in range(60, hold, 120):
                press(t + k, 'A')  # (tutorials, dialogs)
            t += hold + 30
        shots.append(t)
        for b, wait in (('A', 60), ('A', 60), ('X', 90), ('RIGHT', 40), ('RIGHT', 40), ('A', 120), ('B', 60),
                        ('LEFT', 40), ('A', 120), ('B', 60), ('B', 90), ('PLUS', 150), ('A', 60), ('B', 90),
                        ('B', 60), ('MINUS', 150), ('B', 90), ('Y', 150), ('B', 90), ('B', 60)):
            press(t, b)
            t += wait
        for b, hold, wait in (('ZL', 90, 10), ('A', 8, 90), ('X', 8, 90), ('ZR', 30, 90), ('B', 8, 60),
                              ('ZL', 90, 10), ('A', 8, 120), ('B', 8, 60)):
            press(t, b, hold)
            t += hold + wait
        shots.append(t)
        for b, wait in (('X', 120), ('R', 150), ('A', 150), ('A', 150), ('B', 90), ('B', 90)):  # save
            press(t, b)
            t += wait
    shots.append(t - 30)
    return ev, shots, t


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--cycles', type=int, default=4)
    a = p.parse_args()
    ev, shots, t = run_inputs(a.cycles)
    print(json.dumps(dict(input=','.join(ev), shot_at=','.join(map(str, shots)), frames=t, cycles=a.cycles)))


if __name__ == '__main__':
    main()
