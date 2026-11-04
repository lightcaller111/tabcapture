# TabCapture

A local app that captures visible guitar tablature from a YouTube URL or video file and assembles selected images into a printable PDF.

## Phone website and updates

Version 1.2.0 adds a narrow-screen layout and larger touch controls. The prepared cloud target is GitHub + Streamlit Community Cloud; see [DEPLOYMENT.md](DEPLOYMENT.md) for the one-time connection and ongoing update flow. A public HTTPS address has not been assigned yet. Once connected, request changes in this task and deployed releases will appear at the same address after refreshing the phone browser.

## Run on Windows

The copy in this workspace is already configured. For a fresh installation, install Python 3.10 or newer from https://www.python.org/downloads/ with the Python launcher. The dependency file installs a supported Node.js runtime for YouTube downloads.

Double-click **Start TabCapture.bat**. The first run installs dependencies into a local virtual environment. Keep the terminal open while using the app; close it to stop.

## Run from a terminal

```sh
python -m venv .venv
# Windows: .venv\Scripts\activate
# macOS/Linux: source .venv/bin/activate
python -m pip install -r requirements.txt
python -m streamlit run app.py --server.address 127.0.0.1 --server.maxUploadSize 2048
```

## Use

1. Load a YouTube URL or upload a video. Playlist parameters are ignored; only the chosen video is downloaded.
2. Choose Horizontal scrolling or Changing pages / rows. Pick a preview time with visible tabs. Inspect the automatic capture border. Use Fixed crop and adjust the edges if detection misses notes, chords, or rhythm marks.
3. Set the time range and sampling interval. One second is a starting point; use 0.2-0.5 seconds for faster changes. Lower duplicate tolerance preserves smaller note changes.
4. Extract and review the captures. Uncheck unwanted images. Add a manual capture from the preview if a section was missed.
5. Download the PDF. Scrolling tabs default to four detected bars per line, connected at barlines, with smaller notation, measure numbers, and a clean white background. Change Bars per line before extracting to adjust the layout. Captures stay in chronological order on A4 or Letter pages, with a source link.

## Limitations

- Captures images of notation; it does not transcribe audio or produce editable music notation.
- Supports stationary page/row changes and horizontal scrolling. Scrolling mode matches overlapping frames, assembles strips, and splits them near barlines or whitespace with a small overlap. Uncertain matches start a new strip. Vertical scrolling is not stitched. Review for duplicated or missing sections, especially with repeated patterns, jumps, and rapid motion.
- Six-line detection is a visual heuristic. Other string counts, five-line staff notation alone, low contrast, overlays, and moving backgrounds may require Fixed crop.
- Duplicate removal can retain cursor changes or merge small note changes. Sampled frames cannot guarantee every note is captured. Review before printing.
- Downloads prefer H.264 video up to 1080p for fast decoding. Source quality limits PDF sharpness.
- YouTube may block automated downloads. Update yt-dlp with `.venv\Scripts\python.exe -m pip install -U "yt-dlp[default]"`, check Node.js/Deno, or upload a video you already have. The app does not read browser cookies.
- Videos are stored in a temporary session directory; captures use memory. Above 1,000 captures, extraction asks you to reduce the range. For long videos, process shorter ranges.
- The app listens only on localhost. Use videos you have permission to download and reproduce.

## Tests

```sh
python -m unittest discover -s tests -v
```

Dependencies: [yt-dlp](https://github.com/yt-dlp/yt-dlp), [Streamlit](https://docs.streamlit.io/), OpenCV, ReportLab.

For the supplied example (JM8FljbhjV8), choose Horizontal scrolling, preview at 30 seconds, automatic crop, and a one-second sampling interval.
