import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

BASE_URL = "https://api.kickbase.com/v4"

_session = requests.Session()
_retries = Retry(
    total=5,
    connect=5,
    read=5,
    status=5,
    backoff_factor=1,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=frozenset(["HEAD", "GET", "OPTIONS"]),
    raise_on_status=False,
)
_adapter = HTTPAdapter(max_retries=_retries)
_session.mount("https://", _adapter)
_session.mount("http://", _adapter)


def get_json_with_token(url, token):
    """Fetch JSON data from a given URL using token for authorization."""

    headers = {"Authorization": f"Bearer {token}"}
    resp = _session.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.json()
