# ============================================================
#  LUPA (magnifier.py) - lupa ekranowa pod kursorem myszy
#  Wersja Python (odpowiednik lupa.ps1)
#  Uruchomienie:  python magnifier.py
#  Sterowanie:
#   - okno lupy podaza za kursorem myszy
#   - Alt + kolo myszy (scroll) -> powiekszanie / pomniejszanie (1.5x - 16x)
#   - 2x klik (double-click)    -> zamkniecie lupy
#   - Esc                       -> zamkniecie lupy
#   - Ctrl+Alt+L                -> pokaz / ukryj lupe
#  Wymagania:  pip install pillow
# ============================================================

import sys
import time
import ctypes
import queue
import threading
from ctypes import wintypes

import tkinter as tk

try:
        from PIL import Image, ImageGrab, ImageTk, ImageDraw, ImageOps, ImageEnhance
except ImportError:
    print("Brak biblioteki Pillow. Zainstaluj:  pip install pillow")
    sys.exit(1)

DEBUG = "--debug" in sys.argv

# --- ustawienia -------------------------------------------------
LENS_W    = 340     # szerokosc okna lupy (px)
LENS_H    = 340     # wysokosc okna lupy (px)
HUD_H     = 24      # wysokosc paska HUD
ZOOM_MIN  = 1.5
ZOOM_MAX  = 20.0
ZOOM_STEP = 1.25

# Prog powiekszenia, od ktorego przechodzimy na ostre piksele (NEAREST).
# Ponizej tego progu uzywamy wygladzania (LANCZOS) - tekst wyglada gladko.
SHARP_ZOOM_THRESHOLD = 4.0

# Filtr uzywany przy malym zoomie. LANCZOS daje najwyzsza jakosc
# (redukcja aliasingu i zachowanie krawedzi tekstu) kosztem kilku ms.
SMOOTH_FILTER = Image.LANCZOS

# Interwal odswiezania przechwytywania ekranu (sekundy).
# 1/60 s daje ~60 fps, ale grab jest kosztowny - 1/45 jest plynne i lzejsze.
GRAB_INTERVAL = 1.0 / 45.0

# --- stan -------------------------------------------------------
zoom  = 3.0
shown = True
running = True
frozen = False
last_grab = 0.0
screen_img = None
photo = None
esc_was_down = False
l_was_down   = False
f_was_down   = False
i_was_down   = False
c_was_down   = False

# --- filtry kolorow (jakosc obrazu) -----------------------------
invert     = False   # Ctrl+Alt+I  - odwrocenie kolorow
high_contrast = False  # Ctrl+Alt+C  - tryb wysokiego kontrastu

# --- przechwytywanie ekranu (wirtualny pulpit) ------------------
user32 = ctypes.windll.user32
user32.GetAsyncKeyState.restype = ctypes.c_short

VK_ESCAPE  = 0x1B
VK_MENU    = 0x12      # Alt
VK_CONTROL = 0x11
VK_L       = 0x4C
VK_F       = 0x46
VK_I       = 0x49
VK_C       = 0x43

VS_X = user32.GetSystemMetrics(76)   # SM_XVIRTUALSCREEN
VS_Y = user32.GetSystemMetrics(77)   # SM_YVIRTUALSCREEN
VS_W = user32.GetSystemMetrics(78)   # SM_CXVIRTUALSCREEN
VS_H = user32.GetSystemMetrics(79)   # SM_CYVIRTUALSCREEN

def grab_screen():
    """Przechwyc caly wirtualny ekran raz i uzywaj go dla kadru.

    Grab calego wirtualnego pulpitu jest kosztowny, wiec ograniczamy go
    do ~45 fps - obraz jest plynny, a obciazenie CPU zauwazalnie mniejsze.
    """
    global screen_img, last_grab
    now = time.perf_counter()
    if screen_img is None or (now - last_grab) >= GRAB_INTERVAL:
        screen_img = ImageGrab.grab(
            bbox=(VS_X, VS_Y, VS_X + VS_W, VS_Y + VS_H), all_screens=True)
        # znormalizuj tryb koloru - jednolity RGB ulatwia i przyspiesza resize
        if screen_img.mode != "RGB":
            screen_img = screen_img.convert("RGB")
        last_grab = now
    return screen_img


def pixel_sharp_scale(img, zoom_factor):
    """Skaluj obraz z zachowaniem idealnie rownych, ostrych pikseli.

    Zamiast polegac na probkowaniu NEAREST w skali ulamkowej (ktore przy
    wspolczynnikach niebedacych liczba calkowita daje nierowne bloki
    pikseli - raz 3px, raz 4px, i widoczne 'drganie' obrazu przy ruchu),
    skalowanie dzielimy na dwie fazy:

      1) powiekszenie o CALKOWITY mnoznik  n = floor(zoom)
         -> kazdy piksel zrodlowy staje sie dokladnie n x n pikseli,
            wszystkie bloki sa identyczne i idealnie ostre;
      2) delikatne dopasowanie reszty (zoom / n) filtrem NEAREST,
         ktore nie rozmywa, a jedynie wyrownuje rozmiar do okna lupy.

    Dzieki temu piksele sa ostre, rowne i bez rozmycia, a obraz nie
    'oddycha' przy powolnym ruchu myszy.
    """
    tw, th = img.size

    if zoom_factor <= SHARP_ZOOM_THRESHOLD:
        # maly zoom: wygladzone krawedzie najwyzszej jakosci (LANCZOS)
        # - gladki, naturalny obraz, ostre krawedzie tekstu bez rozmycia
        return img.resize((LENS_W, LENS_H), SMOOTH_FILTER)

    # --- DUZY ZOOM: maksymalna ostrosc tekstu bez rozmycia ---------------
    #
    # Zrodlem 'rozmycia' przy duzym powiekszeniu jest ANTYALIASING obrazu
    # zrodlowego: ImageGrab zwraca krawedzie czcionek z szarymi pikselami
    # przejsciowymi. Powielone kilkanascie razy tworza widoczne szare pasy.
    #
    # Zamiast twardego progu 0/255 (ktory gubi cienkie linie i daje
    # schodkowe krawedzie), delikatnie WZMACNIAMY kontrast krawedzi
    # (S-curve wokol srodka), a nastepnie skalujemy z zachowaniem
    # rownych blokow pikseli. Efekt: krawedzie wyraznie ciemniejsze/
    # jasniejsze niz tlo (ostry tekst), ale cienkie elementy nie znikaja.
    lut = [0] * 256
    for v in range(256):
        # S-curve: neutralnie w 128, mocniej przy skrajach
        d = v - 128
        x = 128 + d * 1.35
        lut[v] = 0 if x < 0 else (255 if x > 255 else int(x))
    sharp = img.point(lut * 3)          # LUT dla 3 kanalow RGB

    # Jedno skalowanie NEAREST bezposrednio do rozmiaru okna.
    #
    # Wczesniej byly DWA przeskalowania NEAREST (najpierw n = floor(zoom),
    # potem dopasowanie do 340) - kazde probkowanie w skali ulamkowej
    # gubilo i dublowalo piksele, co dawalo postrzepione, asymetryczne
    # krawedzie liter i znikajace cienkie linie 1px.
    #
    # Jedno przejscie od razu do 340 px zachowuje wszystkie piksele zrodla
    # (kazdy trafia w co najmniej jeden piksel wyniku), wiec bloki sa rowne,
    # a cienkie linie i krawedzie tekstu pozostaja widoczne.
    return sharp.resize((LENS_W, LENS_H), Image.NEAREST)


def apply_color_filters(img):
    """Zastosuj wybrane filtry kolorow do pojedynczej klatki lupy.

    Filtr dziala na gotowym obrazie 1:1 w rozmiarze okna lupy (LENS_W x LENS_H),
    dzieki czemu nie zaburza ostrosci skalowania i nie wymaga dodatkowego resize.

    Dostepne:
      - invert        : odwrocenie kolorow (Ctrl+Alt+I)
      - high_contrast : podbicie kontrastu wokol punktu neutralnego (Ctrl+Alt+C)
    """
    if not invert and not high_contrast:
        return img

    if invert:
        img = ImageOps.invert(img)

    if high_contrast:
        # Kontrast wokol 128: im wyzsza wartosc, tym mocniejszy podzial
        # jasne/ciemne. 1.0 = bez zmian, 2.0 = mocne wzmocnienie.
        img = ImageEnhance.Contrast(img).enhance(2.0)

    return img

# --- okno -------------------------------------------------------
root = tk.Tk()
root.overrideredirect(True)          # bez ramki
root.attributes("-topmost", True)
root.config(bg="#141414")

root.geometry(f"{LENS_W}x{LENS_H + HUD_H}+100+100")

# HUD - licznik powiekszenia (jak w wersji PowerShell - Consolas)
# (pakowany PIERWSZY z side=bottom, zeby canvas go nie wypchnal poza okno)
# Ciemne tlo + jasny tekst o podwyzszonym kontrascie = czytelny odczyt zoomu.
hud = tk.Label(root, text="", fg="#F0F0F0", bg="#1E1E1E",
               font=("Consolas", 10, "bold"), anchor="center")
hud.pack(side="bottom", fill="x", ipady=3)

# obraz lupy
canvas = tk.Canvas(root, width=LENS_W, height=LENS_H,
                   bg="#141414", highlightthickness=0, bd=0)
canvas.pack(fill="both", expand=True)

# Jeden, stale istniejacy element obrazu. Zamiast kasowac i tworzyc go
# od nowa w kazdej klatce (co powoduje migotanie), podmieniamy tylko
# jego zawartosc przez itemconfig - obraz jest plynny i bez mrugania.
canvas_image_id = canvas.create_image(0, 0, anchor="nw")

# Ostatnia pozycja kursora i ostatnia narysowana pozycja - do wykrywania
# braku ruchu (wtedy nie ma sensu przerysowywac klatki).
_last_cursor = (-1, -1)
_last_zoom   = None

# ============================================================
#  RYSOWANIE LUPY
# ============================================================
def update_lens():
    global photo, _last_cursor, _last_zoom, screen_img
    if not shown:
        return

    if not frozen:
        px = root.winfo_pointerx()
        py = root.winfo_pointery()

        # okno lupy lekko przesuniete w dol, zeby nie zaslanialo kursora
        root.geometry(f"{LENS_W}x{LENS_H + HUD_H}+{px - LENS_W // 2}+{py + 24}")

        # Rysuj nowa klatke tylko gdy kursor sie ruszyl albo zmienil sie zoom.
        # Brak ruchu = brak przerysowania = zero migotania i mniejsze CPU.
        if (px, py) != _last_cursor or zoom != _last_zoom:
            _last_cursor = (px, py)
            _last_zoom   = zoom

            full = grab_screen()

            # rozmiar wycinka w pikselach ekranu (zaokraglony w gore),
            # zeby przy kazdym zoomie pokryc pelne okno lupy
            src_w = max(1, int(round(LENS_W / zoom)))
            src_h = max(1, int(round(LENS_H / zoom)))

            # wycinek wysrodkowany pod kursorem i przyciety do ekranu
            sx = min(max(px - VS_X - src_w // 2, 0), max(0, VS_W - src_w))
            sy = min(max(py - VS_Y - src_h // 2, 0), max(0, VS_H - src_h))

            crop = full.crop((sx, sy, sx + src_w, sy + src_h))

            # Adaptacyjny filtr skalowania: gladko przy malym zoomie,
            # ostro (pikselowo) przy duzym - bez rozmycia i 'halo'.
            # Przy duzym zoomie stosujemy dwufazowe skalowanie, ktore daje
            # idealnie rowne, ostre bloki pikseli (bez 'drgania' obrazu).
            crop = pixel_sharp_scale(crop, zoom)

            # Filtry kolorow: inwersja i/lub wysoki kontrast.
            # Dzialaja na gotowym obrazie 1:1 z oknem, wiec nie zaburzaja
            # ostrosci skalowania.
            crop = apply_color_filters(crop)

            # Podmien obraz w istniejacym elemencie - brak migotania.
            # Stara referencje 'photo' zwalnia GC po nadpisaniu.
            photo = ImageTk.PhotoImage(crop)
            canvas.itemconfig(canvas_image_id, image=photo)
            update_hud()

    root.after(16, update_lens)      # ~60 fps

# ============================================================
#  GLOBALNY HAK MYSZY (WH_MOUSE_LL)
#  Rozwiazanie problemu sterowania: zdarzenia myszy lapane
#  GLOBALNIE - nie trzeba byc nad oknem lupy. Hak dziala w
#  osobnym watku z wlasna pompa komunikatow Windows.
# ============================================================
WH_MOUSE_LL    = 14
HC_ACTION      = 0
WM_MOUSEWHEEL  = 0x020A
WM_LBUTTONDOWN = 0x0201
WM_RBUTTONDOWN = 0x0204
WM_QUIT        = 0x0012

class MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [
        ("pt",          wintypes.POINT),
        ("mouseData",   wintypes.DWORD),
        ("flags",       wintypes.DWORD),
        ("time",        wintypes.DWORD),
        ("dwExtraInfo", ctypes.c_size_t),
    ]

MouseHookProc = ctypes.WINFUNCTYPE(
    ctypes.c_ssize_t, ctypes.c_int, ctypes.c_size_t, ctypes.c_ssize_t)

# 64-bitowe deklaracje - bez tego CallNextHookEx rzuca OverflowError
# i zdarzenia myszy ginie w lancuchu hookow systemu
user32.CallNextHookEx.argtypes = [ctypes.c_void_p, ctypes.c_int,
                                  ctypes.c_size_t, ctypes.c_ssize_t]
user32.CallNextHookEx.restype  = ctypes.c_ssize_t
user32.SetWindowsHookExW.argtypes = [ctypes.c_int, MouseHookProc,
                                     ctypes.c_void_p, ctypes.c_uint]
user32.SetWindowsHookExW.restype  = ctypes.c_void_p
user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]
user32.UnhookWindowsHookEx.restype  = ctypes.c_int

# czas i odstep podwojnego klikniecia - jak w ustawieniach Windows
DBL_TIME_MS = user32.GetDoubleClickTime()
DBL_DIST    = max(user32.GetSystemMetrics(36), 2)   # SM_CXDOUBLECLK

events = queue.Queue()   # zdarzenia haka -> petla glowna Tk
_last_down = {WM_LBUTTONDOWN: None, WM_RBUTTONDOWN: None}   # (czas, x, y)
_hook_handle = None
_hook_thread = None

def _mouse_proc(n_code, w_param, l_param):
    if n_code == HC_ACTION:
        try:
            hs = ctypes.cast(l_param, ctypes.POINTER(MSLLHOOKSTRUCT)).contents

            # Alt + kolo myszy = zoom (gdziekolwiek na ekranie)
            if w_param == WM_MOUSEWHEEL:
                if (user32.GetAsyncKeyState(VK_MENU) & 0x8000) and shown:
                    delta = ctypes.c_short((hs.mouseData >> 16) & 0xFFFF).value
                    events.put(("wheel", 1 if delta > 0 else -1))
                    return 1   # przejmujemy scroll - apka pod lupa nie scrolluje

            # 2x klik = zamknij (gdziekolwiek)
            elif w_param in _last_down:
                now  = time.perf_counter()
                prev = _last_down[w_param]
                if (prev is not None
                        and (now - prev[0]) * 1000.0 <= DBL_TIME_MS
                        and abs(hs.pt.x - prev[1]) <= DBL_DIST
                        and abs(hs.pt.y - prev[2]) <= DBL_DIST):
                    events.put(("dblclick", w_param))
                    _last_down[w_param] = None
                else:
                    _last_down[w_param] = (now, hs.pt.x, hs.pt.y)
        except Exception:
            pass   # hak nie moze nigdy wywalic systemu
    return user32.CallNextHookEx(None, n_code, w_param, l_param)

_mouse_proc_cb = MouseHookProc(_mouse_proc)   # referencja musi zyc caly czas!

def mouse_hook_thread():
    """Watek haka - wymaga wlasnej pompy komunikatow Windows."""
    global _hook_handle
    _hook_handle = user32.SetWindowsHookExW(WH_MOUSE_LL, _mouse_proc_cb, None, 0)
    if not _hook_handle:
        events.put(("hook_error", 0))
        return
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
        pass
    user32.UnhookWindowsHookEx(_hook_handle)

# ============================================================
#  OBSLUGA ZDARZEN (petla 100 Hz w Tk)
# ============================================================
def update_hud():
    """Odswiez tekst HUD: powiekszenie + znaczniki aktywnych filtrow."""
    flags = []
    if invert:
        flags.append("INV")
    if high_contrast:
        flags.append("KONTRAST")
    suffix = "  |  " + " ".join(flags) if flags else ""
    hud.config(text=f"x{zoom:.1f}{suffix}")


def apply_zoom(step):
    global zoom
    if frozen:
        return
    zoom = zoom * ZOOM_STEP if step > 0 else zoom / ZOOM_STEP
    zoom = min(ZOOM_MAX, max(ZOOM_MIN, zoom))
    update_hud()
    if DEBUG:
        print(f"[debug] scroll {step:+d} -> zoom x{zoom:.2f}", flush=True)


def toggle_invert():
    """Ctrl+Alt+I - odwrocenie kolorow."""
    global invert, _last_cursor, _last_zoom
    invert = not invert
    _last_cursor = (-1, -1)   # wymus przerysowanie klatki z nowym filtrem
    _last_zoom   = None
    update_hud()
    if DEBUG:
        print(f"[debug] inwersja kolorow: {'on' if invert else 'off'}", flush=True)


def toggle_contrast():
    """Ctrl+Alt+C - tryb wysokiego kontrastu."""
    global high_contrast, _last_cursor, _last_zoom
    high_contrast = not high_contrast
    _last_cursor = (-1, -1)   # wymus przerysowanie klatki z nowym filtrem
    _last_zoom   = None
    update_hud()
    if DEBUG:
        print(f"[debug] wysoki kontrast: {'on' if high_contrast else 'off'}",
              flush=True)

def close_app(reason=""):
    global running
    if not running:
        return
    running = False
    if DEBUG:
        print(f"[debug] zamykanie ({reason})", flush=True)
    try:
        if _hook_thread is not None and _hook_thread.is_alive():
            user32.PostThreadMessageW(_hook_thread.native_id, WM_QUIT, 0, 0)
    except Exception:
        pass
    try:
        root.destroy()
    except tk.TclError:
        pass

def toggle_shown():
    global shown, _last_cursor, _last_zoom
    shown = not shown
    if shown:
        root.deiconify()
        # wymus odswiezenie klatki po powrocie z ukrycia
        _last_cursor = (-1, -1)
        _last_zoom   = None
        update_lens()
    else:
        root.withdraw()

def toggle_frozen():
    global frozen, _last_cursor, _last_zoom
    frozen = not frozen
    # po odmaroznieniu wymus narysowanie swiezej klatki
    _last_cursor = (-1, -1)
    _last_zoom   = None

def process_events():
    """Zdarzenia z haka myszy + globalne klawisze (GetAsyncKeyState,
    tak jak w wersji .ps1) - dziala niezaleznie od focusu."""
    global esc_was_down, l_was_down, f_was_down, i_was_down, c_was_down
    if not running:
        return

    # 1) zdarzenia z globalnego haka myszy
    try:
        while True:
            kind, val = events.get_nowait()
            if kind == "wheel":
                apply_zoom(val)
            elif kind == "dblclick":
                if shown:
                    close_app("2x klik")
                    return
            elif kind == "hook_error":
                print("UWAGA: nie udalo sie zainstalowac globalnego haka myszy.",
                      flush=True)
    except queue.Empty:
        pass

    # 2) Esc = zamknij (globalnie)
    esc_down = bool(user32.GetAsyncKeyState(VK_ESCAPE) & 0x8000)
    if shown and esc_down and not esc_was_down:
        close_app("Esc")
        return
    esc_was_down = esc_down

    # 3) Ctrl+Alt+L = pokaz / ukryj (globalnie)
    l_down = bool(user32.GetAsyncKeyState(VK_L) & 0x8000)
    ctrl   = bool(user32.GetAsyncKeyState(VK_CONTROL) & 0x8000)
    alt    = bool(user32.GetAsyncKeyState(VK_MENU) & 0x8000)
    if l_down and ctrl and alt and not l_was_down:
        toggle_shown()
    l_was_down = l_down

    # 4) Ctrl+Alt+F = zamroz / odmroz (globalnie)
    f_down = bool(user32.GetAsyncKeyState(VK_F) & 0x8000)
    if f_down and ctrl and alt and not f_was_down:
        toggle_frozen()
    f_was_down = f_down

    # 5) Ctrl+Alt+I = odwrocenie kolorow (globalnie)
    i_down = bool(user32.GetAsyncKeyState(VK_I) & 0x8000)
    if i_down and ctrl and alt and not i_was_down:
        toggle_invert()
    i_was_down = i_down

    # 6) Ctrl+Alt+C = wysoki kontrast (globalnie)
    c_down = bool(user32.GetAsyncKeyState(VK_C) & 0x8000)
    if c_down and ctrl and alt and not c_was_down:
        toggle_contrast()
    c_was_down = c_down

    root.after(10, process_events)

# zapasowo: gdyby okno lupy mialo focus (np. start z konsoli)
root.bind("<Escape>", lambda e: close_app("Esc-tk"))

# ============================================================
#  START
# ============================================================
_hook_thread = threading.Thread(target=mouse_hook_thread, daemon=True)
_hook_thread.start()

root.focus_force()
update_lens()
process_events()
root.mainloop()

# sprzatanie po zamknieciu okna
if _hook_thread.is_alive():
    try:
        user32.PostThreadMessageW(_hook_thread.native_id, WM_QUIT, 0, 0)
        _hook_thread.join(timeout=1)
    except Exception:
        pass