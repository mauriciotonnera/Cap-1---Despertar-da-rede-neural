"""Exercise real decoders and the packaged application with tiny synthetic media."""

import base64
import json
import tempfile
import traceback
from pathlib import Path

from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication


def wait(milliseconds):
    loop = QEventLoop()
    QTimer.singleShot(milliseconds, loop.quit)
    loop.exec()


def until(condition, timeout=10000):
    if condition():
        return
    loop = QEventLoop()
    timer = QTimer()
    timer.setInterval(10)
    timer.timeout.connect(lambda: loop.quit() if condition() else None)
    deadline = QTimer()
    deadline.setSingleShot(True)
    deadline.timeout.connect(loop.quit)
    timer.start()
    deadline.start(timeout)
    loop.exec()
    timer.stop()
    deadline.stop()
    assert condition(), "Timed out waiting for playback"


def run(viewer_class, report_path):
    app = QApplication.instance() or QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = viewer_class()
    window.show()
    p = window.playback
    p.audio.setMuted(True)
    frames, errors, checks = [], [], []
    p.frameReady.connect(lambda image: frames.append(image.size()))
    p.failed.connect(errors.append)
    report = {"success": False, "checks": checks}
    try:
        with tempfile.TemporaryDirectory(prefix="imagedesk-test-", ignore_cleanup_errors=True) as directory:
            root = Path(directory)
            fixtures = json.loads(Path(__file__).with_name("test_media.json").read_text())
            for name, encoded in fixtures.items():
                (root / name).write_bytes(base64.b64decode(encoded))

            p.set_loop(False)
            assert window.load_image(root / "sample.mp4")
            until(lambda: p.ended or p.error)
            assert not p.error and len(frames) >= 2 and p.duration >= 600
            assert p.player.hasAudio() and p.last_frame.size().width() == 96
            count = len(frames)
            wait(200)
            assert len(frames) == count and not p.playing
            checks.append("MP4 H.264/AAC decoding, play once and last-frame hold")

            p.restart()
            until(lambda: p.position >= 150)
            p.pause()
            until(lambda: not p.playing)
            p.seek(350)
            until(lambda: abs(p.position - 350) < 80)
            wait(100)
            assert not p.playing
            window.toggle_presentation()
            assert window.presentation is not None
            assert window.preview.pixmap.cacheKey() == window.presentation.canvas.pixmap.cacheKey()
            same_player = p.player
            p.play()
            wait(100)
            assert p.player is same_player
            assert window.preview.pixmap.cacheKey() == window.presentation.canvas.pixmap.cacheKey()
            window.presentation.close()
            checks.append("Pause, seek, resume and shared fullscreen frames")

            p.set_loop(True)
            p.restart()
            count = len(frames)
            wait(1900)
            assert p.playing and not p.ended and len(frames) - count >= 14
            p.set_loop(False)
            p.restart()
            until(lambda: p.ended or p.error)
            assert not p.error and not p.playing
            checks.append("Video loop, live loop-mode change and restart")

            assert window.load_image(root / "sample.mov")
            until(lambda: p.ended or p.error)
            assert not p.error and p.last_frame.width() == 64 and p.last_frame.height() == 48
            checks.append("MOV ProRes decoding")

            assert window.load_image(root / "rotated.mov")
            until(lambda: p.ended or p.error)
            assert not p.error and p.last_frame.width() == 64 and p.last_frame.height() == 96
            checks.append("Rotated MOV displays in portrait orientation")

            assert window.load_image(root / "infinite.gif")
            until(lambda: p.ended)
            assert p.position == 2 and p.last_frame.pixelColor(0, 0).name() == "#0000ff"
            count = len(frames)
            wait(180)
            assert len(frames) == count
            p.set_loop(True)
            assert window.load_image(root / "once.gif")
            count = len(frames)
            wait(950)
            assert p.playing and len(frames) - count >= 6
            p.pause()
            count = len(frames)
            wait(200)
            assert len(frames) == count
            p.seek(1)
            assert p.position == 1 and not p.playing
            p.set_loop(False)
            p.restart()
            until(lambda: p.ended)
            checks.append("GIF embedded-loop override, last-frame hold, pause, seek and restart")

            assert window.load_image(root / "sample.mp4")
            until(lambda: not p.last_frame.isNull() or p.error)
            assert window.load_image(root / "still.png")
            wait(200)
            assert p.player is None and not p.timer.isActive()
            assert window.image.toImage().pixelColor(0, 0).name() == "#123456"
            assert not window.transport.isVisible()
            checks.append("Video-to-image switch releases playback and rejects stale frames")

            assert not errors, errors
            (root / "invalid.mp4").write_bytes(b"not a video")
            assert window.load_image(root / "invalid.mp4")
            until(lambda: bool(p.error))
            assert not window.play_button.isEnabled()
            assert window.load_image(root / "sample.mp4")
            until(lambda: p.ended or p.error)
            assert not p.error
            checks.append("Corrupt-file error and recovery")
            # Windows decoders can retain the file handle after EndOfMedia.
            p.clear()
            wait(50)
        report["success"] = True
    except Exception:
        report["error"] = traceback.format_exc()
        report["decoder_errors"] = errors
    finally:
        window.close()
        Path(report_path).write_text(json.dumps(report, indent=2))
    return 0 if report["success"] else 1
