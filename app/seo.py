# app/seo.py
from flask import make_response, render_template
from app import app
from datetime import datetime

# You can add more dynamic URLs here in the future
static_urls = [
    {'loc': '/', 'priority': '1.0'},
    {'loc': '/pricing', 'priority': '0.8'},
    {'loc': '/login', 'priority': '0.7'},
    {'loc': '/signup', 'priority': '0.7'},
    {'loc': '/news', 'priority': '0.8'},
]

# A list of high-value, popular stocks to ensure they are indexed.
# This list could be generated dynamically in the future.
dynamic_stock_symbols = ['AAPL', 'GOOGL', 'MSFT', 'TSLA', 'NVDA', 'AMZN']


@app.route('/sitemap.xml')
def sitemap():
    """
    Generates the sitemap.xml file dynamically.
    """
    url_root = app.config.get('DOMAIN', 'http://127.0.0.1:5000') 
    last_mod = datetime.now().strftime('%Y-%m-%d')
    
    # Create URLs for our popular stocks
    dynamic_urls = [
        {'loc': f"/dashboard?query={symbol}", 'priority': '0.9'}
        for symbol in dynamic_stock_symbols
    ]
    
    template = render_template('sitemap.xml', 
                               static_urls=static_urls, 
                               dynamic_urls=dynamic_urls, # Pass the new list
                               url_root=url_root,
                               last_mod=last_mod)

    response = make_response(template)
    response.headers['Content-Type'] = 'application/xml'
    
    return response

@app.route('/robots.txt')
def robots_txt():
    """Serves the robots.txt file."""
    # This could also be a static file, but serving it this way is fine.
    lines = [
        "User-agent: *",
        "Allow: /",
        "Allow: /dashboard",
        "Allow: /pricing",
        "Allow: /news",
        "Allow: /login",
        "Allow: /signup",
        "Disallow: /settings",
        "Disallow: /portfolio",
        "Disallow: /journal",
        "Disallow: /backtesting",
        "Disallow: /admin-login",
        "Disallow: /api/",
        "Disallow: /create-checkout-session",
        "Disallow: /create-portal-session",
        f"Sitemap: {app.config.get('DOMAIN', 'http://127.0.0.1:5000')}/sitemap.xml"
    ]
    return "\n".join(lines), 200, {'Content-Type': 'text/plain'}