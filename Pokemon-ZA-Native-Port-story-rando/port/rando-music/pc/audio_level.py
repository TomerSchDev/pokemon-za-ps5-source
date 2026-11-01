"""RMS level of a run's raw audout capture (LARECOMP_AUDOUT_WAV: s16 stereo 48 kHz, no header) per window.
Usage: audio_level.py RUN_DIR [window_seconds]. Prints dBFS per window and the share of windows above -50 dBFS."""
import array
import math
import os
import sys


def levels(path, window=5.0, rate=48000, channels=2):
    data = open(path, 'rb').read()
    if data[:4] == b'RIFF':
        data = data[44:]
    a = array.array('h')
    a.frombytes(data[:len(data) // 2 * 2])
    step = int(window * rate) * channels
    out = []
    for i in range(0, len(a), step):
        chunk = a[i:i + step]
        if len(chunk) < step // 4:
            break
        ms = sum(x * x for x in chunk) / len(chunk)
        out.append(20 * math.log10(math.sqrt(ms) / 32768) if ms else -120.0)
    return out


if __name__ == '__main__':
    run = sys.argv[1]
    w = float(sys.argv[2]) if len(sys.argv) > 2 else 5.0
    lv = levels(os.path.join(run, 'audio.wav'), w)
    print(os.path.basename(run.rstrip('/\\')), 'seconds=%.0f' % (len(lv) * w),
          'audible_windows=%d/%d' % (sum(1 for x in lv if x > -50), len(lv)))
    print(' '.join('%.0f' % x for x in lv))
