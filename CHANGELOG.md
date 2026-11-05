# Release notes

## 1.6.0
- Match consecutive bar boundaries when the video changes measure spacing, preserving one continuous strip before wrapping into four-bar rows.
- Avoid needless horizontal resizing caused by tiny staff-detection variations.
- Retain a captured final double barline on the preceding music row instead of giving it a separate row or page.
- Fill the printable width for complete rows even when tall notation needs a separate height fit.
- Keep five rows per page and upper guitar part as the defaults.

## 1.5.0
- Default to five tab rows per PDF page, adjustable from one to ten.
- Add a guitar-part selector, defaulting to upper part only; preview and manual captures use the selection too.
- Re-detect automatic crop areas throughout the video when the notation layout changes.
- Separate single-part and stacked-part scrolling sections rather than joining incompatible layouts.
- Identify short fragments by width rather than height, avoiding accidental miniaturization of stacked parts.
- Normalize single-part staff size and allow different viewport widths when matching overlapping scrolling captures; uncertain notation reflows remain separate.

## 1.4.0
- Fit normal tab rows to the printable page width independently, with narrower margins.
- Trim empty vertical padding and balance row spacing on full pages.
- Keep short fragments proportional instead of enlarging them into oversized notation.
- Show video timestamps and recovery guidance for uncertain scrolling transitions.

## 1.3.1
- Fixed dark-panel barline detection and excluded opening staff borders from measure counts.
- Applied Bars per line to changing rows as well as scrolling tabs.
- Preserved stationary rows when measure detection is uncertain instead of slicing through notes at a fixed pixel width.

## 1.3.0
- Empty URL field with the placeholder Enter the URL.
- Detect light staff lines on dark backgrounds even when ties add extra horizontal lines.
- Convert dark translucent tab panels to white paper with dark notation.

## 1.2.1
- Published the phone website and connected automatic deployments from GitHub.
- Clarified the upload fallback when YouTube blocks a hosted download.
- Pinned Streamlit to the locally tested UI version for reproducible deployments.

## 1.2.0
- Phone-friendly stacked controls, larger touch targets, and full-width action buttons.
- Version shown in About / updates.
- Ready for GitHub + Streamlit Community Cloud deployment and source-controlled updates.
- Keeps four-bar rows, measure numbers, and print-friendly PDF output.

## 1.1.0
- Wrap at detected barlines, approximately four measures per line.
- Smaller notation, white paper background, no timestamp labels in the PDF.

## 1.0.0
- YouTube and local video loading, automatic tab detection, crop adjustment, review, scrolling reconstruction, and PDF export.
