# Validation

Validated on Windows on 2026-11-04.

On 2026-11-04, the Linux GitHub Actions run passed all 12 tests. Streamlit Community Cloud was deployed with Python 3.12. The hosted app loaded at a 390-pixel phone viewport. A short uploaded excerpt of the example video produced three captures from ten samples and a downloaded one-page PDF containing three images; the PDF was rendered and visually checked. The sample YouTube URL returned HTTP 403 on the cloud server. Browser preview assets intermittently failed to load during the hosted check; this remains separate from successful server extraction and PDF download.

Twelve automated tests cover URL handling, six-line detection, dark backgrounds, duplicate removal, changed notes, repeated passages, fade normalization, horizontal stitching, large jumps, slow scrolling, four-measure wrapping that excludes note stems, PDF generation, and the app's extract/review/manual-capture flow.

The supplied YouTube example was downloaded successfully during development, and live URL access was rechecked on 2026-11-04. Its visible tab panel is detected at the top of the video. The full 7:48 video was sampled at one-second intervals: 468 samples, seven blank/faded samples skipped, and 107 retained captures. Scrolling reconstruction joined 77 transitions and kept one uncertain transition separate. Full-video export is an image reconstruction, not a note-by-note transcription or a guarantee of musical completeness. Inspect transitions and rows before printing.

On this machine, the launcher uses an existing virtual environment and dependencies under the workspace. The ZIP contains portable source code, tests, and setup instructions; it does not bundle Python or the downloaded video.
