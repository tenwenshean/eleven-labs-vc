import numpy as np
from io import BytesIO
from scipy.io.wavfile import write
from scipy.signal import resample_poly

from src.settings.audio import AudioSettings


class AudioProcessor:
    def __init__(self, settings: AudioSettings):
        self.settings = settings

    @classmethod
    def from_env(cls):
        return cls(AudioSettings.from_env())

    def _trim_silence(self, audio_data: np.ndarray) -> np.ndarray:
        if audio_data.size == 0:
            return audio_data

        if audio_data.ndim == 1:
            amplitude = np.abs(audio_data)
        else:
            amplitude = np.max(np.abs(audio_data), axis=1)

        threshold = self.settings.silence_threshold
        non_silent = np.where(amplitude > threshold)[0]
        if non_silent.size == 0:
            return audio_data

        start = int(non_silent[0])
        end = int(non_silent[-1]) + 1
        return audio_data[start:end]

    def get_audio_stream(self, audio_data: np.ndarray) -> BytesIO | None:
        if audio_data is None or len(audio_data) == 0:
            return None

        audio_data = np.concatenate(audio_data, axis=0)
        audio_data = self._trim_silence(audio_data)
        if audio_data.size == 0:
            return None

        min_samples = int(self.settings.min_audio_duration * self.settings.sample_rate)
        if audio_data.shape[0] < min_samples:
            return None

        # Fork change (2026-11-25): mono, peak-normalised and downsampled before
        # upload. A 16 kHz clip is 3x smaller than 48 kHz, so it uploads faster,
        # and a normalised input gives a louder, steadier converted voice.
        if audio_data.ndim > 1:
            audio_data = audio_data.mean(axis=1)
        if self.settings.normalize_input:
            peak = float(np.max(np.abs(audio_data)))
            if 0 < peak < 0.9:
                audio_data = audio_data * min(0.9 / peak, 8.0)  # cap boost so noise isn't blown up
        rate = self.settings.sample_rate
        upload_rate = self.settings.upload_sample_rate
        if upload_rate and upload_rate < rate:
            from math import gcd
            g = gcd(rate, upload_rate)
            audio_data = resample_poly(audio_data, upload_rate // g, rate // g)
            rate = upload_rate

        audio_data_pcm = (np.clip(audio_data, -1.0, 1.0) * 32767).astype(np.int16)
        wav_memory = BytesIO()
        write(wav_memory, rate, audio_data_pcm)
        wav_memory.seek(0)
        return wav_memory
