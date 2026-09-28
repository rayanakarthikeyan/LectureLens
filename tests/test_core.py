import unittest

from lecturelens.core import parse_transcript, search_lecture


class LectureCoreTests(unittest.TestCase):
    def test_srt_and_vtt_timing(self):
        srt = "1\n00:01:02,500 --> 00:01:04,000\nTree search\n"
        vtt = "WEBVTT\n\n00:02.000 --> 00:03.500\nBalanced nodes\n"
        self.assertEqual(parse_transcript(srt)[0]["start"], 62.5)
        self.assertEqual(parse_transcript(vtt)[0]["end"], 3.5)

    def test_plain_text_does_not_fabricate_timestamps(self):
        segments = parse_transcript("First concept. Second concept.")
        self.assertEqual(len(segments), 2)
        self.assertIsNone(segments[0]["start"])

    def test_search_returns_grounded_passage(self):
        transcript = "1\n00:00:03,000 --> 00:00:06,000\nB-tree search is logarithmic.\n"
        lecture = {"segments": parse_transcript(transcript), "pages": [{"number": 1, "text": "B-tree insertion"}]}
        found = search_lecture(lecture, "logarithmic")
        self.assertEqual(found[0]["start"], 3.0)
        self.assertEqual(found[0]["kind"], "transcript")


if __name__ == "__main__":
    unittest.main()
