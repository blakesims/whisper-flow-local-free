#!/usr/bin/env python3
"""
Compare faster-whisper vs openai-whisper performance on Apple Silicon
Usage: python compare_whisper_implementations.py <audio_file>
"""

import os
import sys
import time
import argparse
import numpy as np
import psutil
import threading
from datetime import datetime
import json

# Check if required packages are installed
try:
    import whisper
    has_openai_whisper = True
except ImportError:
    has_openai_whisper = False
    print("Warning: openai-whisper not installed. Install with: pip install openai-whisper")

try:
    from faster_whisper import WhisperModel
    has_faster_whisper = True
except ImportError:
    has_faster_whisper = False
    print("Warning: faster-whisper not installed. Install with: pip install faster-whisper")

class PerformanceMonitor:
    """Monitor CPU and memory usage during transcription"""
    
    def __init__(self):
        self.cpu_samples = []
        self.memory_samples = []
        self.monitoring = False
        self.monitor_thread = None
        
    def start(self):
        """Start monitoring in a separate thread"""
        self.monitoring = True
        self.cpu_samples = []
        self.memory_samples = []
        self.monitor_thread = threading.Thread(target=self._monitor)
        self.monitor_thread.start()
        
    def stop(self):
        """Stop monitoring and return results"""
        self.monitoring = False
        if self.monitor_thread:
            self.monitor_thread.join()
        
        if not self.cpu_samples:
            return {"avg_cpu": 0, "max_cpu": 0, "avg_memory": 0, "max_memory": 0}
            
        return {
            "avg_cpu": sum(self.cpu_samples) / len(self.cpu_samples),
            "max_cpu": max(self.cpu_samples),
            "avg_memory": sum(self.memory_samples) / len(self.memory_samples),
            "max_memory": max(self.memory_samples)
        }
        
    def _monitor(self):
        """Monitor CPU and memory usage"""
        process = psutil.Process()
        
        while self.monitoring:
            try:
                # CPU usage (percentage)
                cpu_percent = psutil.cpu_percent(interval=0.1)
                self.cpu_samples.append(cpu_percent)
                
                # Memory usage (MB)
                memory_mb = process.memory_info().rss / 1024 / 1024
                self.memory_samples.append(memory_mb)
                
                time.sleep(0.1)
            except:
                pass

def test_openai_whisper(audio_file, model_name="base"):
    """Test OpenAI Whisper implementation"""
    if not has_openai_whisper:
        return None
        
    print(f"\n{'='*60}")
    print("Testing OpenAI Whisper")
    print(f"{'='*60}")
    
    monitor = PerformanceMonitor()
    
    # Load model
    print(f"Loading OpenAI Whisper model: {model_name}...")
    load_start = time.time()
    model = whisper.load_model(model_name)
    load_time = time.time() - load_start
    print(f"Model loaded in {load_time:.2f} seconds")
    
    # Transcribe
    print("Starting transcription...")
    monitor.start()
    transcribe_start = time.time()
    
    result = model.transcribe(audio_file, fp16=False, language="en")
    
    transcribe_time = time.time() - transcribe_start
    perf_stats = monitor.stop()
    
    print(f"Transcription completed in {transcribe_time:.2f} seconds")
    
    return {
        "implementation": "openai-whisper",
        "model": model_name,
        "load_time": load_time,
        "transcribe_time": transcribe_time,
        "total_time": load_time + transcribe_time,
        "text": result["text"],
        "performance": perf_stats
    }

def test_faster_whisper(audio_file, model_name="base"):
    """Test faster-whisper implementation"""
    if not has_faster_whisper:
        return None
        
    print(f"\n{'='*60}")
    print("Testing faster-whisper")
    print(f"{'='*60}")
    
    monitor = PerformanceMonitor()
    
    # Detect if on Apple Silicon
    import platform
    is_apple_silicon = sys.platform == "darwin" and "arm" in platform.machine().lower()
    
    # Optimal settings for Apple Silicon
    if is_apple_silicon:
        cpu_threads = os.cpu_count() - 1
        print(f"Apple Silicon detected: Using {cpu_threads} threads")
    else:
        cpu_threads = max(4, min(os.cpu_count() - 2, os.cpu_count() // 2))
        print(f"Using {cpu_threads} threads")
    
    # Load model
    print(f"Loading faster-whisper model: {model_name}...")
    load_start = time.time()
    model = WhisperModel(
        model_name, 
        device="cpu",
        compute_type="int8",
        cpu_threads=cpu_threads
    )
    load_time = time.time() - load_start
    print(f"Model loaded in {load_time:.2f} seconds")
    
    # Transcribe with optimizations
    print("Starting transcription...")
    monitor.start()
    transcribe_start = time.time()
    
    segments, info = model.transcribe(
        audio_file,
        language="en",
        beam_size=1,
        best_of=1,
        patience=1.0,
        temperature=0.0,
        vad_filter=True,
        vad_parameters=dict(
            threshold=0.5,
            min_speech_duration_ms=250,
            max_speech_duration_s=float('inf'),
            min_silence_duration_ms=2000,
            window_size_samples=1024,
            speech_pad_ms=400
        )
    )
    
    # Collect text from segments
    text = " ".join([segment.text for segment in segments])
    
    transcribe_time = time.time() - transcribe_start
    perf_stats = monitor.stop()
    
    print(f"Transcription completed in {transcribe_time:.2f} seconds")
    
    return {
        "implementation": "faster-whisper",
        "model": model_name,
        "load_time": load_time,
        "transcribe_time": transcribe_time,
        "total_time": load_time + transcribe_time,
        "text": text,
        "performance": perf_stats,
        "cpu_threads": cpu_threads
    }

def calculate_similarity(text1, text2):
    """Calculate word-level similarity between two texts"""
    words1 = set(text1.lower().split())
    words2 = set(text2.lower().split())
    
    if not words1 or not words2:
        return 0.0
        
    intersection = words1.intersection(words2)
    union = words1.union(words2)
    
    return len(intersection) / len(union) * 100

def print_comparison(results):
    """Print comparison results"""
    print(f"\n{'='*60}")
    print("PERFORMANCE COMPARISON")
    print(f"{'='*60}")
    
    valid_results = [r for r in results if r is not None]
    
    if len(valid_results) < 2:
        print("Not enough implementations available for comparison")
        return
    
    # Find baseline (openai-whisper if available)
    baseline = next((r for r in valid_results if r["implementation"] == "openai-whisper"), valid_results[0])
    
    for result in valid_results:
        print(f"\n{result['implementation'].upper()}")
        print("-" * 30)
        print(f"Model Load Time: {result['load_time']:.2f}s")
        print(f"Transcription Time: {result['transcribe_time']:.2f}s")
        print(f"Total Time: {result['total_time']:.2f}s")
        print(f"Average CPU Usage: {result['performance']['avg_cpu']:.1f}%")
        print(f"Peak CPU Usage: {result['performance']['max_cpu']:.1f}%")
        print(f"Average Memory: {result['performance']['avg_memory']:.1f} MB")
        print(f"Peak Memory: {result['performance']['max_memory']:.1f} MB")
        
        if result != baseline:
            speedup = baseline['total_time'] / result['total_time']
            print(f"\nSpeedup vs {baseline['implementation']}: {speedup:.2f}x")
            
        print(f"\nTranscription Preview: {result['text'][:200]}...")
    
    # Calculate text similarity
    if len(valid_results) >= 2:
        print(f"\n{'='*60}")
        print("TEXT SIMILARITY")
        print(f"{'='*60}")
        
        for i in range(len(valid_results)):
            for j in range(i + 1, len(valid_results)):
                similarity = calculate_similarity(
                    valid_results[i]['text'],
                    valid_results[j]['text']
                )
                print(f"{valid_results[i]['implementation']} vs {valid_results[j]['implementation']}: {similarity:.1f}%")

def create_test_audio():
    """Create a test audio file if none provided"""
    print("Creating test audio file...")
    import numpy as np
    from scipy.io.wavfile import write as write_wav
    
    sample_rate = 16000
    duration = 10  # 10 seconds
    t = np.linspace(0, duration, int(sample_rate * duration), False)
    
    # Create a more complex signal
    audio_data = 0.3 * np.sin(2 * np.pi * 440 * t)  # A4
    audio_data += 0.2 * np.sin(2 * np.pi * 554.37 * t)  # C#5
    audio_data += 0.1 * np.sin(2 * np.pi * 659.25 * t)  # E5
    
    # Add some silence
    silence_start = int(3 * sample_rate)
    silence_end = int(4 * sample_rate)
    audio_data[silence_start:silence_end] = 0
    
    audio_data_int16 = np.int16(audio_data * 32767)
    
    filename = "test_audio_comparison.wav"
    write_wav(filename, sample_rate, audio_data_int16)
    print(f"Created test audio: {filename}")
    
    return filename

def main():
    parser = argparse.ArgumentParser(
        description="Compare Whisper implementations performance"
    )
    parser.add_argument(
        "audio_file",
        nargs="?",
        help="Path to audio file to transcribe"
    )
    parser.add_argument(
        "--model",
        default="base",
        choices=["tiny", "base", "small", "medium", "large"],
        help="Whisper model size to use (default: base)"
    )
    parser.add_argument(
        "--save-results",
        action="store_true",
        help="Save results to JSON file"
    )
    
    args = parser.parse_args()
    
    # Check if audio file exists or create test file
    if not args.audio_file:
        args.audio_file = create_test_audio()
    elif not os.path.exists(args.audio_file):
        print(f"Error: Audio file not found: {args.audio_file}")
        sys.exit(1)
    
    print(f"Testing with audio file: {args.audio_file}")
    print(f"Model: {args.model}")
    print(f"System: {os.cpu_count()} CPU cores")
    
    # Run tests
    results = []
    
    # Test OpenAI Whisper
    if has_openai_whisper:
        try:
            result = test_openai_whisper(args.audio_file, args.model)
            if result:
                results.append(result)
        except Exception as e:
            print(f"Error testing openai-whisper: {e}")
    
    # Test faster-whisper
    if has_faster_whisper:
        try:
            result = test_faster_whisper(args.audio_file, args.model)
            if result:
                results.append(result)
        except Exception as e:
            print(f"Error testing faster-whisper: {e}")
    
    # Print comparison
    print_comparison(results)
    
    # Save results if requested
    if args.save_results and results:
        filename = f"whisper_comparison_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(filename, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"\nResults saved to: {filename}")

if __name__ == "__main__":
    main()