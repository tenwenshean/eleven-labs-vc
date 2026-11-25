# Added in the "eleven labs vc" fork (2026-11-25): resolve audio devices by name.
# On Windows each physical device is listed once per host API (MME, DirectSound,
# WASAPI, WDM-KS). Passing a bare name to sounddevice then fails with
# "Multiple input devices found", so we pick the first match ourselves
# (sounddevice lists MME first, which is the most compatible choice).
import sounddevice as sd


def resolve_device(value, kind):
    """Turn an index or name substring into a device index.

    kind is "input" or "output". Returns None (system default) when value is
    empty or nothing matches.
    """
    if value is None or str(value).strip() == "":
        return None
    value = str(value).strip()
    if value.lstrip("-").isdigit():
        return int(value)

    channels_key = "max_input_channels" if kind == "input" else "max_output_channels"
    needle = value.lower()
    for index, device in enumerate(sd.query_devices()):
        if needle in device["name"].lower() and device[channels_key] > 0:
            return index
    return None


def device_label(index, kind):
    """Human readable name for a device index (None = system default)."""
    try:
        if index is None:
            info = sd.query_devices(kind=kind)
            return f"{info['name']} (system default)"
        return f"{sd.query_devices(index)['name']} [#{index}]"
    except Exception:
        return f"device #{index}"
