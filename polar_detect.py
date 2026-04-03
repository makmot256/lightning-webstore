#!/usr/bin/env python3
"""
Polar Auto-Detection for LND nodes.

Parses ~/.polar/networks/networks.json to find LND node paths and REST ports
automatically. No more hunting for paths in Polar UI!

Usage:
    from polar_detect import auto_detect
    lnd_dir, rest_host = auto_detect("bob")
"""

import json
import os


POLAR_NETWORKS_FILE = os.path.expanduser(
    "~/.polar/networks/networks.json"
)


def find_polar_node(node_name="bob"):
    """
    Find an LND node from a running Polar network.

    Searches ~/.polar/networks/networks.json for an LND node matching
    the given name. Prefers running networks (status == Started),
    then falls back to highest network ID.

    Args:
        node_name: Name of the LND node to find (case-insensitive)

    Returns:
        dict with keys: name, lnd_dir, rest_host, rest_port, network_name
        None if no matching node found
    """
    if not os.path.exists(POLAR_NETWORKS_FILE):
        return None

    try:
        with open(POLAR_NETWORKS_FILE) as f:
            data = json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

    networks = data.get("networks", [])
    if not networks:
        return None

    # Sort: running networks first (status == Started), then by ID descending
    def sort_key(net):
        status = net.get("status", "")
        is_running = 1 if status == "Started" else 0
        net_id = int(net.get("id", 0))
        return (is_running, net_id)

    networks_sorted = sorted(networks, key=sort_key, reverse=True)

    # Walk newest/running networks first, then scan each Lightning node entry.
    for network in networks_sorted:
        nodes = network.get("nodes", {})
        lnd_nodes = nodes.get("lightning", [])

        for node in lnd_nodes:
            impl = node.get("implementation", "")
            name = node.get("name", "")

            if impl.upper() != "LND":
                continue
            if name.lower() != node_name.lower():
                continue

            # Build the LND directory path
            network_path = network.get("path", "")
            if not network_path:
                net_id = network.get("id", "")
                network_path = os.path.expanduser(
                    f"~/.polar/networks/{net_id}"
                )

            lnd_dir = os.path.join(
                network_path, "volumes", "lnd", name
            )

            # Get REST port from node ports config
            rest_port = None
            ports = node.get("ports", {})
            rest_port = ports.get("rest", 8082)

            rest_host = f"https://127.0.0.1:{rest_port}"

            return {
                "name": name,
                "lnd_dir": lnd_dir,
                "rest_host": rest_host,
                "rest_port": rest_port,
                "network_name": network.get("name", "unknown"),
            }

    return None


def auto_detect(node_name="bob"):
    """
    Auto-detect LND node configuration.

    Priority:
        1. LND_DIR + REST_HOST environment variables (manual override)
        2. Polar auto-detection from networks.json
        3. (None, None) if nothing found

    Args:
        node_name: Name of the Polar LND node to look for

    Returns:
        tuple of (lnd_dir, rest_host) -- either or both may be None
    """
    # Manual override via environment variables
    env_lnd_dir = os.environ.get("LND_DIR")
    env_rest_host = os.environ.get("REST_HOST")

    # Require both values so we do not return a half-configured connection.
    if env_lnd_dir and env_rest_host:
        return (os.path.expanduser(env_lnd_dir), env_rest_host)

    # Try Polar auto-detection
    polar = find_polar_node(node_name)
    if polar:
        return (polar["lnd_dir"], polar["rest_host"])

    # Nothing found
    return (None, None)


# ===========================================
# STANDALONE TEST
# ===========================================
if __name__ == "__main__":
    print("=== Polar Auto-Detection Test ===")
    print()

    polar = find_polar_node("bob")
    if polar:
        print(
            f"Polar: Found node '{polar['name']}' in network '{polar['network_name']}'")
        print(f"  LND dir:   {polar['lnd_dir']}")
        print(f"  REST host: {polar['rest_host']}")
        print(f"  REST port: {polar['rest_port']}")
    else:
        print("Polar: No LND node named 'bob' found.")
        print(f"  Checked: {POLAR_NETWORKS_FILE}")
        if not os.path.exists(POLAR_NETWORKS_FILE):
            print("  File does not exist (Polar not installed?)")

    print()
    lnd_dir, rest_host = auto_detect("bob")
    print(f"auto_detect result:")
    print(f"  LND dir:   {lnd_dir or '(not found)'}")
    print(f"  REST host: {rest_host or '(not found)'}")
