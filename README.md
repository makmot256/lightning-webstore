# Lightning Webstore

A Flask web application that accepts Lightning payments via LND.

## Install dependencies

`pip install -r requirements.txt` or `pip3 install -r requirements.txt`

## Database (PostgreSQL on Railway)

This app now uses SQLAlchemy and reads `DATABASE_URL` from environment variables.

If `DATABASE_URL` is not set, it falls back to local SQLite (`webstore.db`).

### Railway setup

1. In Railway, add a PostgreSQL service to your project.
2. Open your web service (the Flask app), then Variables.
3. Add `DATABASE_URL` and set it to the PostgreSQL connection URL.
4. Add `DISABLE_LIGHTNING=true` if this deployment should run without LND.
5. Redeploy.

Orders created at checkout are stored in the `orders` table automatically.

## Start Application

Start app with command `python app.py`

## View in Browser

Open `http://127.0.0.1:5000` on your browser to view website
