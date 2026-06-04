import os
import base64
import json
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

# Ensures it looks in the absolute root of your project
BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
CREDENTIALS_FILE = os.path.join(BASE_DIR, "gmail_credentials.json")
TOKEN_FILE = os.path.join(BASE_DIR, "tokens", "gmail_token.json") # Looking in your tokens folder!

def get_gmail_service():
    creds = None
    
    # Option 1 — Load from environment variable (Production on Render)
    gmail_token_b64 = os.getenv("GMAIL_TOKEN_B64", "")
    if gmail_token_b64:
        try:
            token_json = base64.b64decode(gmail_token_b64).decode("utf-8")
            creds = Credentials.from_authorized_user_info(json.loads(token_json), SCOPES)
            logger.info("Loaded Gmail credentials from environment variable")
        except Exception as e:
            logger.error(f"Failed to load Gmail token from env: {e}")

    # Option 2 — Load from file (Local Development)
    if not creds and os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
        logger.info("Loaded Gmail credentials from local token file")

    # Refresh if expired
    if creds and creds.expired and creds.refresh_token:
        try:
            creds.refresh(Request())
            logger.info("Gmail credentials refreshed")
        except Exception as e:
            logger.error(f"Failed to refresh Gmail token: {e}")
            creds = None

    # Option 3 — Run local auth flow (Only works locally)
    if not creds or not creds.valid:
        if os.path.exists(CREDENTIALS_FILE):
            flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)
            
            # Save the new token
            os.makedirs(os.path.dirname(TOKEN_FILE), exist_ok=True)
            with open(TOKEN_FILE, "w") as f:
                f.write(creds.to_json())
            logger.info("Gmail authorization completed")
        else:
            raise RuntimeError(
                "Gmail not authorized. Set GMAIL_TOKEN_B64 environment variable on Render."
            )

    return build("gmail", "v1", credentials=creds)

def authorize_gmail():
    print("Starting Gmail OAuth2 authorization flow...")
    service = get_gmail_service()
    profile = service.users().getProfile(userId="me").execute()
    email = profile["emailAddress"]
    print(f"✓ Gmail authorized for: {email}")