#!/usr/bin/env python3
"""
LND REST API Client - Bootcamp Day 4
Connects to an LND node via REST API with macaroon authentication.
Reused in Day 5 hackathon starter.
"""

from polar_detect import auto_detect
import base64
import json
import os
import requests
import urllib3

# Suppress SSL warnings for self-signed LND certificates
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


# ===========================================
# CONFIGURATION
# ===========================================
# Auto-detect from Polar, or fall back to manual defaults

_detected_dir, _detected_host = auto_detect("bob")

# Defaults are module-level so callers can construct LNDClient() with no arguments.
LND_DIR = _detected_dir or os.path.expanduser("~/bootcamp-code/day3/bob")
REST_HOST = _detected_host or "https://localhost:8082"


class LNDClient:
    """
    Client for LND REST API.
    Uses macaroon authentication and self-signed TLS.

    Usage:
        lnd = LNDClient()
        info = lnd.get_info()
        invoice = lnd.add_invoice(amount=50000, memo="Coffee")
    """

    def __init__(self, lnd_dir=None, rest_host=None):
        self.lnd_dir = lnd_dir or LND_DIR
        self.rest_host = rest_host or REST_HOST
        self.macaroon = None

        # Read the macaroon (hex-encoded for REST API header)
        macaroon_path = os.path.join(
            self.lnd_dir, "data", "chain", "bitcoin", "regtest", "admin.macaroon"
        )
        try:
            with open(macaroon_path, "rb") as f:
                self.macaroon = f.read().hex()
        except FileNotFoundError:
            pass  # LND not set up yet -- methods will raise clear errors

        # TLS certificate path (we verify=False for self-signed)
        self.tls_cert = os.path.join(self.lnd_dir, "tls.cert")

    def _request(self, method, endpoint, data=None):
        """Make an authenticated request to LND REST API."""
        if not self.macaroon:
            raise ConnectionError(
                f"LND not found at {self.lnd_dir}. "
                "Make sure your LND node is set up. "
                "If using Polar, make sure it's running with a node named 'bob'."
            )
        url = f"{self.rest_host}{endpoint}"
        # LND REST expects macaroon in this specific gRPC metadata header.
        headers = {"Grpc-Metadata-macaroon": self.macaroon}

        if method == "GET":
            resp = requests.get(url, headers=headers, verify=False)
        elif method == "POST":
            headers["Content-Type"] = "application/json"
            # LND REST endpoints accept JSON payloads for invoice/payment operations.
            resp = requests.post(
                url, headers=headers, data=json.dumps(data), verify=False
            )
        elif method == "DELETE":
            resp = requests.delete(url, headers=headers, verify=False)
        else:
            raise ValueError(f"Unsupported method: {method}")

        resp.raise_for_status()
        # Most LND REST endpoints return JSON objects.
        return resp.json()

    # ===========================================
    # NODE INFO
    # ===========================================
    def get_info(self):
        """Get node information (alias, pubkey, sync status)."""
        return self._request("GET", "/v1/getinfo")

    def channel_balance(self):
        """Get total channel balance."""
        return self._request("GET", "/v1/balance/channels")

    def wallet_balance(self):
        """Get on-chain wallet balance."""
        return self._request("GET", "/v1/balance/blockchain")

    # ===========================================
    # INVOICES
    # ===========================================
    def add_invoice(self, amount, memo=""):
        """
        Create a new Lightning invoice.

        Args:
            amount: Amount in satoshis
            memo: Description for the invoice

        Returns:
            dict with r_hash, payment_request, add_index
        """
        data = {"value": str(amount), "memo": memo}
        return self._request("POST", "/v1/invoices", data)

    def lookup_invoice(self, r_hash_str):
        """
        Look up an invoice by its payment hash.

        Args:
            r_hash_str: URL-safe base64 encoded payment hash

        Returns:
            Invoice details including settled status
        """
        return self._request("GET", f"/v1/invoice/{r_hash_str}")

    def list_invoices(self):
        """List all invoices."""
        return self._request("GET", "/v1/invoices")

    # ===========================================
    # PAYMENTS
    # ===========================================
    def list_payments(self):
        """List all outgoing payments."""
        return self._request("GET", "/v1/payments")

    def decode_pay_req(self, pay_req):
        """Decode a BOLT11 payment request."""
        return self._request("GET", f"/v1/payreq/{pay_req}")

    # ===========================================
    # CHANNELS
    # ===========================================
    def list_channels(self):
        """List all active channels."""
        return self._request("GET", "/v1/channels")

    def list_peers(self):
        """List connected peers."""
        return self._request("GET", "/v1/peers")


# ===========================================
# STANDALONE TEST
# ===========================================
if __name__ == "__main__":
    from polar_detect import find_polar_node

    print("=== LND Client Test ===")
    print()

    # Show Polar detection info
    polar = find_polar_node("bob")
    if polar:
        print(f"Polar: Connected to node '{polar['name']}' in network "
              f"'{polar['network_name']}' (REST port {polar['rest_port']})")
        print(f"  LND dir:   {polar['lnd_dir']}")
        print(f"  REST host: {polar['rest_host']}")
    else:
        print("Polar not detected -- using manual configuration.")
        print(f"  LND dir:   {LND_DIR}")
        print(f"  REST host: {REST_HOST}")
    print()

    try:
        lnd = LNDClient()
        info = lnd.get_info()
        print(f"Node alias:  {info.get('alias', 'unknown')}")
        print(f"Pubkey:      {info.get('identity_pubkey', 'unknown')[:20]}...")
        print(f"Synced:      {info.get('synced_to_chain', False)}")
        print(f"Channels:    {info.get('num_active_channels', 0)}")
        print()

        balance = lnd.channel_balance()
        local = balance.get("local_balance", balance.get("balance", "0"))
        print(f"Channel balance: {local} sats")
        print()

        print("LND client working!")
    except FileNotFoundError as e:
        print(f"Error: Could not find LND files: {e}")
        print(f"Make sure LND_DIR is correct: {LND_DIR}")
    except requests.ConnectionError:
        print(f"Error: Could not connect to {REST_HOST}")
        print("Make sure your LND node is running.")
    except Exception as e:
        print(f"Error: {e}")
