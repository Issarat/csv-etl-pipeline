import pandas as pd
import pytest

from src.transform import transform_order_reviews


REVIEW_ID = "7bc2406110b926393aa56f80a40eba40"
ORDER_ID = "73fc7af87114b39712e6da79b0a377eb"


def review_frame(
    score: object = "5",
    review_id: object = REVIEW_ID,
    order_id: object = ORDER_ID,
) -> pd.DataFrame:
    return pd.DataFrame([{
        "review_id": review_id,
        "order_id": order_id,
        "review_score": score,
        "review_comment_title": None,
        "review_comment_message": None,
        "review_creation_date": "2018-01-18 00:00:00",
        "review_answer_timestamp": "2018-01-18 21:46:59",
    }])


def test_valid_review_score_is_clean():
    clean, rejected = transform_order_reviews(review_frame())

    assert len(clean) == 1
    assert rejected.empty
    assert clean["review_score"].tolist() == [5]
    assert "order_review_id" in clean.columns
    assert clean["order_review_id"].tolist() == [
        "7bc24061-10b9-2639-3aa5-6f80a40eba40"
    ]
    assert clean["order_id"].tolist() == [
        "73fc7af8-7114-b397-12e6-da79b0a377eb"
    ]


@pytest.mark.parametrize("score", ["0", "6", "1.5"])
def test_out_of_range_review_score_is_rejected(score):
    clean, rejected = transform_order_reviews(review_frame(score))

    assert clean.empty
    assert rejected["rejection_reason"].tolist() == ["invalid_review_score"]


@pytest.mark.parametrize(
    ("column", "reason", "raw_column"),
    [
        ("review_id", "invalid_order_review_id", "raw_order_review_id"),
        ("order_id", "invalid_order_id", "raw_order_id"),
    ],
)
def test_invalid_uuid_is_rejected(column, reason, raw_column):
    reviews = review_frame()
    reviews.loc[0, column] = "not-a-uuid"

    clean, rejected = transform_order_reviews(reviews)

    assert clean.empty
    assert rejected["rejection_reason"].tolist() == [reason]
    assert rejected[raw_column].tolist() == ["not-a-uuid"]


def test_uuid_formats_normalize_before_duplicate_detection():
    reviews = pd.concat([review_frame(), review_frame()], ignore_index=True)
    reviews.loc[1, "review_id"] = "7BC24061-10B9-2639-3AA5-6F80A40EBA40"
    reviews.loc[1, "order_id"] = "73FC7AF8-7114-B397-12E6-DA79B0A377EB"

    clean, rejected = transform_order_reviews(reviews)

    assert clean.empty
    assert rejected["rejection_reason"].tolist() == [
        "duplicate_order_review_key",
        "duplicate_order_review_key",
    ]
