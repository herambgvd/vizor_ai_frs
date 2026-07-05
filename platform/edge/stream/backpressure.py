"""Backpressure primitive: a drop-oldest "latest frame" buffer.

The problem this solves
--------------------------------------------------------------------------
A camera produces frames at a fixed real-time rate (say 25fps). If the consumer
(a detection model) is slower than that, an unbounded queue would grow without
limit and the consumer would fall further and further behind real time — you'd
be running the model on video from ten seconds ago. For live analytics that is
worse than useless.

The fix is **drop-oldest** backpressure: keep only the most recent frame(s) and
throw away anything the consumer didn't get to in time. The consumer always
works on video that is "now", at the cost of skipping frames — exactly the right
trade-off for real-time inference where freshness beats completeness.

``collections.deque(maxlen=N)`` gives us the drop-oldest behaviour for free: once
the deque is full, appending to the right silently evicts from the left. We wrap
it with a ``threading.Condition`` so a producer thread and a consumer thread can
hand off frames safely, and so ``get()`` can block until a frame is available.
"""

from __future__ import annotations

import threading
from collections import deque

import numpy as np


class LatestFrameBuffer:
    """Thread-safe bounded buffer that keeps only the newest frame(s).

    Typical wiring: an RTSP reader thread calls ``put(frame)`` in a tight loop;
    an inference thread calls ``get()`` whenever it's ready for more work. Because
    the buffer drops old frames, the inference thread never lags behind live video.
    """

    def __init__(self, maxsize: int = 1) -> None:
        """
        Args:
            maxsize: how many recent frames to retain. Default 1 = strictly "the
                latest frame only". A small value like 2-3 can smooth over jitter
                while still bounding lag.
        """
        if maxsize < 1:
            raise ValueError("maxsize must be >= 1")
        self.maxsize = maxsize
        # deque(maxlen=maxsize): appending past capacity evicts the oldest item.
        self._buf: deque[np.ndarray] = deque(maxlen=maxsize)
        # Condition guards the deque AND lets get() wait for a producer.
        self._cond = threading.Condition()
        self._closed = False

    def put(self, frame: np.ndarray) -> None:
        """Add a frame, silently dropping the oldest if the buffer is full.

        Never blocks — the producer (real-time camera) must not be throttled by a
        slow consumer; that's the whole point. The drop is intentional.
        """
        with self._cond:
            self._buf.append(frame)   # maxlen handles the drop-oldest eviction
            self._cond.notify()       # wake a waiting get()

    def get(self, timeout: float | None = None) -> np.ndarray | None:
        """Return the newest available frame, or None.

        Args:
            timeout: max seconds to wait for a frame. ``None`` blocks forever;
                ``0`` returns immediately (non-blocking poll).

        Returns:
            The most recent frame, or None if the wait timed out / the buffer was
            closed while empty.
        """
        with self._cond:
            # Wait until there's a frame (or we time out / get closed).
            if not self._buf and not self._closed:
                self._cond.wait_for(
                    lambda: bool(self._buf) or self._closed,
                    timeout=timeout,
                )
            if not self._buf:
                return None
            # Pop the RIGHT (newest) and discard anything older — we only ever
            # want the freshest frame, so stale ones in between are dropped.
            frame = self._buf[-1]
            self._buf.clear()
            return frame

    def close(self) -> None:
        """Wake any blocked ``get()`` callers so they can unwind. Idempotent."""
        with self._cond:
            self._closed = True
            self._cond.notify_all()

    def __len__(self) -> int:
        with self._cond:
            return len(self._buf)
