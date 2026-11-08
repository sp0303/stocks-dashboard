"""Largest Triangle Three Buckets (LTTB) downsampling algorithm for chart series."""

from __future__ import annotations

from typing import List, Tuple


def lttb_downsample(data: List[Tuple[float, float]], threshold: int) -> List[Tuple[float, float]]:
    """Downsamples 2D numerical time-series (x, y) to threshold points using LTTB.

    Preserves visual peaks, troughs, and trendlines without data distortion.
    """
    data_len = len(data)
    if threshold >= data_len or threshold <= 2:
        return data

    sampled: List[Tuple[float, float]] = [data[0]]

    every = (data_len - 2) / (threshold - 2)
    a = 0

    for i in range(threshold - 2):
        # Calculate point average for next bucket (bucket c)
        avg_x = 0.0
        avg_y = 0.0
        avg_range_start = int((i + 1) * every) + 1
        avg_range_end = min(int((i + 2) * every) + 1, data_len)
        avg_range_length = avg_range_end - avg_range_start

        if avg_range_length > 0:
            for pt in data[avg_range_start:avg_range_end]:
                avg_x += pt[0]
                avg_y += pt[1]
            avg_x /= avg_range_length
            avg_y /= avg_range_length
        else:
            avg_x = data[avg_range_start - 1][0]
            avg_y = data[avg_range_start - 1][1]

        # Get the range for current bucket (bucket b)
        range_offs = int(i * every) + 1
        range_to = min(int((i + 1) * every) + 1, data_len)

        # Point a
        point_a_x, point_a_y = data[a]

        max_area = -1.0
        next_a = range_offs

        for j in range(range_offs, range_to):
            # Calculate triangle area over points a, point_b, and avg_c
            area = abs(
                (point_a_x - avg_x) * (data[j][1] - point_a_y)
                - (point_a_x - data[j][0]) * (avg_y - point_a_y)
            ) * 0.5
            if area > max_area:
                max_area = area
                next_a = j

        sampled.append(data[next_a])
        a = next_a

    # Always include the last point
    sampled.append(data[-1])
    return sampled
