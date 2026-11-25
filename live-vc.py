import cmd
import os
import sys
from src.audio_handler import AudioHandler
from src.devices import device_label
import colorama
from dotenv import load_dotenv

# Fork changes (2026-11-25): .env is loaded from this folder whatever the
# working directory, startup checks + device summary, --devices / --voices.
HERE = os.path.dirname(os.path.abspath(__file__))
load_dotenv(os.path.join(HERE, ".env"))
colorama.init()

Y, G, R, C, RESET = (colorama.Fore.YELLOW, colorama.Fore.GREEN, colorama.Fore.RED,
                     colorama.Fore.CYAN, colorama.Style.RESET_ALL)


def list_devices():
    """Print each audio device once (first host API = MME on Windows)."""
    import sounddevice as sd
    for kind, key in (("Microphones (INPUT_DEVICE)", "max_input_channels"),
                      ("Outputs (OUTPUT_DEVICE)", "max_output_channels")):
        print(f"{C}{kind}{RESET}")
        for i, d in enumerate(sd.query_devices()):
            if d[key] > 0 and d["hostapi"] == 0 and "Mapper" not in d["name"]:
                print(f"  {i:>3}  {d['name']}")
    print(f"\nPut the number in .env, e.g. INPUT_DEVICE=1 (or use *_DEVICE_NAME with part of the name).")


def list_voices():
    """Print the voices this API key can use."""
    from elevenlabs.client import ElevenLabs
    client = ElevenLabs(api_key=os.getenv("API_KEY"))
    current = os.getenv("VOICE_ID")
    for v in client.voices.get_all().voices:
        mark = "*" if v.voice_id == current else " "
        print(f"{mark} {v.category:<13} {v.voice_id}  {v.name}")
    print(f"\nPremade voices work on the free plan. Copy an ID into VOICE_ID in .env.")


def check_config():
    problems = []
    for name in ("API_KEY", "VOICE_ID"):
        if not os.getenv(name, "").strip():
            problems.append(f"{name} is empty in .env")
    if problems:
        for p in problems:
            print(f"{R}{p}{RESET}")
        print(f"{Y}Open .env (in {HERE}), fill it in and start again.{RESET}")
        sys.exit(1)


def print_summary(handler):
    settings = handler.recorder.settings
    client = handler.el_client
    mode = "hands-free (speak, then pause)" if settings.mode == 1 else "push-to-talk (SPACE)"
    print(f"{C}Mode:   {mode}")
    print(f"Mic:    {device_label(settings.input_device, 'input')}")
    print(f"Output: {device_label(client.output_device, 'output')}{RESET}")
    if settings.input_device_missing:
        print(f"{Y}No microphone matches '{settings.input_device_missing}', using the default. "
              f"Run 'start.bat --devices'.{RESET}")
    if client.output_device_missing:
        print(f"{Y}No output matches '{client.output_device_missing}', using your speakers instead.")
        if "cable" in client.output_device_missing.lower():
            print(f"VB-Cable does not look installed: get it from https://vb-audio.com/Cable/ and reboot.")
        print(RESET, end="")
    print()

banner = """
██╗     ██╗██╗   ██╗███████╗    ██╗   ██╗ ██████╗
██║     ██║██║   ██║██╔════╝    ██║   ██║██╔════╝
██║     ██║██║   ██║█████╗█████╗██║   ██║██║
██║     ██║╚██╗ ██╔╝██╔══╝╚════╝╚██╗ ██╔╝██║
███████╗██║ ╚████╔╝ ███████╗     ╚████╔╝ ╚██████╗
╚══════╝╚═╝  ╚═══╝  ╚══════╝      ╚═══╝   ╚═════╝
"""

description = """Description: A live voice-changer utilizing elevenlabs voice-cloning API.
Author: https://github.com/cavoq
Version: 2.0.0
"""


class ElevenlabsLiveVCCmd(cmd.Cmd):
    intro = f"""{colorama.Fore.GREEN}{banner}\n{
        description}{colorama.Style.RESET_ALL}\n"""
    prompt = f"{colorama.Fore.LIGHTBLUE_EX}(live-vc){colorama.Style.RESET_ALL}"

    def __init__(self):
        super().__init__()
        self.audio_handler = AudioHandler.from_env()

    def cmdloop(self, intro=None):
        # Print banner first, then start VAD to keep ordering clean.
        print(self.intro)
        print_summary(self.audio_handler)
        if self.audio_handler.recorder.vad_enabled:
            self.audio_handler.start_vad_mode()
        super().cmdloop(intro="")

    def do_clear(self, arg=None):
        """Clear the screen."""
        if os.name == 'nt':
            os.system('cls')
        else:
            os.system('clear')
        print(self.intro)

    def do_quit(self, arg=None):
        """Quit the program."""
        print(f"Exiting...")
        return True

    def do_set_mode(self, arg):
        """Set the mode to automatic (1) or manual (0)."""
        try:
            mode = int(arg)
            if mode not in self.audio_handler.recorder.settings.valid_modes():
                print(
                    f"{colorama.Fore.YELLOW}Invalid mode. Please enter 0 for manual or 1 for automatic.{
                        colorama.Style.RESET_ALL}"
                )
                return
            recorder = self.audio_handler.recorder
            was_vad = recorder.vad_enabled
            recorder.settings.mode = mode
            recorder.vad_enabled = mode == 1
            if mode == 1 and not was_vad:
                recorder.set_vad_callback(self.audio_handler.process_vad_recording)
                self.audio_handler.start_vad_mode()
            elif mode == 0 and was_vad:
                recorder.stop_listening()
            mode_str = "automatic" if self.audio_handler.recorder.settings.mode == 1 else "manual"
            print(
                f"{colorama.Fore.GREEN}Mode set to {mode_str}.{
                    colorama.Style.RESET_ALL}"
            )
        except ValueError:
            print(
                f"{colorama.Fore.YELLOW}Invalid input. Please enter 0 for manual or 1 for automatic.{
                    colorama.Style.RESET_ALL}"
            )

    def do_get_mode(self, arg):
        """Get the current mode (1 = automatic, 0 = manual)."""
        mode_str = "automatic" if self.audio_handler.recorder.settings.mode == 1 else "manual"
        print(f"Current mode is {mode_str}.")


if __name__ == "__main__":
    if "--devices" in sys.argv:
        list_devices()
        sys.exit(0)
    check_config()
    if "--voices" in sys.argv:
        list_voices()
        sys.exit(0)
    try:
        ElevenlabsLiveVCCmd().cmdloop()
    except KeyboardInterrupt:
        print("\nExiting gracefully...")
        exit(0)
