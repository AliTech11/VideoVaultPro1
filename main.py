import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import sys
import re
import json
from datetime import datetime
import yt_dlp

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "youtube":  {"main": "#FF0000", "hover": "#CC0000", "light": "#FF4444"},
    "tiktok":   {"main": "#010101", "hover": "#333333", "light": "#69C9D0"},
    "facebook": {"main": "#1877F2", "hover": "#0d5bb5", "light": "#4299F7"},
    "bg":       "#0F0F1A",
    "card":     "#1A1A2E",
    "card2":    "#16213E",
    "text":     "#FFFFFF",
    "subtext":  "#A0A0C0",
    "success":  "#00E676",
    "error":    "#FF5252",
    "warning":  "#FFD740",
    "accent":   "#7C4DFF",
}


def detect_platform(url: str) -> str:
    url = url.lower()
    if "youtube.com" in url or "youtu.be" in url:
        return "youtube"
    if "tiktok.com" in url:
        return "tiktok"
    if "facebook.com" in url or "fb.com" in url or "fb.watch" in url:
        return "facebook"
    return "unknown"


def is_single_video(url: str) -> bool:
    url = url.lower()
    if "youtube.com/watch" in url or "youtu.be/" in url:
        return True
    if re.search(r"tiktok\.com/@[^/]+/video/\d+", url):
        return True
    if "facebook.com/watch" in url or "fb.watch" in url or "/videos/" in url:
        return True
    return False


class DownloadEngine:
    def __init__(self, log_cb, progress_cb, status_cb):
        self.log = log_cb
        self.set_progress = progress_cb
        self.set_status = status_cb
        self.cancelled = False
        self.total = 0
        self.done = 0

    def _hook(self, d):
        if self.cancelled:
            raise Exception("Download cancelled by user.")
        if d["status"] == "downloading":
            total_b = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            down_b = d.get("downloaded_bytes", 0)
            speed = d.get("_speed_str", "")
            eta = d.get("_eta_str", "")
            pct = (down_b / total_b * 100) if total_b else 0
            self.set_progress(pct / 100)
            self.set_status(
                f"⬇  {d.get('_percent_str','').strip()}  |  {speed}  |  ETA {eta}"
            )
        elif d["status"] == "finished":
            self.set_progress(1.0)

    def _post_hook(self, d):
        if d["status"] == "finished":
            self.done += 1
            filename = os.path.basename(d.get("filename", ""))
            self.log(f"✅ [{self.done}/{self.total}] {filename}", "success")
            if self.total > 0:
                self.set_progress(self.done / self.total)

    def _base_opts(self, out_dir: str, cookies: str = "") -> dict:
        opts = {
            "outtmpl": os.path.join(out_dir, "%(uploader)s - %(title)s.%(ext)s"),
            "progress_hooks": [self._hook],
            "postprocessor_hooks": [self._post_hook],
            "quiet": True,
            "no_warnings": True,
            "ignoreerrors": True,
            "retries": 5,
            "fragment_retries": 5,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
            },
        }
        if cookies and os.path.isfile(cookies):
            opts["cookiefile"] = cookies
        return opts

    def download_youtube(self, url: str, out_dir: str, cookies: str = "", quality: str = "best"):
        single = is_single_video(url)
        self.log(f"🔴 YouTube — {'single video' if single else 'full channel/playlist'}", "youtube")
        self.log(f"   URL: {url}", "sub")
        fmt_map = {
            "best":  "bestvideo+bestaudio/best",
            "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "720p":  "bestvideo[height<=720]+bestaudio/best[height<=720]",
            "480p":  "bestvideo[height<=480]+bestaudio/best[height<=480]",
            "audio": "bestaudio/best",
        }
        opts = self._base_opts(out_dir, cookies)
        opts["format"] = fmt_map.get(quality, "bestvideo+bestaudio/best")
        opts["merge_output_format"] = "mp4"
        if not single:
            opts["noplaylist"] = False
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    self.log("❌ Could not read URL. Check link or add cookies.", "error")
                    return
                entries = info.get("entries")
                if entries:
                    entries = [e for e in entries if e]
                    self.total = len(entries)
                    self.log(f"📋 Found {self.total} videos — starting download…", "info")
                else:
                    self.total = 1
                self.done = 0
                ydl.download([url])
        except Exception as e:
            if "cancelled" not in str(e).lower():
                self.log(f"❌ Error: {e}", "error")

    def download_tiktok(self, url: str, out_dir: str, cookies: str = ""):
        single = is_single_video(url)
        self.log(f"🎵 TikTok — {'single video' if single else 'full profile'}", "tiktok")
        self.log(f"   URL: {url}", "sub")
        opts = self._base_opts(out_dir, cookies)
        opts["format"] = "best"
        opts["outtmpl"] = os.path.join(out_dir, "%(uploader)s - %(title).80s - %(id)s.%(ext)s")
        opts["extractor_args"] = {"tiktok": {"api_hostname": ["api22-normal-c-useast2a.tiktokv.com"]}}
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    self.log("❌ Could not read URL. Try adding cookies.", "error")
                    return
                entries = info.get("entries")
                if entries:
                    entries = [e for e in entries if e]
                    self.total = len(entries)
                    self.log(f"📋 Found {self.total} videos — starting download…", "info")
                else:
                    self.total = 1
                self.done = 0
                ydl.download([url])
        except Exception as e:
            if "cancelled" not in str(e).lower():
                self.log(f"❌ Error: {e}", "error")

    def download_facebook(self, url: str, out_dir: str, cookies: str = ""):
        single = is_single_video(url)
        self.log(f"🔵 Facebook — {'single video' if single else 'profile/page'}", "facebook")
        self.log(f"   URL: {url}", "sub")
        opts = self._base_opts(out_dir, cookies)
        opts["format"] = "best"
        opts["outtmpl"] = os.path.join(out_dir, "%(uploader)s - %(title).80s - %(id)s.%(ext)s")
        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info is None:
                    self.log("❌ Could not read URL. Please load your cookies.txt file.", "error")
                    return
                entries = info.get("entries")
                if entries:
                    entries = [e for e in entries if e]
                    self.total = len(entries)
                    self.log(f"📋 Found {self.total} videos — starting download…", "info")
                else:
                    self.total = 1
                self.done = 0
                ydl.download([url])
        except Exception as e:
            if "cancelled" not in str(e).lower():
                self.log(f"❌ Error: {e}", "error")

    def download_from_list(self, links: list, out_dir: str, cookies: str = ""):
        self.total = len(links)
        self.done = 0
        self.log(f"📂 Bulk file — {self.total} links to download", "info")
        for i, url in enumerate(links, 1):
            if self.cancelled:
                break
            url = url.strip()
            if not url or url.startswith("#"):
                self.total -= 1
                continue
            self.log(f"─── Link {i}/{len(links)}: {url[:60]}…", "sub")
            plat = detect_platform(url)
            if plat == "youtube":
                self.download_youtube(url, out_dir, cookies)
            elif plat == "tiktok":
                self.download_tiktok(url, out_dir, cookies)
            else:
                self.download_facebook(url, out_dir, cookies)


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("🎬 VideoVault Pro — YouTube + TikTok + Facebook")
        self.geometry("1050x760")
        self.minsize(900, 660)
        self.configure(fg_color=COLORS["bg"])

        self.out_dir    = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads", "VideoVault"))
        self.cookies    = tk.StringVar()
        self.links_file = tk.StringVar()
        self.quality    = tk.StringVar(value="best")
        self.engine: DownloadEngine | None = None
        self._thread: threading.Thread | None = None

        os.makedirs(self.out_dir.get(), exist_ok=True)
        self._build_ui()

    def _build_ui(self):
        # Header
        header = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=0, height=72)
        header.pack(fill="x")
        header.pack_propagate(False)

        ctk.CTkLabel(
            header,
            text="  🎬  VideoVault Pro",
            font=ctk.CTkFont(family="Segoe UI", size=27, weight="bold"),
            text_color="#FFFFFF",
        ).pack(side="left", padx=24, pady=14)

        ctk.CTkLabel(
            header,
            text="🔴 YouTube   🎵 TikTok   🔵 Facebook",
            font=ctk.CTkFont(size=13),
            text_color=COLORS["subtext"],
        ).pack(side="left", padx=10)

        # Body
        body = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=16, pady=(12, 0))

        left = ctk.CTkFrame(body, fg_color=COLORS["card"], corner_radius=14, width=440)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        right = ctk.CTkFrame(body, fg_color=COLORS["card2"], corner_radius=14)
        right.pack(side="left", fill="both", expand=True)

        self._build_left(left)
        self._build_log(right)
        self._build_bottom()

    def _section(self, parent, text):
        if text:
            ctk.CTkLabel(
                parent, text=text,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=COLORS["accent"],
            ).pack(anchor="w", padx=14, pady=(14, 2))

    def _build_left(self, parent):
        scroll = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        scroll.pack(fill="both", expand=True, padx=4, pady=4)

        # URL
        self._section(scroll, "🔗  Paste Video or Profile Link")
        self.url_entry = ctk.CTkEntry(
            scroll,
            placeholder_text="YouTube / TikTok / Facebook URL here…",
            height=46, font=ctk.CTkFont(size=13),
            fg_color="#0F0F1A", border_color=COLORS["accent"],
            text_color="white",
        )
        self.url_entry.pack(fill="x", padx=12, pady=(4, 4))

        self.platform_label = ctk.CTkLabel(
            scroll, text="⚡ Platform will be detected automatically",
            font=ctk.CTkFont(size=11), text_color=COLORS["subtext"]
        )
        self.platform_label.pack(anchor="w", padx=14, pady=(0, 6))
        self.url_entry.bind("<KeyRelease>", self._on_url_change)

        # Quality
        self._section(scroll, "📺  Video Quality")
        q_row = ctk.CTkFrame(scroll, fg_color="transparent")
        q_row.pack(fill="x", padx=12, pady=(4, 10))
        for q in ["best", "1080p", "720p", "480p", "audio"]:
            ctk.CTkRadioButton(
                q_row, text=q, variable=self.quality, value=q,
                font=ctk.CTkFont(size=12),
                fg_color=COLORS["accent"], hover_color="#5a35cc",
            ).pack(side="left", padx=(0, 12))

        # Save folder
        self._section(scroll, "📁  Save Videos To")
        dir_row = ctk.CTkFrame(scroll, fg_color="transparent")
        dir_row.pack(fill="x", padx=12, pady=(4, 10))
        ctk.CTkEntry(
            dir_row, textvariable=self.out_dir,
            font=ctk.CTkFont(size=11), height=38,
            fg_color="#0F0F1A", text_color="white",
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            dir_row, text="Browse", width=80, height=38,
            fg_color=COLORS["accent"], hover_color="#5a35cc",
            command=self._pick_dir,
        ).pack(side="left")

        # Cookies
        self._section(scroll, "🍪  Cookies File  (for Facebook & private videos)")
        ck_row = ctk.CTkFrame(scroll, fg_color="transparent")
        ck_row.pack(fill="x", padx=12, pady=(4, 2))
        ctk.CTkEntry(
            ck_row, textvariable=self.cookies,
            placeholder_text="Select cookies.txt from your browser…",
            font=ctk.CTkFont(size=11), height=38,
            fg_color="#0F0F1A", text_color="white",
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            ck_row, text="Browse", width=80, height=38,
            fg_color="#2a2a55", hover_color="#3a3a77",
            command=self._pick_cookies,
        ).pack(side="left")

        ctk.CTkLabel(
            scroll,
            text="  ℹ  Get cookies: Chrome → install 'Get cookies.txt LOCALLY'\n"
                 "     extension → go to facebook.com → export cookies.",
            font=ctk.CTkFont(size=10), text_color=COLORS["subtext"], justify="left",
        ).pack(anchor="w", padx=12, pady=(2, 10))

        # Facebook bulk links
        self._section(scroll, "📄  Facebook Bulk — Links File  (one link per line)")
        fl_row = ctk.CTkFrame(scroll, fg_color="transparent")
        fl_row.pack(fill="x", padx=12, pady=(4, 4))
        ctk.CTkEntry(
            fl_row, textvariable=self.links_file,
            placeholder_text="Select links.txt with Facebook video URLs…",
            font=ctk.CTkFont(size=11), height=38,
            fg_color="#0F0F1A", text_color="white",
        ).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ctk.CTkButton(
            fl_row, text="Browse", width=80, height=38,
            fg_color="#2a2a55", hover_color="#3a3a77",
            command=self._pick_links_file,
        ).pack(side="left")

        ctk.CTkButton(
            scroll,
            text="📄  Download All Links from File",
            height=42, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=COLORS["facebook"]["main"],
            hover_color=COLORS["facebook"]["hover"],
            corner_radius=10,
            command=self._start_from_file,
        ).pack(fill="x", padx=12, pady=(6, 4))

        ctk.CTkLabel(
            scroll,
            text="  ℹ  Put one Facebook video URL per line in a .txt file.\n"
                 "     Load it above and click the button to download all.",
            font=ctk.CTkFont(size=10), text_color=COLORS["subtext"], justify="left",
        ).pack(anchor="w", padx=12, pady=(0, 12))

        # Download button
        self.dl_btn = ctk.CTkButton(
            scroll,
            text="⬇   DOWNLOAD NOW",
            height=56, font=ctk.CTkFont(size=19, weight="bold"),
            fg_color=COLORS["accent"], hover_color="#5a35cc",
            corner_radius=14,
            command=self._start_download,
        )
        self.dl_btn.pack(fill="x", padx=12, pady=(4, 6))

        self.cancel_btn = ctk.CTkButton(
            scroll,
            text="✖  Cancel Download",
            height=38, font=ctk.CTkFont(size=13),
            fg_color="#3a1a1a", hover_color="#661111",
            corner_radius=8,
            command=self._cancel,
            state="disabled",
        )
        self.cancel_btn.pack(fill="x", padx=12, pady=(0, 16))

    def _build_log(self, parent):
        ctk.CTkLabel(
            parent, text="📋  Download Log",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["accent"],
        ).pack(anchor="w", padx=12, pady=(10, 4))

        self.log_box = ctk.CTkTextbox(
            parent, font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#0A0A16", text_color="#CCCCFF",
            wrap="word", state="disabled", corner_radius=10,
        )
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        self.log_box._textbox.tag_config("success",  foreground=COLORS["success"])
        self.log_box._textbox.tag_config("error",    foreground=COLORS["error"])
        self.log_box._textbox.tag_config("info",     foreground=COLORS["warning"])
        self.log_box._textbox.tag_config("sub",      foreground=COLORS["subtext"])
        self.log_box._textbox.tag_config("youtube",  foreground=COLORS["youtube"]["light"])
        self.log_box._textbox.tag_config("tiktok",   foreground=COLORS["tiktok"]["light"])
        self.log_box._textbox.tag_config("facebook", foreground=COLORS["facebook"]["light"])

        btn_row = ctk.CTkFrame(parent, fg_color="transparent")
        btn_row.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(
            btn_row, text="🗑 Clear Log", width=110, height=32,
            fg_color="#222244", hover_color="#333366",
            command=self._clear_log,
        ).pack(side="left")
        ctk.CTkButton(
            btn_row, text="📂 Open Download Folder", width=160, height=32,
            fg_color="#1a3322", hover_color="#224433",
            command=self._open_folder,
        ).pack(side="left", padx=8)

    def _build_bottom(self):
        bottom = ctk.CTkFrame(self, fg_color=COLORS["card"], height=64, corner_radius=0)
        bottom.pack(fill="x", pady=(10, 0))
        bottom.pack_propagate(False)

        self.progress = ctk.CTkProgressBar(
            bottom, height=10,
            progress_color=COLORS["accent"],
            fg_color="#0F0F1A",
        )
        self.progress.set(0)
        self.progress.pack(fill="x", padx=20, pady=(10, 2))

        self.status_lbl = ctk.CTkLabel(
            bottom, text="Ready — paste a link above and click DOWNLOAD",
            font=ctk.CTkFont(size=11), text_color=COLORS["subtext"],
        )
        self.status_lbl.pack(pady=(0, 6))

    def _on_url_change(self, _=None):
        url = self.url_entry.get().strip()
        p = detect_platform(url)
        icons  = {"youtube": "🔴 YouTube detected", "tiktok": "🎵 TikTok detected",
                  "facebook": "🔵 Facebook detected", "unknown": "⚡ Auto-detect platform"}
        colors = {"youtube": COLORS["youtube"]["light"], "tiktok": COLORS["tiktok"]["light"],
                  "facebook": COLORS["facebook"]["light"], "unknown": COLORS["subtext"]}
        self.platform_label.configure(text=icons[p], text_color=colors[p])

    def _pick_dir(self):
        d = filedialog.askdirectory(title="Select save folder")
        if d:
            self.out_dir.set(d)

    def _pick_cookies(self):
        f = filedialog.askopenfilename(
            title="Select cookies file",
            filetypes=[("Text/JSON", "*.txt *.json"), ("All files", "*.*")]
        )
        if f:
            self.cookies.set(f)

    def _pick_links_file(self):
        f = filedialog.askopenfilename(
            title="Select links file",
            filetypes=[("Text file", "*.txt"), ("All files", "*.*")]
        )
        if f:
            self.links_file.set(f)

    def _open_folder(self):
        path = self.out_dir.get()
        os.makedirs(path, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            os.system(f'open "{path}"')
        else:
            os.system(f'xdg-open "{path}"')

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("0.0", "end")
        self.log_box.configure(state="disabled")

    def _log(self, msg: str, tag: str = ""):
        ts = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self.log_box.configure(state="normal")
        if tag:
            self.log_box._textbox.insert("end", line, tag)
        else:
            self.log_box.insert("end", line)
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def _set_progress(self, val: float):
        self.progress.set(val)

    def _set_status(self, text: str):
        self.status_lbl.configure(text=text)

    def _busy(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def _set_downloading(self, active: bool):
        self.dl_btn.configure(state="disabled" if active else "normal")
        self.cancel_btn.configure(state="normal" if active else "disabled")

    def _cancel(self):
        if self.engine:
            self.engine.cancelled = True
        self._log("⚠ Cancellation requested…", "info")

    def _start_download(self):
        if self._busy():
            messagebox.showinfo("Busy", "A download is already running.")
            return
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Please paste a video or profile URL first.")
            return
        out = self.out_dir.get().strip()
        os.makedirs(out, exist_ok=True)
        self.engine = DownloadEngine(self._log, self._set_progress, self._set_status)
        plat    = detect_platform(url)
        cookies = self.cookies.get().strip()
        quality = self.quality.get()

        def run():
            self._set_downloading(True)
            self._set_status("Starting download…")
            try:
                if plat == "youtube":
                    self.engine.download_youtube(url, out, cookies, quality)
                elif plat == "tiktok":
                    self.engine.download_tiktok(url, out, cookies)
                elif plat == "facebook":
                    self.engine.download_facebook(url, out, cookies)
                else:
                    self._log("❓ Unknown platform — trying anyway…", "info")
                    self.engine.download_youtube(url, out, cookies, quality)
            finally:
                self._set_downloading(False)
                self._set_status("✅ All done!" if not self.engine.cancelled else "⛔ Cancelled")

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def _start_from_file(self):
        if self._busy():
            messagebox.showinfo("Busy", "A download is already running.")
            return
        path = self.links_file.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("No file", "Please select a links .txt file first.")
            return
        with open(path, encoding="utf-8", errors="ignore") as f:
            links = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        if not links:
            messagebox.showwarning("Empty", "No links found in the file.")
            return
        out = self.out_dir.get().strip()
        os.makedirs(out, exist_ok=True)
        cookies = self.cookies.get().strip()
        self.engine = DownloadEngine(self._log, self._set_progress, self._set_status)

        def run():
            self._set_downloading(True)
            self._set_status("Bulk download starting…")
            try:
                self.engine.download_from_list(links, out, cookies)
            finally:
                self._set_downloading(False)
                self._set_status("✅ All done!" if not self.engine.cancelled else "⛔ Cancelled")

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
