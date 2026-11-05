"""Capture visible tablature, preserving the original notation as images."""
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import math
import shutil
import subprocess
import tempfile
import sys
import cv2
cv2.setNumThreads(1)
import numpy as np
from PIL import Image
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont


@dataclass
class Capture:
    time: float
    image: np.ndarray
    bar_number: int | None = None


def youtube_url(value):
    parsed = urlparse(value.strip())
    if parsed.scheme not in ('http', 'https'):
        raise ValueError('Enter a full YouTube URL beginning with https://.')
    host = (parsed.hostname or '').lower()
    if host in ('youtu.be', 'www.youtu.be'):
        video_id = parsed.path.strip('/').split('/')[0]
    elif host in ('youtube.com', 'www.youtube.com', 'm.youtube.com', 'music.youtube.com'):
        video_id = parse_qs(parsed.query).get('v', [''])[0]
        if not video_id and parsed.path.startswith(('/shorts/', '/embed/', '/live/')):
            video_id = parsed.path.split('/')[2]
    else:
        raise ValueError('Please use a youtube.com or youtu.be video URL.')
    import re
    if not re.fullmatch(r'[A-Za-z0-9_-]{11}', video_id):
        raise ValueError('This URL does not contain a valid YouTube video ID.')
    return 'https://www.youtube.com/watch?v=' + video_id


def download_video(url, folder, progress=None):
    import yt_dlp
    import imageio_ffmpeg
    import uuid
    folder = Path(folder) / uuid.uuid4().hex
    folder.mkdir(parents=True, exist_ok=True)
    def hook(status):
        if progress and status['status'] == 'downloading':
            total = status.get('total_bytes') or status.get('total_bytes_estimate')
            progress(min(.99, status.get('downloaded_bytes', 0) / total) if total else 0)
    opts = {
        'format': 'bestvideo[height<=1080][vcodec^=avc1]/bestvideo[height<=1080][ext=mp4]/best[height<=1080][ext=mp4]/bestvideo[height<=1080]/best',
        'outtmpl': str(Path(folder) / 'source.%(ext)s'),
        'noplaylist': True, 'quiet': True, 'noprogress': True, 'socket_timeout': 30,
        'match_filter': lambda info, **kwargs: 'Use a completed video rather than a live stream.' if info.get('is_live') else None,
        'retries': 2, 'ffmpeg_location': imageio_ffmpeg.get_ffmpeg_exe(),
        'progress_hooks': [hook],
    }
    runtimes = {}
    for name in ('deno', 'node'):
        if shutil.which(name):
            runtimes[name] = {'path': shutil.which(name)}
    bundled_node = Path(sys.base_prefix).parent / 'node' / 'bin' / 'node.exe'
    if bundled_node.exists():
        runtimes['node'] = {'path': str(bundled_node)}
    if runtimes:
        opts['js_runtimes'] = runtimes
    with yt_dlp.YoutubeDL(opts) as downloader:
        info = downloader.extract_info(youtube_url(url), download=True)
        if not info or info.get('is_live'):
            raise ValueError('Use a completed video rather than a live stream.')
        path = Path(downloader.prepare_filename(info))
    if not path.exists():
        raise ValueError('The download did not produce a readable video file.')
    return path, info.get('title', 'Guitar tablature')


def video_info(path):
    video = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    try:
        fps = video.get(cv2.CAP_PROP_FPS)
        count = video.get(cv2.CAP_PROP_FRAME_COUNT)
        if not video.isOpened() or fps <= 0 or count <= 0:
            raise ValueError('Cannot read this video. Try uploading an MP4 file.')
        return {'duration': count / fps, 'width': int(video.get(3)), 'height': int(video.get(4))}
    finally:
        video.release()


def frame_at(path, seconds):
    video = cv2.VideoCapture(str(path), cv2.CAP_FFMPEG, [cv2.CAP_PROP_N_THREADS, 1])
    try:
        video.set(cv2.CAP_PROP_POS_MSEC, seconds * 1000)
        ok, frame = video.read()
        if not ok:
            raise ValueError('Cannot read a frame at this time; choose an earlier time.')
        return frame
    finally:
        video.release()


def ink_mask(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    # Ink is normally the minority, including during fades and on dark paper.
    return 255 - mask if np.mean(mask) > 127.5 else mask


def detect_tab(frame):
    """Find six evenly spaced horizontal lines in either image polarity."""
    height, width = frame.shape[:2]
    scale = min(1., 1280 / width)
    small = cv2.resize(frame, (round(width * scale), round(height * scale)))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    systems = []
    # Threshold each polarity separately: complementing a dark-ink mask
    # produces thick background bands, not thin light staff lines.
    for polarity in (gray, 255 - gray):
        mask = cv2.adaptiveThreshold(polarity, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 9)
        horizontal = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((1, max(20, mask.shape[1] // 30)), np.uint8))
        ys = np.flatnonzero((horizontal > 0).sum(axis=1) > mask.shape[1] * .22)
        groups = np.split(ys, np.where(np.diff(ys) > 2)[0] + 1)
        rows = [int(np.mean(g)) for g in groups if 0 < len(g) <= 4]
        for i, first in enumerate(rows):
            for last in rows[i + 5:]:
                gap = (last - first) / 5
                if not 4 <= gap <= 55:
                    continue
                run = [min(rows, key=lambda y: abs(y - (first + n * gap))) for n in range(6)]
                if len(set(run)) != 6 or any(abs(y - (first + n * gap)) > max(2, gap * .18) for n, y in enumerate(run)):
                    continue
                points = np.where(horizontal[max(0, run[0] - 1):run[-1] + 2] > 0)[1]
                if len(points):
                    systems.append((int(points.min()), run[0], int(points.max()), run[-1], gap))
    if not systems:
        return None
    gap = max(s[4] for s in systems)
    x1 = max(0, min(s[0] for s in systems) - 25)
    x2 = min(gray.shape[1], max(s[2] for s in systems) + 26)
    y1 = max(0, int(min(s[1] for s in systems) - gap * 4))
    y2 = min(gray.shape[0], int(max(s[3] for s in systems) + gap * 4.5))
    return tuple(int(v / scale) for v in (x1, y1, x2, y2))


def crop_frame(frame, region):
    h, w = frame.shape[:2]
    x1, y1, x2, y2 = region
    x1, x2 = max(0, min(w - 1, int(x1))), max(1, min(w, int(x2)))
    y1, y2 = max(0, min(h - 1, int(y1))), max(1, min(h, int(y2)))
    if x2 <= x1 or y2 <= y1:
        raise ValueError('The crop must have positive width and height.')
    return frame[y1:y2, x1:x2].copy()


def signature(image):
    if dark_paper(image):
        mask = cv2.threshold(print_image(image), 140, 255, cv2.THRESH_BINARY_INV)[1]
    else:
        mask = ink_mask(image)
    # Remove staff lines and tall playhead/bar lines for comparison only.
    horizontal = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((1, max(25, mask.shape[1] // 8)), np.uint8))
    vertical = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((max(25, mask.shape[0] // 4), 1), np.uint8))
    mask = cv2.subtract(mask, cv2.bitwise_or(horizontal, vertical))
    return cv2.resize(mask, (640, 160), interpolation=cv2.INTER_AREA) > 90


def difference(a, b):
    # Fraction of changed ink, not blank page area; retain small note changes.
    union = np.logical_or(a, b).sum()
    return float(np.logical_xor(a, b).sum() / max(1, union))


def sampled_frames(path, metadata, interval, start, end, region=None):
    """Decode once, sampling before moving pixel data into Python."""
    import imageio_ffmpeg
    width, height = metadata['width'], metadata['height']
    filters = [f'fps=fps={1 / interval}:round=up:start_time=0']
    if region is not None:
        x1, y1, x2, y2 = [int(v) for v in region]
        x1, x2 = max(0, x1), min(width, x2)
        y1, y2 = max(0, y1), min(height, y2)
        if x2 <= x1 or y2 <= y1:
            raise ValueError('The crop must have positive width and height.')
        width, height = x2 - x1, y2 - y1
        filters.append(f'crop={width}:{height}:{x1}:{y1}:exact=1')
    command = [shutil.which('ffmpeg') or imageio_ffmpeg.get_ffmpeg_exe(), '-nostdin', '-hide_banner',
               '-loglevel', 'error', '-threads', '1', '-ss', str(start),
               '-i', str(path), '-t', str(end - start), '-an', '-sn',
               '-vf', ','.join(filters), '-threads', '1', '-pix_fmt', 'bgr24',
               '-f', 'rawvideo', 'pipe:1']
    with tempfile.TemporaryFile() as errors:
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=errors,
                                   creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            frame_bytes = width * height * 3
            while True:
                data = process.stdout.read(frame_bytes)
                if not data:
                    break
                if len(data) != frame_bytes:
                    raise ValueError('The decoder returned an incomplete frame.')
                yield np.frombuffer(data, np.uint8).reshape(height, width, 3).copy()
            if process.wait() != 0:
                errors.seek(0)
                message = errors.read(2000).decode('utf-8', 'replace')
                raise ValueError('Video decoding failed: ' + message)
        finally:
            process.stdout.close()
            if process.poll() is None:
                process.terminate()
                process.wait()


def extract(path, interval=1., region=None, threshold=.15, start=0., end=None, progress=None, max_captures=1000):
    metadata = video_info(path)
    end = min(end if end is not None else metadata['duration'], metadata['duration'])
    if interval <= 0 or not 0 <= start < end:
        raise ValueError('Choose a positive interval and an end time after the start time.')
    captures, previous, last_shape = [], None, None
    previous_box = None
    total = math.ceil((end - start) / interval)
    missed = 0
    frames = sampled_frames(path, metadata, interval, start, end, region)
    count = 0
    try:
        for index, frame in enumerate(frames):
            count += 1
            time = start + index * interval
            if progress:
                progress(min(1., (index + 1) / total))
            box = (0, 0, frame.shape[1], frame.shape[0]) if region else detect_tab(frame)
            if box is None:
                missed += 1
                continue
            if previous_box is not None and max(abs(a - b) for a, b in zip(box, previous_box)) <= 5:
                box = previous_box
            previous_box = box
            cropped = crop_frame(frame, box)
            gray = cv2.cvtColor(cropped, cv2.COLOR_BGR2GRAY)
            if float(np.percentile(gray, 99) - np.percentile(gray, 1)) < 45:
                missed += 1
                continue
            sig = signature(cropped)
            shape = cropped.shape[:2]
            geometry_changed = last_shape is not None and max(abs(shape[i] / last_shape[i] - 1) for i in (0, 1)) > .08
            if previous is None or geometry_changed or difference(previous, sig) > threshold:
                if len(captures) >= max_captures:
                    raise ValueError('More than 1,000 captures. Narrow the time range, increase interval, or adjust the crop.')
                captures.append(Capture(time, cropped))
                previous, last_shape = sig, shape
            elif np.std(gray) > np.std(cv2.cvtColor(captures[-1].image, cv2.COLOR_BGR2GRAY)) * 1.1:
                # Prefer the clear frame over a fade-in of the same tab content.
                captures[-1].image = cropped
                previous = sig
    finally:
        frames.close()
    if count == 0:
        raise ValueError('No frames were decoded in the selected time range.')
    if progress:
        progress(1.)
    return captures, missed, count


def timestamp(seconds):
    return f'{int(seconds) // 60:02d}:{int(seconds) % 60:02d}'


def dark_paper(image):
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV | cv2.THRESH_OTSU)[1]
    return np.mean(mask) > 127.5


def print_image(image):
    """Return dark notation on white paper, including translucent dark panels."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    if dark_paper(image):
        # Remove slowly varying video showing through a dark overlay while
        # preserving thin staff lines, numbers, ties, and rhythm stems.
        kernel_size = max(9, (gray.shape[0] // 18) | 1)
        ink = cv2.morphologyEx(gray, cv2.MORPH_TOPHAT,
                             cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size)))
        noise = max(12., float(np.percentile(ink, 85)))
        peak = max(noise + 1, float(np.percentile(ink, 99)))
        return (255 * (1 - np.clip((ink.astype(float) - noise) / (peak - noise), 0, 1))).astype(np.uint8)
    white = max(1., float(np.percentile(gray, 85)))
    return (255 * np.clip(gray.astype(float) / white, 0, 1) ** 1.25).astype(np.uint8)


def make_pdf(captures, title='Guitar tablature', source='', paper='A4', monochrome=True, show_timestamps=False):
    if not captures:
        raise ValueError('Select at least one capture before exporting.')
    buffer = BytesIO()
    size = A4 if paper == 'A4' else letter
    doc = canvas.Canvas(buffer, pagesize=size)
    doc.setTitle(title)
    title_font = 'Helvetica-Bold'
    if not title.isascii():
        for font in (Path('C:/Windows/Fonts/malgun.ttf'), Path('/usr/share/fonts/truetype/nanum/NanumGothic.ttf'), Path('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf')):
            if font.exists():
                if 'TabCaptureTitle' not in pdfmetrics.getRegisteredFontNames():
                    pdfmetrics.registerFont(TTFont('TabCaptureTitle', str(font)))
                title_font = 'TabCaptureTitle'
                break
    width, height = size
    margin, page = 28, 0
    prepared = []
    for capture in captures:
        pixels = print_image(capture.image) if monochrome else cv2.cvtColor(capture.image, cv2.COLOR_BGR2RGB)
        # Trim empty vertical padding, retaining notation above/below the staff.
        gray = pixels if pixels.ndim == 2 else cv2.cvtColor(pixels, cv2.COLOR_RGB2GRAY)
        ink = gray < 210 if np.median(gray) >= 115 else gray > 100
        occupied = np.flatnonzero(ink.sum(axis=1) >= 2)
        if len(occupied):
            padding = max(6, round(gray.shape[0] * .025))
            pixels = pixels[max(0, occupied[0] - padding):min(len(pixels), occupied[-1] + padding + 1)]
        prepared.append((capture, Image.fromarray(pixels)))
    typical_ratio = float(np.median([image.width / image.height for _, image in prepared]))
    laid_out = []
    for capture, image in prepared:
        iw, ih = image.size
        # Fit ordinary rows independently, so a very wide stitched strip cannot
        # shrink every other row. Retain the size of genuinely short fragments.
        target_width = width - 2 * margin
        if iw / ih < typical_ratio * .55:
            target_width *= (iw / ih) / typical_ratio
        scale = min(target_width / iw, (height - 120) / ih)
        laid_out.append((capture, image, iw * scale, ih * scale))
    def new_page():
        nonlocal page
        if page:
            doc.showPage()
        page += 1
        doc.setFont(title_font, 12)
        safe_title = title if title_font == 'TabCaptureTitle' else title.encode('latin-1', 'replace').decode('latin-1')
        while doc.stringWidth(safe_title, title_font, 12) > width - 2 * margin:
            safe_title = safe_title[:-4] + '...'
        doc.drawString(margin, height - 35, safe_title)
        doc.setFont('Helvetica', 8)
        doc.drawRightString(width - margin, 20, str(page))
        if source:
            doc.drawString(margin, 20, 'Source video')
            doc.linkURL(source, (margin, 17, margin + 55, 29), relative=0)
        return height - 60
    pages, pending, used = [], [], 0
    available = height - 60 - margin
    for row in laid_out:
        needed = row[3] + 24
        if pending and used + needed > available:
            pages.append(pending)
            pending, used = [], 0
        pending.append(row)
        used += needed
    if pending:
        pages.append(pending)
    for page_index, rows in enumerate(pages):
        y = new_page()
        # Balance full pages down to the bottom margin; leave the last partial
        # page naturally spaced instead of stretching a few rows vertically.
        extra = max(0, available - sum(row[3] + 24 for row in rows))
        gap = 12 + (extra / (len(rows) - 1) if page_index < len(pages) - 1 and len(rows) > 1 else 0)
        for capture, image, draw_w, draw_h in rows:
            doc.setFont('Helvetica', 7)
            doc.setFillColorRGB(.35, .39, .44)
            if show_timestamps:
                doc.drawString(margin, y - 8, timestamp(capture.time))
            elif getattr(capture, 'bar_number', None) is not None:
                doc.drawString(margin, y - 8, str(capture.bar_number))
            doc.drawImage(ImageReader(image), margin, y - 12 - draw_h, draw_w, draw_h)
            doc.setFillColorRGB(0, 0, 0)
            y -= draw_h + 12 + gap
    doc.save()
    return buffer.getvalue()

def scroll_offset(previous, current, minimum_match=.78):
    """Verify the entire overlap, including jumps larger than half a window."""
    width = current.shape[1]
    old = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    new = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    candidates = []
    for left, right in ((.52, .92), (.78, .98)):
        x1, x2 = int(width * left), int(width * right)
        matches = cv2.matchTemplate(new, old[:, x1:x2], cv2.TM_CCOEFF_NORMED)
        # Exclude backwards motion and matches beyond the available overlap.
        allowed = matches[:, :min(matches.shape[1], x1 + 4)]
        _, score, _, location = cv2.minMaxLoc(allowed)
        shift = x1 - location[0]
        if score < minimum_match or shift < -3:
            continue
        shift = max(0, shift)
        overlap_score = float(cv2.matchTemplate(new[:, :width-shift], old[:, shift:], cv2.TM_CCOEFF_NORMED)[0, 0])
        if overlap_score >= minimum_match:
            candidates.append((overlap_score, -shift, shift))
    return max(candidates)[2] if candidates else None


def barline_positions(strip):
    """Find strokes crossing all six strings, excluding note stems below them."""
    gray = cv2.cvtColor(strip, cv2.COLOR_BGR2GRAY)
    if dark_paper(strip):
        gray = print_image(strip)
    sample = gray[:, :min(gray.shape[1], 6000)]
    mask = cv2.adaptiveThreshold(sample, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
                                 cv2.THRESH_BINARY_INV, 31, 9)
    horizontal = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((1, 60), np.uint8))
    ys = np.flatnonzero((horizontal > 0).mean(axis=1) > .3)
    groups = np.split(ys, np.where(np.diff(ys) > 2)[0] + 1)
    lines = [int(np.mean(g)) for g in groups if len(g)]
    system = None
    for i, first in enumerate(lines):
        for last in lines[i + 5:]:
            gap = (last - first) / 5
            if not 4 <= gap <= 80:
                continue
            run = [min(lines, key=lambda y: abs(y - (first + n * gap))) for n in range(6)]
            if len(set(run)) == 6 and all(abs(y - (first + n * gap)) <= 2 for n, y in enumerate(run)):
                system = run
                break
        if system is not None:
            break
    if system is None:
        return []
    top, bottom = system[0] + 1, system[-1] - 1
    band = cv2.threshold(gray[top:bottom+1], 125, 255, cv2.THRESH_BINARY_INV)[1]
    # A barline reaches the top string. High-note stems stop just below it;
    # permitting even a short gap incorrectly counts those stems as measures.
    xs = np.flatnonzero((band > 0).mean(axis=0) >= .98)
    # Merge nearby repeat strokes / arpeggio strokes with the true barline.
    join_distance = max(12, int(np.median(np.diff(system)) * 2.5))
    groups = np.split(xs, np.where(np.diff(xs) > join_distance)[0] + 1)
    staff_pixels = np.flatnonzero((horizontal[system[0]:system[-1]+1] > 0).any(axis=0))
    left_edge = int(staff_pixels[0]) if len(staff_pixels) else 0
    # The opening staff border is not a completed measure.
    return [int(g[0]) for g in groups if len(g) and g[0] > left_edge + max(12, int(np.median(np.diff(system)) * .6))]


def reflow_pages(captures, bars_per_line=4):
    """Wrap each stationary tab row at measures, never treating it as a scroll."""
    result = []
    for capture in captures:
        for row in stitch_scroll([capture], bars_per_line=bars_per_line):
            row.bar_number = None
            result.append(row)
    return result


def stitch_scroll(captures, minimum_match=.78, stats=None, bars_per_line=4):
    """Join overlapping left-moving tab windows; split the strip into print rows."""
    if stats is not None:
        stats.update(joins=0, breaks=0, break_times=[])
    if not captures:
        return []
    rows, chunks, positions = [], [captures[0].image], [(0, captures[0].time)]
    previous = captures[0].image
    total_width = previous.shape[1]
    next_bar = 1

    def finish():
        nonlocal next_bar
        strip = np.concatenate(chunks, axis=1)
        height, length = strip.shape[:2]
        boundaries = barline_positions(strip)
        if len(boundaries) >= 2:
            start = 0
            for offset in range(0, len(boundaries), bars_per_line):
                group = boundaries[offset:offset + bars_per_line]
                end = min(length, group[-1] + 1)
                # Keep a short final tail with its preceding row.
                if length - end < 50:
                    end = length
                time = next((stamp for position, stamp in reversed(positions) if position <= start), positions[0][1])
                rows.append(Capture(time, strip[:, start:end].copy(), next_bar))
                next_bar += len(group)
                start = end - 1
                if end >= length:
                    return
            if length - start > 1:
                rows.append(Capture(positions[-1][1], strip[:, start:].copy(), next_bar))
                next_bar += 1
            return
        if len(chunks) == 1:
            # A stationary row without reliable measure boundaries must stay
            # intact; arbitrary pixel slicing can cut through notes and bars.
            rows.append(Capture(positions[0][1], strip.copy()))
            return
        width = min(chunks[0].shape[1], 1280)
        start = 0
        while start < length:
            end = min(start + width, length)
            if end < length:
                # Prefer a barline or whitespace near the desired row boundary.
                ink = ink_mask(strip[:, max(start + width * 2 // 3, start):end])
                vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN,
                                           np.ones((max(20, int(height * .45)), 1), np.uint8))
                candidates = np.flatnonzero((vertical > 0).sum(axis=0) > height * .40)
                base = max(start + width * 2 // 3, start)
                if len(candidates):
                    end = base + int(candidates[-1]) + 2
                else:
                    lo = max(start + width * 3 // 4, start)
                    area = ink_mask(strip[:, lo:end])
                    lines = cv2.morphologyEx(area, cv2.MORPH_OPEN,
                                            np.ones((1, 30), np.uint8))
                    density = (cv2.subtract(area, lines) > 0).sum(axis=0)
                    if len(density) >= 17:
                        gaps = np.convolve(density, np.ones(17), mode='valid')
                        end = lo + int(np.argmin(gaps)) + 8
            time = positions[0][1]
            for position, stamp in positions:
                if position <= start:
                    time = stamp
            rows.append(Capture(time, strip[:, start:end].copy()))
            if end >= length:
                break
            start = max(start + 1, end - 8)

    for capture in captures[1:]:
        current = capture.image
        if current.shape != previous.shape:
            if stats is not None:
                stats['breaks'] += 1
                stats['break_times'].append(capture.time)
            finish()
            chunks, positions = [current], [(0, capture.time)]
            total_width = current.shape[1]
            previous = current
            continue
        shift = scroll_offset(previous, current, minimum_match)
        if shift is not None:
            if shift > 2:
                if stats is not None:
                    stats['joins'] += 1
                positions.append((total_width, capture.time))
                chunks.append(current[:, -shift:].copy())
                total_width += shift
            else:
                # Keep the reference until tiny movements accumulate; otherwise
                # slow scrolling silently loses pixels at every sample.
                continue
        else:
            if stats is not None:
                stats['breaks'] += 1
                stats['break_times'].append(capture.time)
            # A page jump or uncertain match starts a separate strip.
            finish()
            chunks, positions = [current], [(0, capture.time)]
            total_width = current.shape[1]
        previous = current
    finish()
    return rows
