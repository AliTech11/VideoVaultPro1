import customtkinter as ctk
import tkinter as tk
from tkinter import filedialog, messagebox
import threading
import os
import sys
import re
from datetime import datetime
import yt_dlp

# ── FFmpeg auto-detection ─────────────────────────────────────────────────────
# Finds ffmpeg.exe bundled inside the app folder (added by PyInstaller)
def find_ffmpeg():
    """Find ffmpeg bundled with the app or on system PATH."""
    # When running as PyInstaller EXE — ffmpeg is in same folder as exe
    if getattr(sys, 'frozen', False):
        # Running as compiled EXE
        base = sys._MEIPASS  # PyInstaller temp folder
        ffmpeg_path  = os.path.join(base, "ffmpeg.exe")
        ffprobe_path = os.path.join(base, "ffprobe.exe")
        if os.path.isfile(ffmpeg_path):
            return ffmpeg_path, ffprobe_path
        # Also check next to the exe
        exe_dir = os.path.dirname(sys.executable)
        ffmpeg_path  = os.path.join(exe_dir, "ffmpeg.exe")
        ffprobe_path = os.path.join(exe_dir, "ffprobe.exe")
        if os.path.isfile(ffmpeg_path):
            return ffmpeg_path, ffprobe_path
    else:
        # Running as script — check same folder
        script_dir   = os.path.dirname(os.path.abspath(__file__))
        ffmpeg_path  = os.path.join(script_dir, "ffmpeg.exe")
        ffprobe_path = os.path.join(script_dir, "ffprobe.exe")
        if os.path.isfile(ffmpeg_path):
            return ffmpeg_path, ffprobe_path
    return None, None

FFMPEG_PATH, FFPROBE_PATH = find_ffmpeg()

ctk.set_appearance_mode("light")
ctk.set_default_color_theme("green")

C = {
    "bg":        "#F0F4F0",
    "card":      "#FFFFFF",
    "card2":     "#F8FFF8",
    "header":    "#1B5E20",
    "accent":    "#2E7D32",
    "accent2":   "#43A047",
    "subtext":   "#555555",
    "logbg":     "#1A1A1A",
    "logtext":   "#E0FFE0",
    "yt_btn":    "#D32F2F",
    "yt_hover":  "#B71C1C",
    "yt_text":   "#FF5252",
    "tt_btn":    "#F9A825",
    "tt_hover":  "#F57F17",
    "tt_text":   "#FFD740",
    "fb_btn":    "#1565C0",
    "fb_hover":  "#0D47A1",
    "fb_text":   "#64B5F6",
    "success":   "#00C853",
    "error":     "#D50000",
    "warning":   "#FF6D00",
    "info":      "#0288D1",
}


def detect_platform(url: str) -> str:
    u = url.lower()
    if "youtube.com" in u or "youtu.be" in u: return "youtube"
    if "tiktok.com" in u:                      return "tiktok"
    if "facebook.com" in u or "fb.com" in u or "fb.watch" in u: return "facebook"
    return "unknown"


def is_single(url: str) -> bool:
    u = url.lower()
    if "youtube.com/watch" in u or "youtu.be/" in u: return True
    if re.search(r"tiktok\.com/@[^/]+/video/\d+", u): return True
    if "facebook.com/watch" in u or "fb.watch" in u or re.search(r"/videos/\d+", u): return True
    return False


class DownloadEngine:
    def __init__(self, log_cb, progress_cb, status_cb, info_cb, theme_cb):
        self.log        = log_cb
        self.set_prog   = progress_cb
        self.set_status = status_cb
        self.set_info   = info_cb
        self.set_theme  = theme_cb
        self.cancelled  = False
        self.total      = 0
        self.done       = 0
        self._title     = ""

    def _hook(self, d):
        if self.cancelled:
            raise Exception("Cancelled.")
        if d["status"] == "downloading":
            total_b  = d.get("total_bytes") or d.get("total_bytes_estimate", 0)
            down_b   = d.get("downloaded_bytes", 0)
            speed    = d.get("_speed_str", "").strip()
            eta      = d.get("_eta_str", "").strip()
            pct_str  = d.get("_percent_str", "0%").strip()
            down_mb  = down_b  / 1_048_576
            total_mb = total_b / 1_048_576
            pct      = (down_b / total_b) if total_b else 0
            self.set_prog(pct)
            self.set_status(
                f"⬇  {pct_str}  |  {down_mb:.1f} MB / {total_mb:.1f} MB  |  🚀 {speed}  |  ⏱ ETA {eta}"
            )
            count = f"Video {self.done+1} of {self.total}  —  " if self.total > 1 else ""
            self.set_info(f"{count}{self._title[:60]}")
        elif d["status"] == "finished":
            self.set_prog(1.0)

    def _post_hook(self, d):
        if d["status"] == "finished":
            self.done += 1
            fname   = d.get("filename", "")
            size_mb = os.path.getsize(fname) / 1_048_576 if fname and os.path.isfile(fname) else 0
            self.log(
                f"✅ [{self.done}/{self.total}]  {os.path.basename(fname)}  ({size_mb:.1f} MB)",
                "success"
            )
            if self.total > 0:
                self.set_prog(self.done / self.total)

    def _base_opts(self, out_dir, cookies="", fmt="bestvideo+bestaudio/best"):
        o = {
            "format":              fmt,
            "outtmpl":             os.path.join(out_dir, "%(title)s [%(id)s].%(ext)s"),
            "merge_output_format": "mp4",
            "progress_hooks":      [self._hook],
            "postprocessor_hooks": [self._post_hook],
            "quiet":               True,
            "no_warnings":         True,
            "ignoreerrors":        True,
            "retries":             8,
            "fragment_retries":    8,
            "http_headers": {
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/124.0.0.0 Safari/537.36"
                ),
            },
        }
        # ── FFmpeg — required for high quality merging ────────────────────────
        if FFMPEG_PATH:
            o["ffmpeg_location"] = os.path.dirname(FFMPEG_PATH)
        else:
            self.log("⚠  FFmpeg not found — quality may be limited", "warning")

        if cookies and os.path.isfile(cookies):
            o["cookiefile"] = cookies
        return o

    # ── YouTube FAST ──────────────────────────────────────────────────────────
    def dl_youtube(self, url, out_dir, cookies="", quality="best"):
        single = is_single(url)
        self.set_theme("youtube")
        self.log(
            f"🔴 YouTube — {'Single Video' if single else 'Channel / Playlist'}",
            "yt"
        )
        self.log(f"   🔗 {url}", "sub")

        fmt_map = {
            "best":  "bestvideo[ext=mp4]+bestaudio[ext=m4a]/bestvideo+bestaudio/best",
            "1080p": "bestvideo[height<=1080][ext=mp4]+bestaudio[ext=m4a]/best[height<=1080]",
            "720p":  "bestvideo[height<=720][ext=mp4]+bestaudio[ext=m4a]/best[height<=720]",
            "480p":  "bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480]",
            "audio": "bestaudio[ext=m4a]/bestaudio/best",
        }
        fmt = fmt_map.get(quality, "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best")

        if single:
            # ── Single video — download immediately, no waiting ───────────────
            opts = self._base_opts(out_dir, cookies, fmt)
            opts["extractor_args"] = {
                "youtube": {"player_client": ["android", "web"]}
            }
            try:
                with yt_dlp.YoutubeDL(opts) as ydl:
                    self.log("⚡ Starting download immediately…", "info")
                    self.total = 1
                    self.done  = 0
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        self.log("❌ Cannot read this video URL.", "error")
                        self.log("   ➜ Check the link is correct.", "error")
                        return
                    self._title = info.get("title", "Video")
                    size = (info.get("filesize") or info.get("filesize_approx") or 0) / 1_048_576
                    self.log(f"🎬 {self._title}", "info")
                    if size: self.log(f"📦 Size: ~{size:.1f} MB", "info")
                    ydl.download([url])
            except Exception as e:
                if "cancelled" not in str(e).lower():
                    self.log(f"❌ YouTube ERROR: {e}", "error")
                    self.log("   ➜ Try different quality or add cookies.txt", "error")

        else:
            # ── Channel / Playlist — FAST: get URLs first, download immediately ─
            self.log("⚡ Getting video list instantly…", "info")
            self.set_status("Getting video URLs — starting in seconds…")

            # Step 1 — flat extract: gets ALL video URLs in seconds, no full info
            flat_opts = {
                "quiet":        True,
                "no_warnings":  True,
                "ignoreerrors": True,
                "extract_flat": True,   # ← KEY: gets URLs instantly, no slow info read
                "extractor_args": {
                    "youtube": {"player_client": ["android", "web"]}
                },
            }
            if cookies and os.path.isfile(cookies):
                flat_opts["cookiefile"] = cookies

            video_urls = []
            try:
                with yt_dlp.YoutubeDL(flat_opts) as ydl:
                    info = ydl.extract_info(url, download=False)
                    if not info:
                        self.log("❌ Cannot read channel/playlist URL.", "error")
                        self.log("   ➜ Check the link is correct.", "error")
                        return
                    entries = info.get("entries") or []
                    for e in entries:
                        if e and e.get("id"):
                            video_urls.append(f"https://www.youtube.com/watch?v={e['id']}")

            except Exception as e:
                self.log(f"❌ Cannot read channel: {e}", "error")
                return

            if not video_urls:
                self.log("❌ No videos found in this channel/playlist.", "error")
                self.log("   ➜ Make sure the link is a channel or playlist.", "error")
                return

            self.total = len(video_urls)
            self.done  = 0
            self.log(f"📋 Found {self.total} videos — starting download NOW!", "info")
            self.set_status(f"Found {self.total} videos — downloading…")

            # Step 2 — download each video immediately one by one
            dl_opts = self._base_opts(out_dir, cookies, fmt)
            dl_opts["extractor_args"] = {
                "youtube": {"player_client": ["android", "web"]}
            }

            with yt_dlp.YoutubeDL(dl_opts) as ydl:
                for i, vurl in enumerate(video_urls):
                    if self.cancelled:
                        self.log("⛔ Cancelled by user.", "warning")
                        break
                    self._title = f"Video {i+1}"
                    self.log(f"⬇  [{i+1}/{self.total}] Downloading…", "sub")
                    self.set_info(f"Video {i+1} of {self.total}")
                    try:
                        # Get just the title quickly
                        quick_info = ydl.extract_info(vurl, download=False)
                        if quick_info:
                            self._title = quick_info.get("title", f"Video {i+1}")
                            self.log(f"   🎬 {self._title}", "sub")
                        ydl.download([vurl])
                    except Exception as e:
                        if "cancelled" in str(e).lower():
                            break
                        self.log(f"⚠  Skipped video {i+1}: {e}", "warning")
                        self.done += 1
                        continue

    # ── TikTok ───────────────────────────────────────────────────────────────
    def dl_tiktok(self, url, out_dir, cookies=""):
        single = is_single(url)
        self.set_theme("tiktok")
        self.log(f"🎵 TikTok — {'Single Video' if single else 'Full Profile'}", "tt")
        self.log(f"   🔗 {url}", "sub")

        opts = self._base_opts(out_dir, cookies, "best")
        opts["outtmpl"] = os.path.join(out_dir, "%(title)s [%(id)s].%(ext)s")
        opts["extractor_args"] = {
            "tiktok": {"api_hostname": ["api22-normal-c-useast2a.tiktokv.com"]}
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                self.log("🔍 Reading profile…", "info")
                info = ydl.extract_info(url, download=False)
                if not info:
                    self.log("❌ Cannot read TikTok URL.", "error")
                    self.log("   ➜ Add cookies.txt if profile is private.", "error")
                    return
                entries = [e for e in (info.get("entries") or []) if e]
                if entries:
                    self.total = len(entries)
                    self.log(f"📋 Found {self.total} videos — downloading…", "info")
                    for i, e in enumerate(entries):
                        if self.cancelled: break
                        self._title = e.get("title", f"Video {i+1}")
                        self.log(f"⬇  [{i+1}/{self.total}] {self._title}", "sub")
                        try:    ydl.download([e["webpage_url"]])
                        except Exception as ex:
                            self.log(f"⚠  Skipped: {ex}", "warning")
                else:
                    self.total = 1; self.done = 0
                    self._title = info.get("title", "Video")
                    self.log(f"🎬 {self._title}", "info")
                    ydl.download([url])
        except Exception as e:
            if "cancelled" not in str(e).lower():
                self.log(f"❌ TikTok ERROR: {e}", "error")

    # ── Facebook ─────────────────────────────────────────────────────────────
    def dl_facebook(self, url, out_dir, cookies=""):
        single = is_single(url)
        self.set_theme("facebook")
        self.log(f"🔵 Facebook — {'Single Video' if single else 'Page/Profile'}", "fb")
        self.log(f"   🔗 {url}", "sub")

        if not cookies or not os.path.isfile(cookies):
            self.log("⚠  No cookies file! Facebook needs login cookies.", "warning")
            self.log("   ➜ Use Bulk Link Collector extension to get cookies.txt", "warning")

        opts = self._base_opts(out_dir, cookies, "best")

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                self.log("🔍 Reading Facebook info…", "info")
                info = ydl.extract_info(url, download=False)
                if not info:
                    self.log("❌ Cannot read Facebook URL.", "error")
                    self.log("   ➜ Load cookies.txt and try again.", "error")
                    self.log("   ➜ Or use Bulk Links File method.", "error")
                    return
                entries = [e for e in (info.get("entries") or []) if e]
                if entries:
                    self.total = len(entries)
                    self.log(f"📋 Found {self.total} videos — downloading…", "info")
                    for i, e in enumerate(entries):
                        if self.cancelled: break
                        self._title = e.get("title", f"Video {i+1}")
                        self.log(f"⬇  [{i+1}/{self.total}] {self._title}", "sub")
                        try:    ydl.download([e["webpage_url"]])
                        except Exception as ex:
                            self.log(f"⚠  Skipped: {ex}", "warning")
                else:
                    self.total = 1; self.done = 0
                    self._title = info.get("title", "Video")
                    self.log(f"🎬 {self._title}", "info")
                    size = (info.get("filesize") or info.get("filesize_approx") or 0)/1_048_576
                    if size: self.log(f"📦 Size: ~{size:.1f} MB", "info")
                    ydl.download([url])
        except Exception as e:
            if "cancelled" not in str(e).lower():
                self.log(f"❌ Facebook ERROR: {e}", "error")
                self.log("   ➜ Make sure cookies.txt is loaded.", "error")

    # ── Bulk list ─────────────────────────────────────────────────────────────
    def dl_list(self, links, out_dir, cookies=""):
        self.total = len(links); self.done = 0
        self.log(f"📂 Bulk File — {self.total} links", "info")
        self.log("─"*55, "sub")
        for i, url in enumerate(links, 1):
            if self.cancelled: break
            url = url.strip()
            if not url or url.startswith("#"):
                self.total -= 1; continue
            self.log(f"\n📌 Link {i} of {len(links)}", "info")
            p = detect_platform(url)
            if p == "youtube":   self.dl_youtube(url, out_dir, cookies)
            elif p == "tiktok":  self.dl_tiktok(url, out_dir, cookies)
            else:                self.dl_facebook(url, out_dir, cookies)
            self.log("─"*55, "sub")


# ── App UI ────────────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("Green Downloader — YouTube + TikTok + Facebook")
        self.geometry("1120x820")
        self.minsize(960, 700)
        self.configure(fg_color=C["bg"])
        self._set_icon()

        self.out_dir    = tk.StringVar(value=os.path.join(os.path.expanduser("~"), "Downloads", "GreenDownloader"))
        self.cookies    = tk.StringVar()
        self.links_file = tk.StringVar()
        self.quality    = tk.StringVar(value="best")
        self.engine     = None
        self._thread    = None
        self._cur_plat  = "none"

        os.makedirs(self.out_dir.get(), exist_ok=True)
        self._build_ui()

    def _set_icon(self):
        try:
            img = tk.PhotoImage(width=64, height=64)
            img.put("#2E7D32", to=(0,0,64,64))
            img.put("white",   to=(24,8,40,40))
            img.put("white",   to=(16,32,48,44))
            img.put("#2E7D32", to=(20,8,44,32))
            self.iconphoto(True, img)
        except Exception:
            pass

    def _build_ui(self):
        hdr = ctk.CTkFrame(self, fg_color=C["header"], corner_radius=0, height=76)
        hdr.pack(fill="x")
        hdr.pack_propagate(False)
        ctk.CTkLabel(hdr, text="  🟢  Green Downloader",
            font=ctk.CTkFont(size=28, weight="bold"),
            text_color="#FFFFFF").pack(side="left", padx=22)
        ctk.CTkLabel(hdr, text="🔴 YouTube  ⚡Fast   🎵 TikTok   🔵 Facebook",
            font=ctk.CTkFont(size=13), text_color="#A5D6A7").pack(side="left", padx=10)

        # FFmpeg status
        ffmpeg_status = "✅ FFmpeg ready — Full HD/4K quality" if FFMPEG_PATH else "⚠ FFmpeg missing — limited quality"
        ffmpeg_color  = "#A5D6A7" if FFMPEG_PATH else "#FFD740"
        ctk.CTkLabel(hdr, text=ffmpeg_status,
            font=ctk.CTkFont(size=11), text_color=ffmpeg_color).pack(side="right", padx=16)

        self.info_bar = ctk.CTkLabel(self, text="",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C["accent"], fg_color="#E8F5E9", height=30)
        self.info_bar.pack(fill="x")

        body = ctk.CTkFrame(self, fg_color=C["bg"])
        body.pack(fill="both", expand=True, padx=14, pady=(10,0))

        self.left_frame = ctk.CTkFrame(body, fg_color=C["card"], corner_radius=14, width=460)
        self.left_frame.pack(side="left", fill="y", padx=(0,10))
        self.left_frame.pack_propagate(False)

        right = ctk.CTkFrame(body, fg_color=C["card2"], corner_radius=14)
        right.pack(side="left", fill="both", expand=True)

        self._build_left(self.left_frame)
        self._build_log(right)
        self._build_bottom()

    def _sec(self, p, txt):
        if txt:
            ctk.CTkLabel(p, text=txt,
                font=ctk.CTkFont(size=12, weight="bold"),
                text_color=C["accent"]).pack(anchor="w", padx=14, pady=(12,2))

    def _build_left(self, parent):
        sc = ctk.CTkScrollableFrame(parent, fg_color="transparent")
        sc.pack(fill="both", expand=True, padx=4, pady=4)

        self._sec(sc, "🔗  Paste Any Video or Profile Link")
        self.url_e = ctk.CTkEntry(sc,
            placeholder_text="YouTube / TikTok / Facebook URL…",
            height=46, font=ctk.CTkFont(size=13),
            fg_color="#F1F8E9", border_color=C["accent"],
            text_color="#212121")
        self.url_e.pack(fill="x", padx=12, pady=(4,4))

        self.plat_lbl = ctk.CTkLabel(sc,
            text="⚡ Platform auto-detected when you paste link",
            font=ctk.CTkFont(size=11), text_color=C["subtext"])
        self.plat_lbl.pack(anchor="w", padx=14, pady=(0,6))
        self.url_e.bind("<KeyRelease>", self._on_url)

        # Speed info box
        speed_box = ctk.CTkFrame(sc, fg_color="#E8F5E9", corner_radius=8)
        speed_box.pack(fill="x", padx=12, pady=(0,8))
        ctk.CTkLabel(speed_box,
            text="⚡ YouTube Fast Mode — Gets video list in seconds\n"
                 "   Downloads start IMMEDIATELY — no long wait!",
            font=ctk.CTkFont(size=10), text_color="#1B5E20",
            justify="left").pack(anchor="w", padx=10, pady=6)

        self._sec(sc, "📺  Quality  (YouTube)")
        qr = ctk.CTkFrame(sc, fg_color="transparent")
        qr.pack(fill="x", padx=12, pady=(4,10))
        for q in ["best","1080p","720p","480p","audio"]:
            ctk.CTkRadioButton(qr, text=q, variable=self.quality, value=q,
                font=ctk.CTkFont(size=12), fg_color=C["accent"],
                hover_color=C["accent2"]).pack(side="left", padx=(0,10))

        self._sec(sc, "📁  Save Videos To")
        dr = ctk.CTkFrame(sc, fg_color="transparent")
        dr.pack(fill="x", padx=12, pady=(4,10))
        ctk.CTkEntry(dr, textvariable=self.out_dir,
            font=ctk.CTkFont(size=11), height=38,
            fg_color="#F1F8E9", text_color="#212121").pack(side="left", fill="x", expand=True, padx=(0,6))
        ctk.CTkButton(dr, text="Browse", width=80, height=38,
            fg_color=C["accent"], hover_color=C["accent2"],
            text_color="white", command=self._pick_dir).pack(side="left")

        self._sec(sc, "🍪  Cookies File  (Facebook & private videos)")
        ckr = ctk.CTkFrame(sc, fg_color="transparent")
        ckr.pack(fill="x", padx=12, pady=(4,2))
        ctk.CTkEntry(ckr, textvariable=self.cookies,
            placeholder_text="cookies.txt — from Bulk Link Collector extension",
            font=ctk.CTkFont(size=11), height=38,
            fg_color="#F1F8E9", text_color="#212121").pack(side="left", fill="x", expand=True, padx=(0,6))
        ctk.CTkButton(ckr, text="Browse", width=80, height=38,
            fg_color="#546E7A", hover_color="#37474F", text_color="white",
            command=self._pick_cookies).pack(side="left")

        self._sec(sc, "📄  Facebook Bulk Links File")
        flr = ctk.CTkFrame(sc, fg_color="transparent")
        flr.pack(fill="x", padx=12, pady=(4,4))
        ctk.CTkEntry(flr, textvariable=self.links_file,
            placeholder_text="links.txt — from Bulk Link Collector extension",
            font=ctk.CTkFont(size=11), height=38,
            fg_color="#F1F8E9", text_color="#212121").pack(side="left", fill="x", expand=True, padx=(0,6))
        ctk.CTkButton(flr, text="Browse", width=80, height=38,
            fg_color="#546E7A", hover_color="#37474F", text_color="white",
            command=self._pick_links).pack(side="left")

        self.fb_btn = ctk.CTkButton(sc,
            text="📄  Download All Links from File",
            height=42, font=ctk.CTkFont(size=13, weight="bold"),
            fg_color=C["fb_btn"], hover_color=C["fb_hover"],
            text_color="white", corner_radius=10,
            command=self._start_file)
        self.fb_btn.pack(fill="x", padx=12, pady=(6,10))

        self.dl_btn = ctk.CTkButton(sc,
            text="⬇   DOWNLOAD NOW",
            height=58, font=ctk.CTkFont(size=20, weight="bold"),
            fg_color=C["accent"], hover_color=C["accent2"],
            text_color="white", corner_radius=14,
            command=self._start)
        self.dl_btn.pack(fill="x", padx=12, pady=(4,6))

        self.cancel_btn = ctk.CTkButton(sc,
            text="✖  Cancel",
            height=36, font=ctk.CTkFont(size=13),
            fg_color="#B71C1C", hover_color="#7F0000",
            text_color="white", corner_radius=8,
            command=self._cancel, state="disabled")
        self.cancel_btn.pack(fill="x", padx=12, pady=(0,16))

    def _build_log(self, parent):
        ctk.CTkLabel(parent, text="📋  Download Log",
            font=ctk.CTkFont(size=12, weight="bold"),
            text_color=C["accent"]).pack(anchor="w", padx=12, pady=(10,4))

        self.log_box = ctk.CTkTextbox(parent,
            font=ctk.CTkFont(family="Consolas", size=12),
            fg_color=C["logbg"], text_color=C["logtext"],
            wrap="word", state="disabled", corner_radius=10)
        self.log_box.pack(fill="both", expand=True, padx=10, pady=(0,6))

        tb = self.log_box._textbox
        tb.tag_config("success", foreground="#00E676")
        tb.tag_config("error",   foreground="#FF5252")
        tb.tag_config("warning", foreground="#FFD740")
        tb.tag_config("info",    foreground="#64B5F6")
        tb.tag_config("sub",     foreground="#888888")
        tb.tag_config("yt",      foreground="#FF5252")
        tb.tag_config("tt",      foreground="#FFD740")
        tb.tag_config("fb",      foreground="#64B5F6")

        br = ctk.CTkFrame(parent, fg_color="transparent")
        br.pack(fill="x", padx=10, pady=(0,10))
        ctk.CTkButton(br, text="🗑 Clear Log", width=110, height=32,
            fg_color="#546E7A", hover_color="#37474F", text_color="white",
            command=self._clear_log).pack(side="left")
        ctk.CTkButton(br, text="📂 Open Folder", width=140, height=32,
            fg_color=C["accent"], hover_color=C["accent2"], text_color="white",
            command=self._open_folder).pack(side="left", padx=8)

    def _build_bottom(self):
        self.bot = ctk.CTkFrame(self, fg_color=C["header"], height=68, corner_radius=0)
        self.bot.pack(fill="x", pady=(8,0))
        self.bot.pack_propagate(False)

        self.progress = ctk.CTkProgressBar(self.bot, height=14,
            progress_color=C["accent2"], fg_color="#0A2A0A")
        self.progress.set(0)
        self.progress.pack(fill="x", padx=20, pady=(10,2))

        self.status_lbl = ctk.CTkLabel(self.bot,
            text="Ready — paste a link and click DOWNLOAD NOW",
            font=ctk.CTkFont(size=11), text_color="#A5D6A7")
        self.status_lbl.pack(pady=(0,6))

    def _apply_theme(self, platform: str):
        if platform == self._cur_plat: return
        self._cur_plat = platform
        if platform == "youtube":
            bc,bh,pc,ic,hc = C["yt_btn"],C["yt_hover"],C["yt_btn"],C["yt_text"],"#B71C1C"
        elif platform == "tiktok":
            bc,bh,pc,ic,hc = C["tt_btn"],C["tt_hover"],C["tt_btn"],C["tt_text"],"#E65100"
        elif platform == "facebook":
            bc,bh,pc,ic,hc = C["fb_btn"],C["fb_hover"],C["fb_btn"],C["fb_text"],"#0D47A1"
        else:
            bc,bh,pc,ic,hc = C["accent"],C["accent2"],C["accent2"],C["accent"],C["header"]
        self.dl_btn.configure(fg_color=bc, hover_color=bh)
        self.progress.configure(progress_color=pc)
        self.bot.configure(fg_color=hc)
        self.info_bar.configure(text_color=ic)

    def _on_url(self, _=None):
        p = detect_platform(self.url_e.get())
        d = {
            "youtube":  ("🔴 YouTube detected — ⚡ Fast Mode ON", C["yt_btn"]),
            "tiktok":   ("🎵 TikTok detected",                    C["tt_btn"]),
            "facebook": ("🔵 Facebook detected",                  C["fb_btn"]),
            "unknown":  ("⚡ Auto-detect",                         C["subtext"]),
        }
        self.plat_lbl.configure(text=d[p][0], text_color=d[p][1])
        if p != "unknown": self._apply_theme(p)

    def _pick_dir(self):
        d = filedialog.askdirectory()
        if d: self.out_dir.set(d)

    def _pick_cookies(self):
        f = filedialog.askopenfilename(filetypes=[("cookies","*.txt *.json"),("All","*.*")])
        if f: self.cookies.set(f)

    def _pick_links(self):
        f = filedialog.askopenfilename(filetypes=[("Text","*.txt"),("All","*.*")])
        if f: self.links_file.set(f)

    def _open_folder(self):
        p = self.out_dir.get(); os.makedirs(p, exist_ok=True)
        if sys.platform=="win32":    os.startfile(p)
        elif sys.platform=="darwin": os.system(f'open "{p}"')
        else:                        os.system(f'xdg-open "{p}"')

    def _clear_log(self):
        self.log_box.configure(state="normal")
        self.log_box.delete("0.0","end")
        self.log_box.configure(state="disabled")

    def _log(self, msg, tag=""):
        ts   = datetime.now().strftime("%H:%M:%S")
        line = f"[{ts}] {msg}\n"
        self.log_box.configure(state="normal")
        if tag: self.log_box._textbox.insert("end", line, tag)
        else:   self.log_box.insert("end", line)
        self.log_box.configure(state="disabled")
        self.log_box.see("end")

    def _set_prog(self, v):   self.progress.set(v)
    def _set_status(self, t): self.status_lbl.configure(text=t)
    def _set_info(self, t):   self.info_bar.configure(text="  "+t)
    def _busy(self):          return self._thread and self._thread.is_alive()

    def _set_dl(self, active):
        self.dl_btn.configure(state="disabled" if active else "normal")
        self.cancel_btn.configure(state="normal" if active else "disabled")

    def _cancel(self):
        if self.engine: self.engine.cancelled = True
        self._log("⚠ Cancel requested…", "warning")

    def _start(self):
        if self._busy():
            messagebox.showinfo("Busy","Download already running."); return
        url = self.url_e.get().strip()
        if not url:
            messagebox.showwarning("No URL","Please paste a link first."); return
        out = self.out_dir.get().strip(); os.makedirs(out, exist_ok=True)
        plat    = detect_platform(url)
        cookies = self.cookies.get().strip()
        quality = self.quality.get()
        self._apply_theme(plat)
        self.engine = DownloadEngine(
            self._log, self._set_prog, self._set_status,
            self._set_info, self._apply_theme)

        def run():
            self._set_dl(True)
            self._set_status("Starting…")
            self._log("="*55, "sub")
            try:
                if plat=="youtube":    self.engine.dl_youtube(url, out, cookies, quality)
                elif plat=="tiktok":   self.engine.dl_tiktok(url, out, cookies)
                elif plat=="facebook": self.engine.dl_facebook(url, out, cookies)
                else:
                    self._log("❓ Unknown — trying as YouTube…","warning")
                    self.engine.dl_youtube(url, out, cookies, quality)
            finally:
                ok = not self.engine.cancelled
                self._set_dl(False)
                self._set_status("✅ All done!" if ok else "⛔ Cancelled")
                self._set_info("✅ Finished!" if ok else "⛔ Cancelled")
                self._apply_theme("none")
                self._log("="*55,"sub")

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()

    def _start_file(self):
        if self._busy():
            messagebox.showinfo("Busy","Download already running."); return
        path = self.links_file.get().strip()
        if not path or not os.path.isfile(path):
            messagebox.showwarning("No file","Please select a links .txt file."); return
        with open(path, encoding="utf-8", errors="ignore") as f:
            links = [l.strip() for l in f if l.strip() and not l.startswith("#")]
        if not links:
            messagebox.showwarning("Empty","No links found in file."); return
        out     = self.out_dir.get().strip(); os.makedirs(out, exist_ok=True)
        cookies = self.cookies.get().strip()
        self._apply_theme("facebook")
        self.engine = DownloadEngine(
            self._log, self._set_prog, self._set_status,
            self._set_info, self._apply_theme)

        def run():
            self._set_dl(True)
            self._set_status("Bulk download starting…")
            self._log("="*55,"sub")
            try:
                self.engine.dl_list(links, out, cookies)
            finally:
                ok = not self.engine.cancelled
                self._set_dl(False)
                self._set_status("✅ All done!" if ok else "⛔ Cancelled")
                self._set_info("✅ Finished!" if ok else "⛔ Cancelled")
                self._apply_theme("none")
                self._log("="*55,"sub")

        self._thread = threading.Thread(target=run, daemon=True)
        self._thread.start()


if __name__ == "__main__":
    app = App()
    app.mainloop()
