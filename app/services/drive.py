import base64
import hashlib
import json
import secrets
from pathlib import Path

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload

SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
TOKEN_PATH = DATA_DIR / "google_token.json"
CREDENTIALS_PATH = DATA_DIR / "google_credentials.json"
PKCE_PATH = DATA_DIR / "oauth_pkce.json"


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def has_credentials_file() -> bool:
    return CREDENTIALS_PATH.exists()


def get_credentials() -> Credentials | None:
    if not TOKEN_PATH.exists():
        return None
    creds = Credentials.from_authorized_user_file(str(TOKEN_PATH), SCOPES)
    if creds.expired and creds.refresh_token:
        creds.refresh(Request())
        TOKEN_PATH.write_text(creds.to_json())
    return creds if creds.valid else None


def is_connected() -> bool:
    return get_credentials() is not None


def get_service():
    creds = get_credentials()
    if not creds:
        return None
    return build("drive", "v3", credentials=creds)


def create_auth_url(redirect_uri: str) -> str:
    verifier, challenge = _pkce_pair()
    flow = Flow.from_client_secrets_file(str(CREDENTIALS_PATH), scopes=SCOPES, redirect_uri=redirect_uri)
    # Disable any auto-PKCE the library may add so we control the verifier ourselves
    flow.oauth2session.code_challenge_method = None
    auth_url, state = flow.authorization_url(
        prompt="consent",
        access_type="offline",
        code_challenge=challenge,
        code_challenge_method="S256",
    )
    PKCE_PATH.write_text(json.dumps({"state": state, "verifier": verifier}))
    return auth_url


def exchange_code(code: str, redirect_uri: str) -> None:
    saved = json.loads(PKCE_PATH.read_text()) if PKCE_PATH.exists() else {}
    verifier = saved.get("verifier")

    flow = Flow.from_client_secrets_file(str(CREDENTIALS_PATH), scopes=SCOPES, redirect_uri=redirect_uri)

    if verifier:
        flow.fetch_token(code=code, code_verifier=verifier)
    else:
        flow.fetch_token(code=code)

    TOKEN_PATH.write_text(flow.credentials.to_json())
    if PKCE_PATH.exists():
        PKCE_PATH.unlink()


_IMAGE_MIMES = (
    "mimeType = 'image/jpeg' or mimeType = 'image/png' or "
    "mimeType = 'image/webp' or mimeType = 'image/gif' or "
    "mimeType = 'image/heic' or mimeType = 'image/heif' or "
    "mimeType = 'application/pdf'"
)
_FOLDER_MIME = "application/vnd.google-apps.folder"


def _list_folder(service, folder_id: str) -> list[dict]:
    """Return all image/PDF files in folder and its subfolders."""
    files: list[dict] = []

    # Get files (non-folders)
    result = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false and ({_IMAGE_MIMES})",
        fields="files(id,name,mimeType,modifiedTime)",
        orderBy="modifiedTime desc",
        pageSize=200,
    ).execute()
    files.extend(result.get("files", []))

    # Recurse into subfolders
    subs = service.files().list(
        q=f"'{folder_id}' in parents and trashed=false and mimeType='{_FOLDER_MIME}'",
        fields="files(id,name)",
        pageSize=50,
    ).execute()
    for sub in subs.get("files", []):
        files.extend(_list_folder(service, sub["id"]))

    return files


def list_images_in_folder(folder_id: str) -> list[dict]:
    service = get_service()
    if not service:
        return []
    return _list_folder(service, folder_id)


def download_file(file_id: str, dest: Path) -> None:
    service = get_service()
    req = service.files().get_media(fileId=file_id)
    dest.parent.mkdir(parents=True, exist_ok=True)
    with open(dest, "wb") as f:
        dl = MediaIoBaseDownload(f, req)
        done = False
        while not done:
            _, done = dl.next_chunk()


def stream_file(file_id: str) -> tuple[bytes, str]:
    """Download a Drive file to memory, return (bytes, mime_type)."""
    import io
    service = get_service()
    meta = service.files().get(fileId=file_id, fields="mimeType,name").execute()
    mime = meta.get("mimeType", "application/octet-stream")
    req = service.files().get_media(fileId=file_id)
    buf = io.BytesIO()
    dl = MediaIoBaseDownload(buf, req)
    done = False
    while not done:
        _, done = dl.next_chunk()
    return buf.getvalue(), mime
