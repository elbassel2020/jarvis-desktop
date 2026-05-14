"""Desktop awareness — knows what apps are open."""
import psutil
from loguru import logger

try:
    import win32gui
    import win32process
    WINDOWS = True
except ImportError:
    WINDOWS = False


class ScreenAwareness:
    def get_open_windows(self):
        if not WINDOWS:
            return []
        windows = []

        def cb(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                title = win32gui.GetWindowText(hwnd)
                if title and len(title) > 3:
                    try:
                        _, pid = win32process.GetWindowThreadProcessId(hwnd)
                        proc = psutil.Process(pid)
                        results.append({
                            'title': title,
                            'process': proc.name(),
                            'pid': pid,
                        })
                    except Exception:
                        pass

        win32gui.EnumWindows(cb, windows)
        return windows

    def summary(self):
        try:
            windows = self.get_open_windows()
        except Exception as e:
            logger.debug(f"screen_awareness: {e}")
            return "Desktop state unavailable"

        if not windows:
            return "Desktop empty"

        by_proc = {}
        for w in windows:
            p = w['process'].replace('.exe', '')
            by_proc.setdefault(p, []).append(w['title'][:50])

        parts = []
        for p, titles in sorted(by_proc.items()):
            if len(titles) == 1:
                parts.append(f"{p}: '{titles[0]}'")
            else:
                parts.append(f"{p}({len(titles)} windows)")

        return "Open: " + " | ".join(parts[:8])
