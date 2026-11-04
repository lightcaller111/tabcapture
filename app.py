from pathlib import Path
import tempfile
import cv2
import streamlit as st
from version import __version__
from core import download_video, video_info, frame_at, detect_tab, crop_frame, extract, make_pdf, timestamp, Capture, youtube_url, stitch_scroll

st.set_page_config(page_title="TabCapture", page_icon="🎸", layout="wide")
st.markdown('<style>' + Path(__file__).with_name('mobile.css').read_text() + '</style>', unsafe_allow_html=True)
st.markdown("### 🎸 TabCapture")
st.title("From video to your music stand.")
st.write("Capture on-screen guitar tabs, review the sections, and download one printable PDF.")
st.caption("Supports changing tab pages and horizontally scrolling tablature. Review the result before printing.")
with st.expander(f"About / updates · v{__version__}"):
    st.write("Works in a desktop or phone browser. Video processing runs on the computer or server hosting this app.")
    st.write("After a new version is deployed, refresh this page to use it. Finish and download your current PDF before refreshing.")
    st.caption("On a phone, keep this page open while processing a video.")

if "workspace" not in st.session_state:
    st.session_state.workspace = tempfile.TemporaryDirectory(prefix="tabcapture-")
folder = Path(st.session_state.workspace.name)

def load(path, title, source):
    info = video_info(path)
    st.session_state.video = str(path)
    st.session_state.info = info
    st.session_state.title = title
    st.session_state.source = source
    st.session_state.captures = []
    st.session_state.selected = {}
    st.session_state.pop("report", None)
    st.session_state.pop("settings", None)
    st.session_state.pop("stitch_stats", None)
    st.session_state.generation = st.session_state.get("generation", 0) + 1

with st.expander("1 · Load a video", expanded="video" not in st.session_state):
    mode = st.radio("Video source", ["YouTube URL", "Local video"], horizontal=True)
    if mode == "YouTube URL":
        url = st.text_input("YouTube video URL", "https://www.youtube.com/watch?v=JM8FljbhjV8")
        if st.button("Load from YouTube", type="primary"):
            bar = st.progress(0., text="Downloading video...")
            try:
                path, title = download_video(url, folder, bar.progress)
                load(path, title, youtube_url(url))
                st.rerun()
            except Exception as error:
                st.error(f"Unable to load video: {error}")
                st.info("YouTube can block downloads from this hosting server. Choose Local video above to upload a video file from your phone or computer, or try the desktop app. Refreshing or signing in to YouTube on your phone does not change the server's access.")
            finally:
                bar.empty()
    else:
        upload = st.file_uploader("Video file", type=["mp4", "mkv", "webm", "mov", "avi"])
        if st.button("Load video", disabled=upload is None):
            try:
                path = folder / ("upload" + Path(upload.name).suffix.lower())
                path.write_bytes(upload.getbuffer())
                load(path, Path(upload.name).stem, "")
                st.rerun()
            except Exception as error:
                st.error(str(error))

if "video" not in st.session_state:
    st.info("Start by loading a YouTube link or a video file.")
    st.stop()

path, info = st.session_state.video, st.session_state.info
generation = st.session_state.generation
st.caption(f"{st.session_state.title} · {timestamp(info['duration'])} · {info['width']} × {info['height']}")
st.subheader("2 · Find the tab area")
preview_time = st.number_input("Preview time (seconds)", min_value=0., max_value=max(0., info["duration"]-.1), value=min(30., max(0., info["duration"]-.1)), step=1., key=f"preview-{generation}")
try:
    frame = frame_at(path, preview_time)
except Exception as error:
    st.error(str(error))
    st.stop()
automatic = detect_tab(frame)
layout = st.radio("Tab movement", ["Horizontal scrolling", "Changing pages / rows"], horizontal=True)
crop_mode = st.radio("Capture area", ["Automatic detection", "Fixed crop"], horizontal=True)
region = None
if crop_mode == "Fixed crop":
    box = automatic or (0, int(info["height"]*.55), info["width"], info["height"])
    left, right = st.slider("Left / right edges (%)", 0, 100, (int(box[0]*100/info["width"]), min(100, int(box[2]*100/info["width"]))), key=f"x-{generation}")
    top, bottom = st.slider("Top / bottom edges (%)", 0, 100, (int(box[1]*100/info["height"]), min(100, int(box[3]*100/info["height"]))), key=f"y-{generation}")
    if left >= right or top >= bottom:
        st.warning("Move the crop edges apart to select a visible area.")
        st.stop()
    region = tuple(int(v) for v in (left*info["width"]/100, top*info["height"]/100, right*info["width"]/100, bottom*info["height"]/100))
box = region or automatic
annotated = frame.copy()
if box:
    cv2.rectangle(annotated, box[:2], box[2:], (70, 190, 80), 3)
a, b = st.columns(2)
a.image(annotated, channels="BGR", caption="Green border: capture area", use_container_width=True)
if box:
    b.image(crop_frame(frame, box), channels="BGR", caption="Capture preview", use_container_width=True)
else:
    b.warning("No six-line tab system detected. Try another time or use Fixed crop.")

with st.expander("Extraction settings", expanded=True):
    a, b, c = st.columns(3)
    interval = a.number_input("Sample every (seconds)", .2, 30., 1., .2)
    threshold = b.slider("Duplicate tolerance", .01, .60, .15, .01, help="Lower values retain smaller note changes but can also retain cursor movement.")
    paper = c.selectbox("PDF paper size", ["A4", "Letter"])
    bars_per_line = st.number_input("Bars per line", min_value=2, max_value=8, value=4,
                                    help="Wrap scrolling tablature at detected measure boundaries.")
    a, b = st.columns(2)
    start = a.number_input("Start (seconds)", 0., float(info["duration"]), 0.)
    end = b.number_input("End (seconds)", 0., float(info["duration"]), float(info["duration"]))
    st.caption("Only adjacent near-identical captures are removed. Use a shorter interval for fast-changing tabs.")

if st.button("Extract tabs", type="primary"):
    bar = st.progress(0., text="Finding tab frames...")
    try:
        capture_region = (region or automatic) if layout == "Horizontal scrolling" else region
        if layout == "Horizontal scrolling" and capture_region is None:
            raise ValueError("Choose a preview with visible tabs or set a fixed crop before stitching.")
        captures, missed, total = extract(path, interval, capture_region, threshold, start, end, bar.progress)
        st.session_state.stitch_stats = {}
        if layout == "Horizontal scrolling":
            bar.progress(1., text="Joining scrolling sections...")
            captures = stitch_scroll(captures, stats=st.session_state.stitch_stats, bars_per_line=bars_per_line)
        st.session_state.captures = captures
        st.session_state.selected = {}
        st.session_state.review_revision = st.session_state.get("review_revision", 0) + 1
        st.session_state.report = f"{len(captures)} captures from {total} samples; {missed} samples unreadable or without detected tabs."
        st.session_state.settings = (interval, region, threshold, start, end, layout, bars_per_line)
    except Exception as error:
        st.error(str(error))
    finally:
        bar.empty()

if "report" in st.session_state:
    st.info(st.session_state.report)
    breaks = st.session_state.get("stitch_stats", {}).get("breaks", 0)
    if breaks:
        st.warning(f"{breaks} scrolling transitions could not be joined confidently. Those sections were kept separately; check them for overlap.")
st.subheader("3 · Review and export")
if box and st.button("Add current preview as a manual capture"):
    previous_selection = {id(cap): st.session_state.selected.get(i, True)
                          for i, cap in enumerate(st.session_state.captures)}
    st.session_state.captures.append(Capture(preview_time, crop_frame(frame, box)))
    st.session_state.captures.sort(key=lambda x: x.time)
    st.session_state.selected = {i: previous_selection.get(id(cap), True)
                                for i, cap in enumerate(st.session_state.captures)}
    st.session_state.review_revision = st.session_state.get("review_revision", 0) + 1
captures = st.session_state.get("captures", [])
if captures:
    if st.session_state.get("settings") and st.session_state.settings != (interval, region, threshold, start, end, layout, bars_per_line):
        st.warning("Settings changed. Extract again to apply them to existing captures.")
    st.write("Uncheck unwanted captures. Check for missing sections and partially visible notes before printing.")
    revision = st.session_state.get("review_revision", 0)
    pages = max(1, (len(captures)+11)//12)
    page = st.number_input("Review page (12 captures per page)", 1, pages, 1, key=f"page-{generation}-{revision}")
    for index in range((page-1)*12, min(page*12, len(captures))):
        capture = captures[index]
        keep = st.checkbox(f"Include capture {index+1} · {timestamp(capture.time)}", value=st.session_state.selected.get(index, True), key=f"keep-{generation}-{revision}-{index}")
        st.session_state.selected[index] = keep
        st.image(capture.image, channels="BGR", use_container_width=True)
    title = st.text_input("PDF title", st.session_state.title, key=f"title-{generation}")
    monochrome = st.checkbox("White background for printing", True)
    selected = [cap for i, cap in enumerate(captures) if st.session_state.selected.get(i, True)]
    st.caption(f"{len(selected)} of {len(captures)} captures selected")
    if selected:
        pdf = make_pdf(selected, title or "Guitar tablature", st.session_state.source, paper, monochrome)
        st.download_button("Download complete PDF", pdf, "guitar-tabs.pdf", "application/pdf", type="primary")
    else:
        st.warning("Select at least one capture to export.")
