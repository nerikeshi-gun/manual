"""作業指示の「守ること」を強制するHTTPクライアント。

- robots.txt を RFC 9309 準拠（* と $ のワイルドカード、最長一致）で判定する。
  urllib.robotparser はワイルドカードを解釈しないので使わない。
- 同一ホストへのリクエストは1秒に1回まで。
- PDFの本体GETを拒否する（生存確認は head() / head_or_range()）。
"""
from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

import requests

USER_AGENT = "manual-url-collector/0.1 (+contact@grewai.jp)"
ROBOTS_TOKEN = "manual-url-collector"
MIN_INTERVAL = 1.05  # 1秒に1回を確実に下回らないよう僅かに余裕を持たせる


class RobotsDisallowed(Exception):
    pass


class PdfBodyRefused(Exception):
    pass


def _rule_to_regex(path: str) -> re.Pattern:
    anchored = path.endswith("$")
    if anchored:
        path = path[:-1]
    body = ".*".join(re.escape(p) for p in path.split("*"))
    return re.compile("^" + body + ("$" if anchored else ""))


@dataclass
class Robots:
    status: int | None
    rules: list[tuple[bool, str, re.Pattern]] = field(default_factory=list)
    sitemaps: list[str] = field(default_factory=list)
    deny_all: bool = False

    def allowed(self, path_and_query: str) -> bool:
        if self.deny_all:
            return False
        best: tuple[int, bool] | None = None
        for allow, raw, rx in self.rules:
            if rx.match(path_and_query):
                key = (len(raw), allow)  # 最長一致、同長なら allow 優先
                if best is None or key > best:
                    best = key
        return True if best is None else best[1]


def parse_robots(text: str, status: int | None) -> Robots:
    groups: list[tuple[list[str], list[tuple[bool, str]]]] = []
    sitemaps: list[str] = []
    agents: list[str] = []
    rules: list[tuple[bool, str]] = []
    in_rules = False
    for line in text.splitlines():
        line = line.split("#", 1)[0].strip()
        if ":" not in line:
            continue
        key, value = (s.strip() for s in line.split(":", 1))
        key = key.lower()
        if key == "sitemap":
            sitemaps.append(value)
        elif key == "user-agent":
            if in_rules:
                groups.append((agents, rules))
                agents, rules, in_rules = [], [], False
            agents.append(value.lower())
        elif key in ("allow", "disallow"):
            in_rules = True
            if value:
                rules.append((key == "allow", value))
    if agents:
        groups.append((agents, rules))

    specific = [r for a, r in groups if any(x != "*" and x in ROBOTS_TOKEN for x in a)]
    chosen = specific or [r for a, r in groups if "*" in a]
    merged = [rule for group in chosen for rule in group]
    return Robots(
        status=status,
        rules=[(allow, raw, _rule_to_regex(raw)) for allow, raw in merged],
        sitemaps=sitemaps,
    )


class PoliteClient:
    def __init__(self, log_path: Path | None = None, timeout: float = 30.0):
        self.session = requests.Session()
        self.session.headers["User-Agent"] = USER_AGENT
        self.session.headers["Accept-Language"] = "ja"
        self.timeout = timeout
        self._last: dict[str, float] = {}
        self._robots: dict[str, Robots] = {}
        self._locks: dict[str, threading.Lock] = {}
        self._guard = threading.Lock()
        self.log_path = log_path
        if log_path:
            log_path.parent.mkdir(parents=True, exist_ok=True)

    def _host_lock(self, host: str) -> threading.Lock:
        with self._guard:
            return self._locks.setdefault(host, threading.Lock())

    def _wait(self, host: str) -> None:
        elapsed = time.monotonic() - self._last.get(host, 0.0)
        if elapsed < MIN_INTERVAL:
            time.sleep(MIN_INTERVAL - elapsed)
        self._last[host] = time.monotonic()

    def _log(self, method: str, url: str, status: object) -> None:
        if self.log_path:
            with self.log_path.open("a", encoding="utf-8") as f:
                f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{method}\t{status}\t{url}\n")

    def _send(self, method: str, url: str, **kw) -> requests.Response:
        host = urlsplit(url).netloc.lower()
        with self._host_lock(host):
            self._wait(host)
            kw.setdefault("timeout", self.timeout)
            try:
                resp = self.session.request(method, url, **kw)
            except requests.RequestException as exc:
                self._log(method, url, type(exc).__name__)
                raise
            self._log(method, url, resp.status_code)
            return resp

    def robots(self, url: str) -> Robots:
        parts = urlsplit(url)
        host = parts.netloc.lower()
        if host not in self._robots:
            robots_url = f"{parts.scheme}://{host}/robots.txt"
            try:
                resp = self._send("GET", robots_url, allow_redirects=True)
            except requests.RequestException:
                self._robots[host] = Robots(status=None, deny_all=True)
                return self._robots[host]
            if resp.status_code == 200:
                self._robots[host] = parse_robots(resp.text, 200)
            elif resp.status_code in (401, 403) or resp.status_code >= 500:
                # 明示的な拒否・障害時は保守的に全面不可として扱う
                self._robots[host] = Robots(status=resp.status_code, deny_all=True)
            else:
                self._robots[host] = Robots(status=resp.status_code)
        return self._robots[host]

    def can_fetch(self, url: str) -> bool:
        parts = urlsplit(url)
        target = parts.path or "/"
        if parts.query:
            target += "?" + parts.query
        return self.robots(url).allowed(target)

    def _check(self, url: str) -> None:
        if not self.can_fetch(url):
            raise RobotsDisallowed(url)

    def get(self, url: str, **kw) -> requests.Response:
        self._check(url)
        if urlsplit(url).path.lower().endswith(".pdf"):
            headers = kw.get("headers") or {}
            if "Range" not in headers:
                raise PdfBodyRefused(url)
        return self._send("GET", url, **kw)

    def post(self, url: str, **kw) -> requests.Response:
        self._check(url)
        return self._send("POST", url, **kw)

    def head(self, url: str, **kw) -> requests.Response:
        self._check(url)
        kw.setdefault("allow_redirects", True)
        return self._send("HEAD", url, **kw)

    def head_or_range(self, url: str) -> requests.Response:
        """HEADで確認し、HEADが拒否された場合のみ先頭だけをRange付きGETで取る。"""
        resp = self.head(url)
        if resp.status_code in (403, 405, 501):
            self._check(url)
            ranged = self._send(
                "GET", url, headers={"Range": "bytes=0-0"}, stream=True, allow_redirects=True
            )
            ranged.close()
            return ranged
        return resp
