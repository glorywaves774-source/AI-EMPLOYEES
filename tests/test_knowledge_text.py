import unittest
from app.knowledge.services import chunk_text, extract_document_text

class KnowledgeTextTests(unittest.TestCase):
    def test_chunk_text_keeps_content_and_limits_chunk_size(self):
        source = ("Quarterly business policy and procedure.\n" * 180)
        chunks = chunk_text(source, size=300, overlap=40)
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(0 < len(chunk) <= 300 for chunk in chunks))

    def test_rejects_binary_disguised_as_text(self):
        with self.assertRaises(ValueError):
            extract_document_text("policy.txt", b"bad\x00content")

    def test_extracts_utf8_text(self):
        mime, text = extract_document_text("policy.txt", "Staff handbook".encode("utf-8"))
        self.assertEqual(mime, "text/plain")
        self.assertEqual(text, "Staff handbook")

if __name__ == "__main__":
    unittest.main()
