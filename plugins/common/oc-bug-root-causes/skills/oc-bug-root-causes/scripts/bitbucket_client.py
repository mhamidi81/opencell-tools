#!/usr/bin/env python3
"""Bitbucket Cloud REST transport for /oc-pr-rejection-rate.

Auth reads BITBUCKET_ACCESS_TOKEN (and BITBUCKET_EMAIL) from the environment, never
from the command line, so the token never lands in a shell history or a process list.

Bitbucket accepts two credential types and they use DIFFERENT schemes, so the scheme is
chosen from the token itself rather than assumed:

  ATCTT... repository/workspace Access Token -> `Authorization: Bearer <token>`, no email
  ATATT... Atlassian API token               -> Basic <base64 email:token>

Sending either one the other way returns 401. Assuming Basic — which this module did
originally, because the workspace was documented as using ATATT tokens — makes the whole
plugin 401 against an ATCTT token while reporting the opposite cause.

429 and 503 are retried with a linear backoff; every other status raises with the first
200 bytes of the body. Failing loudly matters here: a swallowed error would report zero
rejected PRs, and zero is indistinguishable from a good week unless it raises.

Every request is a GET. This module has no write path by design — see the spec's D9.
"""
import base64
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://api.bitbucket.org/2.0"
MAX_ATTEMPTS = 5
RETRY_STATUS = (429, 503)


class BitbucketError(RuntimeError):
    """Any non-retryable failure talking to Bitbucket."""


class MissingToken(BitbucketError):
    """BITBUCKET_EMAIL or BITBUCKET_ACCESS_TOKEN is not in the environment."""


ACCESS_TOKEN_PREFIX = "ATCTT"

SETUP_HELP = (
    "BITBUCKET_ACCESS_TOKEN must be set. Either credential type works:\n"
    "  a repository/workspace Access Token (ATCTT...), used alone:\n"
    "    export BITBUCKET_ACCESS_TOKEN='ATCTT...'\n"
    "  or an Atlassian API token (ATATT...) from "
    "https://id.atlassian.com/manage/api-tokens, which also needs an email:\n"
    "    export BITBUCKET_EMAIL='you@opencellsoft.com'\n"
    "    export BITBUCKET_ACCESS_TOKEN='ATATT...'"
)


def auth_header(env=None):
    """Build the Authorization header the token's own type requires.

    The scheme is keyed off the token prefix, not off whether an email happens to be
    set: BITBUCKET_EMAIL is commonly exported for other tooling, so "email present
    therefore Basic" picks the wrong scheme for an ATCTT token and 401s.
    """
    env = os.environ if env is None else env
    token = env.get("BITBUCKET_ACCESS_TOKEN")
    if not token:
        raise MissingToken(SETUP_HELP)
    if token.startswith(ACCESS_TOKEN_PREFIX):
        return "Bearer " + token
    email = env.get("BITBUCKET_EMAIL")
    if not email:
        raise MissingToken(
            "BITBUCKET_ACCESS_TOKEN looks like an Atlassian API token, which "
            "authenticates as email:token, but BITBUCKET_EMAIL is not set.\n\n" + SETUP_HELP
        )
    return "Basic " + base64.b64encode(f"{email}:{token}".encode()).decode()


def encode_params(params):
    """Encode a query string, repeating any list-valued key.

    Bitbucket selects several PR states by repeating `state`, and percent-encoding
    matters: a raw '+' in an ISO offset decodes server-side as a space, which silently
    breaks the created_on filter. urlencode's default quote_plus renders '+' as %2B.
    """
    pairs = []
    for key, value in (params or {}).items():
        if isinstance(value, (list, tuple)):
            pairs.extend((key, str(v)) for v in value)
        else:
            pairs.append((key, str(value)))
    return urllib.parse.urlencode(pairs)


class BitbucketClient:
    def __init__(self, opener=None, env=None, sleep=time.sleep, base=BASE):
        self._open = opener or urllib.request.urlopen
        self._auth = auth_header(env)
        self._sleep = sleep
        self._base = base

    def _url(self, path, params=None):
        url = self._base + path
        query = encode_params(params)
        return f"{url}?{query}" if query else url

    def _request(self, url, label):
        for attempt in range(MAX_ATTEMPTS):
            request = urllib.request.Request(
                url,
                method="GET",
                headers={"Authorization": self._auth, "Accept": "application/json"},
            )
            try:
                with self._open(request, timeout=60) as response:
                    raw = response.read()
                    return json.loads(raw) if raw else {}
            except urllib.error.HTTPError as ex:
                if ex.code in RETRY_STATUS and attempt < MAX_ATTEMPTS - 1:
                    self._sleep(2 * (attempt + 1))
                    continue
                detail = ex.read()[:200].decode("utf-8", "replace")
                if ex.code == 401:
                    detail += (
                        " — the credential was rejected. An ATCTT... repository/workspace "
                        "Access Token must be sent as `Authorization: Bearer` with no "
                        "email; an ATATT... Atlassian API token must be sent as Basic "
                        "email:token. Check BITBUCKET_ACCESS_TOKEN's prefix and that "
                        "BITBUCKET_EMAIL is set only for the ATATT form."
                    )
                raise BitbucketError(f"HTTP {ex.code} on GET {label}: {detail}") from ex
        raise BitbucketError(f"retries exhausted on GET {label}")

    def get(self, path, params=None):
        return self._request(self._url(path, params), path)

    def paginate(self, path, params=None):
        """Yield every element of `values`, following `next` to the last page.

        Bitbucket returns `next` as an absolute URL that already carries the query,
        so it is requested verbatim rather than rebuilt.
        """
        url = self._url(path, params)
        while url:
            page = self._request(url, path)
            yield from page.get("values") or []
            url = page.get("next")
