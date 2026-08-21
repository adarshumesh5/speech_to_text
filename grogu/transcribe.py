"""CLI: transcribe audio without the GUI.

Examples::

    python -m grogu.transcribe note.wav
    python -m grogu.transcribe note.wav --clean
    python -m grogu.transcribe --record 4 --model base.en

Useful for validating the STT + cleanup pipeline, or for scripting.
"""

from __future__ import annotations

import argparse
import sys
import time
import wave

import numpy as np

from grogu.audio import resample_to_16k
from grogu.cleaner import build_cleaner
from grogu.stt import SttEngine


def read_wav(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as w:
        n = w.getnframes()
        channels = w.getnchannels()
        rate = w.getframerate()
        raw = w.readframes(n)
    data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        data = data.reshape(-1, channels).mean(axis=1)
    return data, rate


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Grogu transcription CLI")
    ap.add_argument("wav", nargs="?", help="path to a WAV file")
    ap.add_argument("--record", type=float, metavar="SECONDS",
                    help="record from the microphone instead of reading a file")
    ap.add_argument("--model", default="small.en")
    ap.add_argument("--device", default="auto", choices=["auto", "cuda", "cpu"])
    ap.add_argument("--language", default="auto")
    ap.add_argument("--no-vad", action="store_true")
    ap.add_argument("--clean", action="store_true", help="also print cleaned text")
    ap.add_argument("--cleaner", default="rules", choices=["rules", "passthrough"])
    args = ap.parse_args(argv)

    if args.record and args.wav:
        ap.error("use either --record or a WAV file, not both")
    if not args.record and not args.wav:
        ap.error("pass a WAV file or use --record")

    if args.record:
        from grogu.audio import MicRecorder

        rec = MicRecorder()
        print(f"Recording {args.record}s… speak now.", file=sys.stderr)
        rec.start()
        time.sleep(args.record)
        audio = rec.stop()
    else:
        audio, rate = read_wav(args.wav)
        audio = resample_to_16k(audio, rate)

    t0 = time.perf_counter()
    print("Loading model…", file=sys.stderr)
    engine = SttEngine.create(args.model, device=args.device)
    text = engine.transcribe(
        audio,
        language=args.language,
        vad=not args.no_vad,
    )
    elapsed = time.perf_counter() - t0
    print(f"(loaded + transcribed in {elapsed:.1f}s)", file=sys.stderr)
    print("RAW:", text)
    if args.clean:
        print("CLEAN:", build_cleaner(args.cleaner).clean(text))
    return 0


if __name__ == "__main__":
    sys.exit(main())
