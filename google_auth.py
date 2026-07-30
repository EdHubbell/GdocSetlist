"""
Google Authentication Module
============================
Handles OAuth2 authentication for Google Docs API.

First run will open browser for authentication.
Subsequent runs use cached token.json.
"""

import os
import json
import glob
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.auth.exceptions import RefreshError
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# OAuth scopes needed
SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/drive'
]

TOKEN_FILE = "token.json"


def find_credentials_file():
    """Locate the OAuth client secret JSON downloaded from Cloud Console.

    The filename embeds the client ID, so it changes whenever the OAuth
    client is recreated - discover it rather than hardcoding it.
    """
    matches = sorted(glob.glob("client_secret*.json"))
    if not matches:
        raise FileNotFoundError(
            "No client_secret*.json found in the current directory.\n"
            "Download an OAuth 'Desktop app' client from "
            "https://console.cloud.google.com/apis/credentials and place it here."
        )
    if len(matches) > 1:
        # Most recently downloaded wins; stale ones are usually deleted clients.
        matches.sort(key=os.path.getmtime, reverse=True)
        print(f"[WARNING] Multiple client secret files found; using {matches[0]}")
    return matches[0]


def get_credentials():
    """
    Get or create OAuth credentials.
    
    Returns:
        Credentials object ready to use with Google API
    """
    creds = None
    
    # Load existing token if available
    if os.path.exists(TOKEN_FILE):
        print(f"[INFO] Loading saved credentials from {TOKEN_FILE}")
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    
    # If no valid credentials, run OAuth flow
    if not creds or not creds.valid:
        refreshed = False
        if creds and creds.expired and creds.refresh_token:
            print("[INFO] Refreshing expired token...")
            try:
                creds.refresh(Request())
                refreshed = True
            except RefreshError as e:
                # Token is tied to a deleted/revoked client, or consent was
                # withdrawn. Discard it and re-authenticate from scratch.
                print(f"[WARNING] Could not refresh saved token: {e}")
                print("[INFO] Discarding stale token and re-authenticating.")
                creds = None

        if not refreshed:
            credentials_file = find_credentials_file()
            print("[INFO] No valid credentials found. Starting OAuth flow...")
            print(f"[INFO] Using client secret: {credentials_file}")
            print("[INFO] A browser window will open for authentication.")
            print("[INFO] Please log in and grant the requested permissions.")

            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_file, SCOPES)
            creds = flow.run_local_server(port=0)
            print("[INFO] Authentication successful!")
        
        # Save the credentials for next run
        with open(TOKEN_FILE, 'w') as token:
            token.write(creds.to_json())
        print(f"[INFO] Credentials saved to {TOKEN_FILE}")
    
    return creds


def get_docs_service():
    """
    Get Google Docs API service.
    
    Returns:
        Google Docs API service object
    """
    creds = get_credentials()
    service = build('docs', 'v1', credentials=creds)
    return service


def get_drive_service():
    """
    Get Google Drive API service.
    
    Returns:
        Google Drive API service object
    """
    creds = get_credentials()
    service = build('drive', 'v3', credentials=creds)
    return service
