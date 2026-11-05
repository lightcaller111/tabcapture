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


def staff_contrast(polarity, horizontal, run, gap):
    """Reject bright halos next to strings when testing the opposite polarity."""
    distance = max(2, round(gap * .3))
    contrasts = []
    for y in run:
        xs = horizontal[y] > 0
        if not np.any(xs):
            return 0.
        above = polarity[max(0, y-distance), xs].astype(float)
        below = polarity[min(len(polarity)-1, y+distance), xs].astype(float)
        contrasts.append(float(np.median((above + below) / 2 - polarity[y, xs])))
    return float(np.median(contrasts))


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
        # Chord numbers erase short pieces of every string. Requiring a long
        # uninterrupted run loses whole staffs in dense rhythm-guitar parts.
        horizontal = cv2.morphologyEx(mask, cv2.MORPH_OPEN, np.ones((1, max(12, mask.shape[1] // 64)), np.uint8))
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
                if staff_contrast(polarity, horizontal, run, gap) < 12:
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
    # The desired annotation margin can extend into the performance video.
    # Stop at an unmistakable full-width white-panel edge, when present,
    # instead of printing a dark strip of the guitarist above every row.
    panel = gray[y1:min(y1 + round(gap*2), min(s[1] for s in systems)), x1:x2]
    if len(panel) >= 8:
        white = (panel > 210).mean(axis=1)
        if white[0] < .5:
            for offset in range(1, len(panel)-6):
                if np.all(white[offset:offset+6] > .9):
                    y1 += offset
                    break
    return tuple(int(v / scale) for v in (x1, y1, x2, y2))


def tab_system_rows(image):
    """Locate distinct six-string staffs without treating two parts as one."""
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    candidates = []
    for polarity in (gray, 255 - gray):
        mask = cv2.adaptiveThreshold(polarity,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY_INV,31,9)
        horizontal = cv2.morphologyEx(mask,cv2.MORPH_OPEN,np.ones((1,max(12,gray.shape[1]//64)),np.uint8))
        ys = np.flatnonzero((horizontal > 0).mean(axis=1) > .25)
        groups = np.split(ys,np.where(np.diff(ys)>2)[0]+1)
        lines = [int(np.mean(g)) for g in groups if 0 < len(g) <= 5]
        for i, first in enumerate(lines):
            for last in lines[i+5:]:
                gap = (last-first)/5
                if not 4 <= gap <= 80:
                    continue
                run = [min(lines,key=lambda y:abs(y-first-n*gap)) for n in range(6)]
                if len(set(run)) == 6 and all(abs(y-first-n*gap)<=max(2,gap*.12) for n,y in enumerate(run)):
                    if staff_contrast(polarity, horizontal, run, gap) < 12:
                        continue
                    coverage = float(np.mean([(horizontal[y] > 0).mean() for y in run]))
                    error = float(np.mean([abs(y-first-n*gap) for n,y in enumerate(run)])) / gap
                    candidates.append((coverage - error, gap, run))
    selected = []
    for _, gap, run in sorted(candidates, key=lambda item:(-item[0],item[1],item[2][0])):
        if not any(run[0] <= old[-1]+gap and run[-1] >= old[0]-gap for old in selected):
            selected.append(run)
    return sorted(selected,key=lambda run:run[0])


def select_tab_part(image, part='all'):
    if part not in ('all','upper'):
        raise ValueError('Choose all or upper tab parts.')
    if part == 'all':
        return image
    systems = tab_system_rows(image)
    if len(systems) < 2:
        return image
    # Keep the upper part's rhythm stems/ties, stopping before the lower staff.
    gap = float(np.median(np.diff(systems[0])))
    end = min(systems[1][0] - max(3,int(gap*.7)), int(systems[0][-1] + gap*4.5) + 1)
    return image[:end].copy()


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


def extract(path, interval=1., region=None, threshold=.15, start=0., end=None, progress=None, max_captures=1000, part='all'):
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
            cropped = select_tab_part(crop_frame(frame, box), part)
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


def make_pdf(captures, title='Guitar tablature', source='', paper='A4', monochrome=True, show_timestamps=False, rows_per_page=5):
    if not captures:
        raise ValueError('Select at least one capture before exporting.')
    if not isinstance(rows_per_page, int) or not 1 <= rows_per_page <= 10:
        raise ValueError('Choose between 1 and 10 tab rows per page.')
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
    typical_width = float(np.median([image.width for _, image in prepared]))
    laid_out = []
    for capture, image in prepared:
        iw, ih = image.size
        # Fit ordinary rows independently, so a very wide stitched strip cannot
        # shrink every other row. Retain the size of genuinely short fragments.
        target_width = width - 2 * margin
        if iw < typical_width * .55:
            target_width *= iw / typical_width
        slot_height = (height - 60 - margin) / rows_per_page
        draw_height = min(ih * target_width / iw, slot_height - 24)
        # Tall bends/rhythm marks must not pull a complete row away from the
        # right margin. Fit its height separately within the chosen page grid.
        laid_out.append((capture, image, target_width, draw_height))
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
        if pending and (len(pending) >= rows_per_page or used + needed > available + .01):
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
        gap = 12 + (extra / (len(rows) - 1) if len(rows) == rows_per_page and len(rows) > 1 else 0)
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
    width = previous.shape[1]
    old = cv2.cvtColor(previous, cv2.COLOR_BGR2GRAY)
    new = cv2.cvtColor(current, cv2.COLOR_BGR2GRAY)
    candidates = []
    for left, right in ((.52, .92), (.78, .98)):
        x1, x2 = int(width * left), int(width * right)
        if x2 - x1 > new.shape[1]:
            continue
        matches = cv2.matchTemplate(new, old[:, x1:x2], cv2.TM_CCOEFF_NORMED)
        allowed = matches
        _, score, _, location = cv2.minMaxLoc(allowed)
        shift = x1 - location[0]
        if score < minimum_match:
            continue
        old_start, new_start = max(0, shift), max(0, -shift)
        overlap = min(old.shape[1] - old_start, new.shape[1] - new_start)
        if overlap < max(40, min(old.shape[1], new.shape[1]) * .2):
            continue
        overlap_score = float(cv2.matchTemplate(new[:, new_start:new_start+overlap], old[:, old_start:old_start+overlap], cv2.TM_CCOEFF_NORMED)[0, 0])
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


def normalize_scroll_staff(captures):
    if len(captures) < 2:
        return captures
    systems = [tab_system_rows(cap.image) for cap in captures]
    gaps = [float(np.mean(np.diff(parts[0]))) for parts in systems if len(parts) == 1]
    if not gaps:
        return captures
    single_heights = {cap.image.shape[0] for cap, parts in zip(captures, systems) if len(parts) == 1}
    if max(gaps) / min(gaps) < 1.04 and len(single_heights) <= 1:
        return captures
    target_gap = float(np.median(gaps))
    top = round(target_gap * 4)
    height = round(target_gap * 13.5) + 1
    result = []
    for cap, parts in zip(captures, systems):
        if len(parts) != 1:
            result.append(cap)
            continue
        factor = target_gap / float(np.mean(np.diff(parts[0])))
        # A one-pixel line-detection wobble is not a camera zoom. Rescaling
        # those frames changes every horizontal note coordinate unnecessarily.
        if abs(factor - 1) < .04:
            factor = 1.
        source = cv2.resize(cap.image, (round(cap.image.shape[1]*factor),round(cap.image.shape[0]*factor)), interpolation=cv2.INTER_CUBIC)
        background = 0 if dark_paper(cap.image) else 255
        normalized = np.full((height,source.shape[1],3),background,np.uint8)
        offset = top - round(parts[0][0]*factor)
        source_start, dest_start = max(0,-offset), max(0,offset)
        length = min(len(source)-source_start,height-dest_start)
        if length > 0:
            normalized[dest_start:dest_start+length] = source[source_start:source_start+length]
        result.append(Capture(cap.time,normalized,cap.bar_number))
    return result


def matching_bar_boundary(previous, current):
    """Recover a notation reflow using several ordered, distinctive bar starts.

    Compare local notation rather than stretching a whole measure: the video
    can change beat spacing while retaining the size of the printed symbols.
    Only adjacent video captures are considered, never global repeated music.
    """
    if previous.shape[0] != current.shape[0]:
        return None
    old, new = barline_positions(previous), barline_positions(current)
    if len(old) < 2 or len(new) < 2:
        return None
    systems = tab_system_rows(previous)
    if len(systems) != 1:
        return None
    gap = float(np.mean(np.diff(systems[0])))
    left, right = round(gap * 1.3), round(gap * 3.4)
    a, b = print_image(previous), print_image(current)
    # Antialiasing can move a detected thin string by a pixel. Permit a tiny
    # vertical registration correction as well as the horizontal one.
    b = cv2.copyMakeBorder(b, 3, 3, 0, 0, cv2.BORDER_CONSTANT, value=255)
    scores = np.zeros((len(old), len(new)), np.float32)
    for i, x in enumerate(old):
        available_right = min(right, a.shape[1] - x - 4)
        if x < left or available_right < gap * 1.5:
            continue
        patch = a[:, x-left:x+available_right]
        # Empty staff/bar intersections provide no musical identity.
        ink = cv2.threshold(patch, 140, 255, cv2.THRESH_BINARY_INV)[1]
        horizontal = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((1, 20), np.uint8))
        vertical = cv2.morphologyEx(ink, cv2.MORPH_OPEN, np.ones((20, 1), np.uint8))
        if np.count_nonzero(cv2.subtract(ink, cv2.bitwise_or(horizontal, vertical))) < 60:
            continue
        for j, y in enumerate(new):
            if y < left + 3 or y + available_right + 3 >= b.shape[1]:
                continue
            search = b[:, y-left-3:y+available_right+3]
            scores[i, j] = cv2.minMaxLoc(cv2.matchTemplate(search, patch, cv2.TM_CCOEFF_NORMED))[1]
    candidates = []
    for delta in range(-len(new)+1, len(old)):
        pairs = []
        for j in range(len(new)):
            i = j + delta
            if not 0 <= i < len(old):
                continue
            score = float(scores[i, j])
            alternatives = [float(scores[i, k]) for k in range(len(new)) if k != j]
            if score >= .60 and score - max(alternatives, default=0) >= .08:
                pairs.append((i, j, score))
        if len(pairs) >= 2 and max(p[2] for p in pairs) >= .78:
            candidates.append((sum(p[2] for p in pairs), pairs))
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[0], reverse=True)
    if len(candidates) > 1 and candidates[0][0] - candidates[1][0] < .4:
        return None
    i, j, _ = candidates[0][1][-1]
    return old[i], new[j]


def attach_terminal_barline(rows):
    """Keep a captured closing stroke with the music, without dropping notes."""
    if len(rows) < 2:
        return rows
    previous, tail = rows[-2], rows[-1]
    if previous.image.shape[0] != tail.image.shape[0]:
        return rows
    systems = tab_system_rows(previous.image)
    if len(systems) != 1:
        return rows
    staff = systems[0]
    gap = float(np.mean(np.diff(staff)))
    if tail.image.shape[1] > gap * 3:
        return rows
    ink = cv2.threshold(print_image(tail.image), 140, 255, cv2.THRESH_BINARY_INV)[1]
    for y in staff:
        ink[max(0,y-2):y+3] = 0
    vertical = cv2.morphologyEx(
        cv2.threshold(print_image(tail.image), 140, 255, cv2.THRESH_BINARY_INV)[1],
        cv2.MORPH_OPEN, np.ones((max(10, round(gap*4)), 1), np.uint8))
    if not np.any(vertical):
        return rows
    remaining = cv2.subtract(ink, cv2.dilate(vertical, np.ones((3,3),np.uint8)))
    if np.count_nonzero(remaining) > 12:
        return rows
    joined = np.concatenate([previous.image, tail.image], axis=1)
    return rows[:-2] + [Capture(previous.time, joined, previous.bar_number)]


def stitch_scroll(captures, minimum_match=.78, stats=None, bars_per_line=4):
    """Join overlapping left-moving tab windows; split the strip into print rows."""
    if stats is not None:
        stats.update(joins=0, breaks=0, break_times=[], layout_changes=0, reflow_joins=0)
    if not captures:
        return []
    captures = normalize_scroll_staff(captures)
    rows, chunks, positions = [], [captures[0].image], [(0, captures[0].time)]
    previous = captures[0].image
    previous_parts = len(tab_system_rows(previous))
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
        current_parts = len(tab_system_rows(current))
        layout_changed = current_parts != previous_parts
        if current.shape[0] != previous.shape[0] or layout_changed:
            if stats is not None:
                stats['breaks'] += 1
                stats['break_times'].append(capture.time)
                stats['layout_changes'] += int(layout_changed)
            finish()
            chunks, positions = [current], [(0, capture.time)]
            total_width = current.shape[1]
            previous = current
            previous_parts = current_parts
            continue
        shift = scroll_offset(previous, current, minimum_match)
        if shift is not None:
            advance = shift + current.shape[1] - previous.shape[1]
            if advance > 2:
                if stats is not None:
                    stats['joins'] += 1
                positions.append((total_width, capture.time))
                chunks.append(current[:, -advance:].copy())
                total_width += advance
            else:
                # Keep the reference until tiny movements accumulate; otherwise
                # slow scrolling silently loses pixels at every sample.
                continue
        else:
            boundary = matching_bar_boundary(previous, current)
            if boundary is not None:
                old_x, new_x = boundary
                cut = total_width - previous.shape[1] + old_x
                strip = np.concatenate(chunks, axis=1)
                chunks = [strip[:, :cut].copy(), current[:, new_x:].copy()]
                positions = [(x, t) for x, t in positions if x < cut] + [(cut, capture.time)]
                total_width = cut + current.shape[1] - new_x
                previous = current
                previous_parts = current_parts
                if stats is not None:
                    stats['joins'] += 1
                    stats['reflow_joins'] += 1
                continue
            if stats is not None:
                stats['breaks'] += 1
                stats['break_times'].append(capture.time)
            # A page jump or uncertain match starts a separate strip.
            finish()
            chunks, positions = [current], [(0, capture.time)]
            total_width = current.shape[1]
        previous = current
        previous_parts = current_parts
    finish()
    return attach_terminal_barline(rows)
