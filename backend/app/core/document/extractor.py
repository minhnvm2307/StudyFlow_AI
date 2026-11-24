import os
import re
import zipfile
import xml.etree.ElementTree as ET

import pypdf
from app.config import settings

try:
    import boto3
except ImportError:  # S3 is optional for local/dev RAG flows.
    boto3 = None

UPLOAD_DIR = "data/uploads"
DOCX_PARTS = ["word/document.xml", "word/header1.xml", "word/header2.xml", "word/footer1.xml", "word/footer2.xml"]
WORD_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"

def ensure_upload_dir():
    os.makedirs(UPLOAD_DIR, exist_ok=True)

def save_uploaded_file(file_name: str, file_bytes: bytes) -> str:
    ensure_upload_dir()
    safe_name = "".join(c for c in file_name if c.isalnum() or c in (".", "_", "-")).strip()
    file_path = os.path.join(UPLOAD_DIR, safe_name)
    with open(file_path, "wb") as f:
        f.write(file_bytes)
    return file_path

def upload_file_to_s3(file_bytes: bytes, key: str) -> str:
    bucket_name = settings.S3_BUCKET_NAME
    if not bucket_name:
        raise ValueError("S3_BUCKET_NAME is not configured in settings.")
    if boto3 is None:
        raise ValueError("boto3 is not installed; install backend requirements to enable S3 upload.")
        
    s3_kwargs = {}
    if settings.S3_REGION:
        s3_kwargs["region_name"] = settings.S3_REGION
    if settings.S3_ENDPOINT_URL:
        s3_kwargs["endpoint_url"] = settings.S3_ENDPOINT_URL
    if settings.S3_ACCESS_KEY_ID and settings.S3_SECRET_ACCESS_KEY:
        s3_kwargs["aws_access_key_id"] = settings.S3_ACCESS_KEY_ID
        s3_kwargs["aws_secret_access_key"] = settings.S3_SECRET_ACCESS_KEY
        
    s3 = boto3.client("s3", **s3_kwargs)
    s3.put_object(
        Bucket=bucket_name,
        Key=key,
        Body=file_bytes
    )
    
    if settings.S3_ENDPOINT_URL:
        endpoint = settings.S3_ENDPOINT_URL.rstrip('/')
        return f"{endpoint}/{bucket_name}/{key}"
    else:
        region = settings.S3_REGION or "us-east-1"
        return f"https://{bucket_name}.s3.{region}.amazonaws.com/{key}"

def extract_text_from_file_path(file_path: str) -> str:
    lower_path = file_path.lower()
    if lower_path.endswith(".pdf"):
        try:
            import fitz
            doc = fitz.open(file_path)
            text = ""
            for page in doc:
                text += page.get_text() + "\n"
            if text.strip():
                return sanitize_text_for_postgres(text)
        except Exception:
            pass

        reader = pypdf.PdfReader(file_path)
        text = ""
        for page in reader.pages:
            t = page.extract_text()
            if t:
                text += t + "\n"
        return sanitize_text_for_postgres(text)
    if lower_path.endswith(".docx"):
        return sanitize_text_for_postgres(_extract_docx_text(file_path))

    with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
        return sanitize_text_for_postgres(f.read())

def sanitize_text_for_postgres(text: str | None) -> str:
    if not text:
        return ""
    text = str(text).replace("\x00", "")
    return re.sub(r"[\x01-\x08\x0b\x0c\x0e-\x1f]", "", text)

def _extract_docx_text(file_path: str) -> str:
    blocks: list[str] = []
    with zipfile.ZipFile(file_path) as archive:
        names = set(archive.namelist())
        for part in DOCX_PARTS:
            if part not in names:
                continue
            xml_bytes = archive.read(part)
            blocks.extend(_extract_docx_part(xml_bytes))
    return "\n".join(block for block in blocks if block.strip())

def _extract_docx_part(xml_bytes: bytes) -> list[str]:
    root = ET.fromstring(xml_bytes)
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{WORD_NS}p"):
        pieces: list[str] = []
        for node in paragraph.iter():
            if node.tag == f"{WORD_NS}t" and node.text:
                pieces.append(node.text)
            elif node.tag == f"{WORD_NS}tab":
                pieces.append("\t")
            elif node.tag in {f"{WORD_NS}br", f"{WORD_NS}cr"}:
                pieces.append("\n")
        text = "".join(pieces).strip()
        if text:
            paragraphs.append(text)
    return paragraphs
