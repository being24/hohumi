import unittest

from cogs.thread_keeper import ThreadKeeper


class StripEmojisTest(unittest.TestCase):
    def test_strips_emojis_that_break_masked_links(self):
        cases = {
            "⭐テーマレギュ細部検討261113": "テーマレギュ細部検討261113",
            "⏰告知": "告知",
            "📚雑談": "雑談",
            "❤️好き": "好き",
            "‼️注意": "注意",
            "1️⃣一番": "1一番",
            "<:foo:123>名前": "名前",
        }
        for name, expected in cases.items():
            with self.subTest(name=name):
                self.assertEqual(ThreadKeeper._strip_emojis(name), expected)


if __name__ == "__main__":
    unittest.main()
