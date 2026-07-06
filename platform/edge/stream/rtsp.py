"""RTSP frame reader backed by the FFmpeg *binary* (not PyAV).

Why FFmpeg-over-subprocess instead of ``cv2.VideoCapture``?
--------------------------------------------------------------------------
OpenCV's ``VideoCapture`` links against whatever FFmpeg/GStreamer happens to be
present at build time and is notoriously unreliable for long-running RTSP pulls:
it silently drops the connection on transient network hiccups, mishandles B-frame
reordering on some H.264/H.265 streams, and gives you almost no control over
transport (TCP vs UDP) or reconnection. Running the ``ffmpeg`` CLI directly is
the battle-tested approach used by every production NVR: FFmpeg owns the RTSP
handshake, the depacketization, and the H.264/H.265 decode, and simply hands us
raw ``bgr24`` bytes on stdout. We stay in full control of the process lifecycle
(spawn / read / kill) and can reconnect deterministically when the pipe dies.

We ask FFmpeg for ``-pix_fmt bgr24`` specifically because that is exactly the
memory layout OpenCV/NumPy expect (H x W x 3, channel order Blue-Green-Red), so
each frame is a zero-copy ``np.frombuffer`` reshape — no colour conversion.
"""

from __future__ import annotations

import json
import shutil
import subprocess
import time
from collections.abc import Iterator

import numpy as np

from edge.core.logging import get_logger

log = get_logger("edge.stream.rtsp")


class RTSPReader:
    """Pull frames from an RTSP URL as decoded BGR NumPy arrays.

    Usage::

        reader = RTSPReader("rtsp://cam/stream", fps=5)
        for frame in reader.frames():   # frame: np.ndarray HxWx3 uint8 (BGR)
            ...
        reader.close()

    The contract (``frames()`` yields ``np.ndarray``, ``close()`` tears down) is
    depended on by the pipeline layer and must not change.
    """

    def __init__(
        self,
        url: str,
        *,
        fps: float | None = None,
        width: int | None = None,
        height: int | None = None,
        reconnect: bool = True,
        transport: str = "tcp",
        hw_accel: str = "none",
        max_width: int = 0,
    ) -> None:
        """
        Args:
            url: the RTSP source, e.g. ``rtsp://user:pass@host:554/Streaming/Channels/101``.
            fps: if set, ask FFmpeg to down-sample to this frame rate (``-r``). Handy
                to avoid decoding 25fps when the model only needs 5fps.
            width / height: output frame size. If omitted we probe the real stream
                dimensions with ``ffprobe`` (we MUST know them to slice raw bytes).
            reconnect: when True, transparently respawn FFmpeg with exponential
                backoff after a read failure / EOF instead of ending the iterator.
            transport: RTSP lower-transport — "tcp" (reliable, default) or "udp".
            hw_accel: decode backend — "none" (CPU/software, default) or "nvdec"
                to offload H.264/H.265 decode to the GPU's NVDEC engine via
                FFmpeg ``-hwaccel cuda``. NVDEC decodes on-GPU then downloads the
                frame to system memory, so we still receive plain ``bgr24`` bytes
                — the only change is that the (expensive) decode no longer burns
                CPU. Requires the container to have GPU access + an FFmpeg built
                with CUDA (both true for our streams image).
            max_width: if > 0 and the source is wider, downscale analysis frames to
                this width (aspect preserved). With hw_accel="nvdec" the resize runs
                on the GPU (``scale_cuda``) so the CPU never sees the full-res frame;
                otherwise it's an FFmpeg CPU ``scale`` (still cheaper than resizing
                every frame downstream). 0 = keep native resolution.
        """
        self.url = url
        self.fps = fps
        self.width = width
        self.height = height
        self.reconnect = reconnect
        self.transport = transport
        self.hw_accel = (hw_accel or "none").strip().lower()
        self.max_width = int(max_width or 0)
        # Probed source geometry. self.width/height hold the *output* geometry
        # (post-downscale) because that's what we slice out of the pipe.
        self._src_w: int | None = None
        self._src_h: int | None = None

        # The live FFmpeg child process (None until first spawn / after close).
        self._proc: subprocess.Popen[bytes] | None = None
        # Set by close() so an in-flight frames() loop knows to stop for good.
        self._closed = False

        # Fail fast + loud if the binaries aren't on PATH — otherwise the user
        # gets an opaque FileNotFoundError deep inside subprocess.
        if shutil.which("ffmpeg") is None:
            raise RuntimeError(
                "ffmpeg binary not found on PATH — install FFmpeg to use RTSPReader"
            )
        # ffprobe is only required if we have to auto-detect the frame size.
        if (self.width is None or self.height is None) and shutil.which("ffprobe") is None:
            raise RuntimeError(
                "ffprobe binary not found on PATH — install FFmpeg (needed to probe "
                "stream dimensions) or pass explicit width/height to RTSPReader"
            )

    # ------------------------------------------------------------------ probe
    def _probe_dimensions(self) -> tuple[int, int]:
        """Query the stream's video width/height via ``ffprobe`` (JSON output).

        We must know the exact pixel dimensions before reading raw video, because
        the raw stream has no framing — each frame is exactly ``width*height*3``
        contiguous bytes and we slice stdout in chunks of that size.
        """
        cmd = [
            "ffprobe",
            "-v", "error",
            "-rtsp_transport", self.transport,
            "-select_streams", "v:0",        # first video stream only
            "-show_entries", "stream=width,height",
            "-of", "json",
            self.url,
        ]
        log.debug("ffprobe %s", self.url)
        try:
            out = subprocess.check_output(cmd, timeout=30)
        except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"ffprobe failed for {self.url!r}: {exc}") from exc

        data = json.loads(out)
        streams = data.get("streams") or []
        if not streams:
            raise RuntimeError(f"ffprobe found no video stream in {self.url!r}")
        w = int(streams[0]["width"])
        h = int(streams[0]["height"])
        log.info("probed %s -> %dx%d", self.url, w, h)
        return w, h

    # ------------------------------------------------------------------ spawn
    def _spawn(self) -> subprocess.Popen[bytes]:
        """Launch FFmpeg to emit raw ``bgr24`` frames to stdout.

        The pipeline of flags, in order:
          -rtsp_transport tcp   force RTSP over TCP (survives lossy networks)
          -i <url>              the source
          -r <fps>              (optional) output frame-rate cap
          -f rawvideo           container-less raw pixel output
          -pix_fmt bgr24        OpenCV-native byte order
          -                     write to stdout
        stderr is routed to DEVNULL so FFmpeg's verbose banner doesn't spam us;
        flip to subprocess.PIPE while debugging a stream that won't open.
        """
        # Resolve source geometry (probe once, lazily) unless the caller pinned
        # explicit dims and asked for no downscale — then we trust those as source.
        if self._src_w is None or self._src_h is None:
            if self.width is not None and self.height is not None and self.max_width <= 0:
                self._src_w, self._src_h = self.width, self.height
            else:
                self._src_w, self._src_h = self._probe_dimensions()

        # Decide the *output* (analysis) geometry. If a max width is set and the
        # source is wider, downscale to it (aspect preserved, even dims for yuv).
        out_w, out_h = self._src_w, self._src_h
        do_scale = self.max_width > 0 and self._src_w > self.max_width
        if do_scale:
            out_w = self.max_width - (self.max_width % 2)
            out_h = int(round(self._src_h * out_w / self._src_w))
            out_h -= out_h % 2
        # self.width/height must reflect what we actually read off the pipe.
        self.width, self.height = out_w, out_h

        cmd = ["ffmpeg"]
        # NVDEC hardware decode: -hwaccel cuda must come BEFORE -i so it applies to
        # the input decoder. When we ALSO downscale, keep frames on the GPU
        # (-hwaccel_output_format cuda) so scale_cuda can resize them there; the
        # small result is then hwdownload'ed to system memory. When not downscaling
        # we let FFmpeg auto-download full frames (no output-format flag needed).
        if self.hw_accel == "nvdec":
            cmd += ["-hwaccel", "cuda"]
            if do_scale:
                cmd += ["-hwaccel_output_format", "cuda"]
        cmd += [
            "-rtsp_transport", self.transport,
            "-i", self.url,
        ]
        if self.fps is not None:
            cmd += ["-r", str(self.fps)]
        if do_scale:
            if self.hw_accel == "nvdec":
                # Resize on the GPU, then bring the small frame down to CPU memory.
                # hwdownload can only emit the CUDA surface's native format (nv12),
                # so download as nv12 first, then convert nv12->bgr24 on the CPU (a
                # cheap op on the already-small frame). Downloading straight to bgr24
                # fails with "Invalid output format bgr24 for hwframe download".
                cmd += ["-vf", f"scale_cuda={out_w}:{out_h},hwdownload,format=nv12,format=bgr24"]
            else:
                # Software decode path: cheap FFmpeg swscale resize on the CPU.
                cmd += ["-vf", f"scale={out_w}:{out_h}"]
        cmd += [
            "-f", "rawvideo",
            "-pix_fmt", "bgr24",
            "-",
        ]
        log.info(
            "spawning ffmpeg for %s src=%dx%d out=%dx%d hw_accel=%s scale=%s",
            self.url, self._src_w, self._src_h, out_w, out_h, self.hw_accel, do_scale,
        )
        # bufsize=0: we manage buffering ourselves via read(exact_bytes).
        return subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            bufsize=0,
        )

    def _read_exact(self, proc: subprocess.Popen[bytes], n: int) -> bytes | None:
        """Read exactly ``n`` bytes from the process stdout.

        subprocess pipes may return short reads, so we loop until we have a full
        frame. Returns None on EOF / short final read (stream ended or died),
        which the caller treats as a reconnect trigger.
        """
        assert proc.stdout is not None  # created with stdout=PIPE
        buf = bytearray()
        while len(buf) < n:
            chunk = proc.stdout.read(n - len(buf))
            if not chunk:  # EOF — pipe closed, FFmpeg exited
                return None
            buf.extend(chunk)
        return bytes(buf)

    # ----------------------------------------------------------------- public
    def frames(self) -> Iterator[np.ndarray]:
        """Yield decoded frames forever (or until EOF when ``reconnect=False``).

        Each yielded value is an ``np.ndarray`` of shape ``(height, width, 3)``,
        dtype ``uint8``, channel order BGR — ready to hand straight to OpenCV or
        a detection model.
        """
        backoff = 1.0            # seconds; grows on repeated failures
        backoff_max = 30.0

        while not self._closed:
            try:
                self._proc = self._spawn()
            except Exception as exc:  # spawn/probe failure
                if not self.reconnect:
                    raise
                log.warning("ffmpeg spawn failed (%s); retrying in %.0fs", exc, backoff)
                time.sleep(backoff)
                backoff = min(backoff * 2, backoff_max)
                continue

            frame_bytes = self.width * self.height * 3  # type: ignore[operator]
            got_any = False
            try:
                while not self._closed:
                    raw = self._read_exact(self._proc, frame_bytes)
                    if raw is None:
                        # Pipe closed — stream ended or FFmpeg crashed.
                        break
                    got_any = True
                    # Zero-copy view over the pipe buffer, reshaped to an image.
                    frame = np.frombuffer(raw, dtype=np.uint8).reshape(
                        self.height, self.width, 3  # type: ignore[arg-type]
                    )
                    yield frame
                    # A healthy read resets the backoff clock.
                    if got_any:
                        backoff = 1.0
            finally:
                self._terminate_proc()

            if self._closed:
                break
            if not self.reconnect:
                # Clean EOF and the caller doesn't want us to retry.
                log.info("stream %s ended (reconnect disabled)", self.url)
                return

            log.warning("stream %s dropped; reconnecting in %.0fs", self.url, backoff)
            time.sleep(backoff)
            # Grow backoff only when we never got a frame (persistent failure);
            # a stream that ran and then died should retry quickly.
            backoff = 1.0 if got_any else min(backoff * 2, backoff_max)

    # ----------------------------------------------------------------- teardown
    def _terminate_proc(self) -> None:
        """Kill the current FFmpeg child cleanly (terminate, then hard-kill)."""
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        if proc.poll() is None:  # still running
            proc.terminate()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    log.error("ffmpeg for %s would not die", self.url)
        # Close the stdout pipe fd so we don't leak descriptors.
        if proc.stdout is not None:
            try:
                proc.stdout.close()
            except Exception:
                pass

    def close(self) -> None:
        """Stop reading and terminate FFmpeg. Idempotent."""
        self._closed = True
        self._terminate_proc()
