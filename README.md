Synapse Finance

A full-stack financial SaaS platform I built from scratch. Users can track stocks, view real-time quotes, get in-depth market analysis, manage a portfolio, and stay up on financial news all in one place.

This started as a personal project but grew into a real production app that hit 50+ active users. I handled everything end to end, backend, frontend, database, auth, and deployment.

Tech Stack



Backend: Python, Flask, RESTful APIs

Frontend: HTML, CSS, JavaScript, React

Database: PostgreSQL, SQLAlchemy

Auth: JWT authentication

DevOps: CI/CD pipeline, deployed on Render



Features



Real-time stock quotes and market data

Portfolio tracking and management

Stock analysis with ratings and financial metrics

Financial news feed

User authentication and account management

Price alert system



Live Site

https://synapse-finance.onrender.com

Demo Mode

The live site runs in demo mode so it works without paid API subscriptions:

- Click "Try the Demo" to get a private, pre-filled Pro account (portfolio, trade journal, watchlist, alerts). It is deleted automatically after 24 hours.
- Market data is a real snapshot pulled from Yahoo Finance (prices, 10-year history, fundamentals, analyst ratings, earnings, news) plus the weekly economic calendar, stored in app/demo_data.
- Stripe checkout is simulated (upgrade/cancel instantly) and outbound email is disabled.
- Demo data lives in a local SQLite file, separate from the production database.

Refresh the snapshot:

    pip install -r scripts/requirements-snapshot.txt
    python scripts/build_demo_snapshot.py

Switch back to the full production setup by setting DEMO_MODE=false along with DATABASE_URL, FMP_API_KEY, STRIPE_SECRET_KEY, STRIPE_WEBHOOK_SECRET, STRIPE_PRO_PRICE_ID, SENDGRID_API_KEY and MAIL_FROM_EMAIL.

Run Locally

    python -m venv .venv
    .venv\Scripts\activate        (Windows)  |  source .venv/bin/activate  (macOS/Linux)
    pip install -r requirements.txt
    flask --app app run

