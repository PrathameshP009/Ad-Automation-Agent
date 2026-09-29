"""Turns a Script Agent storyboard (JSON) into a rendered .mp4.

By default, render_with_ffmpeg_fallback() synthesizes and muxes narration, burns in captions,
and optionally mixes a music bed. The OpenMontage adapter is experimental and can be enabled
explicitly once its audio behavior is verified.
"""
import asyncio
import json
import re
import shutil
import subprocess
import textwrap
import wave
from pathlib import Path
import config

PUNCTUATION_PAUSE_SEC = 0.5
CAPTION_WORDS = 4
TTS_EDGE_SILENCE_SEC = 0.02
PAUSE_PUNCTUATION = ",.;:!?…—–"


def render(storyboard: dict, output_name: str = "final_ad.mp4", prefer_openmontage: bool = False) -> Path:
    if prefer_openmontage and _openmontage_available():
        try:
            return render_with_openmontage(storyboard, output_name)
        except Exception as e:  # noqa: BLE001 - fall back rather than hard-fail the whole pipeline
            print(f"[video_gen_tool] OpenMontage render failed ({e}); falling back to ffmpeg renderer.")
    return render_with_ffmpeg_fallback(storyboard, output_name)


def _openmontage_available() -> bool:
    repo = Path(config.OPENMONTAGE_REPO_PATH)
    return repo.exists() and shutil.which("python") is not None


def render_with_openmontage(storyboard: dict, output_name: str) -> Path:
    """Adapter stub — confirm exact CLI against the cloned repo and adjust the command below.
    Expected shape (per OpenMontage's README as of the brief being written): it takes a JSON
    project spec describing clips/shots + audio and renders a montage.
    """
    repo = Path(config.OPENMONTAGE_REPO_PATH)
    project_spec = _storyboard_to_openmontage_spec(storyboard)
    spec_path = config.OUTPUT_DIR / "openmontage_project.json"
    spec_path.write_text(json.dumps(project_spec, indent=2))

    out_path = config.OUTPUT_DIR / output_name
    cmd = _build_openmontage_cmd(repo, spec_path, out_path)
    subprocess.run(cmd, check=True, cwd=repo)
    return out_path


def _storyboard_to_openmontage_spec(storyboard: dict) -> dict:
    return {
        "title": storyboard.get("title", "CWT Ad"),
        "resolution": "1080x1920",  # vertical, for Reels/TikTok/Stories
        "clips": [
            {
                "prompt": shot.get("visual"),
                "duration": shot.get("duration_sec", 4),
                "voiceover": shot.get("vo_line", ""),
                "caption": shot.get("on_screen_text", ""),
                "music_cue": shot.get("sfx_music_cue", ""),
            }
            for shot in storyboard.get("shots", [])
        ],
    }


def _build_openmontage_cmd(repo: Path, spec_path: Path, out_path: Path) -> list[str]:
    # TODO: confirm real entrypoint/flags against https://github.com/calesthio/OpenMontage
    return ["python", "-m", "openmontage.render", "--project", str(spec_path), "--out", str(out_path)]


# ---------------------------------------------------------------------------
# ffmpeg fallback: fully self-contained, no video-gen API keys required
# ---------------------------------------------------------------------------

def render_with_ffmpeg_fallback(storyboard: dict, output_name: str) -> Path:
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("ffmpeg not found on PATH. Install it (apt/brew install ffmpeg) to use the fallback renderer.")

    work_dir = config.OUTPUT_DIR / "_render_tmp"
    work_dir.mkdir(exist_ok=True)
    shots = storyboard.get("shots", [])

    clip_paths = []
    voiceover_paths = []
    for i, shot in enumerate(shots):
        still = _get_or_generate_still(shot, work_dir, i, len(shots))
        voiceover_text = shot.get("vo_line", "").strip()
        if not voiceover_text and i == len(shots) - 1:
            voiceover_text = storyboard.get("cta", {}).get("line", "").strip()
        if not voiceover_text:
            clip_paths.append(_ken_burns_clip_with_caption(still, shot, work_dir, i, []))
            continue

        voiceover, caption_segments = _generate_voiceover(voiceover_text, work_dir, i)
        voiceover_paths.append(voiceover)
        with wave.open(str(voiceover), "rb") as audio:
            speech_duration = audio.getnframes() / audio.getframerate()
        clip_duration = speech_duration
        clip_paths.append(
            _ken_burns_clip_with_caption(
                still,
                {**shot, "duration_sec": clip_duration},
                work_dir,
                i,
                caption_segments,
                duration_override=clip_duration,
            )
        )

    if not clip_paths:
        raise ValueError("Cannot render a storyboard without any shots.")
    out_path = config.OUTPUT_DIR / output_name
    _concat_with_crossfade(
        clip_paths,
        out_path,
        storyboard.get("music_bed_path"),
        voiceover_paths,
    )
    return out_path


def _get_or_generate_still(shot: dict, work_dir: Path, idx: int, scene_count: int = 7) -> Path:
    """Render a storyboard graphic or source an image for a shot."""
    scene_type = shot.get("scene_type")
    if scene_type:
        from tools.storyboard_art import render_scene

        still = work_dir / f"shot_{idx:02d}.png"
        return render_scene(scene_type, still, idx + 1, scene_count)

    from tools import image_gen_tool

    cached = work_dir / f"shot_{idx:02d}.png"
    generated = image_gen_tool.generate_still(shot.get("visual", ""), cached, seed=idx + 1)
    if generated is not None:
        print(f"[video_gen_tool] Shot {idx + 1}: generated image")
        return generated
    print(f"[video_gen_tool] Shot {idx + 1}: image generation failed, using placeholder card")
    return _placeholder_card(shot, work_dir, idx)


def _placeholder_card(shot: dict, work_dir: Path, idx: int) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    img = Image.new("RGB", (1080, 1920), color=(10, 12, 20))
    draw = ImageDraw.Draw(img)
    text = shot.get("visual", "")
    try:
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 46)
    except OSError:
        font = ImageFont.load_default()
    draw.multiline_text((80, 800), _wrap(text, 28), fill=(230, 230, 235), font=font, spacing=14)

    path = work_dir / f"shot_{idx:02d}.png"
    img.save(path)
    return path


def _wrap(text: str, width: int) -> str:
    import textwrap
    return "\n".join(textwrap.wrap(text, width=width))


def _group_word_boundaries(
    text: str,
    boundaries: list[dict],
    duration: float,
    removed_leading_silence: float,
) -> list[tuple[str, float, float]]:
    if not boundaries:
        raise RuntimeError("The speech service returned no word timings; captions cannot be synchronized.")

    source_words = list(re.finditer(r"[\w]+(?:['’][\w]+)*(?:-[\w]+)?", text))
    if len(source_words) != len(boundaries):
        raise RuntimeError(
            f"Speech returned {len(boundaries)} word timings for {len(source_words)} "
            "caption words; refusing to produce unsynchronized captions."
        )
    caption_words = [match.group() for match in source_words]
    for index, match in enumerate(source_words):
        spoken_word = str(boundaries[index]["text"])
        normalize = lambda word: re.sub(r"[^\w]", "", word).casefold()
        if normalize(match.group()) != normalize(spoken_word):
            raise RuntimeError(
                f"Speech timing word {spoken_word!r} does not match script word "
                f"{match.group()!r}."
            )
        gap_end = source_words[index + 1].start() if index + 1 < len(source_words) else len(text)
        punctuation = text[match.end():gap_end]
        ending = "".join(char for char in punctuation if char in ",.;:!?…")
        if ending:
            caption_words[index] += ending
        if any(char in punctuation for char in "—–"):
            if index + 1 < len(caption_words):
                caption_words[index + 1] = f"— {caption_words[index + 1]}"

    groups = []
    for start in range(0, len(boundaries), CAPTION_WORDS):
        words = boundaries[start:start + CAPTION_WORDS]
        caption = " ".join(caption_words[start:start + len(words)])
        start_time = (
            0.0 if start == 0 else
            max(0.0, float(words[0]["offset"]) / 10_000_000 - removed_leading_silence)
        )
        if start + CAPTION_WORDS < len(boundaries):
            end_time = max(
                start_time,
                float(boundaries[start + CAPTION_WORDS]["offset"]) / 10_000_000
                - removed_leading_silence,
            )
        else:
            last_word = boundaries[-1]
            end_time = (
                float(last_word["offset"]) + float(last_word["duration"])
            ) / 10_000_000 - removed_leading_silence
        if end_time <= start_time:
            raise RuntimeError(f"Invalid speech timing for caption: {caption!r}")
        groups.append((caption, start_time, min(end_time, duration)))
    return groups


def _insert_punctuation_pauses(
    path: Path,
    text: str,
    boundaries: list[dict],
    removed_leading_silence: float,
) -> None:
    source_words = list(re.finditer(r"[\w]+(?:['’][\w]+)*(?:-[\w]+)?", text))
    if len(source_words) != len(boundaries):
        raise RuntimeError(
            f"Speech returned {len(boundaries)} word timings for {len(source_words)} "
            "caption words; refusing to add unsynchronized punctuation pauses."
        )

    pause_positions = []
    for index, match in enumerate(source_words):
        spoken_word = str(boundaries[index]["text"])
        normalize = lambda word: re.sub(r"[^\w]", "", word).casefold()
        if normalize(match.group()) != normalize(spoken_word):
            raise RuntimeError(
                f"Speech timing word {spoken_word!r} does not match script word "
                f"{match.group()!r}."
            )
        next_start = source_words[index + 1].start() if index + 1 < len(source_words) else len(text)
        punctuation = text[match.end():next_start]
        if any(char in punctuation for char in PAUSE_PUNCTUATION):
            word_end = (
                float(boundaries[index]["offset"])
                + float(boundaries[index]["duration"])
            ) / 10_000_000 - removed_leading_silence
            pause_positions.append((word_end, index))

    with wave.open(str(path), "rb") as audio:
        params = audio.getparams()
        frames = audio.readframes(audio.getnframes())
    if params.sampwidth != 2:
        raise RuntimeError("Punctuation pauses require 16-bit PCM narration audio.")

    frame_size = params.sampwidth * params.nchannels
    frame_count = len(frames) // frame_size
    pause_frames = round(PUNCTUATION_PAUSE_SEC * params.framerate)
    insertions = []
    for seconds, word_index in pause_positions:
        frame = min(frame_count, max(0, round(seconds * params.framerate)))
        insertions.append((frame, word_index))

    silence = b"\0" * (pause_frames * frame_size)
    output = bytearray()
    cursor = 0
    for frame, word_index in insertions:
        offset = frame * frame_size
        output.extend(frames[cursor:offset])
        output.extend(silence)
        cursor = offset
        for following in range(word_index + 1, len(boundaries)):
            boundaries[following]["offset"] = (
                float(boundaries[following]["offset"])
                + PUNCTUATION_PAUSE_SEC * 10_000_000
            )
    output.extend(frames[cursor:])
    with wave.open(str(path), "wb") as audio:
        audio.setparams(params)
        audio.writeframes(output)


def _generate_voiceover(
    text: str, work_dir: Path, shot_idx: int
) -> tuple[Path, list[tuple[str, float, float]]]:
    """Synthesize each full sentence once and use provider word timings for captions."""
    try:
        import edge_tts
    except ImportError as exc:
        raise RuntimeError(
            "Neural voiceover requires edge-tts. Install project dependencies with "
            "`pip install -r requirements.txt`."
        ) from exc

    path = work_dir / f"voiceover_{shot_idx:02d}.wav"
    mp3_path = path.with_suffix(".mp3")
    boundaries = []

    async def synthesize() -> None:
        communicate = edge_tts.Communicate(
            text, config.TTS_VOICE, rate="+8%", volume="+0%", boundary="WordBoundary"
        )
        with mp3_path.open("wb") as audio_file:
            async for chunk in communicate.stream():
                if chunk["type"] == "audio":
                    audio_file.write(chunk["data"])
                elif chunk["type"] == "WordBoundary":
                    boundaries.append(chunk)

    asyncio.run(synthesize())
    silence_probe = subprocess.run(
        [
            "ffmpeg", "-hide_banner", "-nostats", "-i", str(mp3_path),
            "-af", "silencedetect=noise=-42dB:d=0.08", "-f", "null", "NUL",
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    leading_match = re.search(
        r"silence_start: 0(?:\.0+)?[\r\n]+.*?silence_end: ([0-9.]+)",
        silence_probe.stderr,
        re.DOTALL,
    )
    leading_silence = float(leading_match.group(1)) if leading_match else 0.0
    removed_leading_silence = max(0.0, leading_silence - TTS_EDGE_SILENCE_SEC)
    subprocess.run(
        [
            "ffmpeg", "-y", "-i", str(mp3_path), "-ac", "1", "-ar", "22050",
            "-af",
            "silenceremove=start_periods=1:start_duration=0.08:"
            "start_threshold=-42dB:start_silence=0.02,areverse,silenceremove="
            "start_periods=1:start_duration=0.08:"
            "start_threshold=-42dB:start_silence=0.03,areverse",
            "-c:a", "pcm_s16le", str(path),
        ],
        check=True,
        capture_output=True,
    )
    mp3_path.unlink()
    if not path.is_file() or path.stat().st_size == 0:
        raise RuntimeError(f"Text-to-speech did not create narration for shot {shot_idx + 1}.")
    _insert_punctuation_pauses(
        path, text, boundaries, removed_leading_silence
    )
    with wave.open(str(path), "rb") as audio:
        duration = audio.getnframes() / audio.getframerate()
    return path, _group_word_boundaries(
        text, boundaries, duration, removed_leading_silence
    )


def _ken_burns_clip_with_caption(
    still: Path,
    shot: dict,
    work_dir: Path,
    idx: int,
    caption_segments: list[tuple[str, float, float]],
    duration_override: float | None = None,
) -> Path:
    duration = duration_override or float(shot.get("duration_sec", 4))
    if shot.get("scene_type"):
        zoompan = f"zoompan=z='min(zoom+0.0002,1.02)':d={int(duration * 25)}:s=1080x1920:fps=25"
    else:
        zoompan = f"zoompan=z='min(zoom+0.0015,1.15)':d={int(duration * 25)}:s=1080x1920:fps=25"
    filters = [zoompan]
    font_path = Path("C:/Windows/Fonts/arial.ttf")
    font_option = ""
    if font_path.exists():
        font_option = f"fontfile='{font_path.as_posix().replace(':', r'\:')}':"
    for segment_idx, (caption, start_time, end_time) in enumerate(caption_segments):
        caption_path = work_dir / f"caption_{idx:02d}_{segment_idx:02d}.txt"
        caption_path.write_text(caption, encoding="utf-8")
        textfile = caption_path.resolve().as_posix().replace(":", r"\:")
        filters.append(
            f"drawtext={font_option}textfile='{textfile}':fontcolor=white:fontsize=54:"
            f"box=1:boxcolor=black@0.82:boxborderw=24:x=(w-text_w)/2:y=h-500:"
            f"line_spacing=12:enable='between(t\\,{start_time:.3f}\\,{end_time:.3f})'"
        )

    out = work_dir / f"clip_{idx:02d}.mp4"
    subprocess.run(
        [
            "ffmpeg", "-y", "-loop", "1", "-i", str(still),
            "-t", str(duration), "-vf", ",".join(filters),
            "-an", "-c:v", "libx264", "-pix_fmt", "yuv420p", str(out),
        ],
        check=True,
        capture_output=True,
    )
    return out


def _concat_with_crossfade(
    clip_paths: list[Path],
    out_path: Path,
    music_bed_path: str | None,
    voiceover_paths: list[Path],
) -> None:
    """Join continuous narration takes with pauses already aligned to punctuation."""
    work_dir = out_path.parent / "_render_tmp"
    list_file = work_dir / "concat_list.txt"
    list_file.write_text("\n".join(f"file '{p.resolve()}'" for p in clip_paths))

    video_only = work_dir / "video_concat.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_file), "-c", "copy", str(video_only)],
        check=True, capture_output=True,
    )

    if not voiceover_paths:
        raise RuntimeError("No synthesized narration was produced for the final video.")
    audio_cmd = ["ffmpeg", "-y"]
    for path in voiceover_paths:
        audio_cmd.extend(["-i", str(path)])
    filters = []
    streams = "".join(f"[{index}:a]" for index in range(len(voiceover_paths)))
    filters.append(f"{streams}concat=n={len(voiceover_paths)}:v=0:a=1[narration]")
    narration_path = work_dir / "narration_joined.wav"
    audio_cmd.extend([
        "-filter_complex", ";".join(filters),
        "-map", "[narration]", "-c:a", "pcm_s16le", str(narration_path),
    ])
    subprocess.run(audio_cmd, check=True, capture_output=True)

    if music_bed_path and Path(music_bed_path).exists():
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video_only), "-i", str(narration_path),
                "-stream_loop", "-1", "-i", music_bed_path,
                "-filter_complex",
                "[2:a]volume=0.08[music];[1:a][music]amix=inputs=2:duration=first,"
                "loudnorm=I=-16:TP=-1.5:LRA=11[a]",
                "-map", "0:v:0", "-map", "[a]", "-c:v", "copy", "-c:a", "aac",
                "-b:a", "192k", "-ar", "44100", "-ac", "2", "-shortest", str(out_path),
            ],
            check=True, capture_output=True,
        )
    else:
        subprocess.run(
            [
                "ffmpeg", "-y", "-i", str(video_only), "-i", str(narration_path),
                "-map", "0:v:0", "-map", "1:a:0",
                "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
                "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                "-ar", "44100", "-ac", "2", "-shortest", str(out_path),
            ],
            check=True, capture_output=True,
        )
