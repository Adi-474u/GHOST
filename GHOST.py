"""
Ghost Assistant v11 — ChatGPT-Level + MAX Stealth + REAL Vision
===============================================================
pip install pillow SpeechRecognition pyaudio keyboard pyttsx3 requests

Setup:
  1. ollama serve
  2. ollama pull llava             ← VISION model (reads images!)
  3. ollama pull gpt-oss:120b-cloud  ← TEXT model  (code/math/general)
  4. python ghost_assistant_v11.py

WHY TWO MODELS:
  gpt-oss:120b-cloud  — text only. Great at code, math, aptitude.
  llava               — vision model. Reads screenshots/regions.
  The app auto-picks the right model based on whether image is present.

HOTKEYS:
  Alt+`  show/hide      Alt+S  full screenshot
  Alt+D  draw region    Alt+M  mic
  Alt+T  TTS toggle     Alt+F  fullscreen auto-hide
  Alt+C  clear          Alt+Q  quit
  Alt+A  opacity-       Alt+Z  opacity+

STEALTH LAYERS:
  1. WDA_EXCLUDEFROMCAPTURE  invisible to OBS/Discord/Teams/screenshots
  2. WS_EX_TOOLWINDOW        hidden from taskbar + Alt+Tab
  3. overrideredirect        no title bar, no chrome
  4. Process title spoof     "Runtime Broker Host"
  5. Fullscreen auto-hide    vanishes when fullscreen app detected
  6. Dynamic opacity         slider + hotkeys, near-invisible
  7. No system tray icon     zero footprint
  8. Applied to HWND + parent HWND for max coverage
"""

import tkinter as tk
import threading, io, base64, ctypes, ctypes.wintypes, time, re

try:    from PIL import ImageGrab, Image;  PIL_OK  = True
except: PIL_OK  = False
try:    import speech_recognition as sr;   SR_OK   = True
except: SR_OK   = False
try:    import requests;                   REQ_OK  = True
except: REQ_OK  = False
try:    import keyboard;                   KB_OK   = True
except: KB_OK   = False
try:    import pyttsx3;                    TTS_OK  = True
except: TTS_OK  = False

# ── CONFIG ────────────────────────────────────────────────────────────────────
OLLAMA_URL    = "http://localhost:11434/api/chat"
TEXT_MODEL    = "gpt-oss:120b-cloud"   # text: code + math + general
VISION_MODEL  = "llava"              # vision: reads images (llava / minicpm-v / llava-llama3)
BAR_H         = 48
MAX_H         = 560
WIN_W         = 560
DEF_ALPHA     = 0.93
START_Y       = 6

# ── SYSTEM PROMPT ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """
You are a local, elite AI assistant that excels at math, coding, aptitude, science, logic, and general knowledge.

─────────────────────
GENERAL BEHAVIOR
─────────────────────
* Respond concisely and directly.  Put the final answer first, then any supporting steps or explanations.
* Use a casual tone for informal queries, a precise tone for technical ones.
* Begin every response with a short, polite acknowledgement (e.g., “Sure, here’s …”) – this satisfies the “no filler” requirement while staying friendly.
* If a request is illegal, unsafe, or otherwise disallowed by policy, refuse politely and give a brief rationale.
* If a user explicitly asks “Are you an AI?” or “What model are you?”, answer truthfully (e.g., “I’m an AI language model …”).

─────────────────────
MATHEMATICS & ALGEBRA
─────────────────────
* Solve algebraic, calculus, geometry, and number‑theory problems manually unless the user specifically asks for code.
* Output the final numeric or symbolic answer first, then a clear, step‑by‑step derivation.
* Never provide code for a math problem unless the user says “show me Python/… code”.

─────────────────────
APTITUDE & WORD PROBLEMS
─────────────────────
* Handle work‑time, profit‑loss, ages, clocks, directions, blood‑relations, series, MCQs, etc.
* Provide the answer (or option letter) first, followed by a brief logical walkthrough.
* Do **not** embed any programming code unless the user explicitly requests it.

─────────────────────
CODING & DATA‑STRUCTURES & ALGORITHMS
─────────────────────
* Detect the language from the user’s snippet or request (Python, Java, C++, C, JavaScript, Go, SQL, etc.).
* Return **only** the corrected/complete code inside a fenced block as the first thing after the brief acknowledgement.
  ```<language>
  # code here
        """
# ── Intent prefix injected per query ──────────────────────────────────────────
INTENT_TAG = {
    "math":    "[MATH] Solve step by step. Show all working. Final Answer clearly. NO CODE.\n\n",
    "apti":    "[APTITUDE] Direct answer first, then clean working. No code.\n\n",
    "code":    "[CODE] Detect language. Full working code in fenced block. Brief explanation after.\n\n",
    "image":   "[IMAGE] Read the image. Identify the type (math/code/aptitude/MCQ). Solve it immediately. Do NOT describe the image.\n\n",
    "general": "[GENERAL] Answer directly and concisely.\n\n",
}

INTENT_COLORS = {
    "math": "#fbbf24", "apti": "#a78bfa",
    "code": "#00d4ff", "general": "#10b981", "image": "#f97316",
}
INTENT_ICONS = {
    "math": "∑ MATH", "apti": "⚙ APTI",
    "code": "</> CODE", "general": "◎", "image": "🖼 IMAGE",
}

# ── Classifiers ───────────────────────────────────────────────────────────────
_MATH_RE = re.compile(
    r'(?:\d*\s*[a-zA-Z]\s*[+\-*/]?\s*=|=\s*[+\-]?\s*\d'
    r'|\b(?:solve|simplify|expand|factor|evaluate|calculate|differentiate|integrate|limit)\b'
    r'|\b(?:sin|cos|tan|log|ln|sqrt|square\s*root)\b'
    r'|\b(?:lcm|hcf|gcd|prime|factorial|permutation|combination)\b'
    r'|\b(?:percentage|profit|loss|discount|interest|speed|distance|ratio|average|mean|median)\b'
    r'|\d\s*[+\-*/^]\s*\d'
    r'|\b(?:equation|quadratic|polynomial|matrix)\b)', re.I)

_APTI_RE = re.compile(
    r'\b(?:train|boat|stream|pipe|tank|cistern'
    r'|work.*day|men.*hour|age|older|younger|years\s+ago'
    r'|clock|calendar|leap\s+year|blood\s+relation'
    r'|direction|north|south|east|west|ranking|row|queue'
    r'|aptitude|reasoning|logical|puzzle|riddle'
    r'|number\s+series|odd\s+one\s+out|analogy|syllogism)\b', re.I)

_CODE_RE = re.compile(
    r'(?:\b(?:code|program|function|algorithm|implement|write\s+a'
    r'|array|string|list|tree|graph|stack|queue|linked\s*list'
    r'|sort|search|dynamic\s+programming|recursion'
    r'|python|java(?:script)?|typescript|c\+\+|golang|rust|kotlin|swift'
    r'|sql|html|css|bash|php|ruby|scala'
    r'|bug|error|exception|debug|compile|class|object|loop|pointer)\b'
    r'|def\s+\w|int\s+main|public\s+static|console\.log|System\.out|#include)', re.I)


def classify(text: str) -> str:
    if _MATH_RE.search(text): return "math"
    if _APTI_RE.search(text): return "apti"
    if _CODE_RE.search(text): return "code"
    return "general"


def build_prompt(text: str, is_image: bool = False) -> str:
    key = "image" if is_image else classify(text)
    return INTENT_TAG[key] + text


# ── TTS ───────────────────────────────────────────────────────────────────────
_tts = None
if TTS_OK:
    try:
        _tts = pyttsx3.init()
        _tts.setProperty("rate", 170)
        voices = _tts.getProperty("voices")
        if len(voices) > 1:
            _tts.setProperty("voice", voices[1].id)
    except: _tts = None

# ── Win32 MAX STEALTH ─────────────────────────────────────────────────────────
WDA_EXCLUDEFROMCAPTURE = 0x00000011
GWL_EXSTYLE            = -20
WS_EX_TOOLWINDOW       = 0x00000080
WS_EX_APPWINDOW        = 0x00040000
u32 = ctypes.windll.user32
k32 = ctypes.windll.kernel32


def _stealth_capture(hwnd):
    """Invisible to OBS, Discord, Teams, PrintScreen, screen recorders."""
    try:    return u32.SetWindowDisplayAffinity(hwnd, WDA_EXCLUDEFROMCAPTURE) != 0
    except: return False


def _stealth_taskbar(root):
    """Remove from taskbar and Alt+Tab."""
    try:
        hwnd  = u32.GetParent(root.winfo_id())
        style = u32.GetWindowLongW(hwnd, GWL_EXSTYLE)
        u32.SetWindowLongW(hwnd, GWL_EXSTYLE,
                           (style | WS_EX_TOOLWINDOW) & ~WS_EX_APPWINDOW)
    except: pass


def _stealth_process():
    try: k32.SetConsoleTitleW("Runtime Broker Host")
    except: pass


def _is_fullscreen():
    try:
        hwnd = u32.GetForegroundWindow()
        if not hwnd: return False
        r = ctypes.wintypes.RECT()
        u32.GetWindowRect(hwnd, ctypes.byref(r))
        sw, sh = u32.GetSystemMetrics(0), u32.GetSystemMetrics(1)
        return r.left <= 0 and r.top <= 0 and r.right >= sw and r.bottom >= sh
    except: return False


def _apply_all_stealth(root):
    """Apply every available stealth layer."""
    root.overrideredirect(True)
    root.wm_attributes("-topmost",    True)
    root.wm_attributes("-toolwindow", True)
    root.update()
    hwnd   = root.winfo_id()
    ok     = _stealth_capture(hwnd)
    parent = u32.GetParent(hwnd)
    if parent: _stealth_capture(parent)   # double coverage
    _stealth_taskbar(root)
    return ok


# ── Ollama call — auto-selects TEXT or VISION model ──────────────────────────
def call_ollama(history, prompt, img_bytes):
    model    = VISION_MODEL if img_bytes else TEXT_MODEL
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for h in history[-20:]:
        messages.append(h)
    if img_bytes:
        b64 = base64.b64encode(img_bytes).decode()
        messages.append({"role": "user", "content": prompt, "images": [b64]})
    else:
        messages.append({"role": "user", "content": prompt})
    r = requests.post(OLLAMA_URL, json={
        "model":    model,
        "messages": messages,
        "stream":   False,
        "options":  {"temperature": 0.2, "num_ctx": 4096}
    }, timeout=180)
    r.raise_for_status()
    return r.json()["message"]["content"].strip(), model


# ── Region Selector ───────────────────────────────────────────────────────────
class RegionSelector:
    def __init__(self, on_done):
        self.on_done = on_done
        self.sx = self.sy = 0
        self.root = tk.Toplevel()
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{sw}x{sh}+0+0")
        self.root.overrideredirect(True)
        self.root.wm_attributes("-topmost", True)
        self.root.wm_attributes("-alpha", 0.22)
        self.root.configure(bg="black")
        self.cv = tk.Canvas(self.root, bg="black",
                            highlightthickness=0, cursor="crosshair")
        self.cv.pack(fill="both", expand=True)
        self.rect = None
        tk.Label(self.root, text="drag to select  •  Esc = cancel",
                 font=("Consolas", 13), fg="#00d4ff", bg="black"
                 ).place(relx=0.5, rely=0.02, anchor="n")
        self.root.bind("<Escape>",          self._cancel)
        self.root.bind("<ButtonPress-1>",   self._start)
        self.root.bind("<B1-Motion>",       self._drag)
        self.root.bind("<ButtonRelease-1>", self._release)
        self.root.focus_force()
        self.root.grab_set()

    def _start(self, e):
        self.sx, self.sy = e.x, e.y
        self.rect = self.cv.create_rectangle(
            self.sx, self.sy, self.sx, self.sy,
            outline="#00d4ff", width=2, fill="#00d4ff", stipple="gray25")

    def _drag(self, e):
        if self.rect: self.cv.coords(self.rect, self.sx, self.sy, e.x, e.y)

    def _release(self, e):
        x1, y1 = min(self.sx, e.x), min(self.sy, e.y)
        x2, y2 = max(self.sx, e.x), max(self.sy, e.y)
        self.root.destroy()
        if x2-x1 > 10 and y2-y1 > 10: self.on_done(x1, y1, x2, y2)
        else: self.on_done(None, None, None, None)

    def _cancel(self, e=None):
        self.root.destroy(); self.on_done(None, None, None, None)


# ── THEMES ────────────────────────────────────────────────────────────────────
THEMES = {
    "dark": dict(BG="#07070f", SURF="#0d0d1a", CYAN="#00d4ff",
                 PURPLE="#7c3aed", TEXT="#dce2f2", MUTED="#363650",
                 RED="#f43f5e", GREEN="#10b981", YELLOW="#fbbf24",
                 INPUT="#0f0f20"),
    "light": dict(BG="#f0f2f8", SURF="#ffffff", CYAN="#0077cc",
                  PURPLE="#6d28d9", TEXT="#1a1a2e", MUTED="#9090b0",
                  RED="#e11d48", GREEN="#059669", YELLOW="#d97706",
                  INPUT="#e8eaf5"),
}


# ══════════════════════════════════════════════════════════════════════════════
class Ghost:
    def __init__(self):
        _stealth_process()
        self.theme_name  = "dark"
        self.T           = THEMES["dark"]

        self.root = tk.Tk()
        self.root.title("Runtime Broker Host")
        self.root.configure(bg=self.T["BG"])
        sw = self.root.winfo_screenwidth()
        self.root.geometry(f"{WIN_W}x{BAR_H}+{(sw-WIN_W)//2}+{START_Y}")
        self.stealth_ok = _apply_all_stealth(self.root)

        self._dx = self._dy = 0
        self.listening  = False
        self.visible    = True
        self.tts_on     = False
        self.fs_hide    = False
        self._fs_hidden = False
        self.history    = []
        self._expanded  = False
        self._cur_h     = BAR_H
        self._target_h  = BAR_H
        self._animating = False
        self._btns      = []

        self._build_ui()
        self._register_hotkeys()
        self._boot()
        threading.Thread(target=self._fs_watcher, daemon=True).start()

    # ── fullscreen watcher ────────────────────────────────────────────────────
    def _fs_watcher(self):
        while True:
            time.sleep(0.9)
            if not self.fs_hide: continue
            try:
                fs = _is_fullscreen()
                if fs and self.visible and not self._fs_hidden:
                    self._fs_hidden = True
                    self.root.after(0, self.root.withdraw)
                elif not fs and self._fs_hidden:
                    self._fs_hidden = False
                    self.root.after(0, self.root.deiconify)
                    self.root.after(30, lambda: self.root.wm_attributes("-topmost", True))
            except: pass

    # ── theme ─────────────────────────────────────────────────────────────────
    def _toggle_theme(self):
        self.theme_name = "light" if self.theme_name == "dark" else "dark"
        self.T = THEMES[self.theme_name]
        self._apply_theme()

    def _apply_theme(self):
        T = self.T
        for w, val in [
            (self.root, T["BG"]), (self.bar, T["SURF"]),
            (self.expand, T["BG"]), (self.cf, T["BG"]),
            (self.inp_f, T["SURF"]), (self.lf, T["SURF"]),
            (self.rf, T["SURF"]), (self.sf, T["SURF"]),
            (self.mf, T["BG"]), (self.badge, T["SURF"]),
        ]:
            try: w.configure(bg=val)
            except: pass
        self.chat.configure(bg=T["BG"], fg=T["TEXT"],
                            selectbackground=T["PURPLE"])
        self.inp.configure(bg=T["INPUT"], fg=T["TEXT"],
                           insertbackground=T["CYAN"])
        self.lbl_model.configure(fg=T["PURPLE"], bg=T["BG"])
        self.status_lbl.configure(fg=T["MUTED"], bg=T["SURF"])
        for b in self._btns:
            try: b.configure(bg=T["SURF"])
            except: pass
        self._retag()

    def _retag(self):
        T = self.T
        self.chat.tag_config("user",  foreground=T["CYAN"],   font=("Consolas",10,"bold"))
        self.chat.tag_config("ghost", foreground=T["TEXT"],   font=("Consolas",10))
        self.chat.tag_config("sys",   foreground=T["MUTED"],  font=("Consolas",9,"italic"))
        self.chat.tag_config("err",   foreground=T["RED"])
        self.chat.tag_config("ok",    foreground=T["GREEN"])
        self.chat.tag_config("warn",  foreground=T["YELLOW"])
        for k, col in INTENT_COLORS.items():
            self.chat.tag_config(f"i_{k}", foreground=col, font=("Consolas",8,"bold"))

    # ── BUILD UI ──────────────────────────────────────────────────────────────
    def _build_ui(self):
        T = self.T

        # TOP BAR
        self.bar = tk.Frame(self.root, bg=T["SURF"], height=BAR_H)
        self.bar.pack(fill="x"); self.bar.pack_propagate(False)
        self.bar.bind("<ButtonPress-1>",
            lambda e: (setattr(self,"_dx",e.x), setattr(self,"_dy",e.y)))
        self.bar.bind("<B1-Motion>", self._drag_win)

        # left
        self.lf = tk.Frame(self.bar, bg=T["SURF"])
        self.lf.place(x=10, rely=0.5, anchor="w")
        for col in (T["RED"], T["YELLOW"], T["GREEN"]):
            c = tk.Canvas(self.lf, width=10, height=10,
                          bg=T["SURF"], highlightthickness=0)
            c.create_oval(1,1,9,9, fill=col, outline="")
            c.pack(side="left", padx=2)
        tk.Label(self.lf, text="◈ ghost", font=("Consolas",11,"bold"),
                 fg=T["CYAN"], bg=T["SURF"]).pack(side="left", padx=(6,3))
        self.badge = tk.Label(self.lf, text="◉", font=("Consolas",8),
                              fg=T["MUTED"], bg=T["SURF"])
        self.badge.pack(side="left")

        # center input
        self.inp_f = tk.Frame(self.bar, bg=T["SURF"])
        self.inp_f.place(relx=0.5, rely=0.5, anchor="center", width=175)
        self.ivar = tk.StringVar()
        self.inp = tk.Entry(self.inp_f, textvariable=self.ivar,
                            bg=T["INPUT"], fg=T["TEXT"],
                            insertbackground=T["CYAN"],
                            relief="flat", bd=4, font=("Consolas",9))
        self.inp.pack(fill="x", ipady=5)
        self.inp.bind("<Return>", lambda e: self._send())

        # right buttons
        self.rf = tk.Frame(self.bar, bg=T["SURF"])
        self.rf.place(relx=1.0, x=-6, rely=0.5, anchor="e")

        def btn(txt, cmd, col):
            b = tk.Label(self.rf, text=txt, font=("Consolas",10),
                         fg=col, bg=T["SURF"], cursor="hand2", padx=3)
            b.bind("<Button-1>", lambda e: cmd())
            b.bind("<Enter>",    lambda e: b.config(fg=T["TEXT"]))
            b.bind("<Leave>",    lambda e: b.config(fg=col))
            self._btns.append(b)
            return b

        # opacity slider
        op = tk.Frame(self.rf, bg=T["SURF"]); op.pack(side="left", padx=2)
        tk.Label(op, text="α", font=("Consolas",7),
                 fg=T["MUTED"], bg=T["SURF"]).pack()
        self.av = tk.DoubleVar(value=DEF_ALPHA)
        tk.Scale(op, from_=0.06, to=1.0, resolution=0.04,
                 orient="horizontal", variable=self.av, length=42,
                 bg=T["SURF"], fg=T["MUTED"], highlightthickness=0,
                 troughcolor=T["BG"], sliderrelief="flat", bd=0,
                 showvalue=False,
                 command=lambda v: self.root.wm_attributes("-alpha", float(v))
                 ).pack()

        btn("◑",  self._toggle_theme,   T["MUTED"]).pack(side="left", padx=1)
        btn("🖥",  self._toggle_fshide,  T["MUTED"]).pack(side="left", padx=1)
        btn("📸", self._cap_full,       T["CYAN"]).pack(side="left",  padx=1)
        btn("✏",  self._cap_region,     T["YELLOW"]).pack(side="left", padx=1)
        btn("🎤", self._toggle_mic,     T["PURPLE"]).pack(side="left", padx=1)
        btn("⌫",  self._clear,          T["MUTED"]).pack(side="left",  padx=1)
        btn("✕",  self.root.destroy,    T["RED"]).pack(side="left",   padx=(1,0))

        # EXPAND PANEL
        self.expand = tk.Frame(self.root, bg=T["BG"])
        self.expand.pack(fill="both", expand=True)

        self.mf = tk.Frame(self.expand, bg=T["BG"])
        self.mf.pack(fill="x", padx=10, pady=(3,0))
        self.lbl_model = tk.Label(self.mf,
            text=f"⚙  text:{TEXT_MODEL}  |  vision:{VISION_MODEL}",
            font=("Consolas",7), fg=T["PURPLE"], bg=T["BG"])
        self.lbl_model.pack(side="left")

        self.cf = tk.Frame(self.expand, bg=T["BG"])
        self.cf.pack(fill="both", expand=True, padx=8, pady=(3,3))
        sb = tk.Scrollbar(self.cf, bg=T["SURF"], troughcolor=T["BG"],
                          relief="flat", bd=0, width=3)
        sb.pack(side="right", fill="y")
        self.chat = tk.Text(self.cf, bg=T["BG"], fg=T["TEXT"],
                            font=("Consolas",10), wrap="word",
                            relief="flat", bd=0, state="disabled",
                            spacing1=2, spacing3=4, cursor="arrow",
                            yscrollcommand=sb.set,
                            selectbackground=T["PURPLE"],
                            insertbackground=T["CYAN"])
        self.chat.pack(fill="both", expand=True)
        sb.config(command=self.chat.yview)
        self._retag()

        self.sf = tk.Frame(self.expand, bg=T["SURF"], height=18)
        self.sf.pack(fill="x"); self.sf.pack_propagate(False)
        self.sv = tk.StringVar(value="ready")
        self.status_lbl = tk.Label(self.sf, textvariable=self.sv,
                                   font=("Consolas",7),
                                   fg=T["MUTED"], bg=T["SURF"])
        self.status_lbl.pack(side="left", padx=8)
        tk.Label(self.sf,
                 text="` hide  S screen  D region  M mic  F fs  A/Z opacity  C clear  Q quit",
                 font=("Consolas",6), fg=T["MUTED"], bg=T["SURF"]
                 ).pack(side="right", padx=6)

    # ── drag ──────────────────────────────────────────────────────────────────
    def _drag_win(self, e):
        self.root.geometry(
            f"+{self.root.winfo_x()+e.x-self._dx}"
            f"+{self.root.winfo_y()+e.y-self._dy}")

    # ── animate ───────────────────────────────────────────────────────────────
    def _expand(self):
        if not self._expanded:
            self._expanded = True; self._animate_to(MAX_H)

    def _collapse(self):
        self._expanded = False; self._animate_to(BAR_H)

    def _animate_to(self, t):
        self._target_h = t
        if not self._animating:
            self._animating = True; self.root.after(10, self._step)

    def _step(self):
        d = self._target_h - self._cur_h
        if abs(d) <= 3:
            self._cur_h = self._target_h; self._animating = False
        else:
            self._cur_h += d // 3; self.root.after(12, self._step)
        self.root.geometry(f"{WIN_W}x{self._cur_h}")

    # ── hotkeys ───────────────────────────────────────────────────────────────
    def _register_hotkeys(self):
        if not KB_OK: return
        keyboard.add_hotkey("alt+`", self._toggle_vis)
        keyboard.add_hotkey("alt+s", lambda: self.root.after(0, self._cap_full))
        keyboard.add_hotkey("alt+d", lambda: self.root.after(0, self._cap_region))
        keyboard.add_hotkey("alt+m", lambda: self.root.after(0, self._toggle_mic))
        keyboard.add_hotkey("alt+t", lambda: self.root.after(0, self._toggle_tts))
        keyboard.add_hotkey("alt+f", lambda: self.root.after(0, self._toggle_fshide))
        keyboard.add_hotkey("alt+c", lambda: self.root.after(0, self._clear))
        keyboard.add_hotkey("alt+q", lambda: self.root.after(0, self.root.destroy))
        keyboard.add_hotkey("alt+a", lambda: self.root.after(0, self._op_down))
        keyboard.add_hotkey("alt+z", lambda: self.root.after(0, self._op_up))

    def _toggle_vis(self):
        if self.visible: self.root.after(0, self.root.withdraw)
        else:
            self.root.after(0, self.root.deiconify)
            self.root.after(20, lambda: self.root.wm_attributes("-topmost", True))
        self.visible = not self.visible

    def _toggle_fshide(self):
        self.fs_hide = not self.fs_hide
        self._w("sys", f"fullscreen auto-hide: {'ON' if self.fs_hide else 'OFF'}")
        if not self.fs_hide and self._fs_hidden:
            self._fs_hidden = False
            self.root.deiconify()
            self.root.wm_attributes("-topmost", True)

    def _op_down(self):
        v = max(0.06, round(self.av.get()-0.12, 2))
        self.av.set(v); self.root.wm_attributes("-alpha", v)

    def _op_up(self):
        v = min(1.0, round(self.av.get()+0.12, 2))
        self.av.set(v); self.root.wm_attributes("-alpha", v)

    # ── write helpers ─────────────────────────────────────────────────────────
    def _w(self, tag, text):
        self.chat.config(state="normal")
        pre = {"user":"\n› ","ghost":"","sys":"  ",
               "err":"  ⚠ ","ok":"  ✓ ","warn":"  ⚡ "}
        self.chat.insert("end", pre.get(tag,"") + text + "\n", tag)
        self.chat.see("end")
        self.chat.config(state="disabled")
        if tag in ("ghost","err","ok","warn"):
            self.root.after(0, self._expand)

    def _w_intent(self, intent):
        label = INTENT_ICONS.get(intent, intent.upper())
        self.chat.config(state="normal")
        self.chat.insert("end", f"  {label}\n", f"i_{intent}")
        self.chat.see("end")
        self.chat.config(state="disabled")

    def _st(self, s): self.sv.set(s)

    def _clear(self):
        self.chat.config(state="normal")
        self.chat.delete("1.0","end")
        self.chat.config(state="disabled")
        self.history.clear(); self._collapse()

    # ── boot ──────────────────────────────────────────────────────────────────
    def _boot(self):
        miss = []
        if not PIL_OK:  miss.append("pillow")
        if not SR_OK:   miss.append("SpeechRecognition pyaudio")
        if not REQ_OK:  miss.append("requests")
        if not KB_OK:   miss.append("keyboard")
        if not TTS_OK:  miss.append("pyttsx3")
        if miss: self._w("warn", "pip install " + " ".join(miss))

        if REQ_OK:
            try:
                requests.get("http://localhost:11434", timeout=2)
                self._w("ok", "ollama online")
                # Check if vision model available
                r = requests.get("http://localhost:11434/api/tags", timeout=3)
                models = [m["name"] for m in r.json().get("models", [])]
                has_vision = any(VISION_MODEL.split(":")[0] in m for m in models)
                if not has_vision:
                    self._w("warn",
                        f"vision model '{VISION_MODEL}' not found → "
                        f"run: ollama pull {VISION_MODEL}")
                    self._w("sys", "screenshots will still work but text-only model is used")
            except:
                self._w("err", "ollama offline → run: ollama serve")

        if self.stealth_ok:
            self.badge.config(fg=self.T["GREEN"], text="◉ stealth")
            self._w("ok", "capture exclusion ON — invisible to screen recorders")
        else:
            self.badge.config(fg=self.T["YELLOW"], text="◉ partial")
            self._w("warn", "capture exclusion partial (needs Win10 v2004+)")

        self._st("ready  •  math / code / aptitude / general — type or screenshot")

    # ── TTS ───────────────────────────────────────────────────────────────────
    def _toggle_tts(self):
        if not _tts: self._w("err","pyttsx3 not installed."); return
        self.tts_on = not self.tts_on
        self._w("sys", f"tts {'ON' if self.tts_on else 'OFF'}")

    def _speak(self, text):
        if not self.tts_on or not _tts: return
        threading.Thread(target=lambda: (
            _tts.say(text[:500]), _tts.runAndWait()
        ), daemon=True).start()

    # ── send text ─────────────────────────────────────────────────────────────
    def _send(self):
        t = self.ivar.get().strip()
        if not t: return
        self.ivar.set("")
        self._w("user", t)
        intent = classify(t)
        self._w_intent(intent)
        self._expand()
        threading.Thread(target=self._ask, args=(t, None), daemon=True).start()

    # ── mic ───────────────────────────────────────────────────────────────────
    def _toggle_mic(self):
        if self.listening: return
        if not SR_OK: self._w("err","SpeechRecognition not installed."); return
        self.listening = True
        self._st("🎤 listening…")
        threading.Thread(target=self._listen, daemon=True).start()

    def _listen(self):
        r = sr.Recognizer()
        try:
            with sr.Microphone() as src:
                r.adjust_for_ambient_noise(src, duration=0.3)
                audio = r.listen(src, timeout=8, phrase_time_limit=25)
            text = r.recognize_google(audio)
            self.root.after(0, lambda: self._w("user", f"🎤 {text}"))
            intent = classify(text)
            self.root.after(0, lambda: self._w_intent(intent))
            self._ask(text, None)
        except sr.WaitTimeoutError:
            self.root.after(0, lambda: self._w("sys","no speech."))
        except sr.UnknownValueError:
            self.root.after(0, lambda: self._w("sys","couldn't understand."))
        except Exception as ex:
            self.root.after(0, lambda: self._w("err", str(ex)))
        finally:
            self.listening = False
            self.root.after(0, lambda: self._st("ready"))

    # ── screenshot full ───────────────────────────────────────────────────────
    def _cap_full(self):
        if not PIL_OK: self._w("err","Pillow not installed."); return
        self.root.withdraw()
        self.root.after(200, self._do_cap_full)

    def _do_cap_full(self):
        try:
            img = ImageGrab.grab()
            self.root.deiconify()
            self.root.wm_attributes("-topmost", True)
            # Resize large screens to fit model input
            if img.width > 1280:
                img = img.resize(
                    (1280, int(img.height*1280/img.width)), Image.LANCZOS)
            buf = io.BytesIO(); img.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            self._w("sys", f"analyzing with {VISION_MODEL}…")
            self._w_intent("image")
            self._expand()
            prompt = (
                "Look at this screenshot carefully.\n"
                "STEP 1: Identify what type of problem/content this is.\n"
                "STEP 2: Solve it using the correct approach:\n"
                "  • Math/algebra/equation → solve step by step, show working, give Answer.\n"
                "  • Coding question/error → detect language, write full working code.\n"
                "  • Aptitude/word problem → direct answer + working.\n"
                "  • MCQ → correct option letter + one-line reason.\n"
                "  • Error/exception on screen → show fix.\n"
                "  • Anything else → answer directly.\n"
                "Do NOT describe the image. Jump straight to the solution."
            )
            threading.Thread(target=self._ask, daemon=True,
                             args=(prompt, img_bytes)).start()
        except Exception as ex:
            self.root.deiconify()
            self._w("err", f"capture failed: {ex}")

    # ── screenshot region ─────────────────────────────────────────────────────
    def _cap_region(self):
        if not PIL_OK: self._w("err","Pillow not installed."); return
        self.root.withdraw()
        self.root.after(120, lambda: RegionSelector(self._on_region))

    def _on_region(self, x1, y1, x2, y2):
        self.root.deiconify()
        self.root.wm_attributes("-topmost", True)
        if x1 is None: self._st("ready"); return
        try:
            region = ImageGrab.grab().crop((x1, y1, x2, y2))
            # Upscale tiny crops so model can read text clearly
            min_d = 400
            if region.width < min_d or region.height < min_d:
                scale = max(min_d/region.width, min_d/region.height)
                region = region.resize(
                    (int(region.width*scale), int(region.height*scale)),
                    Image.LANCZOS)
            buf = io.BytesIO(); region.save(buf, format="PNG")
            img_bytes = buf.getvalue()
            self._w("sys", f"analyzing region with {VISION_MODEL}…")
            self._w_intent("image")
            self._expand()
            prompt = (
                "Analyze this image and solve whatever is shown:\n"
                "  • Math/equation → step-by-step working, final Answer.\n"
                "  • Code/DSA → detect language, write full working code.\n"
                "  • Aptitude/word problem → answer + clean working.\n"
                "  • MCQ → correct option + one-line reason.\n"
                "  • Error/exception → fixed code + brief explanation.\n"
                "  • Diagram → explain concisely.\n"
                "Lead with the answer. Do NOT describe the image."
            )
            threading.Thread(target=self._ask, daemon=True,
                             args=(prompt, img_bytes)).start()
        except Exception as ex:
            self._w("err", f"region failed: {ex}")

    # ── core ask ──────────────────────────────────────────────────────────────
    def _ask(self, raw_text, img_bytes):
        if not REQ_OK:
            self.root.after(0, lambda: self._w("err","requests not installed."))
            return
        self.root.after(0, lambda: self._st("thinking…"))
        try:
            prompt        = build_prompt(raw_text, is_image=bool(img_bytes))
            reply, model  = call_ollama(self.history, prompt, img_bytes)
            self.history.append({"role": "user",      "content": raw_text})
            self.history.append({"role": "assistant",  "content": reply})
            if len(self.history) > 40:
                self.history = self.history[-40:]
            # Show which model answered (useful for debugging)
            self.root.after(0, lambda: self._w("ghost", reply))
            self._speak(reply)
        except requests.exceptions.ConnectionError:
            self.root.after(0, lambda: self._w("err",
                "ollama not running → start with: ollama serve"))
        except requests.exceptions.Timeout:
            self.root.after(0, lambda: self._w("err",
                "timeout — model loading, try again in a moment"))
        except Exception as ex:
            self.root.after(0, lambda: self._w("err", str(ex)))
        finally:
            self.root.after(0, lambda: self._st("ready"))

    def run(self): self.root.mainloop()


if __name__ == "__main__":
    Ghost().run()