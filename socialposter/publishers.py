"""Platform adapters. Each publishes the exact text it is given; nothing is rewritten or truncated."""
from __future__ import annotations

import os
import re
import time

import requests

TIMEOUT = 60


class PublishError(RuntimeError):
    pass


def _need(name: str) -> str:
    v = os.environ.get(name)
    if not v:
        raise PublishError(f"missing credential: {name}")
    return v


def _check(r: requests.Response) -> dict:
    if not r.ok:
        raise PublishError(f"{r.request.method} {r.url.split('?')[0]} -> {r.status_code}: {r.text[:300]}")
    return r.json() if r.content else {}


def _graph() -> str:
    return f"https://graph.facebook.com/{os.environ.get('GRAPH_API_VERSION', 'v21.0')}"


class Facebook:
    name = "facebook"

    def publish(self, text: str, media: dict | None) -> dict:
        page, token = _need("FACEBOOK_PAGE_ID"), _need("FACEBOOK_PAGE_ACCESS_TOKEN")
        if media:
            data = {"url": media["url"], "caption": text, "access_token": token}
            res = _check(requests.post(f"{_graph()}/{page}/photos", data=data, timeout=TIMEOUT))
            pid = res.get("post_id") or res.get("id")
        else:
            res = _check(requests.post(f"{_graph()}/{page}/feed", data={"message": text, "access_token": token}, timeout=TIMEOUT))
            pid = res["id"]
        return {"id": pid, "url": f"https://www.facebook.com/{pid}"}


class Instagram:
    name = "instagram"

    def publish(self, text: str, media: dict | None) -> dict:
        ig, token = _need("INSTAGRAM_BUSINESS_ACCOUNT_ID"), _need("INSTAGRAM_ACCESS_TOKEN")
        data = {"caption": text, "access_token": token}
        if media["type"] == "video":
            data.update(media_type="REELS", video_url=media["url"])
        else:
            data["image_url"] = media["url"]
        container = _check(requests.post(f"{_graph()}/{ig}/media", data=data, timeout=TIMEOUT))["id"]
        for _ in range(40):  # wait until Instagram has processed the media
            st = _check(requests.get(f"{_graph()}/{container}", params={"fields": "status_code", "access_token": token}, timeout=TIMEOUT))
            if st.get("status_code") == "FINISHED":
                break
            if st.get("status_code") in ("ERROR", "EXPIRED"):
                raise PublishError(f"instagram media processing failed: {st}")
            time.sleep(5)
        else:
            raise PublishError("instagram media processing timed out")
        pub = _check(requests.post(f"{_graph()}/{ig}/media_publish", data={"creation_id": container, "access_token": token}, timeout=TIMEOUT))
        info = _check(requests.get(f"{_graph()}/{pub['id']}", params={"fields": "permalink", "access_token": token}, timeout=TIMEOUT))
        return {"id": pub["id"], "url": info.get("permalink")}


class LinkedIn:
    name = "linkedin"
    API = "https://api.linkedin.com/rest"

    def _headers(self) -> dict:
        return {
            "Authorization": f"Bearer {_need('LINKEDIN_ACCESS_TOKEN')}",
            "LinkedIn-Version": os.environ.get("LINKEDIN_VERSION", "202510"),
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json",
        }

    @staticmethod
    def escape(text: str) -> str:
        # LinkedIn "little text" treats these as markup and would drop or mangle them. Escaping makes
        # them display literally, so the post reads exactly as written. '#' is left so hashtags work.
        return re.sub(r"([\\|{}@\[\]()<>*_~])", r"\\\1", text)

    def publish(self, text: str, media: dict | None) -> dict:
        author = f"urn:li:person:{_need('LINKEDIN_PERSON_ID')}"
        body = {
            "author": author,
            "commentary": self.escape(text),
            "visibility": "PUBLIC",
            "distribution": {"feedDistribution": "MAIN_FEED", "targetEntities": [], "thirdPartyDistributionChannels": []},
            "lifecycleState": "PUBLISHED",
            "isReshareDisabledByAuthor": False,
        }
        if media:
            init = _check(requests.post(f"{self.API}/images?action=initializeUpload", headers=self._headers(),
                                        json={"initializeUploadRequest": {"owner": author}}, timeout=TIMEOUT))["value"]
            img = requests.get(media["url"], timeout=TIMEOUT)
            if not img.ok:
                raise PublishError(f"could not fetch media {media['url']}: {img.status_code}")
            up = requests.put(init["uploadUrl"], data=img.content, headers={"Authorization": self._headers()["Authorization"]}, timeout=TIMEOUT)
            if not up.ok:
                raise PublishError(f"linkedin image upload failed: {up.status_code}")
            body["content"] = {"media": {"id": init["image"]}}
        r = requests.post(f"{self.API}/posts", headers=self._headers(), json=body, timeout=TIMEOUT)
        _check(r)
        urn = r.headers.get("x-restli-id", "")
        return {"id": urn, "url": f"https://www.linkedin.com/feed/update/{urn}" if urn else None}


def default_publishers() -> dict:
    return {p.name: p for p in (Instagram(), LinkedIn(), Facebook())}
