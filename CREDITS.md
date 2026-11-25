# Credits

## Original project

**elevenlabs-live-vc**: https://github.com/cavoq/elevenlabs-live-vc

- **Author:** [cavoq](https://github.com/cavoq) (David Stromberger)
- **Contributor:** [ayeantics](https://github.com/ayeantics)
- **License:** GNU General Public License v3.0

The recording, voice activity detection, audio processing, ElevenLabs streaming and command-line interface all come from the original project. This fork is based on upstream commit `fdbd583450b5e7960e5842846d6e1dbead53ae44` (7 February 2026, version 2.0.0).

If you find this useful, please star the original repository.

## This fork

**eleven labs vc** adds a simpler Windows setup and setup fixes, so more people can use the original tool. See [CHANGES.md](CHANGES.md) for exactly what was changed.

## Services and tools

- [ElevenLabs](https://elevenlabs.io): speech-to-speech voice conversion API
- [VB-Audio Virtual Cable](https://vb-audio.com/Cable/): free virtual audio device by VB-Audio Software (donationware, installed separately and not bundled)
- [uv](https://docs.astral.sh/uv/) by Astral: Python and package installer used by `setup.bat`
- Python libraries: sounddevice, NumPy, SciPy, librosa, numba, python-dotenv, colorama, elevenlabs, keyboard

ElevenLabs and VB-Audio are not affiliated with this project.
