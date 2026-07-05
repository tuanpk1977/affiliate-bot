from __future__ import annotations

import re
import unittest

from modules.structured_data_upgrade import (
    AUTHOR_NAME,
    article_schema,
    normalize_upload_date,
    review_rating_from_existing,
    review_schema,
    video_schema,
)


class StructuredDataUpgradeTest(unittest.TestCase):
    def test_article_and_review_author_are_person_objects_with_name(self) -> None:
        article = article_schema(
            canonical="https://smileaireviewhub.com/review/example/",
            headline="Example Review",
            description="Example description",
            image="",
            lang="en",
            section="Software Reviews",
            published="2026-06-18",
            modified="2026-06-18",
        )
        review = review_schema(
            name="Example",
            canonical="https://smileaireviewhub.com/review/example/",
            description="Example review body",
            lang="en",
            software_id="https://smileaireviewhub.com/review/example/#software",
            rating={"ratingValue": 4.5, "bestRating": 5, "worstRating": 1},
        )

        for schema in (article, review):
            author = schema.get("author")
            self.assertIsInstance(author, dict)
            self.assertEqual(author.get("@type"), "Person")
            self.assertEqual(author.get("name"), AUTHOR_NAME)

        self.assertEqual(review["itemReviewed"]["name"], "Example")
        self.assertEqual(review["reviewRating"]["ratingValue"], 4.5)
        self.assertEqual(review["publisher"]["name"], "MS Smile AI Review Hub")

    def test_review_rating_is_only_reused_when_valid(self) -> None:
        valid = [
            {
                "@type": "Product",
                "review": {
                    "@type": "Review",
                    "reviewRating": {
                        "@type": "Rating",
                        "ratingValue": "4.2",
                        "bestRating": "5",
                        "worstRating": "1",
                    },
                },
            }
        ]
        invalid = [
            {
                "@type": "Review",
                "reviewRating": {"@type": "Rating", "ratingValue": "9", "bestRating": "5"},
            }
        ]

        self.assertEqual(
            review_rating_from_existing(valid),
            {"ratingValue": 4.2, "bestRating": 5, "worstRating": 1},
        )
        self.assertIsNone(review_rating_from_existing(invalid))

    def test_video_upload_date_uses_iso_8601_datetime_with_timezone(self) -> None:
        upload_date = normalize_upload_date("2026-06-18")
        self.assertRegex(upload_date, r"^2026-06-18T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")

        schema = video_schema(
            source='<iframe src="https://www.youtube.com/embed/abcDEF12345"></iframe>',
            canonical="https://smileaireviewhub.com/review/example/",
            name="Example Video",
            description="Example description",
            image="",
            modified="2026-06-18",
        )
        self.assertIsNotNone(schema)
        assert schema is not None
        self.assertRegex(str(schema["uploadDate"]), r"^2026-06-18T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}$")
        self.assertIsNotNone(re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}", str(schema["uploadDate"])))


if __name__ == "__main__":
    unittest.main()
