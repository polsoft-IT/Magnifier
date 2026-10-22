# 🔍 Lupa · Magnifier

**A zero-friction, always-on-top screen magnifier that follows your mouse cursor — and nothing else.**

No window focus. No clicking "activate". No launcher. Just a lens that tracks the cursor
and magnifies whatever is under it — across **all monitors**, in **every application**.


---

## 📖 Overview

**Magnifying glass** is a lightweight, single-file desktop magnifier for
Windows, written in pure Python. It is the Python port of the original `lupa.ps1` PowerShell
tool, rebuilt around a global low-level mouse hook so that **you never have to give the lens
window focus**.

The window is frameless, always-on-top and positioned just below the cursor, so it magnifies
the area you are working on **without ever covering it**. Everything is controlled globally:
scroll to zoom, double-click to dismiss, hotkeys to toggle filters — all from anywhere on the
desktop, in any application.

> **Design goal:** maximum magnification quality and minimum visual noise.
> A magnifier that "breathes", blurs text or flickers is worse than no magnifier at all.

---

### Why this magnifier?

| Typical magnifier | Lupa |
| --- | --- |
| Needs focus / click to activate | **Global hook** — works while you type in another app |
| Mouse wheel scrolls the app underneath | **Wheel is intercepted** while `Alt` is held |
| Fuzzy, anti-aliased text at high zoom | **Adaptive scaling**: smooth below 4×, razor-sharp pixels above |
| Flickering frame-by-frame redraws | **In-place image swap**, zero flicker |
| Redraws even when idle | **Redraw only on cursor movement** or zoom change |
| Single monitor | **Full virtual desktop** — multi-monitor aware |
| Several dependencies | **Pillow** and the standard library, nothing else |

---

## ✨ Features

### 🔎 Image quality & rendering

- **Adaptive scaling pipeline** — the resize filter switches automatically at a zoom
  threshold of `4.0×`:
  - **Below 4×** → `LANCZOS` resampling. Highest-quality smooth interpolation: anti-aliased
    edges, no shimmering, text stays natural and readable.
  - **Above 4×** → edge-contrast enhancement (an S-curve LUT applied per RGB channel) followed
    by a single `NEAREST` resize. This kills the grey anti-aliasing halos that `ImageGrab`
    captures around glyph edges and that become visible "grey stripes" when blown up.
- **Equal, sharp pixel blocks** — a single NEAREST pass directly to the window size preserves
  every source pixel (each one lands on at least one output pixel). No pixel loss, no doubled
  or dropped columns, no "breathing" of the image during slow mouse movement.
- **Thin 1 px lines survive** — because the sharpening uses a soft S-curve instead of a hard
  `0/255` threshold, hairlines and cursor tips do not vanish or become stair-stepped.
- **Optional zoom smoothing off** — the sharp path is deliberate: pixel-perfect text beats
  false smoothness when you are reading small print.

### 🖥️ Stability & performance

- **Flicker-free rendering** — a single persistent canvas image item is reused and updated via
  `itemconfig`; the item is never destroyed and recreated, so no tearing or blinking occurs.
- **Idle-aware loop** — a new frame is captured **only** when the cursor moved or the zoom
  changed. A stationary cursor costs ~0 % CPU for compositing.
- **Rate-limited screen grabbing** — full virtual-desktop capture is throttled to
  `GRAB_INTERVAL = 1/45 s` (~45 fps) while the draw loop runs at ~60 fps. Motion stays fluid and
  CPU load stays noticeably lower than capturing on every tick.
- **Global mouse hook in its own thread** — `WH_MOUSE_LL` runs on a dedicated thread with its
  own Windows message pump, so a slow or blocked hook can never freeze the Tk event loop.
- **Correct 64-bit hook signatures** — `CallNextHookEx`, `SetWindowsHookExW` and
  `UnhookWindowsHookEx` are declared with explicit `argtypes`/`restype`. Without them the
  callback raises `OverflowError` on 64-bit Python and mouse events get lost in the hook chain.
- **Crash-proof callback** — the hook procedure wraps all its work in `try/except`; a malformed
  event is skipped instead of taking down the system hook chain.
- **Lifetime-safe callback reference** — the `WINFUNCTYPE` object is kept alive for the whole
  process; a garbage-collected callback would make the hook call into freed memory.
- **Clean shutdown** — the hook thread is released with `PostThreadMessageW(WM_QUIT)` and joined
  with a timeout; the thread is a daemon, so nothing survives the process.
- **RGB-normalized frames** — every grab is converted to `RGB` once, which makes the subsequent
  resize cheaper and the color filters deterministic.

### 🎨 Contrast & color filters

- **Invert colors** — `Ctrl+Alt+I`. Useful for reading light text on dark backgrounds.
- **High contrast** — `Ctrl+Alt+C`. A `2.0×` contrast boost around the neutral point (128),
  which sharply separates light and dark for low-vision reading.
- Filters apply **on top of the finished 1:1 lens frame**, so enabling them never disturbs the
  scaling sharpness and never triggers an extra resize.
- The active state of both filters is shown as `INV` / `KONTRAST` flags in the HUD.
- Filters can be **combined** — invert and high contrast stack in a defined order.

### 🎮 Interaction

- **Follows the cursor** — the lens window is centred on the pointer and offset 24 px downward
  so it never obscures the point of interest.
- **`Alt` + mouse wheel to zoom** — from `1.5×` to `20.0×` in multiplicative `1.25×` steps.
  The wheel event is **swallowed** (`return 1`), so the application under the lens does not
  scroll while you zoom.
- **Double-click to close** — anywhere on the desktop, left or right button. Uses the real
  Windows double-click time (`GetDoubleClickTime`) and distance (`SM_CXDOUBLECLK`), so it behaves
  exactly like the OS.
- **Show / hide without losing state** — hiding the lens keeps the zoom level, filters and
  frozen frame intact; showing it again forces a fresh frame.
- **Freeze frame** — pause the capture while the lens stays on screen, handy for inspecting a
  transient tooltip or menu.
- **Global hotkeys** — all shortcuts are polled with `GetAsyncKeyState`, so they work regardless
  of which window owns the focus.
- **HUD readout** — a compact dark strip under the lens shows the current magnification
  (`x3.5`) plus active filter flags, in a high-contrast Consolas font.
- **Debug mode** — run with `--debug` to print zoom changes, filter toggles and shutdown reasons
  to the console.

---

## 🚀 Quick Start

### Requirements

| Item | Value |
| --- | --- |
| **Operating system** | Windows 10 / 11 (uses Win32 API — `ctypes.windll.user32`) |
| **Python** | 3.8 or newer (64-bit recommended) |
| **Python packages** | [`Pillow`](https://pypi.org/project/pillow/) |
| **GUI toolkit** | `tkinter` — ships with the standard python.org installer |

Install the single dependency:

```powershell
pip install pillow
```

> **Note:** if `import tkinter` fails, re-run the Python installer and make sure the optional
> component **tcl/tk and IDLE** is enabled. `tkinter` cannot be installed with `pip`.

### Run

```powershell
python magnifier.py
```

With diagnostics enabled:

```powershell
python magnifier.py --debug
```

The lens appears immediately under the cursor. There is no tray icon, no config file and no
installer — close the process or double-click anywhere to exit.

---

## 🎮 Controls

| Shortcut | Action | Scope |
| --- | --- | --- |
| **Move mouse** | Lens follows the cursor | Global |
| **`Alt` + Mouse Wheel ↑** | Zoom in (`×1.25`, up to `20.0×`) | Global |
| **`Alt` + Mouse Wheel ↓** | Zoom out (`÷1.25`, down to `1.5×`) | Global |
| **Double-click** (L or R) | Close the magnifier | Global |
| **`Esc`** | Close the magnifier | Global / window |
| **`Ctrl` + `Alt` + `L`** | Show / hide the lens | Global |
| **`Ctrl` + `Alt` + `F`** | Freeze / unfreeze the frame | Global |
| **`Ctrl` + `Alt` + `I`** | Toggle color inversion (`INV`) | Global |
| **`Ctrl` + `Alt` + `C`** | Toggle high contrast (`KONTRAST`) | Global |

**Keyboard-only shutdown:** `Esc` works globally; the window also binds `<Escape>` as a fallback
for the case where the lens has focus (for example when started from a console).

---

## 🧠 How It Works

The whole program is a single file, `magnifier.py`, and runs as two cooperating loops.

### 1. The capture loop (`update_lens`, ~60 fps)

1. Read the pointer position with `root.winfo_pointerx()` / `winfo_pointery()`.
2. Move the frameless, always-on-top window to `cursor + (0, 24)` so the lens sits **below**
   the cursor rather than under it.
3. Bail out early if the cursor has not moved **and** the zoom has not changed — this is what
   keeps an idle lens essentially free.
4. Fetch a screen image from `grab_screen()`, which caches a full **virtual desktop** grab
   (`ImageGrab.grab(..., all_screens=True)` over `SM_XVIRTUALSCREEN` / `SM_YVIRTUALSCREEN` /
   `SM_CXVIRTUALSCREEN` / `SM_CYVIRTUALSCREEN`) and refreshes it at most every `1/45 s`.
5. Compute the source crop size from the zoom (`LENS_W / zoom`), centre it on the cursor and
   **clamp it to the virtual desktop bounds**, so the lens never reads outside the screen.
6. Run the crop through `pixel_sharp_scale()` — the adaptive quality pipeline described in
   [Image quality & rendering](#-image-quality--rendering).
7. Apply the optional color filters in `apply_color_filters()`.
8. Wrap the result in `ImageTk.PhotoImage` and swap it into the existing canvas item. The old
   `PhotoImage` reference is dropped and reclaimed by the garbage collector.

### 2. The global mouse hook (`WH_MOUSE_LL`)

A low-level mouse hook is installed with `SetWindowsHookExW` inside a dedicated thread that
owns its own message pump (`GetMessageW` loop). The callback `_mouse_proc`:

- **`WM_MOUSEWHEEL`** — if `Alt` is held (`GetAsyncKeyState(VK_MENU) & 0x8000`) and the lens is
  visible, the wheel delta is decoded from the high word of `mouseData`, a `("wheel", ±1)` event
  is queued and the callback returns `1`, consuming the scroll so the app underneath stays put.
- **`WM_LBUTTONDOWN` / `WM_RBUTTONDOWN`** — timestamps and coordinates are compared against the
  Windows double-click time and distance; a valid double-click queues a `("dblclick", ...)`
  event. Note that the *first* click is still passed through to the system, so the click under
  the lens is not lost.
- Everything else is forwarded with `CallNextHookEx`, keeping other hooks in the chain working.

### 3. The event pump (`process_events`, ~100 Hz)

Drains the hook's queue and polls global key state with `GetAsyncKeyState`, using the classic
"was down last tick" edge detection so each shortcut fires once per press:

| Check | Key | Result |
| --- | --- | --- |
| `Esc` | `VK_ESCAPE` | `close_app("Esc")` |
| `Ctrl+Alt+L` | `VK_CONTROL` + `VK_MENU` + `VK_L` | `toggle_shown()` |
| `Ctrl+Alt+F` | `VK_CONTROL` + `VK_MENU` + `VK_F` | `toggle_frozen()` |
| `Ctrl+Alt+I` | `VK_CONTROL` + `VK_MENU` + `VK_I` | `toggle_invert()` |
| `Ctrl+Alt+C` | `VK_CONTROL` + `VK_MENU` + `VK_C` | `toggle_contrast()` |

### Key design decisions

| Decision | Rationale |
| --- | --- |
| **Global hook instead of Tk bindings** | The lens must never steal focus from the app you are working in. |
| **Separate hook thread** | A hook callback runs on the thread that installed it; blocking the Tk loop would stutter the image. |
| **Persistent canvas image item** | Recreating the item each frame causes visible flicker; `itemconfig` does not. |
| **Cached full-desktop grab** | Cropping a cached bitmap is far cheaper than grabbing a small region every frame. |
| **Soft S-curve instead of hard threshold** | A hard `0/255` threshold removes anti-aliasing but also deletes thin strokes. |
| **Single NEAREST pass at high zoom** | Two chained NEAREST resizes each resample at fractional scale, producing jagged, asymmetric glyph edges. |
| **Filters applied after scaling** | Keeps the sharpening pipeline untouched and avoids a second resize. |

---

## ⚙️ Configuration

All tunables live at the top of `magnifier.py`. There is no config file — edit and restart.

| Constant | Default | Meaning |
| --- | --- | --- |
| `LENS_W` | `340` | Lens window width in pixels |
| `LENS_H` | `340` | Lens window height in pixels |
| `HUD_H` | `24` | Height of the HUD strip |
| `ZOOM_MIN` | `1.5` | Minimum magnification |
| `ZOOM_MAX` | `20.0` | Maximum magnification |
| `ZOOM_STEP` | `1.25` | Multiplicative step per wheel notch |
| `SHARP_ZOOM_THRESHOLD` | `4.0` | Zoom above which the sharp (NEAREST) path is used |
| `SMOOTH_FILTER` | `Image.LANCZOS` | Resampling filter for the smooth path |
| `GRAB_INTERVAL` | `1.0 / 45.0` | Minimum time between full-screen grabs (seconds) |

> **Header comment vs. code:** the file header still mentions `1.5x - 16x`, while the actual
> constants allow up to `20.0×`. `ZOOM_MAX` in the code is authoritative.

---

## 🔧 Troubleshooting

<details>
<summary><b>The lens does not react to <code>Alt</code> + wheel or double-click</b></summary>

The global hook failed to install — usually because another process is already holding a
low-level mouse hook, or a security tool is blocking it. Lupa prints
`UWAGA: nie udalo sie zainstalowac globalnego haka myszy.` in this case.
Try closing other input-remapping / macro utilities, or restart Lupa as administrator.
</details>

<details>
<summary><b><code>Brak biblioteki Pillow</code> / <code>ModuleNotFoundError: No module named 'PIL'</code></b></summary>

The script exits early with a friendly message. Install the dependency:

```powershell
pip install pillow
```

If you use several Python versions, pin the interpreter explicitly:

```powershell
py -3 -m pip install pillow
py -3 magnifier.py
```
</details>

<details>
<summary><b>Nothing appears when running on macOS or Linux</b></summary>

Lupa is **Windows-only by design**. It depends on `ctypes.windll.user32`,
`SetWindowsHookExW`, `GetAsyncKeyState`, `GetSystemMetrics` and Pillow's `ImageGrab`
backed by the Windows GDI. There is no portable fallback.
</details>

<details>
<summary><b>The lens shows a black or stale image</b></summary>

- Some hardware-accelerated or DRM-protected surfaces (full-screen video players, some games,
  some remote-desktop sessions) cannot be captured through GDI.
- Try `Ctrl+Alt+F` to unfreeze, or `Ctrl+Alt+L` to hide and show the lens, which forces a fresh
  capture.
- In an RDP session, keep the desktop session unlocked; locked sessions return black frames.
</details>

<details>
<summary><b>Text looks blurry above 4×</b></summary>

Above `SHARP_ZOOM_THRESHOLD` the sharp path intentionally trades smoothness for pixel fidelity,
and it also boosts edge contrast with the S-curve LUT. If you prefer a softer image at high
zoom, raise `SHARP_ZOOM_THRESHOLD`, or change the final `Image.NEAREST` in `pixel_sharp_scale`
to `SMOOTH_FILTER`.
</details>

<details>
<summary><b>Mouse movement feels heavy on a large multi-monitor setup</b></summary>

A full virtual-desktop grab is proportional to total screen area. Raise `GRAB_INTERVAL`
(e.g. `1.0 / 30.0`) to capture less often, or reduce `LENS_W` / `LENS_H`.
</details>

<details>
<summary><b>Why is the window offset downward?</b></summary>

By design: the lens is placed 24 px *below* the cursor so that the cursor tip and its immediate
surroundings stay visible in the magnified view.
</details>

---

## ❓ FAQ

**Is anything written to disk or to the registry?**
No. Lupa reads the screen and reacts to input. No settings, no logs (unless you use `--debug`,
which prints to stdout only), no registry keys, no autostart entry.

**Does it work in any application?**
Yes — the hook and the screen capture are both system-level. The lens window itself is
`overrideredirect` + `topmost`, so it stays on top of full-screen-ish windows as well.

**Can I keep the lens open while working?**
Yes. `Ctrl+Alt+L` hides it without losing state, and `Ctrl+Alt+F` freezes a frame you want to
keep looking at.

**Does the wheel scroll the app under the lens?**
No — while `Alt` is held the wheel event is consumed by the hook and used only for zoom.

**Is the first click of a double-click lost?**
No — the hook only *observes* button events and forwards them via `CallNextHookEx`. The click
reaches the underlying application as usual; the second one additionally closes the lens.

**Why Tkinter instead of a native Win32 overlay?**
A frameless Tk window is enough for a static bitmap overlay and keeps the project to a single
file with zero build step and zero extra dependencies.

---

## 🗂️ Project Structure

```text
.
├── magnifier.py     # The entire application — single file, no build step
├── README.md        # This document
└── .gitignore
```

---

## 🧾 Notes & Limitations

- **Windows only.** Win32 API calls are used directly through `ctypes`.
- **Global hook privileges.** Some locked-down environments may refuse to install a low-level
  mouse hook; the app degrades gracefully with a console warning instead of crashing.
- **Capture cost scales with desktop area.** The whole virtual desktop is grabbed and cropped;
  this is a deliberate trade for simplicity and correct multi-monitor behaviour.
- **No persistence.** Zoom, filters and position are not remembered between runs.
- **Single-file by design.** Everything is intentionally in `magnifier.py` for easy copying,
  reviewing and auditing.

---

## 👤 Author

```text
author:  Sebastian Januchowski
company: polsoft.ITS™
email:   polsoft.its@mail.com
GitHub:  https://github.com/polsoft-it
```

---

<div align="center">

**🔍 Lupa** — a magnifier that stays out of your way.

<sub>Python port of the original <code>lupa.ps1</code> PowerShell magnifier.</sub>

<br/><br/>

**Sebastian Januchowski** &nbsp;·&nbsp; polsoft.ITS™ &nbsp;·&nbsp;
[polsoft.its@mail.com](mailto:polsoft.its@mail.com) &nbsp;·&nbsp;
[github.com/polsoft-it](https://github.com/polsoft-it)

</div>
