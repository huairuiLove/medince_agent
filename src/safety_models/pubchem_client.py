from __future__ import annotations

import logging
import time
import urllib.parse

import httpx

logger = logging.getLogger(__name__)

PUBCHEM_PROPERTY_URL = (
    "https://pubchem.ncbi.nlm.nih.gov/rest/pug/compound/name/{name}/property/"
    "ConnectivitySMILES,IsomericSMILES/JSON"
)


class PubChemClient:
    """Fetch drug SMILES from PubChem PUG REST (NCBI)."""

    def __init__(
        self,
        *,
        enabled: bool = True,
        timeout: float = 10.0,
        rate_limit_seconds: float = 0.25,
    ) -> None:
        self.enabled = enabled
        self.timeout = timeout
        self.rate_limit_seconds = rate_limit_seconds
        self._last_request_at = 0.0

    def _throttle(self) -> None:
        elapsed = time.monotonic() - self._last_request_at
        if elapsed < self.rate_limit_seconds:
            time.sleep(self.rate_limit_seconds - elapsed)
        self._last_request_at = time.monotonic()

    def fetch_smiles(self, query_name: str) -> str | None:
        if not self.enabled or not query_name.strip():
            return None
        encoded = urllib.parse.quote(query_name.strip(), safe="")
        url = PUBCHEM_PROPERTY_URL.format(name=encoded)
        self._throttle()
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.get(url)
            if response.status_code == 404:
                return None
            response.raise_for_status()
            props = response.json().get("PropertyTable", {}).get("Properties", [])
            if not props:
                return None
            row = props[0]
            return row.get("ConnectivitySMILES") or row.get("IsomericSMILES") or None
        except Exception as exc:
            logger.warning("PubChem lookup failed for %s: %s", query_name, exc)
            return None
