#!/usr/bin/env python3
"""
Test script to verify CPU optimization for Whisper transcription.
Run this to see the difference in CPU usage and speed.
"""

import os
import time
import psutil
from faster_whisper import WhisperModel

def test_transcription(cpu_threads=0, test_file="test_audio.wav"):
    """Test transcription with specified CPU threads"""
    
    print(f"\n{'='*60}")
    print(f"Testing with cpu_threads={cpu_threads}")
    print(f"{'='*60}")
    
    # Create test audio if it doesn't exist
    if not os.path.exists(test_file):
        print("Creating test audio file...")
        import numpy as np
        from scipy.io.wavfile import write as write_wav
        sample_rate = 16000
        duration = 10  # 10 seconds for better CPU usage testing
        t = np.linspace(0, duration, int(sample_rate * duration), False)
        # Create a more complex signal
        audio_data = 0.3 * np.sin(2 * np.pi * 440 * t)  # A4
        audio_data += 0.2 * np.sin(2 * np.pi * 554.37 * t)  # C#5
        audio_data += 0.1 * np.sin(2 * np.pi * 659.25 * t)  # E5
        audio_data_int16 = np.int16(audio_data * 32767)
        write_wav(test_file, sample_rate, audio_data_int16)
        print(f"Created {test_file}")
    
    # Monitor CPU usage
    process = psutil.Process()
    initial_cpu = process.cpu_percent(interval=0.1)
    
    # Load model
    print(f"Loading model with cpu_threads={cpu_threads}...")
    start_time = time.time()
    model = WhisperModel("base", device="cpu", compute_type="int8", 
                        cpu_threads=cpu_threads, num_workers=1)
    load_time = time.time() - start_time
    print(f"Model loaded in {load_time:.2f} seconds")
    
    # Transcribe
    print("Starting transcription...")
    cpu_samples = []
    
    def monitor_cpu():
        while transcribing:
            cpu_samples.append(psutil.cpu_percent(interval=0.1, percpu=False))
    
    import threading
    transcribing = True
    cpu_thread = threading.Thread(target=monitor_cpu)
    cpu_thread.start()
    
    start_time = time.time()
    segments, info = model.transcribe(test_file)
    text = " ".join([segment.text for segment in segments])
    transcribe_time = time.time() - start_time
    
    transcribing = False
    cpu_thread.join()
    
    # Calculate stats
    avg_cpu = sum(cpu_samples) / len(cpu_samples) if cpu_samples else 0
    max_cpu = max(cpu_samples) if cpu_samples else 0
    
    print(f"\nResults:")
    print(f"- Transcription time: {transcribe_time:.2f} seconds")
    print(f"- Average CPU usage: {avg_cpu:.1f}%")
    print(f"- Peak CPU usage: {max_cpu:.1f}%")
    print(f"- Transcribed text: {text[:100]}...")
    
    return transcribe_time, avg_cpu, max_cpu

def main():
    print("CPU Optimization Test for Whisper Transcription")
    print(f"System info: {os.cpu_count()} logical cores")
    
    # Test with default (0) threads
    time_default, cpu_avg_default, cpu_max_default = test_transcription(cpu_threads=0)
    
    # Test with optimized thread count
    logical_cores = os.cpu_count() or 4
    optimal_threads = max(4, min(logical_cores - 2, logical_cores // 2))
    time_optimal, cpu_avg_optimal, cpu_max_optimal = test_transcription(cpu_threads=optimal_threads)
    
    # Compare results
    print(f"\n{'='*60}")
    print("COMPARISON SUMMARY")
    print(f"{'='*60}")
    print(f"Default (0 threads):")
    print(f"  - Time: {time_default:.2f}s")
    print(f"  - Avg CPU: {cpu_avg_default:.1f}%")
    print(f"  - Max CPU: {cpu_max_default:.1f}%")
    print(f"\nOptimized ({optimal_threads} threads):")
    print(f"  - Time: {time_optimal:.2f}s")
    print(f"  - Avg CPU: {cpu_avg_optimal:.1f}%")
    print(f"  - Max CPU: {cpu_max_optimal:.1f}%")
    print(f"\nSpeed improvement: {(time_default - time_optimal) / time_default * 100:.1f}%")
    print(f"CPU utilization improvement: {(cpu_avg_optimal - cpu_avg_default) / cpu_avg_default * 100:.1f}%")

if __name__ == "__main__":
    main()