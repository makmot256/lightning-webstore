#!/usr/bin/env python3
"""
Lightning Webstore - Bootcamp Day 4
A Flask web application that accepts Lightning payments via LND.
"""

import json
import os
import io
import base64
from datetime import datetime

import qrcode
from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy

from polar_detect import auto_detect, find_polar_node
from lnd_client import LNDClient

# ===========================================
# CONFIGURATION
# ===========================================
app = Flask(__name__)
DISABLE_LIGHTNING = os.environ.get(
    "DISABLE_LIGHTNING", "true").lower() == "true"

DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite:///webstore.db")
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

app.config["SQLALCHEMY_DATABASE_URI"] = DATABASE_URL
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
db = SQLAlchemy(app)

# Load product catalog
PRODUCTS_FILE = os.path.join(os.path.dirname(__file__), "products.json")
# Keep products in memory so each request avoids disk I/O.
with open(PRODUCTS_FILE) as f:
    PRODUCTS = json.load(f)

# Auto-detect LND from Polar, or use manual defaults
LND_DIR, REST_HOST = auto_detect("bob")
# Fallbacks keep local bootcamp setup working even if Polar detection fails.
if not LND_DIR:
    LND_DIR = os.path.expanduser("~/bootcamp-code/day3/bob")
if not REST_HOST:
    REST_HOST = "https://localhost:8082"

if not DISABLE_LIGHTNING:
    # Connect to LND only when Lightning is enabled.
    lnd = LNDClient(lnd_dir=LND_DIR, rest_host=REST_HOST)
else:
    print("Lightning disabled for deployment")
    lnd = None


class Order(db.Model):
    """Tracks checkout invoices so payment status can be persisted."""
    id = db.Column(db.Integer, primary_key=True)
    product_id = db.Column(db.String(64), nullable=False)
    amount_sats = db.Column(db.Integer, nullable=False)
    payment_hash = db.Column(db.String(128), unique=True, nullable=False)
    settled = db.Column(db.Boolean, default=False, nullable=False)
    created_at = db.Column(
        db.DateTime, default=datetime.utcnow, nullable=False)


with app.app_context():
    db.create_all()


# ===========================================
# HELPER FUNCTIONS
# ===========================================
def get_product(product_id):
    """Find a product by its ID."""
    for product in PRODUCTS:
        if product["id"] == product_id:
            return product
    return None


def generate_qr_base64(data):
    """Generate a QR code and return as base64-encoded PNG."""
    qr = qrcode.QRCode(version=1, box_size=8, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    buffer.seek(0)
    return base64.b64encode(buffer.getvalue()).decode("utf-8")


def lightning_disabled_message():
    """Consistent error message for deployments with Lightning turned off."""
    return "Lightning payments are disabled for this deployment."


# ===========================================
# ROUTES
# ===========================================
@app.route("/")
def index():
    """Display the product catalog."""
    return render_template("index.html", products=PRODUCTS)


@app.route("/checkout/<product_id>")
def checkout(product_id):
    """Create a Lightning invoice and show QR code for payment."""
    product = get_product(product_id)
    if not product:
        return "Product not found", 404
    if lnd is None:
        return render_template(
            "error.html",
            error=lightning_disabled_message(),
            product=product,
        ), 503

    try:
        # Create a Lightning invoice via LND
        memo = f"Webstore: {product['name']}"
        result = lnd.add_invoice(amount=product["price"], memo=memo)

        payment_request = result["payment_request"]
        # LND returns r_hash in base64; convert to hex so it can be used safely in URL paths.
        r_hash = base64.b64decode(result["r_hash"]).hex()

        order = Order(
            product_id=product_id,
            amount_sats=product["price"],
            payment_hash=r_hash,
            settled=False,
        )
        db.session.add(order)
        db.session.commit()

        # Generate QR code
        qr_base64 = generate_qr_base64(payment_request.upper())

        return render_template(
            "checkout.html",
            product=product,
            payment_request=payment_request,
            r_hash=r_hash,
            qr_base64=qr_base64,
        )
    except Exception as e:
        return render_template(
            "error.html",
            error=str(e),
            product=product,
        )


@app.route("/api/check_payment/<r_hash>")
def check_payment(r_hash):
    """API endpoint to check if an invoice has been paid."""
    if lnd is None:
        return jsonify({"settled": False, "error": lightning_disabled_message()}), 503
    try:
        # Frontend polls this endpoint until settled becomes true.
        invoice = lnd.lookup_invoice(r_hash)
        settled = invoice.get("settled", False)
        if settled:
            order = Order.query.filter_by(payment_hash=r_hash).first()
            if order and not order.settled:
                order.settled = True
                db.session.commit()
        return jsonify({"settled": settled})
    except Exception as e:
        return jsonify({"settled": False, "error": str(e)})


@app.route("/success/<product_id>")
def success(product_id):
    """Display payment success page."""
    product = get_product(product_id)
    if not product:
        return "Product not found", 404
    return render_template("success.html", product=product)


@app.route("/api/node_info")
def node_info():
    """API endpoint to get LND node information."""
    if lnd is None:
        return jsonify({"error": lightning_disabled_message()}), 503
    try:
        info = lnd.get_info()
        balance = lnd.channel_balance()
        # Normalize different balance response formats seen across LND versions.
        return jsonify({
            "alias": info.get("alias", "unknown"),
            "pubkey": info.get("identity_pubkey", "unknown"),
            "channels": info.get("num_active_channels", 0),
            "synced": info.get("synced_to_chain", False),
            "balance": balance.get("local_balance", balance.get("balance", "0")),
        })
    except Exception as e:
        return jsonify({"error": str(e)})


# ===========================================
# MAIN
# ===========================================
if __name__ == "__main__":
    print("=" * 50)
    print("    LIGHTNING WEBSTORE - Bootcamp Day 4")
    print("=" * 50)
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
        print("To fix: set LND_DIR and REST_HOST environment variables,")
        print("or make sure Polar is running with an LND node named 'bob'.")
    print()

    try:
        info = lnd.get_info()
        print(f"Connected to LND node: {info.get('alias', 'unknown')}")
        print(f"Channels: {info.get('num_active_channels', 0)}")
        print()
    except Exception as e:
        print(f"Warning: Could not connect to LND: {e}")
        print("Make sure your LND node is running!")
        print()

    print("Starting webstore at http://127.0.0.1:5000")
    print("Press Ctrl+C to stop")
    print()
    PORT = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=PORT)
