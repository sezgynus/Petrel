"""Compatibility adapter for existing RFID/Info screens.

NFCBackend is the only libnfc hardware owner. No scanner, libnfc handle,
worker or connection configuration is implemented in this module.
"""
from nfc_backend import NFCBackend


class RFIDReader(NFCBackend):
    """Legacy view-facing name; all behavior is implemented by NFCBackend."""
