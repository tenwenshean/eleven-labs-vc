from io import BytesIO
import os
import time
import numpy as np
import sounddevice as sd
import colorama
from scipy.signal import resample_poly
from elevenlabs.client import ElevenLabs
from elevenlabs.core.api_error import ApiError

from src.devices import resolve_device

# Fork changes (2026-11-25): output device names resolve to one index and warn
# when missing; ElevenLabs API errors print a short explanation instead of a
# traceback that kills the listener.
API_ERROR_HINTS = {
    401: "Your API_KEY was rejected. Check it in .env (https://elevenlabs.io/app/settings/api-keys).",
    402: "ElevenLabs needs a paid plan for this voice or you are out of credits. "
         "Free accounts can only use premade voices: run 'start.bat --voices' to list them.",
    404: "VOICE_ID was not found on your account. Run 'start.bat --voices' to list the ones you can use.",
    422: "ElevenLabs could not read the recording. Try speaking a little longer.",
    429: "Too many requests or out of credits. Wait a moment and try again.",
}


class ElevenLabsClient:
    def __init__(self, api_key, voice_id, output_device=None, output_sample_rate=48000, api_sample_rate=22050):
        self.client = ElevenLabs(api_key=api_key)
        self.voice_id = voice_id
        self.output_device = output_device
        self.output_sample_rate = output_sample_rate
        self.api_sample_rate = api_sample_rate
        self.output_device_missing = None  # name from .env that matched nothing
        self.output_gain = 1.0
        self.streaming_latency = None

    @classmethod
    def from_env(cls):
        output_device = resolve_device(os.getenv("OUTPUT_DEVICE"), "output")
        output_device_name = os.getenv("OUTPUT_DEVICE_NAME", "").strip()
        missing_name = None
        if output_device is None and output_device_name:
            output_device = resolve_device(output_device_name, "output")
            if output_device is None:
                missing_name = output_device_name

        client = cls(
            os.getenv("API_KEY", None),
            os.getenv("VOICE_ID", None),
            output_device=output_device,
            output_sample_rate=int(os.getenv("OUTPUT_SAMPLE_RATE", 48000)),
            api_sample_rate=int(os.getenv("API_SAMPLE_RATE", 22050)),
        )
        client.output_device_missing = missing_name
        # Fork additions (2026-11-25): volume and latency tuning.
        client.output_gain = float(os.getenv("OUTPUT_GAIN", 1.0))
        latency = os.getenv("OPTIMIZE_STREAMING_LATENCY", "3").strip()
        client.streaming_latency = int(latency) if latency.isdigit() else None
        return client

    def convert_audio_safe(self, audio: BytesIO, remove_background_noise: bool) -> bool:
        """convert_audio, but report errors in one line and keep the app alive."""
        try:
            self.convert_audio(audio, remove_background_noise)
            print(f"{colorama.Fore.GREEN}Done.{colorama.Style.RESET_ALL}")
            return True
        except ApiError as e:
            hint = API_ERROR_HINTS.get(e.status_code, "")
            detail = e.body.get("detail", e.body) if isinstance(e.body, dict) else e.body
            if isinstance(detail, dict):
                detail = detail.get("message", detail)
            print(f"{colorama.Fore.RED}ElevenLabs error {e.status_code}: {detail}{colorama.Style.RESET_ALL}")
            if hint:
                print(f"{colorama.Fore.YELLOW}{hint}{colorama.Style.RESET_ALL}")
        except Exception as e:  # network, audio device, ...
            print(f"{colorama.Fore.RED}Conversion failed: {e}{colorama.Style.RESET_ALL}")
        return False

    def _resample(self, samples: np.ndarray, orig_rate: int, target_rate: int) -> np.ndarray:
        if orig_rate == target_rate:
            return samples
        if samples.size == 0:
            return samples
        return resample_poly(samples, target_rate, orig_rate).astype(np.float32)

    def convert_audio(self, audio: BytesIO, remove_background_noise: bool):
        start_time = time.time()
        extra = {}
        if self.streaming_latency is not None:
            extra["optimize_streaming_latency"] = self.streaming_latency
        audio_stream = self.client.speech_to_speech.convert_as_stream(
            voice_id=self.voice_id,
            audio=audio,
            # Fork fix: was hard-coded to pcm_22050 even when API_SAMPLE_RATE changed.
            output_format=f"pcm_{self.api_sample_rate}",
            remove_background_noise=remove_background_noise,
            **extra,
        )

        stream = None
        first_chunk_time = None
        try:
            stream = sd.OutputStream(
                samplerate=self.output_sample_rate,
                channels=1,
                dtype="float32",
                device=self.output_device
            )
            stream.start()

            leftover = b""
            for chunk in audio_stream:
                if not chunk:
                    continue
                if first_chunk_time is None:
                    first_chunk_time = time.time()
                    latency_ms = (first_chunk_time - start_time) * 1000
                    print(f"{colorama.Fore.CYAN}First chunk in {latency_ms:.0f}ms{colorama.Style.RESET_ALL}")

                # Fork fix: a network chunk can end halfway through a 16-bit
                # sample; keep the odd byte for the next chunk.
                chunk = leftover + chunk
                cut = len(chunk) - (len(chunk) % 2)
                chunk, leftover = chunk[:cut], chunk[cut:]
                samples = np.frombuffer(chunk, dtype=np.int16).astype(np.float32) / 32768.0
                if samples.size == 0:
                    continue
                samples = self._resample(samples, self.api_sample_rate, self.output_sample_rate)
                if self.output_gain != 1.0:
                    samples = np.clip(samples * self.output_gain, -1.0, 1.0)
                stream.write(samples.reshape(-1, 1))
        finally:
            if stream is not None:
                stream.stop()
                stream.close()
