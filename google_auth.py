"""
Google Authentication Module
============================
Handles OAuth2 authentication for Google Docs API.

First run will open browser for authentication.
Subsequent runs use cached token.json.
"""

import os
import json
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

# OAuth scopes needed
SCOPES = [
    'https://www.googleapis.com/auth/documents',
    'https://www.googleapis.com/auth/drive'
]

CREDENTIALS_FILE = "client_secret_551449482131-lcp5sq6l3qha70vrmd6vs0lb4ngd8tqg.apps.googleusercontent.com.json"
TOKEN_FILE = "token.json"


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
        if creds and creds.expired and creds.refresh_token:
            print("[INFO] Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("[INFO] No valid credentials found. Starting OAuth flow...")
            print("[INFO] A browser window will open for authentication.")
            print("[INFO] Please log in and grant the requested permissions.")
            
            if not os.path.exists(CREDENTIALS_FILE):
                raise FileNotFoundError(
                    f"Credentials file not found: {CREDENTIALS_FILE}\n"
                    "Please ensure the client secrets JSON file is in the current directory."
                )
            
            flow = InstalledAppFlow.from_client_secrets_file(
                CREDENTIALS_FILE, SCOPES)
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
