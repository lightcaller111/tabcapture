import tempfile
import unittest
from pathlib import Path
import cv2
from streamlit.testing.v1 import AppTest
from test_core import tab

class AppTests(unittest.TestCase):
    def test_extract_and_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/"sample.avi"
            writer=cv2.VideoWriter(str(path),cv2.VideoWriter_fourcc(*"MJPG"),10,(960,480))
            for note in ["3","8","3"]:
                for _ in range(20):
                    writer.write(tab(note))
            writer.release()
            app=AppTest.from_file(str(Path(__file__).resolve().parents[1]/"app.py"),default_timeout=30).run()
            self.assertEqual(len(app.exception),0)
            app.session_state["video"]=str(path)
            app.session_state["info"]={"duration":6.,"width":960,"height":480}
            app.session_state["title"]="Synthetic test"
            app.session_state["source"]=""
            app.session_state["generation"]=1
            app.session_state["captures"]=[]
            app.session_state["selected"]={}
            app.run()
            self.assertEqual(len(app.exception),0)
            next(r for r in app.radio if r.label=="Tab movement").set_value("Changing pages / rows").run()
            self.assertEqual(next(n for n in app.number_input if n.label=='Tab rows per page').value,5)
            self.assertEqual(next(s for s in app.selectbox if s.label=='Guitar parts').value,'Upper part only')
            next(b for b in app.button if b.label=="Extract tabs").click().run()
            self.assertEqual(len(app.exception),0)
            self.assertEqual(len(app.session_state["captures"]),3)
            next(c for c in app.checkbox if c.label.startswith("Include capture 1 ")).uncheck().run()
            self.assertEqual(len(app.exception),0)
            self.assertFalse(app.session_state["selected"][0])
            next(b for b in app.button if b.label=="Add current preview as a manual capture").click().run()
            self.assertEqual(len(app.exception),0)
            self.assertFalse(app.session_state["selected"][0])
            self.assertEqual(len(app.session_state["captures"]),4)

if __name__=="__main__":
    unittest.main()
