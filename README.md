# TabCapture

An app that captures visible guitar tablature from a YouTube URL or video file and assembles selected images into a printable PDF.

## Phone website and updates

Open **[TabCapture](https://tabcapture-lightcaller111.streamlit.app/)** on your phone or computer. The app uses a narrow-screen layout and larger touch controls. Request changes in this task; verified releases pushed to `main` deploy automatically at the same address. Refresh after downloading your current PDF to use an update. See [DEPLOYMENT.md](DEPLOYMENT.md) for maintenance details.

The hosted upload-to-PDF flow was verified on 2026-11-04. The example YouTube URL returned HTTP 403 from the cloud server, although it worked during local development. For blocked links, choose **Local video** and upload a video file, or use the desktop app. Cloud URL downloads are not guaranteed.

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
2. Choose Horizontal scrolling or Changing pages / rows. Choose Guitar parts: Upper part only (default) or Both parts / all visible tabs. Pick a preview time with visible tabs and inspect the selected-part preview. Automatic detection follows layout changes; a fixed crop remains the region you specify, so include both parts if you want both when they appear later.
3. Set the time range and sampling interval. One second is a starting point; use 0.2-0.5 seconds for faster changes. Lower duplicate tolerance preserves smaller note changes.
4. Extract and review the captures. Uncheck unwanted images. Add a manual capture from the preview if a section was missed.
5. Download the PDF. Defaults are four detected bars per row and five tab rows per page, with a clean white background. The last page can have fewer rows. An aligned pair of guitar parts counts as one row when both parts are selected. Change Bars per line or Guitar parts before extracting again. Tab rows per page changes the PDF directly. Captures stay in chronological order on A4 or Letter pages, with a source link.

## Limitations

- Captures images of notation; it does not transcribe audio or produce editable music notation.
- Supports stationary page/row changes and horizontal scrolling. Scrolling mode matches overlapping frames and checks multiple ordered bar boundaries when measure spacing changes. It assembles a continuous strip before wrapping at barlines, and attaches an isolated closing barline to the preceding music. Uncertain matches still start a new strip. Vertical scrolling is not stitched. Review for duplicated or missing sections, especially with repeated patterns, jumps, and rapid motion.
- Six-line detection is a visual heuristic. Other string counts, five-line staff notation alone, low contrast, overlays, and moving backgrounds may require Fixed crop.
- Duplicate removal can retain cursor changes or merge small note changes. Sampled frames cannot guarantee every note is captured. Review before printing.
- Downloads prefer H.264 video up to 1080p for fast decoding. Source quality limits PDF sharpness.
- YouTube may block automated downloads. Update yt-dlp with `.venv\Scripts\python.exe -m pip install -U "yt-dlp[default]"`, check Node.js/Deno, or upload a video you already have. The app does not read browser cookies.
- Videos are stored in a temporary session directory; captures use memory. Above 1,000 captures, extraction asks you to reduce the range. For long videos, process shorter ranges.
- The Windows launcher listens only on localhost; the hosted website is public. Use videos you have permission to download and reproduce.

## Tests

```sh
python -m unittest discover -s tests -v
```

Dependencies: [yt-dlp](https://github.com/yt-dlp/yt-dlp), [Streamlit](https://docs.streamlit.io/), OpenCV, ReportLab.

For the supplied example (JM8FljbhjV8), choose Horizontal scrolling, preview at 30 seconds, automatic crop, and a one-second sampling interval.
