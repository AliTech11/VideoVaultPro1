import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import sys
import re
from datetime import datetime
import yt_dlp

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLORS = {
    "bg":       "#0F0F1A",
    "card":     "#1A1A2E",
    "card2":    "#16213E",
    "accent":   "#7C4DFF",
    "success":  "#00E676",
    "error":    "#FF5252",
    "warning":  "#FFD740",
    "subtext":  "#A0A0C0",
    "yt":       "#FF4444",
    "tt":       "#69C9D0",
    "fb":       "#4299F7",
}


def detect_platform(url: str) -> str:
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u:
        return "youtube"
    if "tiktok.com" in u:
        return "tiktok"
    if "facebook.com" in u or "fb.com" in u or "fb.watch" in u:
        return "facebook"
    return "unknown"


def is_single_video(url: str) -> bool:
    u = url.lower()
    if "youtube.com/watch" in u or "youtu.be/" in u:
        return True
    if re.search(r"tiktok\.com/@[^/]+/video/\d+", u):
        return True
    if "facebook.com/watch" in u or "fb.watch" in u or re.search(r"/videos/\d+", u):
        return True
    return False


class DownloadEngine:
    def __init__(self, log_cb, progress_cb, status_cb, info_cb):
        self.log         = log_cb
        self.set_progress = progress_cb
        self.set_status  = status_cb
        self.set_info    = info_cb
        self.cancelled   = False
        self.total       = 0
        self.done        = 0
        self._cur_title  = ""

    # ── progress hook ────────────────────────────────────────────────────────
    def _hook(self, d):
        if self.cancelled:
            raise Exception("Cancelled by user.")

        if d["status"] == "downloading":
            total_b  = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            down_b   = d.get("downloaded_bytes", 0)
            speed    = d.get("_speed_str", "").strip()
            eta      = d.get("_eta_str", "").strip()
            pct_str  = d.get("_percent_str", "0%").strip()
            down_mb  = down_b  / 1_048_576
            total_mb = total_b / 1_048_576
            pct      = (down_b / total_b) if total_b else 0
            self.set_progress(pct)
            self.set_status(
                f"⬇  {pct_str}  |  {down_mb:.1f} MB / {total_mb:.1f} MB  |  {speed}  |  ETA {eta}"
            )
            if self.total > 1:
                self.set_info(f"Video {self.done + 1} of {self.total}  —  {self._cur_title[:55]}")
            else:
                self.set_info(self._cur_title[:70])

        elif d["status"] == "finished":
            self.set_progress(1.0)

    def _post_hook(self, d):
        if d["status"] == "finished":
            self.done += 1
            filename = os.path.basename(d.get("filename", ""))
            size_b   = os.path.getsize(d["filename"]) if os.path.isfile(d.get("filename","")) else 0
            size_mb  = size_b / 1_048_576
            self.log(
                f"✅ [{self.done}/{self.total}]  {filename}  ({size_mb:.1f} MB)",
                "success"
            )
            if self.total > 0:
                self.set_progress(self.done / self.total)

    # ── shared yt-dlp options ────────────────────────────────────────────────
    def _opts(self, out_dir: str, cookies: str = "", fmt: str = "bestvideo+bestaudio/best") -> dict:
        o = {
            "format":           fmt,
            "outtmpl":          os.path.join(out_dir, "%(uploader)s - %(title)s.%(ext)s"),
            "merge_output_format": "mp4",
            "progress_hooks":   [self._hook],
            "postprocessor_hooks": [self._post_hook],
            "quiet":            True,
            "no_warnings":      True,
            "ignoreerrors":     True,
            "retries":          8,
            "fragment_retries": 8,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            },
        }
        if cookies and os.path.isfile(cookies):
            o["cookiefile"] = cookies
        return o

    # ── YouTube ──────────────────────────────────────────────────────────────
    def download_youtube(self, url: str, out_dir: str, cookies: str = "", quality: str = "best"):
        single = is_single_video(url)
        self.log(
            f"🔴 YouTube — {'Single Video' if single else 'Channel / Playlist (ALL videos)'}",
            "yt"
        )
        self.log(f"   🔗 {url}", "sub")

        fmt_map = {
            "best":  "bestvideo+bestaudio/best",
            "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=1080]+bestaudio/best[height<=1080]",
            "720p":  "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/bestvideo[height<=720]+bestaudio/best[height<=720]",
            "480p":  "bestvideo[height<=480]+bestaudio/best[height<=480]",
            "audio": "bestaudio[ext=m4a]/bestaudio/best",
        }

        opts = self._opts(out_dir, cookies, fmt_map.get(quality, "bestvideo+bestaudio/best"))

        # For channels/playlists allow all entries
        if not single:
            opts["noplaylist"] = False
            opts["extract_flat"] = False

        # YouTube needs these fixes
        opts["extractor_args"] = {
            "youtube": {
                "player_client": ["android", "web"],
                "skip": ["hls", "dash"],
            }
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                self.log("🔍 Reading video info…", "info")
                info = ydl.extract_info(url, download=False)
                if not info:
                    self.log("❌ ERROR: Could not read this URL.", "error")
                    self.log("   → Make sure the link is correct.", "error")
                    self.log("   → Try adding a cookies.txt file if video is age-restricted.", "error")
                    return

                entries = info.get("entries")
                if entries:
                    entries = [e for e in entries if e]
                    self.total = len(entries)
                    self.log(f"📋 Found {self.total} videos — downloading all…", "info")
                    for i, entry in enumerate(entries):
                        if self.cancelled:
                            break
                        self._cur_title = entry.get("title", f"Video {i+1}")
                        self.log(f"⬇  [{i+1}/{self.total}] {self._cur_title}", "sub")
                        try:
                            ydl.download([entry["webpage_url"]])
                        except Exception as e:
                            self.log(f"⚠  Skipped: {self._cur_title} — {e}", "warning")
                else:
                    self.total = 1
                    self.done  = 0
                    self._cur_title = info.get("title", "Video")
                    self.log(f"🎬 Title: {self._cur_title}", "info")
                    self.log(f"📦 Size:  ~{(info.get('filesize') or info.get('filesize_approx') or 0)/1_048_576:.1f} MB", "info")
                    ydl.download([url])

        except Exception as e:
            if "cancelled" not in str(e).lower():
                self.log(f"❌ YouTube ERROR: {e}", "error")
                self.log("   → Check your internet connection.", "error")
                self.log("   → Try a different quality setting.", "error")

    # ── TikTok ───────────────────────────────────────────────────────────────
    def download_tiktok(self, url: str, out_dir: str, cookies: str = ""):
        single = is_single_video(url)
        self.log(f"🎵 TikTok — {'Single Video' if single else 'Full Profile (ALL videos)'}", "tt")
        self.log(f"   🔗 {url}", "sub")

        opts = self._opts(out_dir, cookies, "best")
        opts["outtmpl"] = os.path.join(out_dir, "%(uploader)s - %(title).80s - %(id)s.%(ext)s")
        opts["extractor_args"] = {
            "tiktok": {"api_hostname": ["api22-normal-c-useast2a.tiktokv.com"]}
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                self.log("🔍 Reading profile info…", "info")
                info = ydl.extract_info(url, download=False)
                if not info:
                    self.log("❌ ERROR: Could not read TikTok URL.", "error")
                    self.log("   → Try adding cookies.txt if profile is private.", "error")
                    return
                entries = info.get("entries")
                if entries:
                    entries = [e for e in entries if e]
                    self.total = len(entries)
                    self.log(f"📋 Found {self.total} videos — downloading all…", "info")
                    for i, entry in enumerate(entries):
                        if self.cancelled:
                            break
                        self._cur_title = entry.get("title", f"Video {i+1}")
                        self.log(f"⬇  [{i+1}/{self.total}] {self._cur_title}", "sub")
                        try:
                            ydl.download([entry["webpage_url"]])
                        except Exception as e:
                            self.log(f"⚠  Skipped: {self._cur_title} — {e}", "warning")
                else:
                    self.total = 1
                    self.done  = 0
                    self._cur_title = info.get("title", "Video")
                    self.log(f"🎬 Title: {self._cur_title}", "info")
                    ydl.download([url])
        except Exception as e:
            if "cancelled" not in str(e).lower():
                self.log(f"❌ TikTok ERROR: {e}", "error")

    # ── Facebook ─────────────────────────────────────────────────────────────
    def download_facebook(self, url: str, out_dir: str, cookies: str = ""):
        single = is_single_video(url)
        self.log(f"🔵 Facebook — {'Single Video' if single else 'Page/Profile Videos'}", "fb")
        self.log(f"   🔗 {url}", "sub")

        if not cookies or not os.path.isfile(cookies):
            self.log("⚠  WARNING: No cookies file loaded!", "warning")
            self.log("   → Facebook requires cookies to download videos.", "warning")
            self.log("   → Load your cookies.txt file and try again.", "warning")

        opts = self._opts(out_dir, cookies, "best")
        opts["outtmpl"] = os.path.join(out_dir, "%(uploader)s - %(title).80s - %(id)s.%(ext)s")

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                self.log("🔍 Reading Facebook video info…", "info")
                info = ydl.extract_info(url, download=False)
                if not info:
                    self.log("❌ ERROR: Could not read Facebook URL.", "error")
                    self.log("   → Facebook needs login cookies to download.", "error")
                    self.log("   → Use 'Get cookies.txt LOCALLY' Chrome extension.", "error")
                    self.log("   → Or use the Bulk Links File method below.", "error")
                    return
                entries = info.get("entries")
                if entries:
                    entries = [e for e in entries if e]
                    self.total = len(entries)
                    self.log(f"📋 Found {self.total} videos — downloading all…", "info")
                    for i, entry in enumerate(entries):
                        if self.cancelled:
                            break
                        self._cur_title = entry.get("title", f"Video {i+1}")
                        self.log(f"⬇  [{i+1}/{self.total}] {self._cur_title}", "sub")
                        try:
                            ydl.download([entry["webpage_url"]])
                        except Exception as e:
                            self.log(f"⚠  Skipped: {self._cur_title} — {e}", "warning")
                else:
                    self.total = 1
                    self.done  = 0
                    self._cur_title = info.get("title", "Video")
                    self.log(f"🎬 Title: {self._cur_title}", "info")
                    size = (info.get("filesize") or info.get("filesize_approx") or 0) / 1_048_576
                    if size:
                        self.log(f"📦 Size:  ~{size:.1f} MB", "info")
                    ydl.download([url])
        except Exception as e:
            if "cancelled" not in str(e).lower():
                self.log(f"❌ Facebook ERROR: {e}", "error")
                self.log("   → Make sure cookies.txt is loaded.", "error")

    # ── Bulk from file ───────────────────────────────────────────────────────
    def download_from_list(self, links: list, out_dir: str, cookies: str = ""):
        self.total = len(links)
        self.done  = 0
        self.log(f"📂 Bulk File — {self.total} links found", "info")
        self.log("─" * 50, "sub")
        for i, url in enumerate(links, 1):
            if self.cancelled:
                self.log("⛔ Cancelled by user.", "warning")
                break
            url = url.strip()
            if not url or url.startswith("#"):
                self.total -= 1
                continue
            self.log(f"\n📌 Link {i} of {len(links)}", "info")
            plat = detect_platform(url)
            if plat == "youtube":
                self.download_youtube(url, out_dir, cookies)
            elif plat == "tiktok":
                self.download_tiktok(url, out_dir, cookies)
            else:
                self.download_facebook(url, out_dir, cookies)
            self.log("─" * 50, "sub")


# ── Main App Window ──────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("🎬 VideoVault Pro — YouTube + TikTok + Facebook")
        self.geometry("1100x800")
        self.minsize(950, 680)
        self.configure(fg_color=COLORS["bg"])

        self.out_dir    = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads", "VideoVault"))
        self.cookies    = tk.StringVar()
        self.links_file = tk.StringVar()
        self.quality    = tk.StringVar(value="best")
        self.engine     = None
        self._thread    = None

        os.makedirs(self.out_dir.get(), exist_ok=True)
        self._build_ui()

    # ── UI Build ─────────────────────────────────────────────────────────────

    def _build_ui(self):
        # Header
        hdr = ctk.CTkFrame(self, fg_color=COLORS["card"], corner_radius=0, height=74)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="  🎬  VideoVault Pro",
                     font=ctk.CTkFont(size=28, weight="bold"),
                     text_color="#FFFFFF").pack(side="left", padx=24)
        ctk.CTkLabel(hdr, text="🔴 YouTube   🎵 TikTok   🔵 Facebook",
                     font=ctk.CTkFont(size=13), text_color=COLORS["subtext"]).pack(side="left", padx=10)

        # Info bar (video count + title)
        self.info_bar = ctk.CTkLabel(
            self, text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["warning"], fg_color=COLORS["card2"],
            height=28,
        )
        self.info_bar.pack(fill="x")

        # Body
        body = ctk.CTkFrame(self, fg_color=COLORS["bg"])
        body.pack(fill="both", expand=True, padx=14, pady=(10, 0))

        left = ctk.CTkFrame(body, fg_color=COLORS["card"], corner_radius=14, width=450)
        left.pack(side="left", fill="y", padx=(0, 10))
        left.pack_propagate(False)

        right = ctk.CTkFrame(body, fg_color=COLORS["card2"], corner_radius=14)
        right.pack(side="left", fill="both", expand=True)

        self._build_left(left)
        self._build_log(right)
        self._build_bottom()

    def _sec(self, p, text):
        if text:
            ctk.CTkLabel(p, text=text,
                         font=ctk.CTkFont(size=12, weight="bold"),
                         text_color=COLORS["accent"]).pack(anchor="w", padx=14, pady=(12, 2))

    def _build_left(self, parent):
        sc = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        sc.pack(fill="both", expand=True, padx=4, pady=4)

        # URL
        self._sec(sc, "🔗  Paste Any Video or Profile Link")
        self.url_entry = ctk.CTkEntry(sc,
            placeholder_text="YouTube / TikTok / Facebook URL…",
            height=46, font=ctk.CTkFont(size=13),
            fg_color="#0F0F1A", border_color=COLORS["accent"], text_color="white")
        self.url_entry.pack(fill="x", padx=12, pady=(4, 4))

        self.plat_lbl = ctk.CTkLabel(sc, text="⚡ Auto-detect platform",
            font=ctk.CTkFont(size=11), text_color=COLORS["subtext"])
        self.plat_lbl.pack(anchor="w", padx=14, pady=(0, 6))
        self.url_entry.bind("<KeyRelease>", self._on_url)

        # Quality
        self._sec(sc, "📺  Quality  (YouTube)")
        qr = ctk.CTkFrame(sc, fg_color="transparent")
        qr.pack(fill="x", padx=12, pady=(4, 10))
        for q in ["best", "1080p", "720p", "480p", "audio"]:
            ctk.CTkRadioButton(qr, text=q, variable=self.quality, value=q,
                font=ctk.CTkFont(size=12), fg_color=COLORS["accent"]).pack(side="left", padx=(0,10))

        # Save folder
        self._sec(sc, "📁  Save Videos To")
        dr = ctk.CTkFrame(sc, fg_color="transparent")
        dr.pack(fill="x", padx=12, pady=(4, 10))
        ctk.CTkEntry(dr, textvariable=self.out_dir,
            font=ctk.CTkFont(size=11), height=38,
            fg_color="#0F0F1A", text_color="white").pack(side="left", fill="x", expand=True, padx=(0,6))
        ctk.CTkButton(dr, text="Browse", width=80, height=38,
            fg_color=COLORS["accent"], hover_color="#5a35cc",
            command=self._pick_dir).pack(side="left")

        # Cookies
        self._sec(sc, "🍪  Cookies File  (required for Facebook & private videos)")
        ckr = ctk.CTkFrame(sc, fg_color="transparent")
        ckr.pack(fill="x", padx=12, pady=(4, 2))
        ctk.CTkEntry(ckr, textvariable=self.cookies,
            placeholder_text="cookies.txt — export from your browser",
            font=ctk.CTkFont(size=11), height=38,
            fg_color="#0F0F1A", text_color="white").pack(side="left", fill="x", expand=True, padx=(0,6))
        ctk.CTkButton(ckr, text="Browse", width=80, height=38,
            fg_color="#2a2a55", hover_color="#3a3a77",
            command=self._pick_cookies).pack(side="left")

        ctk.CTkLabel(sc,
            text="  ℹ Chrome: install 'Get cookies.txt LOCALLY' → go to\n"
                 "     facebook.com (logged in) → click extension → Export",
            font=ctk.CTkFont(size=10), text_color=COLORS["subtext"], justify="left"
        ).pack(anchor="w", padx=12, pady=(2, 10))

        # Facebook bulk
        self._sec(sc, "📄  Facebook Bulk — Links .txt File")
        flr = ctk.CTkFrame(sc, fg_color="transparent")
        flr.pack(fill="x", padx=12, pady=(4, 4))
        ctk.CTkEntry(flr, textvariable=self.links_file,
            placeholder_text="links.txt — one Facebook video URL per line",
            font=ctk.CTkFont(size=11), height=38,
            fg_color="#0F0F1A", text_color="white").pack(side="left", fill="x", expand=True, padx=(0,6))
        ctk.CTkButton(flr, text="Browse", width=80, height=38,
            fg_color="#2a2a55", hover_color="#3a3a77",
            command=self._pick_links).pack(side="left")

        ctk.CTkLabel(sc,
            text="  ℹ How to get Facebook links:\n"
                 "     1. Go to Facebook profile → Videos tab\n"
                 "     2. Copy each video link\n"
                 "     3. Paste into a .txt file, one link per line\n"
                 "     4. Load that file here → click Download All",
            font=ctk.CTkFont(size=10), text_color=COLORS["subtext"], justify="left"
        ).pack(anchor="w", padx=12, pady=(2, 6))

        ctk.CTkButton(sc,
            text="📄  Download All Links from File",
            height=42, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color="#1877F2", hover_color="#0d5bb5", corner_radius=10,
            command=self._start_file).pack(fill="x", padx=12, pady=(4, 10))

        # Big download button
        self.dl_btn = ctk.CTkButton(sc,
            text="⬇   DOWNLOAD NOW",
            height=56, font=ctk.CTkFont(size=19, weight="bold"),
            fg_color=COLORS["accent"], hover_color="#5a35cc", corner_radius=14,
            command=self._start)
        self.dl_btn.pack(fill="x", padx=12, pady=(4, 6))

        self.cancel_btn = ctk.CTkButton(sc,
            text="✖  Cancel",
            height=36, font=ctk.CTkFont(size=13),
            fg_color="#3a1a1a", hover_color="#661111", corner_radius=8,
            command=self._cancel, state="disabled")
        self.cancel_btn.pack(fill="x", padx=12, pady=(0, 16))

    def _build_log(self, parent):
        ctk.CTkLabel(parent, text="📋  Download Log",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=COLORS["accent"]).pack(anchor="w", padx=12, pady=(10, 4))

        self.log_box = ctk.CTkTextbox(parent,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color="#0A0A16", text_color="#CCCCFF",
            wrap="word", state="disabled", corner_radius=10)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0, 6))

        tb = self.log_box._textbox
        tb.tag_config("success",  foreground=COLORS["success"])
        tb.tag_config("error",    foreground=COLORS["error"])
        tb.tag_config("warning",  foreground=COLORS["warning"])
        tb.tag_config("info",     foreground="#64B5F6")
        tb.tag_config("sub",      foreground=COLORS["subtext"])
        tb.tag_config("yt",       foreground=COLORS["yt"])
        tb.tag_config("tt",       foreground=COLORS["tt"])
        tb.tag_config("fb",       foreground=COLORS["fb"])

        br = ctk.CTkFrame(parent, fg_color="transparent")
        br.pack(fill="x", padx=10, pady=(0, 10))
        ctk.CTkButton(br, text="🗑 Clear Log", width=110, height=32,
            fg_color="#222244", hover_color="#333366",
            command=self._clear_log).pack(side="left")
        ctk.CTkButton(br, text="📂 Open Folder", width=130, height=32,
            fg_color="#1a3322", hover_color="#224433",
            command=self._open_folder).pack(side="left", padx=8)

    def _build_bottom(self):
        bot = ctk.CTkFrame(self, fg_color=COLORS["card"], height=66, corner_radius=0)
        bot.pack(fill="x", pady=(8, 0))
        bot.pack_propagate(False)

        self.progress = ctk.CTkProgressBar(bot, height=12,
            progress_color=COLORS["accent"], fg_color="#0F0F1A")
        self.progress.set(0)
        self.progress.pack(fill="x", padx=20, pady=(10, 2))

        self.status_lbl = ctk.CTkLabel(bot,
            text="Ready — paste a link above and click DOWNLOAD NOW",
            font=ctk.CTkFont(size=11), text_color=COLORS["subtext"])
        self.status_lbl.pack(pady=(0, 6))

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _on_url(self, _=None):
        p = detect_platform(self.url_entry.get())
        d = {"youtube": ("🔴 YouTube detected",  COLORS["yt"]),
             "tiktok":  ("🎵 TikTok detected",   COLORS["tt"]),
             "facebook":("🔵 Facebook detected", COLORS["fb"]),
             "unknown": ("⚡ Auto-detect",        COLORS["subtext"])}
        self.plat_lbl.configure(text=d[p][0], text_color=d[p][1])

    def _pick_dir(self):
        d = filedialog.askdirectory()
        if d: self.out_dir.set(d)

    def _pick_cookies(self):
        f = filedialog.askopenfilename(filetypes=[("Text/JSON","*.txt *.json"),("All","*.*")])
        if f: self.cookies.set(f)

    def _pick_links(self):
        f = filedialog.askopenfilename(filetypes=[("Text","*.txt"),("All","*.*")])
        if f: self.links_file.set(f)

    def _open_folder(self):
        p = self.out_dir.get()
        os.makedirs(p, exist_ok=True)
        if sys.platform == "win32":   os.startfile(p)
        elif sys.platform == "darwin": os.system(f'open "{p}"')
        else:                          os.system(f'xdg-open "{p}"')

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("0.0", "end")
        self.log_box.configure(state="disabled")

    def _log(self, msg: str, tag: str = ""):
        ts   = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self.log_box.configure(state="normal")
        if tag:
            self.log_box._textbox.insert("end", line, tag)
        else:
            self.log_box.insert("end", line)
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def _set_progress(self, v):  self.progress.set(v)
    def _set_status(self, t):    self.status_lbl.configure(text=t)
    def _set_info(self, t):      self.info_bar.configure(text="  " + t)

    def _busy(self): return self._thread and self._thread.is_alive()

    def _set_dl(self, active):
        self.dl_btn.configure(state="disabled" if active else "normal")
        self.cancel_btn.configure(state="normal" if active else "disabled")

    def _cancel(self):
        if self.engine: self.engine.cancelled = True
        self._log("⚠ Cancel requested…", "warning")

    # ── Start download ────────────────────────────────────────────────────────

    def _start(self):
        if self._busy():
            messagebox.showinfo("Busy", "Download already running.")
            return
        url = self.url_entry.get().strip()
        if not url:
            messagebox.showwarning("No URL", "Please paste a link first.")
            return
        out = self.out_dir.get().strip()
        os.makedirs(out, exist_ok=True)

        self.engine  = DownloadEngine(self._log, self._set_progress, self._set_status, self._set_info)
        plat         = detect_platform(url)
        cookies      = self.cookies.get().strip()
        quality      = self.quality.get()

        def run():
            self._set_dl(True)
            self._set_status("Starting…")
            self._log("=" * 55, "sub")
            try:
                if plat == "youtube":
                    self.engine.download_youtube(url, out, cookies, quality)
                elif plat == "tiktok":
                    self.engine.download_tiktok(url, out, cookies)
                elif plat == "facebook":
                    self.engine.download_facebook(url, out, cookies)
                else:
                    self._log("❓ Unknown platform — trying as YouTube…", "warning")
                    self.engine.download_youtube(url, out, cookies, quality)
            finally:
                done = not self.engine.cancelled
                self._set_dl(False)
                self._set_status("✅ All done!" if done else "⛔ Cancelled")
                self._set_info("✅ Finished!" if done else "⛔ Cancelled")
                self._log("=" * 55, "sub")

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def _start_file(self):
        if self._busy():
            messagebox.showinfo("Busy", "Download already running.")
            return
        path = self.links_file.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("No file", "Please select a links .txt file.")
            return
        with open(path, encoding="utf-8", errors="ignore") as f:
            links = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        if not links:
            messagebox.showwarning("Empty", "No links found in file.")
            return
        out     = self.out_dir.get().strip()
        os.makedirs(out, exist_ok=True)
        cookies = self.cookies.get().strip()
        self.engine = DownloadEngine(self._log, self._set_progress, self._set_status, self._set_info)

        def run():
            self._set_dl(True)
            self._set_status("Bulk download starting…")
            self._log("=" * 55, "sub")
            try:
                self.engine.download_from_list(links, out, cookies)
            finally:
                done = not self.engine.cancelled
                self._set_dl(False)
                self._set_status("✅ All done!" if done else "⛔ Cancelled")
                self._set_info("✅ Finished!" if done else "⛔ Cancelled")
                self._log("=" * 55, "sub")

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
