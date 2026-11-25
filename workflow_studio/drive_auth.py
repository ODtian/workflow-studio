"""Connect Drive from the file panel for the life of that panel."""


class DriveAuthorization:
    def begin(self):
        from google_auth_oauthlib.flow import InstalledAppFlow
        from pydata_google_auth import auth

        config = {"installed": {
            "client_id": auth.WEBAPP_CLIENT_ID,
            "client_secret": auth.WEBAPP_CLIENT_SECRET,
            "auth_uri": auth.GOOGLE_AUTH_URI,
            "token_uri": auth.GOOGLE_TOKEN_URI,
            "redirect_uris": [auth.WEBAPP_REDIRECT_URI],
        }}
        self.flow = InstalledAppFlow.from_client_config(
            config, scopes=["https://www.googleapis.com/auth/drive"])
        self.flow.redirect_uri = auth.WEBAPP_REDIRECT_URI
        url, _ = self.flow.authorization_url(**auth.AUTH_URI_KWARGS)
        return url

    def complete(self, code):
        import httplib2
        from google_auth_httplib2 import AuthorizedHttp
        from googleapiclient.discovery import build
        from transfer_core import GoogleDriveProvider

        self.flow.fetch_token(code=code.strip())
        http = AuthorizedHttp(self.flow.credentials, http=httplib2.Http(timeout=30))
        return GoogleDriveProvider(build("drive", "v3", http=http, cache_discovery=False))
