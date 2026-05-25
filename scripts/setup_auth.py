"""
One-time setup script to get your Strava refresh token.
Run this locally once: python scripts/setup_auth.py
"""

import os
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
import requests

CLIENT_ID = os.environ.get("STRAVA_CLIENT_ID") or input("Enter your Strava Client ID: ").strip()
CLIENT_SECRET = os.environ.get("STRAVA_CLIENT_SECRET") or input("Enter your Strava Client Secret: ").strip()

AUTH_URL = (
    f"https://www.strava.com/oauth/authorize"
    f"?client_id={CLIENT_ID}"
    f"&response_type=code"
    f"&redirect_uri=http://localhost:8080/callback"
    f"&scope=activity:read_all,profile:read_all"
    f"&approval_prompt=force"
)

received_code = None


class CallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global received_code
        params = parse_qs(urlparse(self.path).query)
        if "code" in params:
            received_code = params["code"][0]
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b"<h2>Auth complete! You can close this tab.</h2>")
        else:
            self.send_response(400)
            self.end_headers()
            self.wfile.write(b"<h2>No code received.</h2>")

    def log_message(self, format, *args):
        pass  # suppress server logs


print("\nOpening Strava authorisation in your browser...")
webbrowser.open(AUTH_URL)

server = HTTPServer(("localhost", 8080), CallbackHandler)
print("Waiting for Strava callback on http://localhost:8080 ...")
server.handle_request()

if not received_code:
    print("ERROR: no authorisation code received.")
    raise SystemExit(1)

resp = requests.post(
    "https://www.strava.com/oauth/token",
    data={
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "code": received_code,
        "grant_type": "authorization_code",
    },
    timeout=10,
)
resp.raise_for_status()
data = resp.json()

print("\n--- Store these as GitHub repository secrets ---")
print(f"STRAVA_CLIENT_ID     = {CLIENT_ID}")
print(f"STRAVA_CLIENT_SECRET = {CLIENT_SECRET}")
print(f"STRAVA_REFRESH_TOKEN = {data['refresh_token']}")
print(f"STRAVA_ATHLETE_ID    = {data['athlete']['id']}")
print("------------------------------------------------\n")
