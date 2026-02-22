#!/usr/bin/env python3
"""Test Claude CLI streaming behavior. Run this OUTSIDE of a claude session."""

import json
import subprocess
import threading
import time

prompt = "Say hello in 5 different languages. Number each one."

# Test 1: -p with prompt as argument
print("=" * 60)
print(
    "TEST 1: claude -p <prompt> --model haiku --verbose --output-format stream-json --include-partial-messages"
)
print("=" * 60)

proc = subprocess.Popen(
    [
        "claude",
        "-p",
        prompt,
        "--model",
        "haiku",
        "--verbose",
        "--output-format",
        "stream-json",
        "--include-partial-messages",
    ],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,
)

start = time.time()
line_count = 0


def read_stderr(p, s):
    for line in iter(p.stderr.readline, ""):
        elapsed = time.time() - s
        print(f"  [STDERR {elapsed:.1f}s] {line.rstrip()[:100]}")


t = threading.Thread(target=read_stderr, args=(proc, start), daemon=True)
t.start()

for line in iter(proc.stdout.readline, ""):
    elapsed = time.time() - start
    line = line.rstrip()
    if not line:
        continue
    line_count += 1
    preview = line[:150] + "..." if len(line) > 150 else line
    print(f"  [STDOUT {elapsed:.1f}s] #{line_count}: {preview}")

proc.wait()
elapsed = time.time() - start
print(f"\n  Total: {line_count} lines in {elapsed:.1f}s, exit code {proc.returncode}")
print()

# Test 2: prompt via stdin
print("=" * 60)
print("TEST 2: claude -p --input-format stream-json --model haiku --verbose (prompt via stdin)")
print("=" * 60)

proc2 = subprocess.Popen(
    [
        "claude",
        "-p",
        "--model",
        "haiku",
        "--verbose",
        "--output-format",
        "stream-json",
        "--input-format",
        "stream-json",
        "--include-partial-messages",
    ],
    stdin=subprocess.PIPE,
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True,
    bufsize=1,
)

start2 = time.time()
line_count2 = 0

msg = json.dumps(
    {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": prompt}]}}
)
proc2.stdin.write(msg + "\n")
proc2.stdin.flush()
proc2.stdin.close()

t2 = threading.Thread(target=read_stderr, args=(proc2, start2), daemon=True)
t2.start()

for line in iter(proc2.stdout.readline, ""):
    elapsed = time.time() - start2
    line = line.rstrip()
    if not line:
        continue
    line_count2 += 1
    preview = line[:150] + "..." if len(line) > 150 else line
    print(f"  [STDOUT {elapsed:.1f}s] #{line_count2}: {preview}")

proc2.wait()
elapsed2 = time.time() - start2
print(f"\n  Total: {line_count2} lines in {elapsed2:.1f}s, exit code {proc2.returncode}")
