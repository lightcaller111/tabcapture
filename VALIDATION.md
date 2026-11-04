# Validation

Validated on Windows on 2026-11-04.

Twelve automated tests cover URL handling, six-line detection, dark backgrounds, duplicate removal, changed notes, repeated passages, fade normalization, horizontal stitching, large jumps, slow scrolling, four-measure wrapping that excludes note stems, PDF generation, and the app's extract/review/manual-capture flow.

The supplied YouTube example was downloaded successfully during development, and live URL access was rechecked on 2026-11-04. Its visible tab panel is detected at the top of the video. The full 7:48 video was sampled at one-second intervals: 468 samples, seven blank/faded samples skipped, and 107 retained captures. Scrolling reconstruction joined 77 transitions and kept one uncertain transition separate. Full-video export is an image reconstruction, not a note-by-note transcription or a guarantee of musical completeness. Inspect transitions and rows before printing.

On this machine, the launcher uses an existing virtual environment and dependencies under the workspace. The ZIP contains portable source code, tests, and setup instructions; it does not bundle Python or the downloaded video.
