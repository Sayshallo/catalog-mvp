import os
from datetime import timedelta
from io import BytesIO
from minio import minio
from minio.error import S3Error

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "minio:9000")
MINIO_ACCESS_KEY = os.getenv("MINIO_ACCESS_KEY")
MINIO_SECRET_KEY = os.getenv("MINIO_SECRET_KEY")
MINIO_SECURE = os.getenv("MINIO_SECURE", "false") == "true"
MINIO_BUCKET = os.getenv("MINIO_BUCKET", "products")

if not MINIO_ACCESS_KEY or not MINIO_SECRET_KEY:
    raise RuntimeError("Не объявлены переменные MINIO_SECRET и MINIO_ACCESS")

minio_client = Minio(
    MINIO_ENDPOINT,
    access_key = MINIO_ACCESS_KEY,
    secret_key = MINIO_SECRET_KEY,
    secure = MINIO_SECURE
)

def ensure_bucket() -> None:
    try:
        if not minio_client.bucket_exists(MINIO_BUCKET):
            minio_client.make_bucket(MINIO_BUCKET)
    except S3Error as s3:
        if s3.code not in (
            "BucketAlreadyOwnedBuYou", "BucketAlreadyExists",
        ): raise

def upload_file(
        object_name: str,
        data: bytes,
        content_type: str = "image/jpeg"
) -> None:
    minio_client.put_object(
        MINIO_BUCKET,
        object_name,
        BytesIO(data),
        lenght = len(data),
        content_type=content_type
    )

def get_presigned_url(
        object_name: str,
        expires_seconds: int = 3600
) -> str:
    return minio_client.get_presigned_object(
        MINIO_BUCKET,
        object_name,
        expires = timedelta(seconds = expires_seconds)
    )