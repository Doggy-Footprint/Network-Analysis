import sys, time
from pathlib import Path
sys.path.insert(0, sys.argv[1])
from language_analyzers.kotlin import KotlinAnalyzer
fx = Path(sys.argv[2]); ts = []
for _ in range(3):
    t = time.perf_counter(); KotlinAnalyzer(fx).build(); ts.append(time.perf_counter() - t)
print(min(ts))
