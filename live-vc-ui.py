# Added in the "eleven labs vc" fork (2026-11-25): a small window for the
# voice changer. Start/stop, a live mic meter with a draggable threshold,
# pause length, volume, noise suppression, voice and device pickers.
# Settings are saved back to .env. The command-line version (live-vc.py)
# still works as before.
import os
import queue
import threading
import tkinter as tk
from tkinter import ttk, messagebox

import sounddevice as sd
from dotenv import dotenv_values

HERE = os.path.dirname(os.path.abspath(__file__))
ENV_PATH = os.path.join(HERE, ".env")
EXAMPLE_PATH = os.path.join(HERE, ".env.example")

METER_MAX = 0.2  # RMS that fills the meter; the meter uses a square-root scale


def level_to_pos(v):
    return min(max(v, 0.0) / METER_MAX, 1.0) ** 0.5


def pos_to_level(p):
    return (p ** 2) * METER_MAX


# ---- .env helpers ---------------------------------------------------------
def load_env():
    if not os.path.exists(ENV_PATH) and os.path.exists(EXAMPLE_PATH):
        with open(EXAMPLE_PATH, encoding="utf-8") as src, open(ENV_PATH, "w", encoding="utf-8") as dst:
            dst.write(src.read())
    return {k: (v or "") for k, v in dotenv_values(ENV_PATH).items()} if os.path.exists(ENV_PATH) else {}


def save_env(updates):
    """Update keys in .env in place, keeping comments and other lines."""
    lines = []
    if os.path.exists(ENV_PATH):
        with open(ENV_PATH, encoding="utf-8") as f:
            lines = f.read().splitlines()
    done = set()
    for i, line in enumerate(lines):
        key = line.split("=", 1)[0].strip()
        if "=" in line and not line.lstrip().startswith("#") and key in updates:
            lines[i] = f"{key}={updates[key]}"
            done.add(key)
    missing = [k for k in updates if k not in done]
    if missing:
        lines.append("")
        lines.append("# Saved by the UI")
        lines.extend(f"{k}={updates[k]}" for k in missing)
    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")


def mme_devices(kind):
    key = "max_input_channels" if kind == "input" else "max_output_channels"
    return [d["name"] for d in sd.query_devices()
            if d[key] > 0 and d["hostapi"] == 0 and "Mapper" not in d["name"]]


def pick(names, wanted, fallback_words):
    if wanted:
        for n in names:
            if wanted.lower() in n.lower():
                return n
    for word in fallback_words:
        for n in names:
            if word.lower() in n.lower():
                return n
    return names[0] if names else ""


# ---- window ---------------------------------------------------------------
class App:
    def __init__(self, root):
        self.root = root
        self.env = load_env()
        self.engine = None
        self.events = queue.Queue()
        self.voices = {}  # label -> id

        root.title("eleven labs vc")
        root.resizable(False, False)
        style = ttk.Style()
        if "vista" in style.theme_names():
            style.theme_use("vista")

        main = ttk.Frame(root, padding=14)
        main.grid(sticky="nsew")
        main.columnconfigure(1, weight=1)
        row = 0

        # Start / status
        top = ttk.Frame(main)
        top.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        self.start_btn = ttk.Button(top, text="▶  Start", width=12, command=self.toggle)
        self.start_btn.pack(side="left")
        self.status = tk.Label(top, text="●  Stopped", fg="#888", font=("Segoe UI", 11, "bold"))
        self.status.pack(side="left", padx=12)
        self.latency = ttk.Label(top, text="")
        self.latency.pack(side="right")
        row += 1

        # Meter + threshold
        ttk.Label(main, text="Mic level").grid(row=row, column=0, sticky="w")
        self.meter = tk.Canvas(main, width=360, height=22, bg="#1e1e1e", highlightthickness=0)
        self.meter.grid(row=row, column=1, columnspan=2, sticky="ew", pady=2)
        row += 1
        ttk.Label(main, text="Talk threshold").grid(row=row, column=0, sticky="w")
        threshold = float(self.env.get("VAD_THRESHOLD") or 0.01)
        self.thr_pos = tk.DoubleVar(value=level_to_pos(threshold))
        ttk.Scale(main, from_=0.05, to=0.8, variable=self.thr_pos,
                  command=lambda _=None: self.apply_live()).grid(row=row, column=1, sticky="ew")
        self.thr_label = ttk.Label(main, width=7)
        self.thr_label.grid(row=row, column=2, sticky="e")
        row += 1
        ttk.Label(main, text="Drag the red line just above the bar's level when you are silent.",
                  foreground="#777").grid(row=row, column=1, columnspan=2, sticky="w", pady=(0, 8))
        row += 1

        # Pause + volume
        ttk.Label(main, text="Pause before sending").grid(row=row, column=0, sticky="w")
        self.pause = tk.DoubleVar(value=float(self.env.get("VAD_SILENCE_DURATION") or 0.5))
        ttk.Scale(main, from_=0.2, to=1.5, variable=self.pause,
                  command=lambda _=None: self.apply_live()).grid(row=row, column=1, sticky="ew")
        self.pause_label = ttk.Label(main, width=7)
        self.pause_label.grid(row=row, column=2, sticky="e")
        row += 1
        ttk.Label(main, text="Shorter = faster replies, but it may cut you off mid-sentence.",
                  foreground="#777").grid(row=row, column=1, columnspan=2, sticky="w", pady=(0, 8))
        row += 1

        ttk.Label(main, text="Output volume").grid(row=row, column=0, sticky="w")
        self.gain = tk.DoubleVar(value=float(self.env.get("OUTPUT_GAIN") or 1.5))
        ttk.Scale(main, from_=0.3, to=3.0, variable=self.gain,
                  command=lambda _=None: self.apply_live()).grid(row=row, column=1, sticky="ew", pady=(0, 8))
        self.gain_label = ttk.Label(main, width=7)
        self.gain_label.grid(row=row, column=2, sticky="e")
        row += 1

        # Toggles
        toggles = ttk.Frame(main)
        toggles.grid(row=row, column=0, columnspan=3, sticky="w", pady=(0, 10))
        self.noise = tk.BooleanVar(value=self.env.get("REMOVE_BACKGROUND_NOISE", "0") in ("1", "true", "True"))
        ttk.Checkbutton(toggles, text="Noise suppression (slower)", variable=self.noise,
                        command=self.apply_live).pack(side="left")
        self.muted = tk.BooleanVar(value=False)
        ttk.Checkbutton(toggles, text="Mute", variable=self.muted,
                        command=self.apply_live).pack(side="left", padx=16)
        row += 1

        ttk.Separator(main).grid(row=row, column=0, columnspan=3, sticky="ew", pady=(0, 10))
        row += 1

        # Voice / devices / key
        ttk.Label(main, text="Voice").grid(row=row, column=0, sticky="w")
        self.voice = ttk.Combobox(main, state="readonly", width=44)
        self.voice.grid(row=row, column=1, sticky="ew", pady=2)
        self.voice.bind("<<ComboboxSelected>>", lambda e: self.apply_live())
        ttk.Button(main, text="↻", width=3, command=self.load_voices).grid(row=row, column=2, sticky="e")
        row += 1

        inputs, outputs = mme_devices("input"), mme_devices("output")
        ttk.Label(main, text="Microphone").grid(row=row, column=0, sticky="w")
        self.mic = ttk.Combobox(main, state="readonly", values=inputs, width=44)
        self.mic.set(pick(inputs, self.env.get("INPUT_DEVICE_NAME"), ["Microphone"]))
        self.mic.grid(row=row, column=1, columnspan=2, sticky="ew", pady=2)
        row += 1
        ttk.Label(main, text="Send voice to").grid(row=row, column=0, sticky="w")
        self.out = ttk.Combobox(main, state="readonly", values=outputs, width=44)
        self.out.set(pick(outputs, self.env.get("OUTPUT_DEVICE_NAME"), ["CABLE Input", "Speakers"]))
        self.out.grid(row=row, column=1, columnspan=2, sticky="ew", pady=2)
        row += 1
        self.cable_hint = ttk.Label(main, foreground="#777")
        self.cable_hint.grid(row=row, column=1, columnspan=2, sticky="w")
        self.out.bind("<<ComboboxSelected>>", lambda e: self.update_hint())
        row += 1

        ttk.Label(main, text="API key").grid(row=row, column=0, sticky="w")
        self.key = tk.StringVar(value=self.env.get("API_KEY", ""))
        ttk.Entry(main, textvariable=self.key, show="•", width=44).grid(
            row=row, column=1, columnspan=2, sticky="ew", pady=2)
        row += 1

        # Log
        self.log = tk.Text(main, height=6, width=60, state="disabled", relief="flat",
                           bg="#f5f5f5", font=("Consolas", 9))
        self.log.grid(row=row, column=0, columnspan=3, sticky="ew", pady=(10, 0))
        self.log.tag_config("error", foreground="#c0392b")
        row += 1

        self.update_hint()
        self.apply_live()
        root.protocol("WM_DELETE_WINDOW", self.close)
        self.load_voices()
        self.tick()

    # ---- helpers -----------------------------------------------------------
    def write_log(self, text, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n", tag)
        lines = int(self.log.index("end-1c").split(".")[0])
        if lines > 200:
            self.log.delete("1.0", f"{lines - 200}.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def set_status(self, text):
        colors = {"Listening": "#27ae60", "Recording": "#e67e22", "Converting": "#2980b9",
                  "Stopped": "#888", "Muted": "#888"}
        self.status.configure(text=f"●  {text}", fg=colors.get(text, "#333"))

    def update_hint(self):
        if "cable" in self.out.get().lower():
            self.cable_hint.configure(text="In Discord/Zoom pick “CABLE Output” as the microphone.")
        else:
            self.cable_hint.configure(text="Playing to speakers: the mic is paused while the voice plays.")

    def voice_id(self):
        return self.voices.get(self.voice.get(), self.env.get("VOICE_ID", ""))

    # ---- voices ------------------------------------------------------------
    def load_voices(self):
        key = self.key.get().strip()
        if not key:
            self.write_log("Paste your ElevenLabs API key below, then press ↻ to load voices.")
            return

        def work():
            try:
                from elevenlabs.client import ElevenLabs
                found = ElevenLabs(api_key=key).voices.get_all().voices
                self.events.put(("voices", found))
            except Exception as e:
                self.events.put(("error", f"Could not load voices: {e}"))
        threading.Thread(target=work, daemon=True).start()

    def show_voices(self, found):
        current = self.env.get("VOICE_ID", "")
        self.voices = {}
        selected = None
        for v in sorted(found, key=lambda v: (v.category != "premade", v.name)):
            label = f"{v.name}  ({v.category})"
            self.voices[label] = v.voice_id
            if v.voice_id == current:
                selected = label
        self.voice.configure(values=list(self.voices))
        if selected:
            self.voice.set(selected)
        elif self.voices:
            self.voice.set(next(iter(self.voices)))
        self.write_log(f"Loaded {len(found)} voices. Free accounts can use the (premade) ones.")

    # ---- live settings -----------------------------------------------------
    def apply_live(self):
        thr = pos_to_level(self.thr_pos.get())
        self.thr_label.configure(text=f"{thr:.3f}")
        self.pause_label.configure(text=f"{self.pause.get():.2f} s")
        self.gain_label.configure(text=f"{self.gain.get():.1f}x")
        if self.engine:
            self.engine.threshold = thr
            self.engine.silence_duration = self.pause.get()
            self.engine.remove_noise = self.noise.get()
            self.engine.muted = self.muted.get()
            self.engine.client.output_gain = self.gain.get()
            if self.voice_id():
                self.engine.client.voice_id = self.voice_id()
            if self.muted.get() != getattr(self, "_was_muted", False):
                self._was_muted = self.muted.get()
                self.set_status("Muted" if self._was_muted else "Listening")

    def settings_dict(self):
        return {
            "API_KEY": self.key.get().strip(),
            "VOICE_ID": self.voice_id(),
            "MODE": "1",
            "INPUT_DEVICE": "",
            "INPUT_DEVICE_NAME": self.mic.get(),
            "OUTPUT_DEVICE": "",
            "OUTPUT_DEVICE_NAME": self.out.get(),
            "VAD_THRESHOLD": f"{pos_to_level(self.thr_pos.get()):.4f}",
            "VAD_SILENCE_DURATION": f"{self.pause.get():.2f}",
            "OUTPUT_GAIN": f"{self.gain.get():.2f}",
            "REMOVE_BACKGROUND_NOISE": "1" if self.noise.get() else "0",
        }

    # ---- start / stop ------------------------------------------------------
    def toggle(self):
        if self.engine:
            self.stop()
        else:
            self.start()

    def start(self):
        values = self.settings_dict()
        if not values["API_KEY"] or not values["VOICE_ID"]:
            messagebox.showwarning("eleven labs vc", "Add your API key and pick a voice first.")
            return
        save_env(values)
        os.environ.update(values)
        try:
            from src.settings.audio import AudioSettings
            from src.el_client import ElevenLabsClient
            from src.engine import LiveEngine
            settings = AudioSettings.from_env()
            client = ElevenLabsClient.from_env()
            self.engine = LiveEngine(settings, client, lambda kind, text: self.events.put((kind, text)))
            self.engine.pause_while_playing = "cable" not in self.out.get().lower()
            self.apply_live()
            self.engine.start()
        except Exception as e:
            self.engine = None
            messagebox.showerror("eleven labs vc", f"Could not start audio:\n{e}")
            return
        self.start_btn.configure(text="■  Stop")
        self.write_log(f"Started: {self.mic.get()}  →  {self.out.get()}")

    def stop(self):
        if self.engine:
            self.engine.stop()
            self.engine = None
        self.start_btn.configure(text="▶  Start")
        self.set_status("Stopped")
        save_env(self.settings_dict())

    def close(self):
        """Window X: stop audio, save settings, and end the whole process."""
        try:
            self.stop()
        except Exception:
            pass
        finally:
            try:
                self.root.destroy()
            finally:
                # Hard exit so no conversion or voice-loading thread can keep the
                # app alive in the background after the window is gone.
                os._exit(0)

    # ---- UI loop -----------------------------------------------------------
    def tick(self):
        while True:
            try:
                kind, payload = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "status" and not self.muted.get():
                self.set_status(payload)
            elif kind == "latency":
                self.latency.configure(text=f"Response time: {payload} ms")
            elif kind == "log":
                self.write_log(payload)
            elif kind == "error":
                self.write_log(payload, "error")
            elif kind == "voices":
                self.show_voices(payload)

        width = int(self.meter.winfo_width()) or 360
        level = self.engine.level if self.engine else 0.0
        thr = pos_to_level(self.thr_pos.get())
        self.meter.delete("all")
        color = "#2ecc71" if level > thr else "#5d6d7e"
        self.meter.create_rectangle(0, 0, level_to_pos(level) * width, 22, fill=color, width=0)
        x = level_to_pos(thr) * width
        self.meter.create_line(x, 0, x, 22, fill="#e74c3c", width=2)
        self.root.after(40, self.tick)


def main():
    root = tk.Tk()
    try:
        App(root)
    except Exception as e:
        messagebox.showerror("eleven labs vc", str(e))
        raise
    root.mainloop()
    os._exit(0)  # the window is gone: never linger in the background


if __name__ == "__main__":
    main()
