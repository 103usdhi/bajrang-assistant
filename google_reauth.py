import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow

# Scopes maintained from google_test.py and bot.py requirements
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.compose"
]

CREDENTIALS_FILE = "google_credentials.json"
TOKEN_FILE = "token.json"

def main():
    """
    Run this locally to generate a fresh GOOGLE_TOKEN_JSON value.
    Requires 'google_credentials.json' (OAuth Client ID) in the same folder.
    """
    if not os.path.exists(CREDENTIALS_FILE):
        print(f"ERROR: '{CREDENTIALS_FILE}' not found.")
        print("Please download your 'Desktop' OAuth 2.0 Client ID JSON from the Google Cloud Console.")
        print("Reference REAUTH.md for step-by-step instructions.")
        return

    print("Starting local OAuth flow for Bajrang...")
    print(f"Requested Scopes: {', '.join(SCOPES)}")

    try:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        
        # access_type='offline' and prompt='consent' ensure we get a refresh_token
        creds = flow.run_local_server(
            port=0,
            access_type="offline",
            prompt="consent"
        )

        # Save locally to token.json for convenience/testing
        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())
        
        print("\n" + "="*60)
        print("SUCCESS: Google Re-authentication Complete")
        print("="*60)
        print("\nCopy the JSON block below and update your GOOGLE_TOKEN_JSON environment variable:")
        print("\n--- BEGIN JSON ---")
        print(creds.to_json())
        print("--- END JSON ---\n")
        print("SAFETY WARNING: This JSON contains sensitive access and refresh tokens.")
        print("Store it only in your local .env or Render Environment Variables.")
    except Exception as e:
        print(f"\nAn error occurred during authentication: {e}")

if __name__ == "__main__":
    main()