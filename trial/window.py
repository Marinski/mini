"""Night-window gate for the trial queue (SPEC step 8).

The full batch runs only in the open window (22:00-07:00 by default) and never overlaps the
nightly backups, which close two windows inside it: 01:15-01:45 (Postgres) and
02:50-04:10 (cockpit, ats-translate-db, aigate, portfolio). A run may start only if it ends
before the next closed window or the close time, so no run is ever active during a backup.

This module only answers the yes/no and the wait; it runs nothing.

    python3 trial/window.py --task-min 65      # can a 65-min run start now? exit 0 = yes
    python3 trial/window.py --next 65          # seconds to the next start that fits (0 if now)
    python3 trial/window.py --config           # print the parsed window
    python3 trial/window.py --selftest

Env: WINDOW_OPEN=22:00 WINDOW_CLOSE=07:00 CLOSED_WINDOWS="01:15-01:45 02:50-04:10"
     WINDOW_PAD=1.25 (multiplier applied to a task's longest pilot run by --task-min)
"""
import os
import sys
from datetime import datetime

MINUTES = 1440.0


def hm(s):
    h, m = s.split(":")
    return int(h) * 60 + int(m)


OPEN = hm(os.environ.get("WINDOW_OPEN", "22:00"))
CLOSE = hm(os.environ.get("WINDOW_CLOSE", "07:00"))
CLOSED = tuple(tuple(hm(x) for x in w.split("-"))
               for w in os.environ.get("CLOSED_WINDOWS", "01:15-01:45 02:50-04:10").split())
PAD = float(os.environ.get("WINDOW_PAD", "1.25"))


def open_at(m):
    """Is wall-clock minute m inside the open window (which may wrap midnight)?"""
    m %= 1440
    if OPEN < CLOSE:
        return OPEN <= m < CLOSE
    return m >= OPEN or m < CLOSE


def allowed(m):
    """m is a minute a run may be active in: open and not inside a closed (backup) window."""
    m %= 1440
    if not open_at(m):
        return False
    return not any(a <= m < b for a, b in CLOSED)


def fits(now, dur):
    """Can a run of dur minutes start at minute now and stay allowed throughout?"""
    dur = max(1, int(dur))
    return all(allowed(now + i) for i in range(dur))


def next_start(now, dur, horizon=1440):
    """Minutes from now until dur allowed minutes begin; None if nowhere in the horizon."""
    for d in range(horizon + 1):
        if fits(now + d, dur):
            return d
    return None


def _now_minutes(now=None):
    t = now or datetime.now()
    return t.hour * 60 + t.minute


def cli(argv):
    dur = None
    if "--task-min" in argv:
        i = argv.index("--task-min")
        dur = int(int(argv[i + 1]) * PAD + 0.5)
    if "--dur" in argv:
        i = argv.index("--dur")
        dur = int(argv[i + 1])
    if dur is None:
        dur = 60
    now = _now_minutes()
    if "--next" in argv:
        # Informational: print the seconds to the next fitting start and exit 0.
        # The "does it fit now" signal is --task-min's exit code.
        d = next_start(now, dur)
        print(86400 if d is None else d * 60)
        return 0
    if "--config" in argv:
        print(f"open {OPEN}-{CLOSE}, closed {CLOSED}, pad {PAD}")
        return 0
    return 0 if fits(now, dur) else 1


def selftest():
    """Fixed times, so the wrap and both backup windows are exercised without a clock."""
    bad = []
    # 23:00 (1380): a 60-min run ends 24:00, well before 01:15 -> fits; 200 min crosses 01:15.
    if not fits(1380, 60):
        bad.append("23:00 +60 should fit")
    if fits(1380, 200):
        bad.append("23:00 +200 crosses 01:15 and should not fit")
    # 01:20 (80) is inside the Postgres backup -> nothing fits.
    if fits(80, 1) or open_at(80) and allowed(80):
        bad.append("01:20 is closed and should not fit")
    # 03:00 (180) is inside the second backup.
    if allowed(180):
        bad.append("03:00 should be closed")
    # 06:30 (390): +30 ends exactly at 07:00 -> fits; +31 spills past the close.
    if not fits(390, 30):
        bad.append("06:30 +30 should fit (ends 07:00)")
    if fits(390, 31):
        bad.append("06:30 +31 should not fit")
    # 01:50 (110): +50 ends 02:40, before 02:50 -> fits; +70 crosses 02:50.
    if not fits(110, 50):
        bad.append("01:50 +50 should fit")
    if fits(110, 70):
        bad.append("01:50 +70 crosses 02:50 and should not fit")
    # 08:00 (480) is closed; the next start for a 60-min run is 22:00 (1320) -> 840 min.
    if fits(480, 60):
        bad.append("08:00 should be closed")
    if next_start(480, 60) != 840:
        bad.append(f"next_start(08:00, 60) = {next_start(480, 60)}, want 840")
    # 21:00 (1260) is still closed; 22:00 fits.
    if fits(1260, 60) or next_start(1260, 60) != 60:
        bad.append("21:00 should wait 60 min")
    print("window selftest:", "FAILED\n  " + "\n  ".join(bad) if bad else
          "ok (wrap, both backup windows, exact close)")
    return not bad


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if selftest() else 1)
    sys.exit(cli(sys.argv[1:]))
