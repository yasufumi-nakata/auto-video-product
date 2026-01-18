import os
import google_auth_oauthlib.flow
from google.oauth2.credentials import Credentials

# "web" 形式のJSONに対応するため、installed形式として読み込むか、flowを直接作る
CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

def authenticate():
    print("Starting authentication flow...")
    print("NOTE: If you are using a non-default Google account, please ensure you select the correct one in the browser.")

    try:
        # Load flow from client secrets
        flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
            CLIENT_SECRETS_FILE, SCOPES)

        # Try local server with fixed port 8080
        try:
            print("Attempting to start local server on http://localhost:8080/ ...")
            # prompt='select_account' helps when user uses multiple accounts
            creds = flow.run_local_server(port=8080, timeout_seconds=300, prompt='select_account')
        except Exception as local_e:
            print(f"Local server failed: {local_e}")
            print("Falling back to any available port...")
            creds = flow.run_local_server(port=0, open_browser=True, prompt='select_account')

        # トークン保存
        with open("token.json", "w") as token:
            token.write(creds.to_json())

        print("Authentication successful! 'token.json' created.")

    except Exception as e:
        print(f"Authentication failed: {e}")
        print("\nIMPORTANT: If you see 'Error 400: redirect_uri_mismatch':")
        print("1. Go to Google Cloud Console -> Credentials.")
        print("2. Select your OAuth 2.0 Client ID (Web Application).")
        print("3. Add 'http://localhost:[PORT]/' to 'Authorized redirect URIs'.")
        print("4. OR: Re-create the Client ID as a 'Desktop App'.")

if __name__ == "__main__":
    authenticate()

