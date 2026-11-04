import unittest
import tempfile
from pathlib import Path
import sys
import cv2
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from core import detect_tab, signature, difference, extract, make_pdf, Capture, youtube_url, crop_frame

def tab(note="3"):
    frame = np.full((480, 960, 3), 255, np.uint8)
    for y in range(260, 341, 16):
        cv2.line(frame, (50, y), (910, y), (0, 0, 0), 1)
    for x in range(130, 850, 100):
        cv2.rectangle(frame, (x-3, 266), (x+25, 287), (255,255,255), -1)
        cv2.putText(frame, note, (x, 283), cv2.FONT_HERSHEY_SIMPLEX, .65, (0,0,0), 2)
    cv2.putText(frame, "Am", (70, 230), cv2.FONT_HERSHEY_SIMPLEX, .7, (0,0,0), 2)
    return frame

class CoreTests(unittest.TestCase):
    def test_url_single_video(self):
        self.assertEqual(youtube_url("https://www.youtube.com/watch?v=JM8FljbhjV8&list=x&index=4"), "https://www.youtube.com/watch?v=JM8FljbhjV8")
        self.assertEqual(youtube_url("https://youtu.be/JM8FljbhjV8"), "https://www.youtube.com/watch?v=JM8FljbhjV8")
        with self.assertRaises(ValueError):
            youtube_url("https://youtube.com.evil.test/watch?v=JM8FljbhjV8")

    def test_detection(self):
        box = detect_tab(tab())
        self.assertIsNotNone(box)
        self.assertLessEqual(box[1], 230)
        self.assertGreaterEqual(box[3], 340)
        self.assertIsNone(detect_tab(np.full((480,960,3), 255, np.uint8)))

    def test_cursor_and_notes(self):
        a = tab()
        b = a.copy()
        cv2.line(b, (440, 210), (440, 380), (0,0,0), 2)
        self.assertLess(difference(signature(a), signature(b)), .15)
        self.assertGreater(difference(signature(a), signature(tab("8"))), .15)

    def test_capture_sequence(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp)/"test.avi"
            out = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"MJPG"), 10, (960,480))
            self.assertTrue(out.isOpened())
            for note in ["3","8","3"]:
                for _ in range(20):
                    out.write(tab(note))
            out.release()
            captures, missed, total = extract(path, interval=.5)
            self.assertEqual(len(captures), 3)
            self.assertEqual(missed, 0)
            self.assertEqual(total, 12)
            self.assertEqual([c.time for c in captures], [0.,2.,4.])
            with self.assertRaises(ValueError):
                extract(path, start=3, end=2)

    def test_pdf_and_bad_crop(self):
        data = make_pdf([Capture(i*2, tab()) for i in range(12)], "Test tabs", "https://youtu.be/JM8FljbhjV8")
        self.assertTrue(data.startswith(b"%PDF"))
        self.assertIn(b"/Type /Page", data)
        with self.assertRaises(ValueError):
            make_pdf([])
        with self.assertRaises(ValueError):
            crop_frame(tab(), (10,10,5,5))


    def test_horizontal_scroll(self):
        from core import stitch_scroll
        strip=np.full((180,1920,3),255,np.uint8)
        for y in range(50,131,16):
            cv2.line(strip,(0,y),(1919,y),(100,100,100),1)
        for x in range(30,1880,60):
            cv2.putText(strip,str(x),(x,44),cv2.FONT_HERSHEY_SIMPLEX,.5,(0,0,0),1)
            cv2.putText(strip,str(x%13),(x,100),cv2.FONT_HERSHEY_SIMPLEX,.6,(0,0,0),2)
        captures=[Capture(i,strip[:,offset:offset+960].copy()) for i,offset in enumerate(range(0,961,120))]
        rows=stitch_scroll(captures)
        reconstructed=np.concatenate([rows[0].image]+[row.image[:,8:] for row in rows[1:]],axis=1)
        self.assertEqual(reconstructed.shape,strip.shape)
        self.assertTrue(np.array_equal(reconstructed,strip))

    def test_dark_background_panel(self):
        frame=tab()
        frame[:200]=20
        frame[410:]=20
        self.assertIsNotNone(detect_tab(frame))
        self.assertIsNotNone(detect_tab(255-tab()))

    def test_fade_signature(self):
        full = tab()
        faded = (full.astype(float) * .4).astype(np.uint8)
        self.assertLess(difference(signature(full), signature(faded)), .02)

    def test_tiny_scroll_accumulates(self):
        from core import stitch_scroll
        rng = np.random.default_rng(4)
        strip = rng.integers(0, 256, (80, 1010, 3), dtype=np.uint8)
        captures = [Capture(i, strip[:, i:i+1000].copy()) for i in range(10)]
        rows = stitch_scroll(captures)
        width = sum(row.image.shape[1] for row in rows) - 8 * (len(rows)-1)
        self.assertEqual(width, 1009)

    def test_large_scroll_jump(self):
        from core import scroll_offset
        rng = np.random.default_rng(9)
        strip = rng.integers(0, 256, (80, 1600, 3), dtype=np.uint8)
        self.assertEqual(scroll_offset(strip[:, :1000], strip[:, 600:1600]), 600)

    def test_four_bars_per_row(self):
        from core import stitch_scroll, barline_positions
        strip = np.full((200, 2001, 3), 255, np.uint8)
        for y in range(50, 151, 20):
            cv2.line(strip, (0, y), (2000, y), (100,100,100), 1)
        for x in range(250, 2001, 250):
            cv2.line(strip, (x, 50), (x, 175), (0,0,0), 2)
        for x in range(125, 2000, 250):
            cv2.line(strip, (x, 57), (x, 175), (0,0,0), 2)
        self.assertEqual(len(barline_positions(strip)), 8)
        rows = stitch_scroll([Capture(0, strip)], bars_per_line=4)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row.bar_number for row in rows], [1, 5])
        self.assertTrue(all(995 <= row.image.shape[1] <= 1005 for row in rows))

if __name__ == "__main__":
    unittest.main()
