import boto3
from botocore.client import Config
from botocore.exceptions import ClientError
from app.core.config import settings
from typing import BinaryIO, Optional
import io
import logging

logger = logging.getLogger(__name__)

s3_client = boto3.client(
    's3',
    endpoint_url=settings.MINIO_SERVER_URL,
    aws_access_key_id=settings.MINIO_ACCESS_KEY,
    aws_secret_access_key=settings.MINIO_SECRET_KEY,
    config=Config(signature_version='s3v4')
)

BUCKET_NAME: str = settings.MINIO_BUCKET_NAME

def create_minio_bucket_if_not_exists() -> None:
    """
    Ensure the MinIO bucket exists. Create it if it does not exist.
    """
    try:
        s3_client.head_bucket(Bucket=BUCKET_NAME)
        logger.info(f"Bucket '{BUCKET_NAME}' already exists.")
    except ClientError as e:
        if e.response['Error']['Code'] == '404':
            logger.info(f"Bucket '{BUCKET_NAME}' not found. Creating it.")
            s3_client.create_bucket(Bucket=BUCKET_NAME)
            logger.info(f"Bucket '{BUCKET_NAME}' created.")
        else:
            logger.error(f"Error checking for bucket: {e}", exc_info=True)
            raise

def upload_file_obj(file_obj: BinaryIO, object_name: str) -> bool:
    """
    Upload a file-like object to the MinIO bucket.
    """
    try:
        s3_client.upload_fileobj(file_obj, BUCKET_NAME, object_name)
    except ClientError as e:
        logger.error(f"Error uploading to MinIO: {e}", exc_info=True)
        return False
    return True

def download_file(object_name: str, file_path: str) -> bool:
    """
    Download an object from the MinIO bucket to a local file.
    """
    try:
        s3_client.download_file(BUCKET_NAME, object_name, file_path)
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "404":
            logger.warning(f"File '{object_name}' not found in MinIO.")
        else:
            logger.error(f"Error downloading from MinIO: {e}", exc_info=True)
        return False
    return True

def delete_file(object_name: str) -> bool:
    """
    Delete an object from the MinIO bucket.
    """
    try:
        s3_client.delete_object(Bucket=BUCKET_NAME, Key=object_name)
    except ClientError as e:
        logger.error(f"Error deleting from MinIO: {e}", exc_info=True)
        return False
    return True

def upload_in_memory_object(object_name: str, data: bytes) -> bool:
    """
    Upload an in-memory bytes object to MinIO.
    """
    try:
        with io.BytesIO(data) as file_obj:
            s3_client.upload_fileobj(file_obj, BUCKET_NAME, object_name)
    except ClientError as e:
        logger.error(f"Error uploading in-memory object to MinIO: {e}", exc_info=True)
        return False
    return True

def download_in_memory_object(object_name: str) -> Optional[bytes]:
    """
    Download an object from MinIO into an in-memory bytes object.
    Returns None if the object is not found.
    """
    try:
        with io.BytesIO() as file_obj:
            s3_client.download_fileobj(BUCKET_NAME, object_name, file_obj)
            file_obj.seek(0)
            return file_obj.read()
    except ClientError as e:
        if e.response.get("Error", {}).get("Code") == "404":
            logger.info(f"Object '{object_name}' not found in MinIO bucket '{BUCKET_NAME}'.")
        else:
            logger.error(f"Error downloading in-memory object from MinIO: {e}", exc_info=True)
        return None