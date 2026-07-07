import threading
import time
from datetime import datetime, timezone, timedelta
from typing import Callable

_stop   = threading.Event()
_thread: threading.Thread | None = None
_speak:  Callable | None         = None

_alerted: set[str] = set()
_last_cal_check    = 0.0


def _push(msg: str) -> None:
    import mobile_server
    mobile_server.push_log(f"ALERT: {msg}")
    if _speak:
        _speak(msg)


def _check_system() -> None:
    import psutil
    cpu = psutil.cpu_percent(interval=2)
    if cpu > 90:
        key = f"cpu_high_{int(cpu // 5) * 5}"
        if key not in _alerted:
            _alerted.add(key)
            _push(f"Sir, CPU usage is critically high at {cpu:.0f} percent.")
    else:
        _alerted.discard("cpu_high")

    mem = psutil.virtual_memory()
    if mem.percent > 92:
        key = "mem_high"
        if key not in _alerted:
            _alerted.add(key)
            _push(f"Sir, memory usage is at {mem.percent:.0f} percent.")
    else:
        _alerted.discard("mem_high")

    disk = psutil.disk_usage("/")
    if disk.free < 5 * 1024 ** 3:
        key = "disk_low"
        if key not in _alerted:
            _alerted.add(key)
            free_gb = disk.free / 1024 ** 3
            _push(f"Sir, disk space is critically low — only {free_gb:.1f} GB remaining.")


def _check_calendar() -> None:
    global _last_cal_check
    now_ts = time.time()
    if now_ts - _last_cal_check < 300:
        return
    _last_cal_check = now_ts

    try:
        from actions.google_calendar import get_upcoming_events
        events = get_upcoming_events(minutes_ahead=16)
        now    = datetime.now(timezone.utc)
        for ev in events:
            start_str = ev["start"].get("dateTime")
            if not start_str:
                continue
            start_dt  = datetime.fromisoformat(start_str.replace("Z", "+00:00"))
            diff_mins = (start_dt - now).total_seconds() / 60
            if diff_mins < 0:
                continue
            title = ev.get("summary", "an event")
            key   = f"cal_{ev.get('id', title)}_{start_str}"
            if key not in _alerted:
                _alerted.add(key)
                mins = int(diff_mins)
                if mins < 2:
                    _push(f"Sir, {title} is starting now.")
                else:
                    _push(f"Sir, reminder: {title} starts in {mins} minutes.")
    except Exception:
        pass


def _loop() -> None:
    while not _stop.is_set():
        try:
            _check_system()
            _check_calendar()
        except Exception as e:
            print(f"[Proactive] ⚠️ {e}")
        _stop.wait(60)


def start(speak_fn: Callable) -> None:
    global _thread, _speak
    _speak = speak_fn
    _stop.clear()
    _thread = threading.Thread(target=_loop, daemon=True, name="proactive-monitor")
    _thread.start()
    print("[Proactive] ✅ Monitor started (system health + calendar reminders)")


def stop() -> None:
    _stop.set()
