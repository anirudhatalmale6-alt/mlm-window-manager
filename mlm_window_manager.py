"""
Multilogin Window Manager v1.1
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
import subprocess
import json
import threading
import time
import re

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

class MultiloginWindowManager:
    def __init__(self, root):
        self.root = root
        self.root.title("Multilogin Window Manager v1.1")
        self.root.geometry("550x650")
        self.root.resizable(True, True)

        # Profile data
        self.profiles = []
        self.selected_index = None

        # Checkbox states - dictionary of profile index -> BooleanVar
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

        # Options frame
        options_frame = ttk.Frame(self.main_frame)
        options_frame.pack(fill=tk.X, padx=5, pady=5)

        self.hotkeys_var = tk.BooleanVar(value=True)
        self.hotkeys_cb = ttk.Checkbutton(options_frame, text="Hotkeys", variable=self.hotkeys_var)
        self.hotkeys_cb.pack(side=tk.LEFT, padx=5)

        self.ontop_var = tk.BooleanVar(value=False)
        self.ontop_cb = ttk.Checkbutton(options_frame, text="On top", variable=self.ontop_var,
                                         command=self.toggle_ontop)
        self.ontop_cb.pack(side=tk.LEFT, padx=5)

        # Navigation buttons
        nav_frame = ttk.Frame(self.main_frame)
        nav_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(nav_frame, text="<<<", width=8, command=self.nav_prev).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text="TOP", width=8, command=self.nav_top).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text=">>>", width=8, command=self.nav_next).pack(side=tk.LEFT, padx=2)
        ttk.Button(nav_frame, text="Refresh", width=8, command=self.refresh_profiles).pack(side=tk.RIGHT, padx=2)

        # Selection buttons
        select_frame = ttk.Frame(self.main_frame)
        select_frame.pack(fill=tk.X, padx=5, pady=2)

        ttk.Button(select_frame, text="Select All", width=10, command=self.select_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(select_frame, text="Deselect All", width=10, command=self.deselect_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(select_frame, text="Invert", width=8, command=self.invert_selection).pack(side=tk.LEFT, padx=2)

        # Profile list frame with canvas for checkboxes
        list_container = ttk.LabelFrame(self.main_frame, text="Profiles")
        list_container.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        # Create canvas with scrollbar for the checkbox list
        self.canvas = tk.Canvas(list_container, highlightthickness=0)
        scrollbar = ttk.Scrollbar(list_container, orient=tk.VERTICAL, command=self.canvas.yview)
        self.scrollable_frame = ttk.Frame(self.canvas)

        self.scrollable_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        self.canvas_window = self.canvas.create_window((0, 0), window=self.scrollable_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=scrollbar.set)

        # Bind canvas resize to adjust scrollable frame width
        self.canvas.bind('<Configure>', self.on_canvas_configure)

        # Bind mousewheel
        self.canvas.bind_all("<MouseWheel>", self.on_mousewheel)

        self.canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)

        # Column headers
        header_frame = ttk.Frame(self.scrollable_frame)
        header_frame.pack(fill=tk.X, pady=2)
        ttk.Label(header_frame, text="", width=3).pack(side=tk.LEFT)  # Checkbox column
        ttk.Label(header_frame, text="Profile", width=18, anchor=tk.W, font=("", 9, "bold")).pack(side=tk.LEFT, padx=2)
        ttk.Label(header_frame, text="Current Tab", anchor=tk.W, font=("", 9, "bold")).pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)

        ttk.Separator(self.scrollable_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=2)

        # Profile rows container
        self.profile_rows_frame = ttk.Frame(self.scrollable_frame)
        self.profile_rows_frame.pack(fill=tk.BOTH, expand=True)

        # Selected profile buttons
        selected_frame = ttk.LabelFrame(self.main_frame, text="Selected Profiles Actions")
        selected_frame.pack(fill=tk.X, padx=5, pady=5)

        btn_row1 = ttk.Frame(selected_frame)
        btn_row1.pack(fill=tk.X, pady=2)

        ttk.Button(btn_row1, text="Show Selected", width=14, command=self.show_checked).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row1, text="Minimize Selected", width=14, command=self.minimize_checked).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row1, text="Close Selected", width=14, command=self.close_checked).pack(side=tk.LEFT, padx=2)

        # All profiles buttons
        all_frame = ttk.LabelFrame(self.main_frame, text="All Profiles Actions")
        all_frame.pack(fill=tk.X, padx=5, pady=5)

        btn_row2 = ttk.Frame(all_frame)
        btn_row2.pack(fill=tk.X, pady=2)

        ttk.Button(btn_row2, text="Show All", width=12, command=self.show_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row2, text="Minimize All", width=12, command=self.minimize_all).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_row2, text="Close All", width=12, command=self.close_all).pack(side=tk.LEFT, padx=2)

        # URL input frame
        url_frame = ttk.LabelFrame(self.main_frame, text="Open URL in Selected Profiles")
        url_frame.pack(fill=tk.X, padx=5, pady=5)

        url_row = ttk.Frame(url_frame)
        url_row.pack(fill=tk.X, padx=5, pady=5)

        self.url_entry = ttk.Entry(url_row, width=50)
        self.url_entry.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
        self.url_entry.insert(0, "https://")

        ttk.Button(url_row, text="Apply", width=10, command=self.open_url_checked).pack(side=tk.RIGHT, padx=2)

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

        ttk.Label(about_content, text="Multilogin Window Manager v1.1", font=("", 12, "bold")).pack(pady=10)
        ttk.Label(about_content, text="Manage your Multilogin X browser profiles easily.").pack()
        ttk.Label(about_content, text="").pack()
        ttk.Label(about_content, text="Features:").pack(anchor=tk.W)
        ttk.Label(about_content, text="- View all running profiles with checkboxes").pack(anchor=tk.W)
        ttk.Label(about_content, text="- Select multiple profiles at once").pack(anchor=tk.W)
        ttk.Label(about_content, text="- Show/Minimize/Close selected windows").pack(anchor=tk.W)
        ttk.Label(about_content, text="- Open URL in selected profiles").pack(anchor=tk.W)
        ttk.Label(about_content, text="- Hotkeys support").pack(anchor=tk.W)

    def on_canvas_configure(self, event):
        """Handle canvas resize"""
        self.canvas.itemconfig(self.canvas_window, width=event.width)

    def on_mousewheel(self, event):
        """Handle mousewheel scrolling"""
        self.canvas.yview_scroll(int(-1*(event.delta/120)), "units")

    def setup_hotkeys(self):
        """Setup global hotkeys using keyboard listener"""
        self.root.bind("<Control-Shift-Left>", lambda e: self.nav_prev())
        self.root.bind("<Control-Shift-Right>", lambda e: self.nav_next())
        self.root.bind("<Control-Shift-Up>", lambda e: self.show_current())
        self.root.bind("<Control-Shift-h>", lambda e: self.toggle_hotkeys())

    def toggle_ontop(self):
        """Toggle always on top"""
        self.root.attributes("-topmost", self.ontop_var.get())

    def toggle_hotkeys(self):
        """Toggle hotkeys on/off"""
        self.hotkeys_var.set(not self.hotkeys_var.get())

    def get_multilogin_windows(self):
        """Find all Multilogin browser windows"""
        windows = []

        def enum_callback(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                # Get window title
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value

                    # Get process name
                    pid = wintypes.DWORD()
                    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))

                    try:
                        handle = kernel32.OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ, False, pid.value)
                        if handle:
                            exe_path = ctypes.create_unicode_buffer(260)
                            psapi.GetModuleFileNameExW(handle, None, exe_path, 260)
                            kernel32.CloseHandle(handle)
                            exe_name = exe_path.value.split("\\")[-1].lower()

                            # Check if it's a Multilogin browser (usually mimic browser or chrome-based)
                            if "mimic" in exe_name or ("chrome" in exe_name and self.is_multilogin_profile(title)):
                                # Extract profile name from title
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

        # Enum windows callback type
        EnumWindowsProc = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
        user32.EnumWindows(EnumWindowsProc(enum_callback), 0)

        return windows

    def is_multilogin_profile(self, title):
        """Check if window title indicates a Multilogin profile"""
        indicators = ["--proxy", "DC", "Profile", "Mimic"]
        return any(ind in title for ind in indicators)

    def extract_profile_name(self, title):
        """Extract profile name from window title"""
        # Pattern 1: DC## format
        match = re.search(r'(DC\d+)', title)
        if match:
            return match.group(1)

        # Pattern 2: Before " - " separator
        if " - " in title:
            parts = title.split(" - ")
            if len(parts) >= 2:
                return parts[0][:20] + "..." if len(parts[0]) > 20 else parts[0]

        # Pattern 3: First part before common browser indicators
        for sep in [" --", " |", " —"]:
            if sep in title:
                return title.split(sep)[0][:20]

        return title[:20] + "..." if len(title) > 20 else title

    def extract_tab_title(self, title):
        """Extract current tab title from window title"""
        if " - " in title:
            parts = title.split(" - ")
            if len(parts) >= 2:
                tab = parts[-2] if len(parts) > 2 else parts[-1]
                return tab[:40] + "..." if len(tab) > 40 else tab

        return title[:40] + "..." if len(title) > 40 else title

    def refresh_profiles(self):
        """Refresh the profile list with checkboxes"""
        # Save current checkbox states before refresh
        old_states = {}
        for i, var in self.checkbox_vars.items():
            if i < len(self.profiles):
                # Use profile title as key to preserve state across refreshes
                old_states[self.profiles[i]["title"]] = var.get()

        self.profiles = self.get_multilogin_windows()

        # Clear existing profile rows
        for widget in self.profile_rows_frame.winfo_children():
            widget.destroy()

        self.checkbox_vars = {}

        # Add profile rows with checkboxes
        for i, profile in enumerate(self.profiles):
            row_frame = ttk.Frame(self.profile_rows_frame)
            row_frame.pack(fill=tk.X, pady=1)

            # Checkbox
            var = tk.BooleanVar(value=old_states.get(profile["title"], False))
            self.checkbox_vars[i] = var
            cb = ttk.Checkbutton(row_frame, variable=var)
            cb.pack(side=tk.LEFT, padx=2)

            # Profile name (clickable to show window)
            profile_label = ttk.Label(row_frame, text=profile["profile"], width=18, anchor=tk.W, cursor="hand2")
            profile_label.pack(side=tk.LEFT, padx=2)
            profile_label.bind("<Button-1>", lambda e, idx=i: self.on_profile_click(idx))
            profile_label.bind("<Double-1>", lambda e, idx=i: self.show_profile(idx))

            # Tab title
            tab_label = ttk.Label(row_frame, text=profile["tab"], anchor=tk.W)
            tab_label.pack(side=tk.LEFT, padx=2, fill=tk.X, expand=True)
            tab_label.bind("<Button-1>", lambda e, idx=i: self.on_profile_click(idx))
            tab_label.bind("<Double-1>", lambda e, idx=i: self.show_profile(idx))

        self.status_var.set(f"Found {len(self.profiles)} profile(s)")

    def on_profile_click(self, index):
        """Handle single click on profile - toggle checkbox"""
        if index in self.checkbox_vars:
            self.checkbox_vars[index].set(not self.checkbox_vars[index].get())
        self.selected_index = index

    def show_profile(self, index):
        """Show specific profile window"""
        if index < len(self.profiles):
            profile = self.profiles[index]
            hwnd = profile["hwnd"]
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.SetForegroundWindow(hwnd)
            self.status_var.set(f"Showing: {profile['profile']}")

    def auto_refresh(self):
        """Auto refresh in background"""
        while self.running:
            try:
                interval = int(self.refresh_interval.get())
            except:
                interval = 3
            time.sleep(interval)
            if self.running:
                self.root.after(0, self.refresh_profiles)

    def get_checked_profiles(self):
        """Get list of profiles that are checked"""
        checked = []
        for i, var in self.checkbox_vars.items():
            if var.get() and i < len(self.profiles):
                checked.append(self.profiles[i])
        return checked

    def select_all(self):
        """Select all checkboxes"""
        for var in self.checkbox_vars.values():
            var.set(True)
        self.status_var.set(f"Selected all {len(self.profiles)} profiles")

    def deselect_all(self):
        """Deselect all checkboxes"""
        for var in self.checkbox_vars.values():
            var.set(False)
        self.status_var.set("Deselected all profiles")

    def invert_selection(self):
        """Invert checkbox selection"""
        for var in self.checkbox_vars.values():
            var.set(not var.get())
        count = len(self.get_checked_profiles())
        self.status_var.set(f"Inverted selection: {count} selected")

    def show_checked(self):
        """Show all checked profile windows"""
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
        """Minimize all checked profile windows"""
        checked = self.get_checked_profiles()
        if not checked:
            self.status_var.set("No profiles selected")
            return
        for profile in checked:
            user32.ShowWindow(profile["hwnd"], SW_MINIMIZE)
        self.status_var.set(f"Minimized {len(checked)} selected profiles")

    def close_checked(self):
        """Close all checked profile windows"""
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
        """Show all profile windows"""
        for profile in self.profiles:
            user32.ShowWindow(profile["hwnd"], SW_RESTORE)
        self.status_var.set(f"Showing all {len(self.profiles)} profiles")

    def minimize_all(self):
        """Minimize all profile windows"""
        for profile in self.profiles:
            user32.ShowWindow(profile["hwnd"], SW_MINIMIZE)
        self.status_var.set(f"Minimized all {len(self.profiles)} profiles")

    def close_all(self):
        """Close all profile windows"""
        if self.profiles and messagebox.askyesno("Confirm", f"Close all {len(self.profiles)} profiles?"):
            for profile in self.profiles:
                user32.PostMessageW(profile["hwnd"], WM_CLOSE, 0, 0)
            self.status_var.set(f"Closing all profiles...")
            self.root.after(1000, self.refresh_profiles)

    def open_url_checked(self):
        """Open URL in all checked profile browsers"""
        url = self.url_entry.get().strip()
        if not url or url == "https://":
            messagebox.showwarning("Warning", "Please enter a valid URL")
            return

        if not url.startswith("http"):
            url = "https://" + url

        checked = self.get_checked_profiles()
        if not checked:
            # If nothing selected, apply to all profiles
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
        """Send URL to browser window"""
        VK_CONTROL = 0x11
        VK_L = 0x4C
        VK_RETURN = 0x0D
        VK_V = 0x56

        # Focus address bar with Ctrl+L
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_L, 0, 0, 0)
        user32.keybd_event(VK_L, 0, 2, 0)
        user32.keybd_event(VK_CONTROL, 0, 2, 0)

        time.sleep(0.1)

        # Use clipboard to paste URL
        self.root.clipboard_clear()
        self.root.clipboard_append(url)

        # Paste with Ctrl+V
        user32.keybd_event(VK_CONTROL, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 0, 0)
        user32.keybd_event(VK_V, 0, 2, 0)
        user32.keybd_event(VK_CONTROL, 0, 2, 0)

        time.sleep(0.1)

        # Press Enter
        user32.keybd_event(VK_RETURN, 0, 0, 0)
        user32.keybd_event(VK_RETURN, 0, 2, 0)

    def show_current(self):
        """Show currently selected profile"""
        if self.selected_index is not None and self.selected_index < len(self.profiles):
            self.show_profile(self.selected_index)

    def nav_prev(self):
        """Navigate to previous profile"""
        if not self.profiles:
            return
        if self.selected_index is None:
            self.selected_index = 0
        else:
            self.selected_index = (self.selected_index - 1) % len(self.profiles)
        self.show_profile(self.selected_index)

    def nav_next(self):
        """Navigate to next profile"""
        if not self.profiles:
            return
        if self.selected_index is None:
            self.selected_index = 0
        else:
            self.selected_index = (self.selected_index + 1) % len(self.profiles)
        self.show_profile(self.selected_index)

    def nav_top(self):
        """Navigate to first profile and bring to front"""
        if self.profiles:
            self.selected_index = 0
            self.show_profile(0)

    def on_close(self):
        """Handle window close"""
        self.running = False
        self.root.destroy()


def main():
    root = tk.Tk()

    # Set icon if available
    try:
        root.iconbitmap("icon.ico")
    except:
        pass

    app = MultiloginWindowManager(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()
