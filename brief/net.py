"""Shared HTTP session: browser User-Agent, timeouts and simple retries."""
import time

import requests

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36")

_session = requests.Session()
_session.headers.update({"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"})


def get(url, headers=None, params=None, tries=3, timeout=15):
    """GET with retries on network errors and 429/5xx. Raises on final failure."""
    last = None
    for attempt in range(tries):
        try:
            r = _session.get(url, headers=headers, params=params, timeout=timeout)
            if r.status_code == 429 or r.status_code >= 500:
                last = requests.HTTPError(f"HTTP {r.status_code} for {url}")
            else:
                r.raise_for_status()
                return r
        except requests.RequestException as e:
            last = e
        time.sleep(1.5 * (attempt + 1))
    raise last


def post(url, json, headers=None, timeout=30):
    return _session.post(url, json=json, headers=headers, timeout=timeout)
