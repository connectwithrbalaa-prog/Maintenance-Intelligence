"""Maximo ingestion adapter.

Reads assets, work orders, and failure records FROM Maximo via OSLC/REST API,
and normalizes to the canonical schema. Extends the existing cmms/maximo.py
(which handles WO push) with bidirectional read capability.
"""
