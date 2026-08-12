"""Small S3-compatible SigV4 object transport."""

from __future__ import annotations

from datetime import UTC, datetime
import hashlib
import hmac
from pathlib import Path
from urllib.parse import quote, urlencode, urlsplit
import urllib.error
import urllib.request


class ObjectNotFound(Exception):
    pass


class ObjectStore:
    def __init__(self, endpoint: str, bucket: str, region: str, access_key: str, secret_key: str, *, opener=urllib.request.urlopen):
        self.endpoint = endpoint.rstrip("/")
        self.bucket = bucket
        self.region = region
        self.access_key = access_key
        self.secret_key = secret_key
        self.opener = opener

    def _key(self, date: str) -> bytes:
        key = hmac.new(("AWS4" + self.secret_key).encode(), date.encode(), hashlib.sha256).digest()
        key = hmac.new(key, self.region.encode(), hashlib.sha256).digest()
        key = hmac.new(key, b"s3", hashlib.sha256).digest()
        return hmac.new(key, b"aws4_request", hashlib.sha256).digest()

    def presign(self, method: str, object_key: str, expires: int, *, now: datetime | None = None) -> str:
        now = now or datetime.now(UTC)
        timestamp, date = now.strftime("%Y%m%dT%H%M%SZ"), now.strftime("%Y%m%d")
        parsed = urlsplit(self.endpoint)
        path = f"/{quote(self.bucket, safe='')}/{quote(object_key, safe='/')}"
        scope = f"{date}/{self.region}/s3/aws4_request"
        params = {
            "X-Amz-Algorithm": "AWS4-HMAC-SHA256", "X-Amz-Credential": f"{self.access_key}/{scope}",
            "X-Amz-Date": timestamp, "X-Amz-Expires": str(expires), "X-Amz-SignedHeaders": "host",
        }
        query = urlencode(sorted(params.items()), quote_via=quote)
        canonical = f"{method}\n{path}\n{query}\nhost:{parsed.netloc}\n\nhost\nUNSIGNED-PAYLOAD"
        string = f"AWS4-HMAC-SHA256\n{timestamp}\n{scope}\n{hashlib.sha256(canonical.encode()).hexdigest()}"
        params["X-Amz-Signature"] = hmac.new(self._key(date), string.encode(), hashlib.sha256).hexdigest()
        return f"{self.endpoint}{path}?{urlencode(sorted(params.items()), quote_via=quote)}"

    def _request(self, method: str, object_key: str, data: bytes | None = None) -> bytes:
        url = self.presign(method, object_key, 300)
        try:
            with self.opener(urllib.request.Request(url, data=data, method=method), timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                raise ObjectNotFound(object_key) from exc
            raise

    def upload(self, object_key: str, path: Path) -> None:
        self._request("PUT", object_key, path.read_bytes())

    def download(self, object_key: str) -> bytes:
        return self._request("GET", object_key)

    def exists(self, object_key: str) -> bool:
        try:
            self._request("HEAD", object_key)
            return True
        except ObjectNotFound:
            return False

    def delete(self, object_key: str) -> None:
        try:
            self._request("DELETE", object_key)
        except ObjectNotFound:
            pass
