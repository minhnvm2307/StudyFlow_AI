"""AWS S3 document upload helper."""
import boto3
from app.config import settings


def get_s3_client():
    kwargs = {}
    if settings.S3_ENDPOINT_URL:
        kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
    if settings.S3_ACCESS_KEY_ID:
        kwargs["aws_access_key_id"] = settings.S3_ACCESS_KEY_ID
    if settings.S3_SECRET_ACCESS_KEY:
        kwargs["aws_secret_access_key"] = settings.S3_SECRET_ACCESS_KEY
    if settings.S3_REGION:
        kwargs["region_name"] = settings.S3_REGION
    return boto3.client("s3", **kwargs)


def upload_file_to_s3(file_bytes: bytes, key: str) -> str | None:
    """Upload bytes to S3, return the S3 URL or None on failure."""
    if not settings.S3_BUCKET_NAME:
        return None
    try:
        client = get_s3_client()
        client.put_object(Bucket=settings.S3_BUCKET_NAME, Key=key, Body=file_bytes)
        region = settings.S3_REGION or "ap-southeast-1"
        return f"https://{settings.S3_BUCKET_NAME}.s3.{region}.amazonaws.com/{key}"
    except Exception:
        return None
