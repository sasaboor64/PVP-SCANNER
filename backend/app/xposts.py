"""Text of public X posts via X's syndication endpoint (the one embedded tweets use)."""
import logging
import math
import re
import urllib.parse

from .net import get_json

log = logging.getLogger("pvp.x")
_STATUS_RE = re.compile(r"(?:twitter\.com|x\.com)/(?:[^/?#]+|i(?:/web)?)/status(?:es)?/(\d+)", re.I)
_DIGITS = "0123456789abcdefghijklmnopqrstuvwxyz"


def tweet_id_from_url(url):
    if not url:
        return None
    match = _STATUS_RE.search(url)
    return match.group(1) if match else None


def _js_to_radix36(value):
    """Port of V8's DoubleToRadixCString, i.e. JavaScript's Number.prototype.toString(36)."""
    radix = 36
    integer = math.floor(value)
    fraction = value - integer
    delta = max(0.5 * (math.nextafter(value, math.inf) - value), math.nextafter(0.0, 1.0))
    frac_digits = []
    if fraction >= delta:
        while True:
            fraction *= radix
            delta *= radix
            digit = int(fraction)
            frac_digits.append(digit)
            fraction -= digit
            if fraction > 0.5 or (fraction == 0.5 and (digit & 1)):
                if fraction + delta > 1:
                    # Round up, propagating carries.
                    while True:
                        if not frac_digits:
                            integer += 1
                            break
                        last = frac_digits.pop()
                        if last + 1 < radix:
                            frac_digits.append(last + 1)
                            break
                    break
            if not fraction >= delta:
                break
    int_digits = []
    while True:
        remainder = math.fmod(integer, radix)
        int_digits.append(_DIGITS[int(remainder)])
        integer = (integer - remainder) / radix
        if not integer > 0:
            break
    out = "".join(reversed(int_digits))
    if frac_digits:
        out += "." + "".join(_DIGITS[d] for d in frac_digits)
    return out


def syndication_token(tweet_id):
    """Same token the embed widget sends: ((id / 1e15) * PI).toString(36) without 0s and dots."""
    return re.sub(r"(0+|\.)", "", _js_to_radix36((int(tweet_id) / 1e15) * math.pi))


def fetch_tweet_text(url):
    tweet_id = tweet_id_from_url(url)
    if not tweet_id:
        return None
    endpoint = "https://cdn.syndication.twimg.com/tweet-result?" + urllib.parse.urlencode(
        {"id": tweet_id, "lang": "en", "token": syndication_token(tweet_id)})
    try:
        data = get_json(endpoint, timeout=4, ttl=3600)
    except Exception as exc:
        log.info("X post %s unavailable: %s", tweet_id, exc)
        return None
    if isinstance(data, dict):
        text = data.get("text")
        if isinstance(text, str) and text.strip():
            return text.strip()
    return None
