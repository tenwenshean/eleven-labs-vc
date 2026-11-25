# Changes from the original

This project is a modified version of [cavoq/elevenlabs-live-vc](https://github.com/cavoq/elevenlabs-live-vc) (upstream commit `fdbd583`, v2.0.0), as required by GPL-3.0 section 5.

## 2026-11-25

### Easier setup (new files)

- **`setup.bat` / `setup.ps1`**: one-click Windows setup. Installs uv if missing, puts a private Python 3.13 and the package cache inside the project folder (`.python/`, `.uv-cache/`), installs the packages, checks for VB-Cable and FFmpeg, and creates `.env` from the template.
- **`start.bat`**: double-click launcher. Passes flags through, e.g. `start.bat --devices`.
- **`.env.example`**: commented settings template. Defaults to hands-free mode, VB-Cable output and a premade voice that works on the free plan.

### Hands-free by default

- `MODE=1` (voice activity detection) is the default in `.env.example`, and output goes to `CABLE Input`, so the app works as a mic for call apps once it's set up.

### Fixes

- **Device names that match several drivers no longer crash** (`src/devices.py`, `src/settings/audio.py`, `src/el_client.py`). On Windows one mic appears under MME, DirectSound, WASAPI and WDM-KS, and `INPUT_DEVICE_NAME` used to fail with "Multiple input devices found". Names now resolve to the first match, for both input and output.
- **ElevenLabs errors no longer kill the app** (`src/el_client.py`, `src/audio_handler.py`). Errors such as 402 (paid plan required) or 401 (bad key) print one line with a hint, and hands-free mode goes back to listening instead of stopping silently.
- **`set_mode` now really switches modes** (`live-vc.py`, `src/audio_recorder.py`). Before, it only changed a setting: `set_mode 1` never started listening and `set_mode 0` never stopped it.
- **Empty push-to-talk recordings** are skipped with a message instead of being sent to the API.

### Friendlier output

- At startup the app shows the mode, microphone and output in use, and warns when a configured device isn't found (with a VB-Cable install hint).
- It checks that `API_KEY` and `VOICE_ID` are set before starting.
- New flags: `--devices` lists each microphone and output once, and `--voices` lists the voices your API key can use.
- `.env` is loaded from the project folder, whatever folder you start the app from.

### Faster and louder

- **Smaller uploads** (`src/audio_processor.py`): recordings are mixed to mono and downsampled to `UPLOAD_SAMPLE_RATE` (default 16 kHz) before upload, a third of the size of 48 kHz.
- **Less waiting:** `VAD_SILENCE_DURATION` defaults to 0.5 s (was 0.8), background-noise removal is off by default (it adds a processing step), and `OPTIMIZE_STREAMING_LATENCY` (default 3) is passed to ElevenLabs. In testing, time to the first audio dropped from about 1.4–2.8 s to about 0.6–0.8 s.
- **Volume:** `NORMALIZE_INPUT` boosts quiet recordings (capped at 8x), and `OUTPUT_GAIN` scales the converted voice (default 1.5, with clipping protection).
- `API_SAMPLE_RATE` now really changes the requested output format (it was hard-coded to `pcm_22050`).
- **Streaming fix:** a network chunk that ends halfway through a 16-bit sample no longer causes an error or a click.
- **SPACE is ignored in hands-free mode.** The key hook is global, so typing a space in any app used to open a second recording on top of the listening one.

### Docs

- README rewritten as a step-by-step guide for call apps, with a troubleshooting table.
- Added `CREDITS.md` and this file.
