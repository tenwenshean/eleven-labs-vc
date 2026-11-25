# Added in the "eleven labs vc" fork (2026-11-25): audio engine for the UI.
#
# Differences from the command-line recorder (src/audio_recorder.py):
# - The mic stays open while a phrase is being converted, so you can keep
#   talking; finished phrases queue up and are converted one after another.
# - The output stream stays open, so each phrase skips opening the device.
# - Threshold, pause length, noise removal and volume can change while running.
# - Very long phrases are sent in pieces (max_phrase) so you hear something sooner.
import queue
import threading
import time
from collections import deque

import numpy as np
import sounddevice as sd
from elevenlabs.core.api_error import ApiError

from src.audio_processor import AudioProcessor
from src.el_client import ElevenLabsClient, describe_api_error

BLOCK = 1024  # samples per mic callback (~21 ms at 48 kHz)


class LiveEngine:
    def __init__(self, settings, client: ElevenLabsClient, on_event):
        self.settings = settings
        self.client = client
        self.processor = AudioProcessor(settings)
        self.on_event = on_event  # on_event(kind, text), called from audio threads

        # Live-tunable
        self.threshold = settings.vad_threshold
        self.silence_duration = settings.vad_silence_duration
        self.min_duration = settings.vad_min_recording_duration
        self.remove_noise = settings.remove_background_noise
        self.max_phrase = 12.0
        self.muted = False
        # If the voice plays through speakers the mic would hear it and convert
        # it again, so the mic is ignored while playing. Not needed for VB-Cable.
        self.pause_while_playing = True

        self.level = 0.0
        self.recording = False
        self.playing = False
        self._chunks = []
        self._pre = deque(maxlen=int(settings.vad_pre_buffer_duration * settings.sample_rate / BLOCK) + 2)
        self._start = 0.0
        self._last_voice = 0.0
        self._queue = queue.Queue()
        self._in = None
        self._out = None
        self._worker = None

    # ---- lifecycle -------------------------------------------------------
    def start(self):
        self._out = sd.OutputStream(samplerate=self.client.output_sample_rate, channels=1,
                                    dtype="float32", device=self.client.output_device)
        self._out.start()
        self._in = sd.InputStream(samplerate=self.settings.sample_rate, channels=1, dtype="float32",
                                  blocksize=BLOCK, device=self.settings.input_device,
                                  callback=self._callback)
        self._in.start()
        self._worker = threading.Thread(target=self._work, daemon=True)
        self._worker.start()
        self.on_event("status", "Listening")

    def stop(self):
        for stream in (self._in, self._out):
            if stream is not None:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass
        self._in = self._out = None
        self._queue.put(None)
        self.recording = False
        self.level = 0.0

    # ---- mic callback (audio thread: keep it light) ----------------------
    def _callback(self, indata, frames, time_info, status):
        block = indata.copy()
        rms = float(np.sqrt(np.mean(block ** 2)))
        self.level = rms
        if self.muted or (self.pause_while_playing and self.playing):
            if self.recording:
                self._reset()
            return

        now = time.time()
        if not self.recording:
            self._pre.append(block)
            if rms > self.threshold:
                self.recording = True
                self._chunks = list(self._pre)
                self._start = self._last_voice = now
                self.on_event("status", "Recording")
            return

        self._chunks.append(block)
        if rms > self.threshold:
            self._last_voice = now
        long_enough = now - self._start > self.min_duration
        if (long_enough and now - self._last_voice > self.silence_duration) or now - self._start > self.max_phrase:
            self._queue.put(self._chunks)
            self._reset()
            self.on_event("status", "Converting")

    def _reset(self):
        self.recording = False
        self._chunks = []
        self._pre.clear()

    # ---- conversion worker ----------------------------------------------
    def _work(self):
        while True:
            chunks = self._queue.get()
            if chunks is None:
                return
            if self._out is None:
                continue
            wav = self.processor.get_audio_stream(chunks)
            if wav is None:
                self.on_event("log", "Too short, skipped")
                self.on_event("status", "Listening")
                continue
            self.playing = True
            started = time.time()
            try:
                self.client.convert_audio(
                    wav, self.remove_noise, output_stream=self._out,
                    on_first_chunk=lambda ms: self.on_event("latency", f"{ms:.0f}"),
                )
                self.on_event("log", f"Done in {time.time() - started:.1f}s")
            except ApiError as e:
                message, hint = describe_api_error(e)
                self.on_event("error", f"{message}\n{hint}".strip())
            except Exception as e:
                self.on_event("error", f"Conversion failed: {e}")
            finally:
                self.playing = False
            if self._queue.empty():
                self.on_event("status", "Listening")
