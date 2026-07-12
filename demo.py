from ctypes import windll, wintypes, byref, create_unicode_buffer
import ctypes
import time
import os

user32 = windll.user32
kernel32 = windll.kernel32

SW_HIDE  = 0
SW_SHOW  = 5

# WinAPI prototypes (convenience)
FindWindowW = user32.FindWindowW
FindWindowExW = user32.FindWindowExW
ShowWindow = user32.ShowWindow
IsWindowVisible = user32.IsWindowVisible
EnumWindows = user32.EnumWindows
GetClassNameW = user32.GetClassNameW
SendMessageTimeoutW = user32.SendMessageTimeoutW

SMTO_NORMAL = 0x0
WM_SPAWN_WORKER = 0x052C  # magic used by some solutions

# -----------------------------
# Desktop icons (SHELLDLL_DefView / SysListView32)
# -----------------------------
def _find_shelldll_defview():
    # Try direct child of Progman first
    progman = FindWindowW("Progman", None)
    if progman:
        defview = FindWindowExW(progman, 0, "SHELLDLL_DefView", None)
        if defview:
            return defview

    # Otherwise, enumerate top-level windows to find WorkerW that contains SHELLDLL_DefView
    def enum_proc(hwnd, lParam):
        # for each top window, find SHELLDLL_DefView child
        buf = create_unicode_buffer(256)
        GetClassNameW(hwnd, buf, 256)
        cls = buf.value
        # look for SHELLDLL_DefView child
        child = FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None)
        if child:
            # store hwnd in lParam (ctypes expects return nonzero to continue)
            lParam[0] = child
            return False  # stop enumeration
        return True

    # Create a ctypes callback for EnumWindows
    EnumWindowsProc = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    found = (wintypes.HWND * 1)()
    def _cb(hwnd, lparam):
        # wrapper matching signature
        buf = create_unicode_buffer(256)
        GetClassNameW(hwnd, buf, 256)
        child = FindWindowExW(hwnd, 0, "SHELLDLL_DefView", None)
        if child:
            found[0] = child
            return 0  # stop
        return 1  # continue

    enum_cb = EnumWindowsProc(_cb)
    EnumWindows(enum_cb, 0)
    if found[0]:
        return found[0]
    return None

def _find_syslistview_from_defview(defview_hwnd):
    if not defview_hwnd:
        return None
    listview = FindWindowExW(defview_hwnd, 0, "SysListView32", None)
    return listview

def hide_desktop_icons():
    defview = _find_shelldll_defview()
    listview = _find_syslistview_from_defview(defview)
    if listview:
        ShowWindow(listview, SW_HIDE)
        return True
    return False

def show_desktop_icons():
    defview = _find_shelldll_defview()
    listview = _find_syslistview_from_defview(defview)
    if listview:
        ShowWindow(listview, SW_SHOW)
        return True
    return False

# -----------------------------
# Taskbar (Shell_TrayWnd)
# -----------------------------
def hide_taskbar():
    tray = FindWindowW("Shell_TrayWnd", None)
    if tray:
        ShowWindow(tray, SW_HIDE)
        # also hide the secondary tray (NotifyTray)
        tray_notify = FindWindowExW(tray, 0, "TrayNotifyWnd", None)
        if tray_notify:
            ShowWindow(tray_notify, SW_HIDE)
        return True
    return False

def show_taskbar():
    tray = FindWindowW("Shell_TrayWnd", None)
    if tray:
        ShowWindow(tray, SW_SHOW)
        tray_notify = FindWindowExW(tray, 0, "TrayNotifyWnd", None)
        if tray_notify:
            ShowWindow(tray_notify, SW_SHOW)
        return True
    return False

# -----------------------------
# Simple demo CLI
# -----------------------------
if __name__ == "__main__":
    while True:
        print("Demo: 1 hide desktop icons, 2 show desktop icons, 3 hide taskbar, 4 show taskbar")
        choice = input("Choice: ").strip()
        if choice == "1":
            ok = hide_desktop_icons()
            print("Desktop icons hidden." if ok else "Failed to find desktop icon window.")
        elif choice == "2":
            ok = show_desktop_icons()
            print("Desktop icons shown." if ok else "Failed to find desktop icon window.")
        elif choice == "3":
            ok = hide_taskbar()
            print("Taskbar hidden." if ok else "Failed to find taskbar window.")
        elif choice == "4":
            ok = show_taskbar()
            print("Taskbar shown." if ok else "Failed to find taskbar window.")
        else:
            print("No action.")
        os.system('cls' if os.name == 'nt' else 'clear')
