"""ffmpeg helpers: probe, extract audio, and render social-media clips with captions."""
import json
import re
import subprocess
from pathlib import Path

FONT_DIR = Path(__file__).parent / "fonts"
FORMATS = {
    # name: (width, height, label)
    "vertical": (720, 1280, "TikTok / Reels / Shorts (9:16)"),
    "youtube": (1280, 720, "YouTube (16:9)"),
}


def ffmpeg():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return "ffmpeg"


def _run(args, timeout=900):
    proc = subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", "-y", *args], capture_output=True, text=True,
                          timeout=timeout)
    if proc.returncode != 0:
        raise RuntimeError("Video processing failed: " + (proc.stderr or "")[-400:].strip())
    return proc


def probe(path):
    """Return (duration_seconds, has_video, has_audio, width, height) without ffprobe."""
    proc = subprocess.run([ffmpeg(), "-hide_banner", "-nostdin", "-i", str(path)], capture_output=True, text=True, timeout=120)
    text = proc.stderr or ""
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", text)
    duration = (int(m.group(1)) * 3600 + int(m.group(2)) * 60 + float(m.group(3))) if m else 0.0
    vm = re.search(r"Stream #.*Video:.*?(\d{2,5})x(\d{2,5})", text)
    return (duration, bool(vm), "Audio:" in text,
            int(vm.group(1)) if vm else 0, int(vm.group(2)) if vm else 0)


def extract_audio(src, dest):
    _run(["-i", str(src), "-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k", str(dest)])


def _ass_time(t):
    t = max(0.0, t)
    h, rem = divmod(t, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _ass_escape(text):
    return text.replace("\\", "\\\\").replace("{", "(").replace("}", ")").replace("\n", " ")


def write_captions(segments, clip_start, clip_end, path, width, height):
    """Write an ASS subtitle file with short, bold, centred captions for one clip."""
    vertical = height > width
    size = 54 if vertical else 46
    margin_v = int(height * (0.22 if vertical else 0.08))
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {width}", f"PlayResY: {height}", "WrapStyle: 0", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
        f"Style: Cap,Inter,{size},&H00FFFFFF,&H00FFFFFF,&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,4,1,2,60,60,{margin_v},1",
        "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    words_per_card = 6 if vertical else 9
    for seg in segments:
        s, e = float(seg["start"]), float(seg["end"])
        if e <= clip_start or s >= clip_end or not seg.get("text"):
            continue
        words = seg["text"].split()
        if not words:
            continue
        cards = [words[i:i + words_per_card] for i in range(0, len(words), words_per_card)]
        span = (e - s) / len(cards)
        for i, card in enumerate(cards):
            cs, ce = s + i * span, s + (i + 1) * span
            if ce <= clip_start or cs >= clip_end:
                continue
            cs, ce = max(cs, clip_start) - clip_start, min(ce, clip_end) - clip_start
            lines.append(f"Dialogue: 0,{_ass_time(cs)},{_ass_time(ce)},Cap,,0,0,0,,{_ass_escape(' '.join(card))}")
    Path(path).write_text("\n".join(lines) + "\n", encoding="utf-8")


def render_clip(src, dest, start, end, fmt, captions_path=None):
    """Cut [start, end] and reframe to the platform format: the full picture sits
    centred over a blurred, zoomed copy of itself (no important edges cut off)."""
    width, height = FORMATS[fmt][:2]
    duration = max(0.5, end - start)
    graph = (f"[0:v]scale={width}:{height}:force_original_aspect_ratio=increase,crop={width}:{height},"
             f"boxblur=20:2,eq=brightness=-0.08[bg];"
             f"[0:v]scale={width}:{height}:force_original_aspect_ratio=decrease[fg];"
             f"[bg][fg]overlay=(W-w)/2:(H-h)/2,setsar=1")
    if captions_path:
        cap = str(captions_path).replace("\\", "/").replace(":", "\\:")
        fonts = str(FONT_DIR).replace("\\", "/").replace(":", "\\:")
        graph += f",subtitles=filename='{cap}':fontsdir='{fonts}'"
    graph += "[v]"
    _run(["-ss", f"{start:.2f}", "-t", f"{duration:.2f}", "-i", str(src),
          "-filter_complex", graph, "-map", "[v]", "-map", "0:a?",
          "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-threads", "2", "-pix_fmt", "yuv420p",
          "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(dest)], timeout=900)


def write_json(path, value):
    Path(path).write_text(json.dumps(value), encoding="utf-8")
