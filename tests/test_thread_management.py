import unittest

from cogs.utils.thread_management import _build_mention_batches


class BuildMentionBatchesTest(unittest.TestCase):
    def test_keeps_every_batch_within_discord_limit(self):
        mentions = [f"<@{10**18 + index}>" for index in range(200)]
        suffix = " スレッドが作成されました"

        batches = _build_mention_batches(mentions, suffix.strip())

        self.assertEqual(
            " ".join(batch.removesuffix(suffix) for batch in batches),
            " ".join(mentions),
        )
        self.assertTrue(all(len(batch) <= 2000 for batch in batches))


if __name__ == "__main__":
    unittest.main()
