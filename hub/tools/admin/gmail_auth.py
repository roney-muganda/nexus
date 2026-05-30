import os
import logging
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/gmail.modify",
]

CREDENTIALS_FILE = "gmail_credentials.json"
TOKEN_DIR = "tokens"

os.makedirs(TOKEN_DIR, exist_ok=True)

def get_token_path(user_id: str) -> str:
    """Returns a unique token file path for each user."""
    return os.path.join(TOKEN_DIR, f"{user_id}_gmail_token.json")


def get_gmail_service(user_id: str):
    creds = None
    token_file = get_token_path(user_id)

    if os.path.exists(token_file):
        creds = Credentials.from_authorized_user_file(token_file, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Gmail credentials not found at {CREDENTIALS_FILE}. "
                    f"Download from Google Cloud Console."
                )
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "w") as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def authorize_gmail(user_id: str):
    print("Starting Gmail OAuth2 authorization flow...")
    service = get_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    print(f"✓ Gmail authorized for: {profile['emailAddress']}")
    return profile["emailAddress"]