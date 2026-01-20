"""
Fast JSON Module - Using ujson for 2-4x faster JSON operations

ujson (UltraJSON) is a fast JSON encoder/decoder written in C with Python bindings.
It's 2-4x faster than standard json module for most operations.

Benchmarks:
- Encoding: 2-3x faster
- Decoding: 2-4x faster
- Lower memory usage

Falls back to standard json if ujson is not available.
"""

import logging

logger = logging.getLogger(__name__)

# Try to use ujson (ultra-fast JSON), fall back to standard json
try:
    import ujson as json
    FAST_JSON = True
    logger.info("✅ Using ujson - 2-4x faster JSON operations")
except ImportError:
    import json
    FAST_JSON = False
    logger.warning("⚠️  ujson not available, using standard json (slower)")


# Export common functions
dumps = json.dumps
loads = json.loads
dump = json.dump
load = json.load


def dumps_pretty(obj, **kwargs):
    """
    Serialize object to pretty-printed JSON string.
    
    Args:
        obj: Object to serialize
        **kwargs: Additional arguments
        
    Returns:
        Pretty-printed JSON string
    """
    if FAST_JSON:
        return json.dumps(obj, indent=2, **kwargs)
    else:
        return json.dumps(obj, indent=2, **kwargs)


def encode_fast(obj):
    """
    Fast JSON encoding without extra options.
    
    Args:
        obj: Object to encode
        
    Returns:
        JSON string
    """
    if FAST_JSON:
        return json.dumps(obj, ensure_ascii=False)
    else:
        return json.dumps(obj, ensure_ascii=False)


def decode_fast(s):
    """
    Fast JSON decoding.
    
    Args:
        s: JSON string to decode
        
    Returns:
        Decoded object
    """
    return json.loads(s)


def is_fast_json_enabled():
    """Check if fast JSON (ujson) is enabled."""
    return FAST_JSON


# Benchmark function
def benchmark_json(obj, iterations=10000):
    """
    Benchmark JSON encoding/decoding performance.
    
    Args:
        obj: Object to test with
        iterations: Number of iterations
        
    Returns:
        Dict with timing results
    """
    import time
    
    results = {
        'library': 'ujson' if FAST_JSON else 'json',
        'iterations': iterations
    }
    
    # Encode benchmark
    start = time.perf_counter()
    for _ in range(iterations):
        _ = dumps(obj)
    results['encode_time'] = time.perf_counter() - start
    
    # Decode benchmark
    json_str = dumps(obj)
    start = time.perf_counter()
    for _ in range(iterations):
        _ = loads(json_str)
    results['decode_time'] = time.perf_counter() - start
    
    return results


if __name__ == '__main__':
    # Test data
    test_data = {
        'users': [
            {'id': i, 'name': f'User {i}', 'active': i % 2 == 0}
            for i in range(100)
        ],
        'metadata': {
            'count': 100,
            'timestamp': '2026-01-20T00:00:00Z'
        }
    }
    
    print(f"Fast JSON enabled: {is_fast_json_enabled()}")
    print(f"Library: {'ujson' if FAST_JSON else 'standard json'}")
    
    # Benchmark
    results = benchmark_json(test_data, iterations=1000)
    print(f"\nBenchmark ({results['iterations']} iterations):")
    print(f"  Library: {results['library']}")
    print(f"  Encode time: {results['encode_time']:.4f}s")
    print(f"  Decode time: {results['decode_time']:.4f}s")
