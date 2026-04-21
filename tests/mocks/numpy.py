"""Minimal numpy compatibility shim for test environments without NumPy."""

from __future__ import annotations


uint8 = int


def zeros(shape, dtype=None):
    if not shape:
        return 0
    size = int(shape[0])
    remainder = tuple(shape[1:])
    return [zeros(remainder, dtype=dtype) for _ in range(size)]


def median(values):
    ordered = sorted(values)
    if not ordered:
        return 0.0
    mid = len(ordered) // 2
    if len(ordered) % 2:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) / 2)
