import os
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build


SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/calendar",
    "https://www.googleapis.com/auth/gmail.compose"
]

CREDENTIALS_FILE = "google_credentials.json"
TOKEN_FILE = "token.json"


def get_google_credentials():
    creds = None

    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    "google_credentials.json not found. Put it in the same folder as google_test.py"
                )

            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE,
                SCOPES
            )

            creds = flow.run_local_server(
                port=0,
                access_type="offline",
                prompt="consent"
            )

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return creds


def test_gmail(creds):
    print("\n=== Gmail Test ===")

    service = build("gmail", "v1", credentials=creds)

    results = service.users().messages().list(
        userId="me",
        maxResults=5,
        q="in:inbox"
    ).execute()

    messages = results.get("messages", [])

    if not messages:
        print("No Gmail messages found.")
        return

    for msg in messages:
        message = service.users().messages().get(
            userId="me",
            id=msg["id"],
            format="metadata",
            metadataHeaders=["From", "Subject", "Date"]
        ).execute()

        headers = message.get("payload", {}).get("headers", [])

        from_value = ""
        subject_value = ""
        date_value = ""

        for header in headers:
            if header["name"].lower() == "from":
                from_value = header["value"]
            elif header["name"].lower() == "subject":
                subject_value = header["value"]
            elif header["name"].lower() == "date":
                date_value = header["value"]

        print(f"\nFrom: {from_value}")
        print(f"Subject: {subject_value}")
        print(f"Date: {date_value}")


def test_calendar(creds):
    print("\n=== Google Calendar Test ===")

    service = build("calendar", "v3", credentials=creds)

    now = datetime.now(ZoneInfo("Europe/Berlin"))
    end = now + timedelta(days=7)

    events_result = service.events().list(
        calendarId="primary",
        timeMin=now.isoformat(),
        timeMax=end.isoformat(),
        maxResults=10,
        singleEvents=True,
        orderBy="startTime"
    ).execute()

    events = events_result.get("items", [])

    if not events:
        print("No upcoming calendar events found.")
        return

    for event in events:
        start = event.get("start", {}).get("dateTime", event.get("start", {}).get("date"))
        summary = event.get("summary", "No title")
        location = event.get("location", "")

        print(f"\nEvent: {summary}")
        print(f"Start: {start}")
        if location:
            print(f"Location: {location}")


def main():
    print("Starting Google Gmail + Calendar test...")

    creds = get_google_credentials()

    print("Google authentication successful.")

    test_gmail(creds)
    test_calendar(creds)

    print("\nGoogle test completed successfully.")


if __name__ == "__main__":
    main()