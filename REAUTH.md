# Bajrang Google Re-authentication Guide

If Bajrang reports "Access token expired or revoked" and automatic refresh fails, follow these steps to generate a fresh token.

## 1. Prerequisites
Ensure you have the required libraries installed locally:
```bash
pip install google-auth-oauthlib google-api-python-client
```

## 2. Obtain Client Credentials
1. Go to the [Google Cloud Console](https://console.cloud.google.com/).
2. Navigate to **APIs & Services > Credentials**.
3. Find your **OAuth 2.0 Client ID** (Type: Desktop).
4. Download the JSON file and rename it to `google_credentials.json`.
5. Place `google_credentials.json` in the root of the `bajrang-assistant` folder.

## 3. Run the Re-auth Utility
Execute the script locally:
```bash
python google_reauth.py
```
1. Your default browser will open.
2. Log in with the Google account used for Bajrang.
3. Grant permissions for Gmail (Read/Compose) and Calendar.
4. Once the browser says "The authentication flow has completed," return to your terminal.

## 4. Update Environment Variables
1. The script will print a JSON block labeled `--- BEGIN JSON ---`.
2. **Local:** Copy this block into your `.env` file for the `GOOGLE_TOKEN_JSON` key.
3. **Render:**
   - Go to your Render Dashboard.
   - Navigate to **Environment**.
   - Edit `GOOGLE_TOKEN_JSON` and paste the new JSON block.
   - Save changes (Render will trigger a redeploy).

## 5. Verification
- Run `google_test.py` locally to verify the new token works.
- Once deployed, use the **System Status** button in the Telegram bot to confirm Gmail and Calendar are `Operational`.

> **Safety Note:** `GOOGLE_TOKEN_JSON` is highly sensitive. Never commit it to GitHub or share the output of `google_reauth.py` with others.