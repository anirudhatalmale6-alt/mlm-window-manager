"""
Multilogin Window Manager v2.0 Clone with Discord Screenshot
Exact replica of the original with added Discord integration
"""

import ctypes
from ctypes import wintypes
import sys
import os
import time
import re
import json
import threading
import io
import csv
import requests
from datetime import datetime

# Check and install dependencies
def install_deps():
    import subprocess
    try:
        import PIL
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pillow"])
    try:
        import requests
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "requests"])
    try:
        import gspread
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "gspread"])
    try:
        import google.auth
    except ImportError:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "google-auth"])

install_deps()

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageGrab

# Windows API
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
EnumWindows = user32.EnumWindows
EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
GetWindowTextW = user32.GetWindowTextW
GetWindowTextLengthW = user32.GetWindowTextLengthW
IsWindowVisible = user32.IsWindowVisible
SetWindowPos = user32.SetWindowPos
ShowWindow = user32.ShowWindow
GetClassName = user32.GetClassNameW
GetWindowThreadProcessId = user32.GetWindowThreadProcessId
SetForegroundWindow = user32.SetForegroundWindow

SW_RESTORE = 9
SW_MINIMIZE = 6
SW_HIDE = 0
HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOMOVE = 0x0002
SWP_NOSIZE = 0x0001

# Settings file
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "settings.json")

DEFAULT_SETTINGS = {
    "discord_webhook_1": "https://discord.com/api/webhooks/1464267517139877930/Ae0LDeglr3CEYK_vjsTd1htYoevub_ajXCcb4CAWVSGkg-s2XweTo9MIqNiZNNAH_iOQ",
    "discord_webhook_2": "https://discord.com/api/webhooks/1464267286918594652/tz1Go3i_cGsHz0f08bpAAR_C1wRhw6eU629CrajA4uDxf4kd5L-0ZKbxh6vLduCLibPo",
    "discord_name_1": "Que",
    "discord_name_2": "Prod",
    "discord_username": "",
    "hotkeys_enabled": True,
    "always_on_top": False,
    "auto_refresh": True,
    "refresh_interval": 3,
    "google_sheet_id": "1hkNIuTCUh5qCCGFrG-vmcfGQE0Sm9Bj1x_pdUSDV7Jk"
}

# Google Sheets service account key file (same folder as script)
GSHEET_KEY_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "service_account.json")

PROFILE_INDICATORS = ['whoerip', 'whoer', 'mimic']
EXCLUDE_INDICATORS = ['multilogin x app', 'multilogin app', 'multilogin window manager']
PROFILE_PATTERNS = [r'\b[A-Z]{2}\d+\b', r'\b\d{4}\s*-\s*[A-Z]\s*-\s*[A-Z]\b']


def load_settings():
    try:
        if os.path.exists(SETTINGS_FILE):
            with open(SETTINGS_FILE, 'r') as f:
                saved = json.load(f)
                settings = DEFAULT_SETTINGS.copy()
                settings.update(saved)
                return settings
    except:
        pass
    return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    try:
        with open(SETTINGS_FILE, 'w') as f:
            json.dump(settings, f, indent=2)
    except:
        pass


class ProfileManager:
    def __init__(self):
        pass

    def get_window_title(self, hwnd):
        length = GetWindowTextLengthW(hwnd)
        if length == 0:
            return ""
        buffer = ctypes.create_unicode_buffer(length + 1)
        GetWindowTextW(hwnd, buffer, length + 1)
        return buffer.value

    def get_window_class(self, hwnd):
        buffer = ctypes.create_unicode_buffer(256)
        GetClassName(hwnd, buffer, 256)
        return buffer.value

    def get_process_creation_time(self, hwnd):
        pid = wintypes.DWORD()
        GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return 0
        class FILETIME(ctypes.Structure):
            _fields_ = [('dwLowDateTime', wintypes.DWORD), ('dwHighDateTime', wintypes.DWORD)]
        creation_time = FILETIME()
        exit_time = FILETIME()
        kernel_time = FILETIME()
        user_time = FILETIME()
        result = kernel32.GetProcessTimes(handle, ctypes.byref(creation_time), ctypes.byref(exit_time),
                                          ctypes.byref(kernel_time), ctypes.byref(user_time))
        kernel32.CloseHandle(handle)
        if result:
            return (creation_time.dwHighDateTime << 32) | creation_time.dwLowDateTime
        return 0

    def is_profile_window(self, hwnd):
        if not IsWindowVisible(hwnd):
            return False
        title = self.get_window_title(hwnd)
        title_lower = title.lower()
        class_name = self.get_window_class(hwnd).lower()
        if not title:
            return False
        for exclude in EXCLUDE_INDICATORS:
            if exclude in title_lower:
                return False
        for indicator in PROFILE_INDICATORS:
            if indicator in title_lower:
                return True
        for pattern in PROFILE_PATTERNS:
            if re.search(pattern, title):
                if 'chrome_widgetwin' in class_name:
                    return True
        return False

    def get_profile_windows(self):
        windows = []
        def callback(hwnd, lParam):
            if self.is_profile_window(hwnd):
                creation_time = self.get_process_creation_time(hwnd)
                windows.append((hwnd, self.get_window_title(hwnd), creation_time))
            return True
        EnumWindows(EnumWindowsProc(callback), 0)
        windows.sort(key=lambda x: x[2])
        return [(hwnd, title) for hwnd, title, _ in windows]

    def extract_profile_info(self, title):
        """Extract profile name and tab info from window title.
        MLX title formats:
          email | NNNN - C - B - CODE: page title - Chromium
          email | NNNN - C: page title - Chromium
          NNNN - C - H - CODE: page title - Chromium
        We extract just the serial (NNNN) + naming code as profile, page as tab."""
        clean = re.sub(r'\s*-\s*(Chromium|Google Chrome|Mimic)\s*$', '', title, flags=re.IGNORECASE)

        # Strip email prefix: "email | rest" -> "rest"
        if '|' in clean:
            pipe_parts = clean.split('|', 1)
            # Check if left side looks like an email
            if '@' in pipe_parts[0]:
                clean = pipe_parts[1].strip()

        # Split on ": " to separate profile naming from page title
        colon_parts = clean.split(': ', 1)
        profile_part = colon_parts[0].strip()
        tab_info = colon_parts[1].strip() if len(colon_parts) >= 2 else 'Google'

        # Try to extract serial + naming code: "NNNN - X - X - CODE" or "NNNN - X"
        serial_match = re.search(r'(\d{4}(?:\s*-\s*[A-Z](?:\s*-\s*[A-Z])?(?:\s*-\s*\w+)?)?)', profile_part)
        if serial_match:
            profile_name = serial_match.group(1)
        else:
            profile_name = profile_part

        tab_info = self.clean_tab_info(tab_info)
        return profile_name if profile_name else 'Unknown', tab_info if tab_info else 'Google'

    def clean_tab_info(self, tab_info):
        """Remove ticket number prefix like '666-57A-' from tab info"""
        # Match pattern: digits-alphanumeric- at the start (e.g. "666-57A-", "666-60A-")
        cleaned = re.sub(r'^\d{3}-\w{2,4}-', '', tab_info)
        return cleaned

    def show_window(self, hwnd):
        ShowWindow(hwnd, SW_RESTORE)
        SetForegroundWindow(hwnd)

    def minimize_window(self, hwnd):
        ShowWindow(hwnd, SW_MINIMIZE)

    def close_window(self, hwnd):
        user32.PostMessageW(hwnd, 0x0010, 0, 0)  # WM_CLOSE

    def refresh_window(self, hwnd):
        """Send F5 to refresh the window"""
        import keyboard
        ShowWindow(hwnd, SW_RESTORE)
        SetForegroundWindow(hwnd)
        time.sleep(0.1)
        keyboard.press_and_release('F5')


class App:
    def __init__(self):
        self.settings = load_settings()
        self.profile_manager = ProfileManager()
        self.root = None
        self.profiles = []
        self.auto_refresh_job = None
        self.create_window()

    def create_window(self):
        self.root = tk.Tk()
        self.root.title("Multilogin Window Manager")
        self.root.geometry("380x520")
        self.root.resizable(True, True)

        # Top bar with checkboxes
        top_bar = ttk.Frame(self.root)
        top_bar.pack(fill=tk.X, padx=5, pady=2)

        self.hotkeys_var = tk.BooleanVar(value=self.settings.get("hotkeys_enabled", True))
        ttk.Checkbutton(top_bar, text="Hotkeys", variable=self.hotkeys_var,
                        command=self.toggle_hotkeys).pack(side=tk.RIGHT, padx=5)

        self.ontop_var = tk.BooleanVar(value=self.settings.get("always_on_top", False))
        ttk.Checkbutton(top_bar, text="On top", variable=self.ontop_var,
                        command=self.toggle_ontop).pack(side=tk.RIGHT, padx=5)

        # Notebook (tabs)
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Main tab
        self.main_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.main_frame, text="Main")

        # Settings tab
        self.settings_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.settings_frame, text="Settings")

        # About tab
        self.about_frame = ttk.Frame(self.notebook)
        self.notebook.add(self.about_frame, text="About")

        self.create_main_tab()
        self.create_settings_tab()
        self.create_about_tab()

        # Initial refresh
        self.refresh_profiles()

        # Start auto-refresh
        self.start_auto_refresh()

        # Apply on-top if enabled
        if self.settings.get("always_on_top", False):
            self.root.attributes('-topmost', True)

    def create_main_tab(self):
        # Navigation buttons
        nav_frame = ttk.Frame(self.main_frame)
        nav_frame.pack(fill=tk.X, pady=5)

        ttk.Button(nav_frame, text="<<<", width=5, command=self.scroll_left).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text="TOP", width=8, command=self.scroll_top).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text=">>>", width=5, command=self.scroll_right).pack(side=tk.LEFT, padx=2)

        # Discord name input (on main tab)
        name_frame = ttk.Frame(self.main_frame)
        name_frame.pack(fill=tk.X, pady=2)
        ttk.Label(name_frame, text="Name:").pack(side=tk.LEFT, padx=2)
        self.discord_name_var = tk.StringVar(value=self.settings.get("discord_username", "chingching"))
        ttk.Entry(name_frame, textvariable=self.discord_name_var, width=15).pack(side=tk.LEFT, padx=2)

        # Main content frame
        content_frame = ttk.Frame(self.main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, pady=5)

        # Profile list (left side)
        list_frame = ttk.Frame(content_frame)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Profile count label
        self.count_var = tk.StringVar(value="Profile (0)")
        ttk.Label(list_frame, textvariable=self.count_var).pack(anchor=tk.W)

        # Style for treeview with grid lines
        style = ttk.Style()
        style.configure("Grid.Treeview", rowheight=22)

        # Treeview for profiles (extended selection for multi-select)
        columns = ('Profile', 'Tab')
        self.tree = ttk.Treeview(list_frame, columns=columns, show='headings', height=18, selectmode='extended', style="Grid.Treeview")
        self.tree.heading('Profile', text='Profile')
        self.tree.heading('Tab', text='Tab')
        self.tree.column('Profile', width=75, minwidth=50)
        self.tree.column('Tab', width=160, minwidth=80)

        # Alternating row colors for visual separation
        self.tree.tag_configure('oddrow', background='#FFFFFF')
        self.tree.tag_configure('evenrow', background='#F0F0F0')


        # Scrollbar
        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Buttons (right side)
        btn_frame = ttk.Frame(content_frame)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=5)

        # Single window buttons
        ttk.Button(btn_frame, text="Show", width=10, command=self.show_selected).pack(pady=2)
        ttk.Button(btn_frame, text="Minimize", width=10, command=self.minimize_selected).pack(pady=2)
        ttk.Button(btn_frame, text="Close", width=10, command=self.close_selected).pack(pady=2)
        ttk.Button(btn_frame, text="RefreshAll", width=10, command=self.refresh_all).pack(pady=2)

        ttk.Separator(btn_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        # URL input and Open URL button
        ttk.Label(btn_frame, text="URL:").pack(anchor=tk.W)
        self.url_var = tk.StringVar()
        ttk.Entry(btn_frame, textvariable=self.url_var, width=12).pack(pady=2, fill=tk.X)
        ttk.Button(btn_frame, text="Open URL", width=10, command=self.open_url_selected).pack(pady=2)

        ttk.Separator(btn_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        # All windows buttons
        ttk.Button(btn_frame, text="Show All", width=10, command=self.show_all).pack(pady=2)
        ttk.Button(btn_frame, text="MinimizeAll", width=10, command=self.minimize_all).pack(pady=2)
        ttk.Button(btn_frame, text="Close All", width=10, command=self.close_all).pack(pady=2)

        ttk.Separator(btn_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=5)

        # Discord message input
        ttk.Label(btn_frame, text="Message:").pack(anchor=tk.W)
        self.discord_msg_var = tk.StringVar()
        ttk.Entry(btn_frame, textvariable=self.discord_msg_var, width=12).pack(pady=2, fill=tk.X)

        # Discord buttons - Que and Prod
        ttk.Button(btn_frame, text="📷 Que", width=10, command=lambda: self.send_to_discord(1)).pack(pady=2)
        ttk.Button(btn_frame, text="📷 Prod", width=10, command=lambda: self.send_to_discord(2)).pack(pady=2)

        # Refresh button at bottom
        ttk.Button(btn_frame, text="Refresh", width=10, command=self.refresh_profiles).pack(pady=2)

    def create_settings_tab(self):
        # Discord Que
        discord1_frame = ttk.LabelFrame(self.settings_frame, text="Discord Que", padding=10)
        discord1_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(discord1_frame, text="Channel Name:").pack(anchor=tk.W)
        self.channel1_name_var = tk.StringVar(value=self.settings.get("discord_name_1", "Que"))
        ttk.Entry(discord1_frame, textvariable=self.channel1_name_var, width=20).pack(anchor=tk.W, pady=2)

        ttk.Label(discord1_frame, text="Webhook URL:").pack(anchor=tk.W)
        self.webhook1_var = tk.StringVar(value=self.settings.get("discord_webhook_1", ""))
        ttk.Entry(discord1_frame, textvariable=self.webhook1_var, width=45).pack(fill=tk.X, pady=2)

        # Discord Prod
        discord2_frame = ttk.LabelFrame(self.settings_frame, text="Discord Prod", padding=10)
        discord2_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(discord2_frame, text="Channel Name:").pack(anchor=tk.W)
        self.channel2_name_var = tk.StringVar(value=self.settings.get("discord_name_2", "Prod"))
        ttk.Entry(discord2_frame, textvariable=self.channel2_name_var, width=20).pack(anchor=tk.W, pady=2)

        ttk.Label(discord2_frame, text="Webhook URL:").pack(anchor=tk.W)
        self.webhook2_var = tk.StringVar(value=self.settings.get("discord_webhook_2", ""))
        ttk.Entry(discord2_frame, textvariable=self.webhook2_var, width=45).pack(fill=tk.X, pady=2)

        # Your name
        name_frame = ttk.LabelFrame(self.settings_frame, text="Your Info", padding=10)
        name_frame.pack(fill=tk.X, padx=10, pady=5)

        ttk.Label(name_frame, text="Your Discord Name:").pack(anchor=tk.W)
        self.username_var = tk.StringVar(value=self.settings.get("discord_username", "chingching"))
        ttk.Entry(name_frame, textvariable=self.username_var, width=20).pack(anchor=tk.W, pady=2)

        ttk.Button(self.settings_frame, text="Save Settings", command=self.save_discord_settings).pack(pady=10)

        # Status
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(self.settings_frame, textvariable=self.status_var).pack(pady=5)

    def create_about_tab(self):
        ttk.Label(self.about_frame, text="Multilogin Window Manager v2.0",
                  font=('Helvetica', 12, 'bold')).pack(pady=20)
        ttk.Label(self.about_frame, text="With Discord Screenshot Integration").pack()
        ttk.Label(self.about_frame, text="").pack(pady=10)
        ttk.Label(self.about_frame, text="Features:").pack()
        ttk.Label(self.about_frame, text="• View all Multilogin browser profiles").pack()
        ttk.Label(self.about_frame, text="• Show/Minimize/Close individual or all profiles").pack()
        ttk.Label(self.about_frame, text="• Refresh all profiles (F5)").pack()
        ttk.Label(self.about_frame, text="• Send profile list to Discord").pack()

    def toggle_hotkeys(self):
        self.settings["hotkeys_enabled"] = self.hotkeys_var.get()
        save_settings(self.settings)

    def toggle_ontop(self):
        self.settings["always_on_top"] = self.ontop_var.get()
        save_settings(self.settings)
        self.root.attributes('-topmost', self.ontop_var.get())

    def scroll_left(self):
        self.tree.yview_scroll(-5, "units")

    def scroll_right(self):
        self.tree.yview_scroll(5, "units")

    def scroll_top(self):
        self.tree.yview_moveto(0)

    def refresh_profiles(self):
        # Save ALL selected hwnds (for multi-select)
        selected_hwnds = set()
        for item in self.tree.selection():
            tags = self.tree.item(item, 'tags')
            if tags:
                selected_hwnds.add(tags[0])

        # Save scroll position
        scroll_pos = self.tree.yview()

        # Clear existing items
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Get profiles
        self.profiles = self.profile_manager.get_profile_windows()

        # Add to treeview with alternating row colors
        for i, (hwnd, title) in enumerate(self.profiles):
            profile_name, tab_info = self.profile_manager.extract_profile_info(title)
            row_tag = 'evenrow' if i % 2 == 0 else 'oddrow'
            self.tree.insert('', tk.END, values=(profile_name, tab_info), tags=(str(hwnd), row_tag))

        # Restore all selections
        if selected_hwnds:
            items_to_select = []
            for item in self.tree.get_children():
                tags = self.tree.item(item, 'tags')
                if tags and tags[0] in selected_hwnds:
                    items_to_select.append(item)
            if items_to_select:
                self.tree.selection_set(items_to_select)

        # Restore scroll position
        self.tree.yview_moveto(scroll_pos[0])

        # Update count
        self.count_var.set(f"Profile ({len(self.profiles)})")

    def start_auto_refresh(self):
        def do_refresh():
            # Skip refresh if items are selected (to prevent losing Ctrl+click selections)
            if not self.tree.selection():
                self.refresh_profiles()
            interval = self.settings.get("refresh_interval", 3) * 1000
            self.auto_refresh_job = self.root.after(interval, do_refresh)
        self.auto_refresh_job = self.root.after(3000, do_refresh)

    def get_selected_hwnd(self):
        selection = self.tree.selection()
        if not selection:
            return None
        item = selection[0]
        tags = self.tree.item(item, 'tags')
        if tags:
            return int(tags[0])
        return None

    def get_selected_hwnds(self):
        """Get all selected window handles (for multi-select)"""
        selection = self.tree.selection()
        hwnds = []
        for item in selection:
            tags = self.tree.item(item, 'tags')
            if tags:
                hwnds.append(int(tags[0]))
        return hwnds

    def show_selected(self):
        hwnd = self.get_selected_hwnd()
        if hwnd:
            self.profile_manager.show_window(hwnd)

    def minimize_selected(self):
        hwnd = self.get_selected_hwnd()
        if hwnd:
            self.profile_manager.minimize_window(hwnd)

    def close_selected(self):
        hwnd = self.get_selected_hwnd()
        if hwnd:
            self.profile_manager.close_window(hwnd)
            self.root.after(500, self.refresh_profiles)

    def open_url_selected(self):
        """Open URL in all selected profile windows using clipboard paste"""
        url = self.url_var.get().strip()
        if not url:
            messagebox.showerror("Error", "Please enter a URL first!")
            return

        hwnds = self.get_selected_hwnds()
        if not hwnds:
            messagebox.showerror("Error", "Please select at least one profile!")
            return

        try:
            import keyboard
            for hwnd in hwnds:
                # Show the window, bring to front
                ShowWindow(hwnd, SW_RESTORE)
                SetForegroundWindow(hwnd)
                time.sleep(0.15)
                # Copy URL to clipboard
                self.root.clipboard_clear()
                self.root.clipboard_append(url)
                self.root.update()
                # Ctrl+L to focus address bar, then Ctrl+V to paste, then Enter
                keyboard.press_and_release('ctrl+l')
                time.sleep(0.1)
                keyboard.press_and_release('ctrl+v')
                time.sleep(0.1)
                keyboard.press_and_release('enter')
                time.sleep(0.2)

            self.status_var.set(f"Opened URL in {len(hwnds)} profiles")
        except ImportError:
            self.status_var.set("Error: keyboard module not installed")

    def show_all(self):
        for hwnd, title in self.profiles:
            ShowWindow(hwnd, SW_RESTORE)
            time.sleep(0.05)

    def minimize_all(self):
        for hwnd, title in self.profiles:
            ShowWindow(hwnd, SW_MINIMIZE)
            time.sleep(0.02)

    def close_all(self):
        if messagebox.askyesno("Confirm", "Close all profile windows?"):
            for hwnd, title in self.profiles:
                self.profile_manager.close_window(hwnd)
                time.sleep(0.05)
            self.root.after(500, self.refresh_profiles)

    def refresh_all(self):
        """Send F5 to all windows"""
        try:
            import keyboard
            for hwnd, title in self.profiles:
                ShowWindow(hwnd, SW_RESTORE)
                SetForegroundWindow(hwnd)
                time.sleep(0.1)
                keyboard.press_and_release('F5')
                time.sleep(0.1)
            self.status_var.set(f"Refreshed {len(self.profiles)} windows")
        except ImportError:
            self.status_var.set("Error: keyboard module not installed")

    def save_discord_settings(self):
        self.settings["discord_webhook_1"] = self.webhook1_var.get().strip()
        self.settings["discord_webhook_2"] = self.webhook2_var.get().strip()
        self.settings["discord_name_1"] = self.channel1_name_var.get().strip()
        self.settings["discord_name_2"] = self.channel2_name_var.get().strip()
        self.settings["discord_username"] = self.discord_name_var.get().strip()
        save_settings(self.settings)
        self.status_var.set("Settings saved!")

    def capture_window_screenshot(self):
        """Take a screenshot of only the profile list area (treeview)"""
        try:
            from PIL import ImageGrab

            self.root.update()

            # Get the treeview widget's screen position and size
            x = self.tree.winfo_rootx()
            y = self.tree.winfo_rooty()
            w = self.tree.winfo_width()
            h = self.tree.winfo_height()

            # Include the "Profile (X)" label above the treeview
            # Go up a bit to capture the count label
            label_offset = 20
            img = ImageGrab.grab(bbox=(x, y - label_offset, x + w, y + h))
            return img

        except Exception as e:
            # Fallback: capture the whole window
            from PIL import ImageGrab
            self.root.update()
            x = self.root.winfo_rootx()
            y = self.root.winfo_rooty()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            return ImageGrab.grab(bbox=(x, y, x + w, y + h))

    def get_profile_names(self):
        """Get list of profile names from current profiles"""
        profile_names = []
        for hwnd, title in self.profiles:
            profile_name, tab_info = self.profile_manager.extract_profile_info(title)
            profile_names.append(profile_name)
        return profile_names

    def log_to_csv(self, username, channel_name, message, screenshot_url, profile_names):
        """Log Discord send to local CSV file - one row per profile"""
        try:
            log_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "discord_log.csv")
            file_exists = os.path.exists(log_file)
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            with open(log_file, 'a', newline='', encoding='utf-8') as f:
                writer = csv.writer(f)
                if not file_exists:
                    writer.writerow(["Date/Time", "VA Name", "Profile ID", "Channel", "Message", "Screenshot URL"])
                for profile in profile_names:
                    writer.writerow([
                        timestamp,
                        username,
                        profile,
                        channel_name,
                        message,
                        screenshot_url
                    ])
        except Exception as e:
            print(f"Error logging to CSV: {e}")

    def log_to_google_sheets(self, username, channel_name, message, screenshot_url, profile_names):
        """Log Discord send to Google Sheets - one row per profile"""
        try:
            import gspread
            from google.oauth2.service_account import Credentials

            if not os.path.exists(GSHEET_KEY_FILE):
                print("Google Sheets key file not found")
                return

            sheet_id = self.settings.get("google_sheet_id", "")
            if not sheet_id:
                return

            scopes = ['https://www.googleapis.com/auth/spreadsheets']
            creds = Credentials.from_service_account_file(GSHEET_KEY_FILE, scopes=scopes)
            client = gspread.authorize(creds)

            sheet = client.open_by_key(sheet_id).sheet1

            # Add header if sheet is empty
            if sheet.row_count == 0 or not sheet.cell(1, 1).value:
                sheet.append_row(["Date/Time", "VA Name", "Profile ID", "Channel", "Message", "Screenshot URL"])

            # Append one row per profile
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            rows = []
            for profile in profile_names:
                rows.append([
                    timestamp,
                    username,
                    profile,
                    channel_name,
                    message,
                    screenshot_url
                ])

            # Batch append all rows
            if rows:
                sheet.append_rows(rows)

        except Exception as e:
            print(f"Error logging to Google Sheets: {e}")

    def send_to_discord(self, channel_num):
        """Send to Discord channel 1 or 2"""
        if channel_num == 1:
            webhook_url = self.webhook1_var.get().strip()
            channel_name = self.channel1_name_var.get().strip() or "Channel 1"
        else:
            webhook_url = self.webhook2_var.get().strip()
            channel_name = self.channel2_name_var.get().strip() or "Channel 2"

        username = self.discord_name_var.get().strip() or "MLM Manager"

        if not webhook_url:
            messagebox.showerror("Error", f"Please set Discord webhook URL for {channel_name} in Settings tab first!")
            return

        self.status_var.set(f"Sending to {channel_name}...")
        self.root.update()

        def thread_func():
            try:
                # Take screenshot of profile list
                img = self.capture_window_screenshot()

                # Convert to bytes
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='PNG')
                img_byte_arr.seek(0)

                # Send to Discord with screenshot
                custom_msg = self.discord_msg_var.get().strip()
                content = f"**{username}**"
                if custom_msg:
                    content += f" - {custom_msg}"

                payload = {
                    "username": username,
                    "content": content
                }

                files = {
                    "file": ("profiles.png", img_byte_arr, "image/png")
                }

                response = requests.post(webhook_url, data=payload, files=files)

                if response.status_code in [200, 204]:
                    # Extract screenshot URL from Discord response
                    screenshot_url = ""
                    try:
                        resp_json = response.json()
                        if resp_json.get("attachments"):
                            screenshot_url = resp_json["attachments"][0].get("url", "")
                    except:
                        pass

                    # Get current profile names
                    profile_names = self.get_profile_names()
                    if not profile_names:
                        profile_names = ["(no profiles)"]

                    # Log to CSV and Google Sheets - one row per profile
                    self.log_to_csv(username, channel_name, custom_msg, screenshot_url, profile_names)
                    self.log_to_google_sheets(username, channel_name, custom_msg, screenshot_url, profile_names)

                    self.root.after(0, lambda: self.status_var.set(f"✅ Sent to {channel_name}!"))
                else:
                    self.root.after(0, lambda: self.status_var.set(f"❌ Error: {response.status_code}"))

            except Exception as e:
                self.root.after(0, lambda: self.status_var.set(f"❌ Error: {str(e)}"))

        threading.Thread(target=thread_func, daemon=True).start()

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()
