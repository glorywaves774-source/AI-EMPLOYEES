"""Storage for large video files, streamed to and from disk (never fully in memory).

S3: stored with S3 server-side encryption (AES-256) under video/. Local: a private
folder for development. Keys are random 32-hex strings.
"""
import re
import shutil
from pathlib import Path

from flask import current_app

_KEY_RE = re.compile(r"^[a-f0-9]{32}$")


def _check(key):
    if not _KEY_RE.fullmatch(key or ""):
        raise ValueError("Invalid video storage key.")


def _backend():
    return current_app.config.get("STORAGE_BACKEND", "local").lower()


def _local_path(key):
    root = (Path(current_app.config["PRIVATE_UPLOAD_ROOT"]) / "video").resolve()
    root.mkdir(parents=True, exist_ok=True)
    path = (root / f"{key}.bin").resolve()
    if root not in path.parents:
        raise ValueError("Invalid storage path.")
    return path


def _s3():
    import boto3
    return boto3.client("s3", region_name=current_app.config.get("AWS_REGION")), current_app.config["S3_BUCKET"]


def put_path(key, src_path, content_type="video/mp4"):
    _check(key)
    if _backend() == "s3":
        client, bucket = _s3()
        client.upload_file(str(src_path), bucket, f"video/{key}.bin",
                           ExtraArgs={"ServerSideEncryption": "AES256", "ContentType": content_type})
    else:
        shutil.copyfile(src_path, _local_path(key))


def get_path(key, dest_path):
    _check(key)
    if _backend() == "s3":
        client, bucket = _s3()
        client.download_file(bucket, f"video/{key}.bin", str(dest_path))
    else:
        shutil.copyfile(_local_path(key), dest_path)


def open_stream(key):
    """(iterator of bytes, size) for sending a stored video to the browser."""
    _check(key)
    if _backend() == "s3":
        client, bucket = _s3()
        obj = client.get_object(Bucket=bucket, Key=f"video/{key}.bin")
        body = obj["Body"]
        return body.iter_chunks(chunk_size=256 * 1024), obj.get("ContentLength")
    path = _local_path(key)
    if not path.is_file():
        raise FileNotFoundError("Video is unavailable.")

    def chunks():
        with open(path, "rb") as fh:
            while True:
                block = fh.read(256 * 1024)
                if not block:
                    break
                yield block
    return chunks(), path.stat().st_size


def delete(key):
    _check(key)
    try:
        if _backend() == "s3":
            client, bucket = _s3()
            client.delete_object(Bucket=bucket, Key=f"video/{key}.bin")
        else:
            _local_path(key).unlink(missing_ok=True)
    except Exception:
        current_app.logger.exception("Could not delete video %s", key)
