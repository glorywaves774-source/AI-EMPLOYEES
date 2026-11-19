"""Private encrypted file storage. Local disk is for development; S3 is for deployment."""
import re
from io import BytesIO
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from flask import current_app

_KEY_RE = re.compile(r"^[a-f0-9]{32}$")


def _cipher():
    key = current_app.config.get("FILE_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("FILE_ENCRYPTION_KEY is not configured; uploads are disabled until encryption is configured.")
    try:
        return Fernet(key.encode("ascii") if isinstance(key, str) else key)
    except (ValueError, TypeError) as exc:
        raise RuntimeError("FILE_ENCRYPTION_KEY must be a valid Fernet key.") from exc


def _validate_key(storage_key):
    if not _KEY_RE.fullmatch(storage_key or ""):
        raise ValueError("Invalid private storage key.")


def store_file(storage_key, raw_bytes):
    _validate_key(storage_key)
    encrypted = _cipher().encrypt(raw_bytes)
    backend = current_app.config.get("STORAGE_BACKEND", "local").lower()
    if backend == "local":
        root = Path(current_app.config["PRIVATE_UPLOAD_ROOT"]).resolve()
        root.mkdir(parents=True, exist_ok=True)
        path = (root / f"{storage_key}.enc").resolve()
        if root not in path.parents:
            raise ValueError("Invalid storage path.")
        path.write_bytes(encrypted)
        return
    if backend == "s3":
        bucket = current_app.config.get("S3_BUCKET")
        if not bucket:
            raise RuntimeError("S3_BUCKET is required when STORAGE_BACKEND=s3.")
        import boto3
        client = boto3.client("s3", region_name=current_app.config.get("AWS_REGION"))
        client.put_object(Bucket=bucket, Key=f"knowledge/{storage_key}.enc", Body=encrypted,
                          ServerSideEncryption="AES256", ContentType="application/octet-stream")
        return
    raise RuntimeError("STORAGE_BACKEND must be either 'local' or 's3'.")


def read_file(storage_key):
    _validate_key(storage_key)
    backend = current_app.config.get("STORAGE_BACKEND", "local").lower()
    if backend == "local":
        root = Path(current_app.config["PRIVATE_UPLOAD_ROOT"]).resolve()
        path = (root / f"{storage_key}.enc").resolve()
        if root not in path.parents or not path.is_file():
            raise FileNotFoundError("Stored document is unavailable.")
        encrypted = path.read_bytes()
    elif backend == "s3":
        bucket = current_app.config.get("S3_BUCKET")
        if not bucket:
            raise RuntimeError("S3_BUCKET is required when STORAGE_BACKEND=s3.")
        import boto3
        client = boto3.client("s3", region_name=current_app.config.get("AWS_REGION"))
        response = client.get_object(Bucket=bucket, Key=f"knowledge/{storage_key}.enc")
        encrypted = response["Body"].read()
    else:
        raise RuntimeError("STORAGE_BACKEND must be either 'local' or 's3'.")
    try:
        return BytesIO(_cipher().decrypt(encrypted)).getvalue()
    except InvalidToken as exc:
        raise RuntimeError("Document decryption failed. Check the configured encryption key.") from exc


def delete_file(storage_key):
    _validate_key(storage_key)
    backend = current_app.config.get("STORAGE_BACKEND", "local").lower()
    if backend == "local":
        root = Path(current_app.config["PRIVATE_UPLOAD_ROOT"]).resolve()
        path = (root / f"{storage_key}.enc").resolve()
        if root in path.parents and path.exists():
            path.unlink()
    elif backend == "s3":
        bucket = current_app.config.get("S3_BUCKET")
        if not bucket:
            raise RuntimeError("S3_BUCKET is required when STORAGE_BACKEND=s3.")
        import boto3
        boto3.client("s3", region_name=current_app.config.get("AWS_REGION")).delete_object(
            Bucket=bucket, Key=f"knowledge/{storage_key}.enc")
    else:
        raise RuntimeError("STORAGE_BACKEND must be either 'local' or 's3'.")
