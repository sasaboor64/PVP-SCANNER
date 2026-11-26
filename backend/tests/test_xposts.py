import pytest

from app.xposts import syndication_token, tweet_id_from_url



@pytest.mark.parametrize("url,expected", [
    ("https://x.com/someone/status/1849112312437182717", "1849112312437182717"),
    ("https://twitter.com/a/status/20?s=46", "20"),
    ("https://x.com/i/status/123456", "123456"),
    ("https://x.com/i/web/status/987", "987"),
    ("https://x.com/someone", None),
    ("https://example.com/status/1", None),
    (None, None),
])
def test_tweet_id(url, expected):
    assert tweet_id_from_url(url) == expected


def test_token_matches_javascript(js_tokens):
    for tweet_id, expected in js_tokens:
        assert syndication_token(tweet_id) == expected, tweet_id


# Expected values produced by Node: ((Number(id)/1e15)*Math.PI).toString(36).replace(/(0+|\.)/g, "")
@pytest.fixture
def js_tokens():
    return [["20", "6dq1a2xwd93"],
            ["1", "bhi2ay3f28n"],
            ["1849112312437182717", "4hd5obm8jip"],
            ["1234567890123456789", "2zqic77uqyk"],
            ["1600000000000000000", "3vmjqiybmlu"],
            ["999999999999999999", "2f9lc2ug9mm"],
            ["1790000000000000001", "4c7g8auqyik"],
            ["1000000000000000", "353i5ab8p5f"],
            ["1500000000000000000", "3mwe49oefy"],
            ["804580502864376320", "1y7nwsrxxfc"],
            ["71734299063292072", "69cyhonhjmb"],
            ["1165194731927944704", "2tokf3qp6tp"]]
