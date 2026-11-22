"""Set the Saros window to the 2560 Ã— 1440 client size used in the gameplay tests."""
import ctypes
from ctypes import wintypes
import time
import subprocess
import win32api, win32con, win32gui, win32process

WIDTH, HEIGHT = 2560, 1440

def resize(pid, find_windows, timeout=5.0):
    wins = [(h, title) for h, title, visible in find_windows(pid) if visible and ('saros' in title.lower() or 'ppsa07631' in title.lower())]
    if len(wins) != 1:
        raise RuntimeError(f'expected one visible game window for {pid}, got {len(wins)}')
    hwnd, _ = wins[0]
    if win32process.GetWindowThreadProcessId(hwnd)[1] != pid:
        raise RuntimeError('window owner changed')
    user = ctypes.WinDLL('user32', use_last_error=True)
    user.GetDpiForWindow.argtypes = [wintypes.HWND]; user.GetDpiForWindow.restype = wintypes.UINT
    user.GetWindowDpiAwarenessContext.argtypes = [wintypes.HWND]; user.GetWindowDpiAwarenessContext.restype = ctypes.c_void_p
    user.SetThreadDpiAwarenessContext.argtypes = [ctypes.c_void_p]; user.SetThreadDpiAwarenessContext.restype = ctypes.c_void_p
    user.AdjustWindowRectExForDpi.argtypes = [ctypes.POINTER(wintypes.RECT), wintypes.DWORD, wintypes.BOOL, wintypes.DWORD, wintypes.UINT]; user.AdjustWindowRectExForDpi.restype = wintypes.BOOL
    before_mode = _monitor(hwnd)
    ctx = user.GetWindowDpiAwarenessContext(hwnd)
    old = user.SetThreadDpiAwarenessContext(ctx)
    if not old: raise ctypes.WinError(ctypes.get_last_error())
    try:
        original_style = win32gui.GetWindowLong(hwnd, win32con.GWL_STYLE)
        style = ((original_style & ~(win32con.WS_CAPTION | win32con.WS_THICKFRAME)) | win32con.WS_POPUP) & 0xffffffff
        exstyle = win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & 0xffffffff
        dpi = user.GetDpiForWindow(hwnd)
        if not dpi: raise ctypes.WinError(ctypes.get_last_error())
        rect = wintypes.RECT(0, 0, WIDTH, HEIGHT)
        if not user.AdjustWindowRectExForDpi(ctypes.byref(rect), style, bool(win32gui.GetMenu(hwnd)), exstyle, dpi):
            raise ctypes.WinError(ctypes.get_last_error())
        if win32process.GetWindowThreadProcessId(hwnd)[1] != pid: raise RuntimeError('window owner changed before resize')
        signed_style = ctypes.c_int32(style).value
        win32gui.SetWindowLong(hwnd, win32con.GWL_STYLE, signed_style)
        win32gui.SetWindowPos(hwnd, 0, 0, 0, rect.right-rect.left, rect.bottom-rect.top,
                              win32con.SWP_NOMOVE | win32con.SWP_NOZORDER | win32con.SWP_NOACTIVATE | win32con.SWP_NOOWNERZORDER | win32con.SWP_FRAMECHANGED)
        deadline = time.monotonic() + timeout
        while True:
            client = win32gui.GetClientRect(hwnd)
            size = [client[2]-client[0], client[3]-client[1]]
            if size == [WIDTH, HEIGHT]: break
            if time.monotonic() >= deadline: raise RuntimeError(f'client resize rejected: {size}')
            time.sleep(.05)
        after_mode = _monitor(hwnd)
        if before_mode != after_mode: raise RuntimeError('desktop mode changed during resize')
        return {'pid':pid, 'hwnd':int(hwnd), 'client':size, 'dpi':dpi, 'original_style':original_style, 'popup_style':signed_style, 'desktop_before':before_mode, 'desktop_after':after_mode,
                'epoch_ns':time.time_ns(), 'qpc_ns':time.perf_counter_ns(), 'scope':'Windows client pixels, not Vulkan drawable'}
    finally:
        user.SetThreadDpiAwarenessContext(old)

def _monitor(hwnd):
    monitor = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONULL)
    if not monitor: raise RuntimeError('window is not associated with monitor')
    name = win32api.GetMonitorInfo(monitor)['Device']
    mode = win32api.EnumDisplaySettings(name, win32con.ENUM_CURRENT_SETTINGS)
    return {'device':name, 'width':mode.PelsWidth, 'height':mode.PelsHeight, 'hz':mode.DisplayFrequency}

def _windows(pid):
    windows = []
    def visit(hwnd, _):
        if win32process.GetWindowThreadProcessId(hwnd)[1] == pid:
            windows.append((hwnd, win32gui.GetWindowText(hwnd), win32gui.IsWindowVisible(hwnd)))
        return True
    win32gui.EnumWindows(visit, None)
    return windows

def run_windowed(command, installation, env):
    with subprocess.Popen(command, cwd=installation, env=env) as game:
        deadline = time.monotonic() + 90
        configured = False
        next_check = time.monotonic()
        while game.poll() is None and time.monotonic() < deadline:
            if time.monotonic() >= next_check:
                matches = [h for h, title, visible in _windows(game.pid)
                           if visible and ("saros" in title.lower() or "ppsa07631" in title.lower())]
                if len(matches) == 1:
                    x, y, right, bottom = win32gui.GetClientRect(matches[0])
                    if not configured or (right-x, bottom-y) != (WIDTH, HEIGHT):
                        try:
                            resize(game.pid, _windows)
                        except (OSError, RuntimeError) as error:
                            if game.poll() is None:
                                print(f"Window resize unavailable: {error}")
                            break
                        configured = True
                next_check = time.monotonic() + 2.0
            time.sleep(0.25)
        if game.poll() is None and not configured:
            print("The launcher could not verify the 2560 Ã— 1440 window.")
        return game.wait()
