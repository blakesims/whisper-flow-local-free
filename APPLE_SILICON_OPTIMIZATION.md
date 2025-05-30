# Apple Silicon Optimization Guide for faster-whisper

## Overview

This document explains the optimal configuration for running faster-whisper on Apple Silicon (M1/M2/M3) processors.

## Key Findings

### 1. Device Support
- **faster-whisper does NOT support MPS (Metal Performance Shaders)**
- Only `device="cpu"` is supported on Apple Silicon
- Attempting to use `device="mps"` will result in: `ValueError: unsupported device mps`
- This limitation comes from CTranslate2, the underlying inference engine

### 2. Optimal Settings for M2

```python
# Optimal configuration for Apple Silicon M2
model = WhisperModel(
    model_name="base",  # or any model size
    device="cpu",       # ONLY supported option
    compute_type="int8" # Best performance on Apple Silicon
)
```

### 3. Compute Type Options
- **Best**: `compute_type="int8"` - Provides optimal performance on Apple Silicon
- **Alternative**: `compute_type="float32"` - Default fallback, slower than int8
- **Avoid**: `float16` - Not efficiently supported on Apple Silicon

### 4. Why CPU-only Still Performs Well

Despite being CPU-only, faster-whisper outperforms OpenAI Whisper on Apple Silicon because:

1. **CTranslate2 Optimizations**: Highly optimized inference engine
2. **Apple Accelerate Framework**: Utilizes Apple's optimized math libraries
3. **INT8 Quantization**: Supported on ARM64 architecture (since CTranslate2 v3.11+)
4. **Memory Efficiency**: Uses less memory than OpenAI Whisper
5. **No MPS Overhead**: Avoids the problematic MPS implementation in PyTorch

### 5. Performance Comparison

- faster-whisper is **4x faster** than openai-whisper for the same accuracy
- Uses significantly less memory
- Even without GPU acceleration, it outperforms vanilla Whisper on M2

### 6. Alternative Solutions for GPU Acceleration

If GPU acceleration is critical for your use case:

1. **whisper.cpp**: Best alternative for Apple Silicon GPU usage
   - Native Metal support
   - CoreML optimization available
   - "Works like a charm" on Apple Silicon

2. **insanely-fast-whisper**: 
   - Supports MPS with `--device-id mps` flag
   - Built on different architecture than faster-whisper

3. **MLX Framework**: 
   - Apple's own framework for machine learning on Apple Silicon
   - Provides native GPU acceleration

## Implementation Notes

The TranscriptionService in this project is already optimized for Apple Silicon:

1. Default device is set to "cpu"
2. Default compute_type is "int8" 
3. CPU threads are auto-detected for optimal performance
4. Comments explain why MPS is not available

## Future Considerations

- Monitor CTranslate2 development for potential MPS support
- Consider adding whisper.cpp as an alternative backend
- Keep compute_type as "int8" unless specific accuracy requirements demand float32