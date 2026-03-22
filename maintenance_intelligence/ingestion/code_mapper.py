"""CMMS code mapper — translates SAP PM / Maximo codes to ISO 14224 canonical codes.

Uses the sap_failure_code_map and maximo_failure_code_map tables.
Falls back to a configurable default when no mapping exists.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import psycopg2

from maintenance_intelligence.runner.config import Settings


class CodeMapper:
    """Translate source-system failure codes to ISO 14224 canonical codes."""

    def __init__(self, conn=None, settings: Optional[Settings] = None):
        self._conn = conn
        self._settings = settings or Settings()
        self._cache: Dict[str, Dict[str, str]] = {}

    def _get_conn(self):
        if self._conn:
            return self._conn
        return psycopg2.connect(self._settings.pg_dsn)

    def _load_map(self, table: str) -> Dict[str, str]:
        cache_key = table
        if cache_key in self._cache:
            return self._cache[cache_key]
        conn = self._get_conn()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    f"SELECT source_domain, source_code, iso_concept, iso_standard_code FROM {table}"
                )
                mapping = {}
                for row in cur.fetchall():
                    domain, code, concept, iso_code = row
                    key = f"{domain}:{code}".upper()
                    mapping[key] = iso_code.upper()
                self._cache[cache_key] = mapping
                return mapping
        finally:
            if not self._conn:
                conn.close()

    def map_sap_code(
        self, domain: str, source_code: str, fallback: Optional[str] = None
    ) -> Optional[str]:
        """Map a SAP PM catalog code to its ISO 14224 equivalent.

        Args:
            domain: SAP catalog type (OBJECT_PART, DAMAGE, CAUSE, ACTIVITY)
            source_code: SAP catalog code value
            fallback: returned if no mapping exists
        """
        mapping = self._load_map("sap_failure_code_map")
        key = f"{domain}:{source_code}".upper()
        return mapping.get(key, fallback)

    def map_maximo_code(
        self, domain: str, source_code: str, fallback: Optional[str] = None
    ) -> Optional[str]:
        """Map a Maximo Failure Class code to its ISO 14224 equivalent.

        Args:
            domain: Maximo domain (PROBLEM, CAUSE, REMEDY)
            source_code: Maximo failure code value
            fallback: returned if no mapping exists
        """
        mapping = self._load_map("maximo_failure_code_map")
        key = f"{domain}:{source_code}".upper()
        return mapping.get(key, fallback)

    def map_codes(
        self, source_system: str, codes: Dict[str, str]
    ) -> Dict[str, Optional[str]]:
        """Batch-map a dict of {domain: source_code} for a given source system.

        Returns: {domain: iso_standard_code or None}
        """
        mapper = self.map_sap_code if source_system.upper() == "SAP" else self.map_maximo_code
        return {domain: mapper(domain, code) for domain, code in codes.items()}
