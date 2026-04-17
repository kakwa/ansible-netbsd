"""Certbot OVH authenticator plugin (OVH REST via stdlib; no python-ovh package)."""
from __future__ import annotations

import configparser
import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Any, Dict, Optional

from acme import challenges

from certbot import errors
from certbot.plugins import dns_common

logger = logging.getLogger(__name__)

INSTRUCTIONS = (
    "To use certbot-dns-ovh, configure credentials as described at "
    "https://api.ovh.com/g934.first_step_with_api"
    "and add the necessary permissions for OVH access on /domain and /domain/* for all HTTP Verbs"
)

# Same mapping as python-ovh ovh.client.ENDPOINTS (subset + common variants).
ENDPOINTS = {
    "ovh-eu": "https://eu.api.ovh.com/1.0",
    "ovh-us": "https://api.us.ovhcloud.com/1.0",
    "ovh-ca": "https://ca.api.ovh.com/1.0",
    "kimsufi-eu": "https://eu.api.kimsufi.com/1.0",
    "kimsufi-ca": "https://ca.api.kimsufi.com/1.0",
    "soyoustart-eu": "https://eu.api.soyoustart.com/1.0",
    "soyoustart-ca": "https://ca.api.soyoustart.com/1.0",
}

_OVH_CONF_PATHS = (
    "/root/.ovh.conf",
    os.path.expanduser("~/.ovh.conf"),
    "/etc/ovh.conf",
)


def _env(name: str) -> Optional[str]:
    return os.environ.get(name)


def _cfg_chain(parser: configparser.RawConfigParser, endpoint: str, key: str) -> Optional[str]:
    """Match python-ovh: env OVH_KEY, then [endpoint], then [default]."""
    env_name = "OVH_" + key.upper()
    v = _env(env_name)
    if v is not None:
        return v
    if parser.has_option(endpoint, key):
        return parser.get(endpoint, key)
    if parser.has_option("default", key):
        return parser.get("default", key)
    return None


def _load_ovh_ini() -> configparser.RawConfigParser:
    parser = configparser.RawConfigParser()
    for path in _OVH_CONF_PATHS:
        if path and os.path.isfile(path):
            parser.read(path)
            break
    return parser


class _OvhRestClient:
    """Minimal OVH API v1 client: consumer-key signing + urllib only."""

    def __init__(self) -> None:
        self._parser = _load_ovh_ini()
        endpoint = _env("OVH_ENDPOINT") or (
            self._parser.get("default", "endpoint") if self._parser.has_option("default", "endpoint") else None
        )
        if not endpoint:
            raise errors.PluginError("OVH endpoint missing: set OVH_ENDPOINT or [default] endpoint= in .ovh.conf")
        try:
            self._base = ENDPOINTS[endpoint]
        except KeyError as exc:
            raise errors.PluginError("Unknown OVH endpoint %r; known: %s" % (endpoint, ", ".join(sorted(ENDPOINTS)))) from exc

        self._application_key = _cfg_chain(self._parser, endpoint, "application_key")
        self._application_secret = _cfg_chain(self._parser, endpoint, "application_secret")
        self._consumer_key = _cfg_chain(self._parser, endpoint, "consumer_key")
        if not all((self._application_key, self._application_secret, self._consumer_key)):
            raise errors.PluginError(
                "OVH credentials incomplete: need application_key, application_secret, consumer_key "
                "(env OVH_* or [%s]/[default] in .ovh.conf)" % endpoint
            )
        self._time_delta: Optional[int] = None

    def _url(self, path: str) -> str:
        if not path.startswith("/"):
            path = "/" + path
        return self._base + path

    def _server_time_delta(self) -> int:
        if self._time_delta is not None:
            return self._time_delta
        url = self._url("/auth/time")
        req = urllib.request.Request(url, method="GET")
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                body = resp.read().decode("utf-8").strip()
        except urllib.error.HTTPError as exc:
            raise errors.PluginError("OVH /auth/time HTTP error: %s" % exc) from exc
        except urllib.error.URLError as exc:
            raise errors.PluginError("OVH /auth/time network error: %s" % exc) from exc
        try:
            server_time = int(body)
        except ValueError as exc:
            raise errors.PluginError("OVH /auth/time invalid response: %r" % body) from exc
        self._time_delta = server_time - int(time.time())
        return self._time_delta

    def _sign(self, method: str, full_url: str, body: str) -> Dict[str, str]:
        now = str(int(time.time()) + self._server_time_delta())
        to_sign = "+".join(
            [
                self._application_secret,
                self._consumer_key,
                method.upper(),
                full_url,
                body,
                now,
            ]
        )
        digest = hashlib.sha1(to_sign.encode("utf-8")).hexdigest()
        return {
            "X-Ovh-Consumer": self._consumer_key,
            "X-Ovh-Timestamp": now,
            "X-Ovh-Signature": "$1$" + digest,
            "X-Ovh-Application": self._application_key,
        }

    def request(self, method: str, path: str, payload: Optional[Dict[str, Any]] = None, *, need_auth: bool = True) -> Any:
        full_url = self._url(path)
        body_str = ""
        headers: Dict[str, str] = {}
        data: Optional[bytes] = None
        if payload is not None:
            headers["Content-Type"] = "application/json"
            body_str = json.dumps(payload, separators=(",", ":"))
            data = body_str.encode("utf-8")
        if need_auth:
            headers.update(self._sign(method, full_url, body_str))

        req = urllib.request.Request(full_url, data=data, headers=headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=180) as resp:
                status = resp.getcode()
                raw = resp.read()
        except urllib.error.HTTPError as exc:
            try:
                detail = exc.read().decode("utf-8")
            except Exception:  # pylint: disable=broad-except
                detail = str(exc)
            raise errors.PluginError("OVH API HTTP %s %s: %s" % (method, path, detail)) from exc
        except urllib.error.URLError as exc:
            raise errors.PluginError("OVH API request failed %s %s: %s" % (method, path, exc)) from exc

        if status == 204 or not raw:
            return None
        try:
            return json.loads(raw.decode("utf-8"))
        except ValueError as exc:
            raise errors.PluginError("OVH API invalid JSON for %s %s" % (method, path)) from exc

    def post(self, path: str, **kwargs: Any) -> Any:
        payload = kwargs if kwargs else None
        return self.request("POST", path, payload, need_auth=True)

    def delete(self, path: str) -> Any:
        return self.request("DELETE", path, None, need_auth=True)


class Authenticator(dns_common.DNSAuthenticator):
    """OVH Authenticator: DNS-01 via OVH REST (no third-party OVH SDK)."""

    description = ("Obtain certificates using a DNS TXT record (if you are using OVH DNS).")

    def __init__(self, *args, **kwargs):
        super(Authenticator, self).__init__(*args, **kwargs)
        self.client = _OvhRestClient()
        self.responses = {}

    @classmethod
    def add_parser_arguments(cls, add):  # pylint: disable=arguments-differ
        super(Authenticator, cls).add_parser_arguments(add, default_propagation_seconds=60)

    def more_info(self):  # pylint: disable=missing-docstring,no-self-use
        return "Solve a DNS01 challenge using OVH DNS"

    def get_chall_pref(self, unused_domain):  # pylint: disable=missing-docstring,no-self-use
        return [challenges.DNS01]

    def _setup_credentials(self):
        """
        Credentials: /root/.ovh.conf (or ~/.ovh.conf, /etc/ovh.conf) and/or env vars
        OVH_ENDPOINT, OVH_APPLICATION_KEY, OVH_APPLICATION_SECRET, OVH_CONSUMER_KEY.
        INI layout matches python-ovh (see ovh.config).
        """
        pass

    def _perform(self, domain, validation_domain_name, validation):  # pylint: disable=missing-docstring
        ndd = domain
        token = "\"" + validation + "\""

        ndd = ndd.split(".")
        basedomain = ndd[len(ndd) - 2] + "." + ndd[len(ndd) - 1]
        subdomain = "_acme-challenge"
        if len(ndd) > 2:
            subdomain += "."
            for i in range(0, len(ndd) - 2):
                if i == len(ndd) - 3:
                    subdomain += ndd[i]
                else:
                    subdomain += ndd[i] + "."
        id_record = self.client.post(
            "/domain/zone/%s/record" % basedomain,
            fieldType="TXT",
            subDomain=subdomain,
            ttl=0,
            target=token,
        )
        self.responses[validation] = id_record["id"]
        self.client.post("/domain/zone/%s/refresh" % basedomain)
        time.sleep(5)
        return id_record["id"]

    def _cleanup(self, domain, validation_domain_name, validation):
        ndd = domain
        ndd = ndd.split(".")
        basedomain = ndd[len(ndd) - 2] + "." + ndd[len(ndd) - 1]
        self.client.delete("/domain/zone/%s/record/%s" % (basedomain, self.responses[validation]))
        self.responses.pop(validation, None)
        self.client.post("/domain/zone/%s/refresh" % basedomain)
