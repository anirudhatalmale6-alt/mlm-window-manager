"""
Multilogin Window Manager v1.2
A tool to manage Multilogin X browser profile windows.

Features:
- List all running Multilogin profiles with checkboxes
- Show current website/tab for each profile
- Select multiple profiles with checkboxes
- Show / Minimize / Close selected profiles
- Show All / Minimize All / Close All
- Open URL in selected profile browsers
- Hotkeys support
- Always on top option
"""

import tkinter as tk
from tkinter import ttk, messagebox
import ctypes
from ctypes import wintypes
import threading
import time
import re
import os
from datetime import datetime

# Try to import PIL for screenshots
try:
    from PIL import ImageGrab
    HAS_PIL = True
except ImportError:
    HAS_PIL = False

# Windows API constants
SW_MINIMIZE = 6
SW_RESTORE = 9
SW_SHOW = 5
SW_HIDE = 0
GW_HWNDNEXT = 2
WM_CLOSE = 0x0010
PROCESS_QUERY_INFORMATION = 0x0400
PROCESS_VM_READ = 0x0010

# Load Windows DLLs
user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
psapi = ctypes.windll.psapi

def get_screen_size():
    """Get screen width and height"""
    return user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)

def resize_window_33(hwnd, index=0):
    """Resize window to 33% of screen width and position it"""
    screen_w, screen_h = get_screen_size()
    win_w = screen_w // 3
    win_h = screen_h - 40  # Leave space for taskbar
    x = (index % 3) * win_w  # Position based on index (0, 1, 2)
    y = 0
    user32.MoveWindow(hwnd, x, y, win_w, win_h, True)

class MultiloginWindowManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Multilogin Window Manager v1.9")
        self.root.geometry("500x500")
        self.root.resizable(True, True)

        # Profile data
        self.profiles = []
        self.selected_index = None

        # Checkbox states
        self.checkbox_vars = {}

        # Create UI
        self.create_ui()

        # Start refresh thread
        self.running = True
        self.refresh_thread = threading.Thread(target=self.auto_refresh, daemon=True)
        self.refresh_thread.start()

        # Initial refresh
        self.refresh_profiles()

        # Bind hotkeys
        self.setup_hotkeys()

    def create_ui(self):
        # Top frame with tabs
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

        # === Main Tab Content ===

        # Top options frame (Hotkeys, On top checkboxes)
        top_options = ttk.Frame(self.main_frame)
        top_options.pack(fill=tk.X, padx=5, pady=2)

        self.hotkeys_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top_options, text="Hotkeys", variable=self.hotkeys_var).pack(side=tk.RIGHT, padx=5)

        self.ontop_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(top_options, text="On top", variable=self.ontop_var,
                        command=self.toggle_ontop).pack(side=tk.RIGHT, padx=5)

        # Navigation buttons
        nav_frame = ttk.Frame(self.main_frame)
        nav_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Button(nav_frame, text="<<<", width=6, command=self.nav_prev).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text="TOP", width=6, command=self.nav_top).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text=">>>", width=6, command=self.nav_next).pack(side=tk.LEFT, padx=2)

        # Main content area with list on left and buttons on right
        content_frame = ttk.Frame(self.main_frame)
        content_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Right side - Buttons (pack FIRST so they get priority space)
        btn_frame = ttk.Frame(content_frame)
        btn_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=(10, 0))

        # Single profile buttons
        ttk.Button(btn_frame, text="Show", width=10, command=self.show_checked).pack(pady=2)
        ttk.Button(btn_frame, text="Minimize", width=10, command=self.minimize_checked).pack(pady=2)
        ttk.Button(btn_frame, text="RefreshAll", width=10, command=self.refresh_profiles).pack(pady=2)
        ttk.Button(btn_frame, text="Close", width=10, command=self.close_checked).pack(pady=2)

        ttk.Separator(btn_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # All profiles buttons
        ttk.Button(btn_frame, text="Show All", width=10, command=self.show_all).pack(pady=2)
        ttk.Button(btn_frame, text="MinimizeAll", width=10, command=self.minimize_all).pack(pady=2)
        ttk.Button(btn_frame, text="Close All", width=10, command=self.close_all).pack(pady=2)

        ttk.Separator(btn_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # Selection buttons
        ttk.Button(btn_frame, text="Select All", width=10, command=self.select_all).pack(pady=2)
        ttk.Button(btn_frame, text="Deselect All", width=10, command=self.deselect_all).pack(pady=2)

        ttk.Separator(btn_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        # Screenshot button
        ttk.Button(btn_frame, text="Screenshot", width=10, command=self.take_screenshot).pack(pady=2)

        # Left side - Profile list with checkboxes
        list_frame = ttk.Frame(content_frame)
        list_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # Column headers with profile count
        header_frame = ttk.Frame(list_frame)
        header_frame.pack(fill=tk.X)
        self.profile_count_label = ttk.Label(header_frame, text="Profile (0)", width=15, anchor=tk.W, font=("", 9, "bold"))
        self.profile_count_label.pack(side=tk.LEFT, padx=(20, 5))
        ttk.Label(header_frame, text="Tab", anchor=tk.W, font=("", 9, "bold")).pack(side=tk.LEFT, padx=5)

        # Scrollable list
        list_container = ttk.Frame(list_frame)
        list_container.pack(fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(list_container, highlightthickness=0, bg="white")
        scrollbar_y = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.canvas.yview)
        scrollbar_x = ttk.Scrollbar(list_container, orient=tk.HORIZONTAL, command=self.canvas.xview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        self.canvas.bind('<Configure>', self.on_canvas_configure)
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)

        scrollbar_y.pack(side=tk.RIGHT, fill=tk.Y)
        scrollbar_x.pack(side=tk.BOTTOM, fill=tk.X)
        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        # URL input at bottom (no frame, like original)
        url_row = ttk.Frame(self.main_frame)
        url_row.pack(fill=tk.X, padx=5, pady=5)

        self.url_entry = ttk.Entry(url_row)
        self.url_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        self.url_entry.insert(0, "https://")

        ttk.Button(url_row, text="Apply", width=8, command=self.open_url_checked).pack(side=tk.RIGHT)

        # Status bar
        self.status_var = tk.StringVar(value="Ready")
        status_bar = ttk.Label(self.main_frame, textvariable=self.status_var, relief=tk.SUNKEN)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=5, pady=2)

        # === Settings Tab Content ===
        settings_content = ttk.Frame(self.settings_frame)
        settings_content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(settings_content, text="Hotkey Settings:", font=("", 10, "bold")).pack(anchor=tk.W, pady=5)
        ttk.Label(settings_content, text="Ctrl+Shift+Left: Previous profile").pack(anchor=tk.W)
        ttk.Label(settings_content, text="Ctrl+Shift+Right: Next profile").pack(anchor=tk.W)
        ttk.Label(settings_content, text="Ctrl+Shift+Up: Show current profile").pack(anchor=tk.W)
        ttk.Label(settings_content, text="Ctrl+Shift+H: Toggle hotkeys").pack(anchor=tk.W)

        ttk.Separator(settings_content, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)

        ttk.Label(settings_content, text="Refresh Interval (seconds):").pack(anchor=tk.W, pady=5)
        self.refresh_interval = ttk.Spinbox(settings_content, from_=1, to=60, width=10)
        self.refresh_interval.set(3)
        self.refresh_interval.pack(anchor=tk.W)

        # === About Tab Content ===
        about_content = ttk.Frame(self.about_frame)
        about_content.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        ttk.Label(about_content, text="Multilogin Window Manager v1.2", font=("", 12, "bold")).pack(pady=10)
        ttk.Label(about_content, text="Manage your Multilogin X browser profiles easily.").pack()
        ttk.Label(about_content, text="").pack()
        ttk.Label(about_content, text="Features:").pack(anchor=tk.W)
        ttk.Label(about_content, text="- View all running profiles with checkboxes").pack(anchor=tk.W)
        ttk.Label(about_content, text="- Select multiple profiles at once").pack(anchor=tk.W)
        ttk.Label(about_content, text="- Show/Minimize/Close selected windows").pack(anchor=tk.W)
        ttk.Label(about_content, text="- Open URL in selected profiles").pack(anchor=tk.W)
        ttk.Label(about_content, text="- Hotkeys support").pack(anchor=tk.W)

    def on_canvas_configure(self, event):
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def on_mousewheel(self, event):
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def setup_hotkeys(self):
        self.root.bind("<Control-Shift-Left>", lambda e: self.nav_prev())
        self.root.bind("<Control-Shift-Right>", lambda e: self.nav_next())
        self.root.bind("<Control-Shift-Up>", lambda e: self.show_current())
        self.root.bind("<Control-Shift-h>", lambda e: self.toggle_hotkeys())

    def toggle_ontop(self):
        self.root.attributes("-topmost", self.ontop_var.get())

    def toggle_hotkeys(self):
        self.hotkeys_var.set(not self.hotkeys_var.get())

    def get_multilogin_windows(self):
        windows = []

        def enum_callback(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value

                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

                    try:
                        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid.value)
                        if handle:
                            exe_path = ctypes.create_unicode_buffer(260)
                            psapi.GetModuleFileNameExW(handle, None, exe_path, 260)
                            kernel32.CloseHandle(handle)
                            exe_name = exe_path.value.split("\\")[-1].lower()

                            if "mimic" in exe_name or ("chrome" in exe_name and self.is_multilogin_profile(title)):
                                profile_name = self.extract_profile_name(title)
                                tab_title = self.extract_tab_title(title)

                                windows.append({
                                    "hwnd": hwnd,
                                    "title": title,
                                    "profile": profile_name,
                                    "tab": tab_title,
                                    "pid": pid.value
                                })
                    except:
                        pass
            return True

        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(EnumWindowsProc(enum_callback), 0)

        # Deduplicate by PID - keep only one window per browser profile
        seen_pids = {}
        unique_windows = []
        for w in windows:
            pid = w["pid"]
            if pid not in seen_pids:
                seen_pids[pid] = w
                unique_windows.append(w)
            else:
                # Keep the window with the more informative title (longer usually means actual page)
                if len(w["title"]) > len(seen_pids[pid]["title"]):
                    # Replace with better window
                    idx = unique_windows.index(seen_pids[pid])
                    unique_windows[idx] = w
                    seen_pids[pid] = w

        return unique_windows

    def is_multilogin_profile(self, title):
        indicators = ["--proxy", "DC", "Profile", "Mimic"]
        return any(ind in title for ind in indicators)

    def extract_profile_name(self, title):
        match = re.search(r'(DC\d+)', title)
        if match:
            return match.group(1)

        if " - " in title:
            parts = title.split(" - ")
            if len(parts) >= 2:
                return parts[0][:18] + ".." if len(parts[0]) > 18 else parts[0]

        for sep in [" --", " |", " —"]:
            if sep in title:
                return title.split(sep)[0][:18]

        return title[:18] + ".." if len(title) > 18 else title

    def extract_tab_title(self, title):
        # Browser titles are usually: "Page Title - Browser Name"
        # We want the page title (first part before " - ")
        if " - " in title:
            parts = title.split(" - ")
            # First part is usually the page/website title
            tab = parts[0].strip()
            # If first part looks like a profile name (DC##), try second part
            if tab.startswith("DC") and tab[2:].split()[0].isdigit() and len(parts) > 1:
                tab = parts[1].strip()
            return tab[:20] + ".." if len(tab) > 20 else tab

        return title[:20] + ".." if len(title) > 20 else title

    def refresh_profiles(self):
        old_states = {}
        for i, var in self.checkbox_vars.items():
            if i < len(self.profiles):
                old_states[self.profiles[i]["title"]] = var.get()

        self.profiles = self.get_multilogin_windows()

        for widget in self.scrollable_frame.winfo_children():
            widget.destroy()

        self.checkbox_vars = {}

        for i, profile in enumerate(self.profiles):
            row_frame = ttk.Frame(self.scrollable_frame)
            row_frame.pack(fill=tk.X, pady=1)

            var = tk.BooleanVar(value=old_states.get(profile["title"], False))
            self.checkbox_vars[i] = var
            cb = ttk.Checkbutton(row_frame, variable=var)
            cb.pack(side=tk.LEFT, padx=2)

            profile_label = ttk.Label(row_frame, text=profile["profile"], width=15, anchor=tk.W, cursor="hand2")
            profile_label.pack(side=tk.LEFT, padx=2)
            profile_label.bind("<Button-1>", lambda e, idx=i: self.on_profile_click(idx))
            profile_label.bind("<Double-1>", lambda e, idx=i: self.show_profile(idx))

            tab_label = ttk.Label(row_frame, text=profile["tab"], anchor=tk.W)
            tab_label.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
            tab_label.bind("<Button-1>", lambda e, idx=i: self.on_profile_click(idx))
            tab_label.bind("<Double-1>", lambda e, idx=i: self.show_profile(idx))

        # Update profile count in header
        self.profile_count_label.config(text=f"Profile ({len(self.profiles)})")
        self.status_var.set("Ready")

    def on_profile_click(self, index):
        if index in self.checkbox_vars:
            self.checkbox_vars[index].set(not self.checkbox_vars[index].get())
        self.selected_index = index

    def show_profile(self, index):
        if index < len(self.profiles):
            profile = self.profiles[index]
            hwnd = profile["hwnd"]
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            self.status_var.set(f"Showing: {profile['profile']}")

    def auto_refresh(self):
        while self.running:
            try:
                interval = int(self.refresh_interval.get())
            except:
                interval = 3
            time.sleep(interval)
            if self.running:
                self.root.after(0, self.refresh_profiles)

    def get_checked_profiles(self):
        checked = []
        for i, var in self.checkbox_vars.items():
            if var.get() and i < len(self.profiles):
                checked.append(self.profiles[i])
        return checked

    def select_all(self):
        for var in self.checkbox_vars.values():
            var.set(True)
        self.status_var.set(f"Selected all {len(self.profiles)} profiles")

    def deselect_all(self):
        for var in self.checkbox_vars.values():
            var.set(False)
        self.status_var.set("Deselected all profiles")

    def take_screenshot(self):
        """Take screenshot of the MLM Window Manager and save to Screenshots folder"""
        if not HAS_PIL:
            messagebox.showerror("Error", "PIL/Pillow not installed.\nRun: pip install Pillow")
            return

        # Create Screenshots folder next to the exe/script
        script_dir = os.path.dirname(os.path.abspath(__file__))
        screenshots_dir = os.path.join(script_dir, "Screenshots")
        if not os.path.exists(screenshots_dir):
            os.makedirs(screenshots_dir)

        # Get window position
        x = self.root.winfo_rootx()
        y = self.root.winfo_rooty()
        width = self.root.winfo_width()
        height = self.root.winfo_height()

        # Capture screenshot
        screenshot = ImageGrab.grab(bbox=(x, y, x + width, y + height))

        # Save with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"MLM_Screenshot_{timestamp}.png"
        filepath = os.path.join(screenshots_dir, filename)
        screenshot.save(filepath)

        self.status_var.set(f"Saved: {filename}")

        # Open the Screenshots folder
        os.startfile(screenshots_dir)

    def show_checked(self):
        checked = self.get_checked_profiles()
        if not checked:
            self.status_var.set("No profiles selected")
            return
        for profile in checked:
            user32.ShowWindow(profile["hwnd"], SW_RESTORE)
            user32.SetForegroundWindow(profile["hwnd"])
            time.sleep(0.1)
        self.status_var.set(f"Showing {len(checked)} selected profiles")

    def minimize_checked(self):
        checked = self.get_checked_profiles()
        if not checked:
            self.status_var.set("No profiles selected")
            return
        for profile in checked:
            user32.ShowWindow(profile["hwnd"], SW_MINIMIZE)
        self.status_var.set(f"Minimized {len(checked)} selected profiles")

    def close_checked(self):
        checked = self.get_checked_profiles()
        if not checked:
            self.status_var.set("No profiles selected")
            return
        if messagebox.askyesno("Confirm", f"Close {len(checked)} selected profiles?"):
            for profile in checked:
                user32.PostMessageW(profile["hwnd"], WM_CLOSE, 0, 0)
            self.status_var.set(f"Closing {len(checked)} profiles...")
            self.root.after(1000, self.refresh_profiles)

    def show_all(self):
        for profile in self.profiles:
            user32.ShowWindow(profile["hwnd"], SW_RESTORE)
        self.status_var.set(f"Showing all {len(self.profiles)} profiles")

    def minimize_all(self):
        for profile in self.profiles:
            user32.ShowWindow(profile["hwnd"], SW_MINIMIZE)
        self.status_var.set(f"Minimized all {len(self.profiles)} profiles")

    def close_all(self):
        if self.profiles and messagebox.askyesno("Confirm", f"Close all {len(self.profiles)} profiles?"):
            for profile in self.profiles:
                user32.PostMessageW(profile["hwnd"], WM_CLOSE, 0, 0)
            self.status_var.set(f"Closing all profiles...")
            self.root.after(1000, self.refresh_profiles)

    def open_url_checked(self):
        url = self.url_entry.get().strip()
        if not url or url == "https://":
            messagebox.showwarning("Warning", "Please enter a valid URL")
            return

        if not url.startswith("http"):
            url = "https://" + url

        checked = self.get_checked_profiles()
        if not checked:
            if messagebox.askyesno("No Selection", "No profiles selected. Apply to ALL profiles?"):
                checked = self.profiles
            else:
                return

        count = 0
        for profile in checked:
            hwnd = profile["hwnd"]
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            time.sleep(0.2)
            self.send_url_to_window(hwnd, url)
            count += 1
            time.sleep(0.3)

        self.status_var.set(f"Opened URL in {count} profiles")

    def send_url_to_window(self, hwnd, url):
        VK_CONTROL = 0x11
        VK_T = 0x54  # T key for new tab
        VK_RETURN = 0x0D
        VK_V = 0x56

        # Open new tab with Ctrl+T
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_T, 0, 0, 0)
        user32.keybd_event(VK_T, 0, 2, 0)
        user32.keybd_event(VK_CONTROL, 0, 2, 0)

        time.sleep(0.15)

        # Copy URL to clipboard and paste
        self.root.clipboard_clear()
        self.root.clipboard_append(url)

        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 2, 0)
        user32.keybd_event(VK_CONTROL, 0, 2, 0)

        time.sleep(0.1)

        # Press Enter to navigate
        user32.keybd_event(VK_RETURN, 0, 0, 0)
        user32.keybd_event(VK_RETURN, 0, 2, 0)

    def show_current(self):
        if self.selected_index is not None and self.selected_index < len(self.profiles):
            self.show_profile(self.selected_index)

    def nav_prev(self):
        if not self.profiles:
            return
        if self.selected_index is None:
            self.selected_index = 0
        else:
            self.selected_index = (self.selected_index - 1) % len(self.profiles)
        self.show_profile(self.selected_index)

    def nav_next(self):
        if not self.profiles:
            return
        if self.selected_index is None:
            self.selected_index = 0
        else:
            self.selected_index = (self.selected_index + 1) % len(self.profiles)
        self.show_profile(self.selected_index)

    def nav_top(self):
        if self.profiles:
            self.selected_index = 0
            self.show_profile(0)

    def on_close(self):
        self.running = False
        self.root.destroy()


def main():
    root = tk.Tk()

    try:
        root.iconbitmap("icon.ico")
    except:
        pass

    app = MultiloginWindowManager(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
