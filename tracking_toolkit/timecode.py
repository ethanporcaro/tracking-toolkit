import array
from dataclasses import dataclass, field

import bpy
import pyaudio

from .utils import get_state


from .. import __package__ as base_package


@dataclass
class LTCState:
    timecode: str = "00:00:00:00"
    running: bool = False
    stream = None
    sample_rate: int = 48000
    buffer: array.array = field(default_factory=lambda: array.array("h"))


pa: pyaudio.PyAudio = pyaudio.PyAudio()
state: LTCState = LTCState()


def _audio_callback(in_data, *_):
    """PyAudio callback: Appends live audio and decodes the latest LTC frame."""
    global state

    # Append incoming chunk to the rolling buffer.
    state.buffer.extend(array.array("h", in_data))

    # Process when enough data is collected (~0.2 seconds at the current sample rate).
    min_decode_samples = max(1, state.sample_rate // 5)
    if len(state.buffer) >= min_decode_samples:
        buf = state.buffer

        # Detect zero-crossings.
        crossings = []
        prev_sign = buf[0] >= 0
        for i in range(1, len(buf)):
            curr_sign = buf[i] >= 0
            if curr_sign != prev_sign:
                crossings.append(i)
                prev_sign = curr_sign

        # Decode if signal is present.
        if len(crossings) > 10:
            durs = [crossings[i] - crossings[i - 1] for i in range(1, len(crossings))]
            sorted_durs = sorted(durs)

            # Pick short bit from the 10th percentile.
            short_dur = sorted_durs[max(0, len(sorted_durs) // 10)]
            long_threshold = max(1, int(round(short_dur * 1.5)))

            bits = []
            i = 0
            while i < len(durs) - 1:
                if durs[i] >= long_threshold:
                    bits.append("0")
                    i += 1
                else:
                    bits.append("1")
                    i += 2

            bits_str = "".join(bits)

            # Find the last sync word to get the most recent timecode.
            sync_idx = bits_str.rfind("0011111111111101")

            if sync_idx >= 64:
                frame = bits_str[sync_idx - 64 : sync_idx]
                try:
                    # Parse SMPTE BCD (LSB first) into integers
                    f = int(frame[8:10][::-1], 2) * 10 + int(frame[0:4][::-1], 2)
                    s = int(frame[24:27][::-1], 2) * 10 + int(frame[16:20][::-1], 2)
                    m = int(frame[40:43][::-1], 2) * 10 + int(frame[32:36][::-1], 2)
                    h = int(frame[56:58][::-1], 2) * 10 + int(frame[48:52][::-1], 2)

                    state.timecode = f"{h:02d}:{m:02d}:{s:02d}:{f:02d}"
                except ValueError:
                    pass  # Ignore mangled bits

        # Truncate buffer, keeping a small tail proportional to the sample rate.
        state.buffer = buf[-max(1, state.sample_rate // 25) :]

    return in_data, pyaudio.paContinue


def _timecode_preview_timer():
    xr_state = get_state()
    xr_state.timecode = state.timecode
    return 0.5  # Half seconds.


def get_audio_inputs():
    """
    Get all available input devices.
    :return: dict of name:dev_info
    """
    devices = {}

    for i in range(pa.get_device_count()):
        dev = pa.get_device_info_by_index(i)

        # Input only.
        if dev["maxInputChannels"] < 1:
            continue

        devices[dev["name"]] = dev

    return devices


def get_current_timecode():
    return state.timecode


def start_timecode():
    global pa, state

    # Get device from Blender preference.

    devices = get_audio_inputs()
    # Get here to prevent circular import.
    preferences = bpy.context.preferences.addons[base_package].preferences
    dev_name = preferences.ltc_source
    if dev_name == "None":
        print("No LTC source configured")
        return

    dev = devices.get(dev_name)
    if not dev:
        print(f"No such device: {dev_name}")
        return

    state.sample_rate = int(dev["defaultSampleRate"])
    state.stream = pa.open(
        input_device_index=dev["index"],
        format=pyaudio.paInt16,
        channels=1,
        rate=state.sample_rate,
        input=True,
        frames_per_buffer=128,
        stream_callback=_audio_callback,
    )
    state.running = True

    print(f"Listening for timecode on {dev['name']}")

    # Start timecode preview timer.
    if not bpy.app.timers.is_registered(_timecode_preview_timer):
        bpy.app.timers.register(_timecode_preview_timer)


def stop_timecode():
    global pa, state

    if not pa or not state.running:
        return

    state.running = False
    state.stream.stop_stream()
    state.stream.close()
    pa.terminate()

    print("Stopped listening for timecode.")

    # Stop timecode preview timer.
    if bpy.app.timers.is_registered(_timecode_preview_timer):
        bpy.app.timers.unregister(_timecode_preview_timer)
