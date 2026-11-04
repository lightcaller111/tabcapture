# Validation

Validated on Windows on 2026-11-04.

On 2026-11-04, local and Linux GitHub Actions runs passed all 12 tests. Streamlit Community Cloud was deployed with Python 3.12. The hosted app loaded at a 390-pixel phone viewport. A short uploaded excerpt of the example video produced three captures from ten samples and a downloaded one-page PDF containing three images; the PDF was rendered and visually checked. The sample YouTube URL returned HTTP 403 on the cloud server.

After pinning Streamlit to the locally tested 1.64.0, version 1.2.1 deployed automatically from GitHub and was verified at the same public address. The mobile recheck showed preview images, stacked extraction settings, capture selection, editable PDF title, and the download control without the earlier asset-loading errors. Extraction again produced three captures from ten samples. A 390 x 844 browser viewport was used; physical iOS/Android device testing has not been performed.

Twelve automated tests cover URL handling, six-line detection, dark backgrounds, duplicate removal, changed notes, repeated passages, fade normalization, horizontal stitching, large jumps, slow scrolling, four-measure wrapping that excludes note stems, PDF generation, and the app's extract/review/manual-capture flow.

The supplied YouTube example was downloaded successfully during development, and live URL access was rechecked on 2026-11-04. Its visible tab panel is detected at the top of the video. The full 7:48 video was sampled at one-second intervals: 468 samples, seven blank/faded samples skipped, and 107 retained captures. Scrolling reconstruction joined 77 transitions and kept one uncertain transition separate. Full-video export is an image reconstruction, not a note-by-note transcription or a guarantee of musical completeness. Inspect transitions and rows before printing.

On this machine, the launcher uses an existing virtual environment and dependencies under the workspace. The ZIP contains portable source code, tests, and setup instructions; it does not bundle Python or the downloaded video.

