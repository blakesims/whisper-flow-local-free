#!/usr/bin/env python3
"""
Benchmark: Real-time streaming transcription vs file-based transcription.

Usage:
    # Record the benchmark paragraph first:
    python tests/benchmark_transcription.py record

    # Run benchmark (uses saved recording):
    python tests/benchmark_transcription.py

    # Run with a specific WAV file:
    python tests/benchmark_transcription.py /path/to/recording.wav

This simulates real-time audio by feeding a WAV file chunk-by-chunk at the
actual recording rate (16kHz, 1024 samples per chunk = 64ms per chunk).
It tests both v1 (file-based) and v2 (streaming) paths and reports timings.
"""

import os
import sys
import time
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from scipy.io import wavfile

BENCHMARK_WAV = os.path.join(os.path.dirname(__file__), "benchmark_recording.wav")
SAMPLE_RATE = 16000
CHUNK_SIZE = 1024  # matches AudioRecorder.chunk_size


def record_benchmark():
    """Record a benchmark WAV file using the microphone."""
    import sounddevice as sd

    paragraph_path = os.path.join(os.path.dirname(__file__), "benchmark_paragraph.txt")
    with open(paragraph_path) as f:
        paragraph = f.read().strip()

    print("=" * 60)
    print("  BENCHMARK RECORDING")
    print("=" * 60)
    print()
    print("Read this paragraph naturally (don't rush):")
    print()
    print(f"  {paragraph}")
    print()
    input("Press ENTER when ready to start recording...")
    print("Recording... (press Ctrl+C to stop)")

    audio_chunks = []

    def callback(indata, frames, time_info, status):
        audio_chunks.append(indata.copy())

    try:
        with sd.InputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                            blocksize=CHUNK_SIZE, callback=callback):
            while True:
                time.sleep(0.05)
    except KeyboardInterrupt:
        pass

    if not audio_chunks:
        print("No audio captured!")
        return

    audio = np.concatenate(audio_chunks)
    duration = len(audio) / SAMPLE_RATE
    wavfile.write(BENCHMARK_WAV, SAMPLE_RATE, audio)
    print(f"\nSaved: {BENCHMARK_WAV} ({duration:.1f}s, {len(audio)} samples)")


def load_audio(path: str) -> np.ndarray:
    """Load a WAV file and return int16 mono audio at 16kHz."""
    sr, data = wavfile.read(path)
    if sr != SAMPLE_RATE:
        raise ValueError(f"Expected {SAMPLE_RATE}Hz, got {sr}Hz")
    if data.ndim > 1:
        data = data[:, 0]  # take first channel
    if data.dtype != np.int16:
        if data.dtype in (np.float32, np.float64):
            data = (np.clip(data, -1.0, 1.0) * 32767).astype(np.int16)
        else:
            data = data.astype(np.int16)
    return data


def benchmark_v1_file(service, audio: np.ndarray, wav_path: str) -> dict:
    """Benchmark v1: write to file, then transcribe the whole thing."""
    import tempfile

    # Simulate: save audio to WAV (like AudioRecorder does)
    fd, tmp_path = tempfile.mkstemp(suffix=".wav")
    os.close(fd)
    wavfile.write(tmp_path, SAMPLE_RATE, audio)

    duration = len(audio) / SAMPLE_RATE
    print(f"\n--- V1 FILE-BASED (audio: {duration:.1f}s) ---")

    start = time.time()
    result = service.transcribe(tmp_path, language="en", beam_size=1)
    elapsed = time.time() - start

    os.remove(tmp_path)

    text = result.get("text", "").strip()
    print(f"  Transcription time: {elapsed*1000:.0f}ms")
    print(f"  Text ({len(text)} chars): {text[:80]}...")

    return {
        "version": "v1-file",
        "audio_duration": duration,
        "transcription_time_ms": elapsed * 1000,
        "total_latency_ms": elapsed * 1000,  # v1: latency = full transcription
        "text": text,
        "text_length": len(text),
    }


def benchmark_v2_streaming(service, audio: np.ndarray) -> dict:
    """Benchmark v2: feed chunks in real-time, then flush remaining."""
    from app.core.streaming_transcriber import StreamingTranscriber

    duration = len(audio) / SAMPLE_RATE
    print(f"\n--- V2 STREAMING (audio: {duration:.1f}s) ---")

    st = StreamingTranscriber(service, language="en")
    st.start_session()

    vad_status = "yes" if st._vad is not None else "no"
    # Force VAD init so we can report
    if not st._vad_initialized:
        st._init_vad()
        vad_status = "yes" if st._vad is not None else "no (fallback)"

    # Feed chunks at real-time rate
    chunk_count = 0
    segment_log = []
    recording_start = time.time()

    for i in range(0, len(audio), CHUNK_SIZE):
        chunk = audio[i:i + CHUNK_SIZE]
        st.feed_chunk(chunk)
        chunk_count += 1

        # Real-time pacing: sleep to match actual recording rate
        expected_time = (i + CHUNK_SIZE) / SAMPLE_RATE
        actual_elapsed = time.time() - recording_start
        sleep_time = expected_time - actual_elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

        # Log segment completions
        with st._transcribe_lock:
            current_segments = len(st._confirmed_texts)
        if current_segments > len(segment_log):
            elapsed = time.time() - recording_start
            segment_log.append((elapsed, current_segments))
            print(f"  [{elapsed:.1f}s] Segment {current_segments} completed during recording")

    recording_time = time.time() - recording_start

    # Now flush (this is what the user actually waits for)
    with st._transcribe_lock:
        segments_before_flush = len(st._confirmed_texts)

    flush_start = time.time()
    text = st.flush()
    flush_time = time.time() - flush_start

    with st._transcribe_lock:
        segments_after_flush = len(st._confirmed_texts)

    print(f"  VAD: {vad_status}")
    print(f"  Chunks fed: {chunk_count}")
    print(f"  Recording sim time: {recording_time:.2f}s")
    print(f"  Segments during recording: {segments_before_flush}")
    print(f"  Segments after flush: {segments_after_flush}")
    print(f"  Flush time (user waits): {flush_time*1000:.0f}ms")
    print(f"  Text ({len(text)} chars): {text[:80]}...")

    return {
        "version": "v2-streaming",
        "audio_duration": duration,
        "vad": vad_status,
        "segments_during": segments_before_flush,
        "segments_total": segments_after_flush,
        "flush_time_ms": flush_time * 1000,
        "total_latency_ms": flush_time * 1000,  # v2: latency = flush only
        "text": text,
        "text_length": len(text),
    }


def benchmark_v2_streaming_no_vad(service, audio: np.ndarray) -> dict:
    """Benchmark v2 with VAD disabled (fixed 3s intervals)."""
    from app.core.streaming_transcriber import StreamingTranscriber

    duration = len(audio) / SAMPLE_RATE
    print(f"\n--- V2 STREAMING NO-VAD (audio: {duration:.1f}s) ---")

    st = StreamingTranscriber(service, language="en")
    # Force no-VAD mode
    st._vad_initialized = True
    st._vad = None
    st.start_session()
    # Re-force after start_session reset
    st._vad = None

    chunk_count = 0
    segment_log = []
    recording_start = time.time()

    for i in range(0, len(audio), CHUNK_SIZE):
        chunk = audio[i:i + CHUNK_SIZE]
        st.feed_chunk(chunk)
        chunk_count += 1

        expected_time = (i + CHUNK_SIZE) / SAMPLE_RATE
        actual_elapsed = time.time() - recording_start
        sleep_time = expected_time - actual_elapsed
        if sleep_time > 0:
            time.sleep(sleep_time)

        with st._transcribe_lock:
            current_segments = len(st._confirmed_texts)
        if current_segments > len(segment_log):
            elapsed = time.time() - recording_start
            segment_log.append((elapsed, current_segments))
            print(f"  [{elapsed:.1f}s] Segment {current_segments} completed during recording")

    recording_time = time.time() - recording_start

    with st._transcribe_lock:
        segments_before_flush = len(st._confirmed_texts)

    flush_start = time.time()
    text = st.flush()
    flush_time = time.time() - flush_start

    with st._transcribe_lock:
        segments_after_flush = len(st._confirmed_texts)

    print(f"  VAD: disabled (fixed 3s)")
    print(f"  Chunks fed: {chunk_count}")
    print(f"  Recording sim time: {recording_time:.2f}s")
    print(f"  Segments during recording: {segments_before_flush}")
    print(f"  Segments after flush: {segments_after_flush}")
    print(f"  Flush time (user waits): {flush_time*1000:.0f}ms")
    print(f"  Text ({len(text)} chars): {text[:80]}...")

    return {
        "version": "v2-no-vad",
        "audio_duration": duration,
        "vad": "disabled",
        "segments_during": segments_before_flush,
        "segments_total": segments_after_flush,
        "flush_time_ms": flush_time * 1000,
        "total_latency_ms": flush_time * 1000,
        "text": text,
        "text_length": len(text),
    }


def print_comparison(results: list[dict]):
    """Print a comparison table of all benchmark results."""
    print("\n" + "=" * 70)
    print("  BENCHMARK COMPARISON")
    print("=" * 70)

    for r in results:
        version = r["version"]
        dur = r["audio_duration"]
        latency = r["total_latency_ms"]
        txt_len = r["text_length"]
        segs = r.get("segments_during", "-")

        print(f"\n  {version}:")
        print(f"    Audio duration:     {dur:.1f}s")
        print(f"    Segments (during):  {segs}")
        print(f"    User-felt latency:  {latency:.0f}ms")
        print(f"    Text length:        {txt_len} chars")

    # Calculate improvements
    if len(results) >= 2:
        v1 = results[0]
        print(f"\n  --- Improvement vs {v1['version']} ---")
        for r in results[1:]:
            if v1["total_latency_ms"] > 0:
                improvement = (1 - r["total_latency_ms"] / v1["total_latency_ms"]) * 100
                print(f"  {r['version']}: {improvement:+.1f}% latency ({v1['total_latency_ms']:.0f}ms → {r['total_latency_ms']:.0f}ms)")

    print("\n" + "=" * 70)

    # Print full texts for quality comparison
    print("\n  TRANSCRIPTION QUALITY COMPARISON:")
    print("-" * 70)
    for r in results:
        print(f"\n  [{r['version']}]:")
        # Word-wrap at 70 chars
        text = r["text"]
        while text:
            print(f"    {text[:66]}")
            text = text[66:]
    print()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "record":
        record_benchmark()
        return

    # Determine WAV path
    if len(sys.argv) > 1 and os.path.isfile(sys.argv[1]):
        wav_path = sys.argv[1]
    elif os.path.isfile(BENCHMARK_WAV):
        wav_path = BENCHMARK_WAV
    else:
        print(f"No benchmark recording found at: {BENCHMARK_WAV}")
        print(f"Record one first: python {__file__} record")
        return

    # Load audio
    audio = load_audio(wav_path)
    duration = len(audio) / SAMPLE_RATE
    print(f"Loaded: {wav_path} ({duration:.1f}s)")

    # Load model once
    from app.core.transcription_service_cpp import WhisperCppService
    from app.utils.config_manager import ConfigManager

    config = ConfigManager()
    model_name = config.get("transcription_model_name", "base.en")

    service = WhisperCppService(config)
    service.set_target_model_config(model_name)
    service.load_model()
    print(f"Model loaded: {service.model_name}")

    # Warm up the model (first call is slower)
    print("Warming up model...")
    warmup = np.zeros(SAMPLE_RATE, dtype=np.int16)  # 1s silence
    service.transcribe_array(warmup, language="en")

    # Run benchmarks
    results = []

    r1 = benchmark_v1_file(service, audio, wav_path)
    results.append(r1)

    r2 = benchmark_v2_streaming(service, audio)
    results.append(r2)

    r3 = benchmark_v2_streaming_no_vad(service, audio)
    results.append(r3)

    print_comparison(results)


if __name__ == "__main__":
    main()
