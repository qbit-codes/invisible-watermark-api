# main.py
# FastAPI: blind_watermark ile embed + verify (server-side persist + URL)
import multiprocessing
import os

# Monkey patch to prevent blind_watermark from setting multiprocessing method
original_set_start_method = multiprocessing.set_start_method
def patched_set_start_method(*args, **kwargs):
    try:
        return original_set_start_method(*args, **kwargs)
    except RuntimeError:
        pass  # Ignore "context has already been set" errors

multiprocessing.set_start_method = patched_set_start_method

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import base64, uuid, tempfile
from typing import Dict, Any
import numpy as np
import cv2

from watermark_adapters import create_watermark_adapter

from dotenv import load_dotenv
load_dotenv()

# Watermark adapter configuration
WATERMARK_ADAPTER = os.getenv("WATERMARK_ADAPTER", "trustmark")
WM_PASS_IMG = int(os.getenv("WM_PASS_IMG", "1"))
WM_PASS_WM = int(os.getenv("WM_PASS_WM", "1"))

# Create watermark adapter instance
if WATERMARK_ADAPTER == "blind_watermark":
    watermark_adapter = create_watermark_adapter("blind_watermark", password_img=WM_PASS_IMG, password_wm=WM_PASS_WM)
else:
    watermark_adapter = create_watermark_adapter(WATERMARK_ADAPTER)

app = FastAPI(
    title="Invisible Watermark API",
    description=f"Watermarking service using {WATERMARK_ADAPTER} adapter"
)

# --- storage klasörü ve statik servis (kalıcı dosyalar için) ---
os.makedirs("storage/embeds", exist_ok=True)
os.makedirs("storage/models", exist_ok=True)
app.mount("/files", StaticFiles(directory="storage"), name="files")

# --- In-memory DB (demo) ---
# watermark_id -> {"adapter_type": str, "metadata": dict, "shape": (h,w), "file_path": str}
DB: Dict[str, Dict[str, Any]] = {}

# --- Utils ---
def imread_from_upload(file: UploadFile) -> np.ndarray:
    data = file.file.read()
    arr = np.frombuffer(data, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="Invalid image file")
    return img

def imencode_png_to_base64(img_bgr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", img_bgr)
    if not ok:
        raise HTTPException(status_code=500, detail="PNG encoding failed")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def save_temp_png(img_bgr: np.ndarray) -> str:
    fd, path = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    cv2.imwrite(path, img_bgr)
    return path

# --- Schemas ---
class EmbedResponse(BaseModel):
    watermark_id: str
    wm_len: int
    watermarked_image_base64: str  # sadece base64
    message: str
    file_url: str | None = None    # kalıcı dosya URL'i

class VerifyResponse(BaseModel):
    watermark_found: bool
    matches_expected: bool
    extracted_watermark: str | None
    details: dict | None

# --- Endpoints ---
@app.post("/embed", response_model=EmbedResponse)
async def embed_endpoint(
    request: Request,
    file: UploadFile = File(...),
    wm_text: str | None = Form(None)
):
    """
    Upload an image, embed invisible watermark, return PNG(base64) + metadata.
    Also persist embedded PNG on server and return a URL.
    """
    # 1) Input image
    img = imread_from_upload(file)
    h, w = img.shape[:2]

    # 2) Watermark text
    if not wm_text:
        wm_text = f"WM-{uuid.uuid4()}"

    # 3) Temp paths for blind_watermark
    in_path  = save_temp_png(img)
    out_path = tempfile.mktemp(suffix=".png")

    # 4) Embed using adapter
    embed_metadata = watermark_adapter.embed(in_path, wm_text, out_path)

    # 5) Read embedded result
    embedded = cv2.imread(out_path, cv2.IMREAD_COLOR)
    if embedded is None:
        # temizlik
        if os.path.exists(in_path): os.remove(in_path)
        if os.path.exists(out_path): os.remove(out_path)
        raise HTTPException(status_code=500, detail="Embedded image not readable")

    # 6) Create watermark_id & persist embedded PNG on server
    watermark_id = str(uuid.uuid4())
    persist_path = os.path.join("storage", "embeds", f"{watermark_id}.png")
    cv2.imwrite(persist_path, embedded)

    # absolute URL (Swagger kullanırken rahat)
    base = str(request.base_url).rstrip("/")
    file_url = f"{base}/files/embeds/{watermark_id}.png"

    # 7) Save metadata
    DB[watermark_id] = {
        "adapter_type": WATERMARK_ADAPTER,
        "metadata": embed_metadata,
        "shape": (h, w),
        "file_path": persist_path,
    }

    # 8) Return
    b64 = imencode_png_to_base64(embedded)
    # cleanup temps
    if os.path.exists(in_path): os.remove(in_path)
    if os.path.exists(out_path): os.remove(out_path)

    return EmbedResponse(
        watermark_id=watermark_id,
        wm_len=embed_metadata.get("wm_len", 0),
        watermarked_image_base64=b64,
        message=f"Watermark embedded successfully using {WATERMARK_ADAPTER}.",
        file_url=file_url
    )

@app.post("/verify", response_model=VerifyResponse)
async def verify_endpoint(
    file: UploadFile = File(...),
    watermark_id: str = Form(...),
    try_recover: bool = Form(True)
):
    """
    Upload an edited image and check:
     - Is the expected watermark present?
     - If present, is it exactly the same (pHash=0) or modified?
     - Optionally try geometric recovery using the persisted reference.
    """
    # 0) Metadata
    meta = DB.get(watermark_id)
    if not meta:
        raise HTTPException(status_code=404, detail="Unknown watermark_id")

    adapter_type = meta["adapter_type"]
    embed_metadata = meta["metadata"]
    ori_shape = meta["shape"]          # (h, w)
    ref_path = meta.get("file_path")   # persisted reference
    
    # Create adapter instance (could be different from current global adapter)
    if adapter_type == "blind_watermark":
        used_adapter = create_watermark_adapter("blind_watermark", password_img=WM_PASS_IMG, password_wm=WM_PASS_WM)
    else:
        used_adapter = create_watermark_adapter(adapter_type)

    # 1) Read uploaded edited image
    edited = imread_from_upload(file)

    # 2) Direct extraction using adapter
    tmp_in = save_temp_png(edited)
    extracted = used_adapter.extract(tmp_in, embed_metadata)

    # 3) Optional geometric recovery using adapter
    details = {}
    if extracted is None and try_recover and used_adapter.supports_recovery() and ref_path and os.path.exists(ref_path):
        extracted, details = used_adapter.recover_and_extract(tmp_in, ref_path, embed_metadata)
    elif extracted is None and try_recover and not (ref_path and os.path.exists(ref_path)):
        details["recovery_error"] = "Reference embedded image not found on server."
    elif extracted is None and try_recover and not used_adapter.supports_recovery():
        details["recovery_error"] = f"{adapter_type} adapter does not support geometric recovery."

    # 4) Decide result
    expected_text = embed_metadata.get("wm_text")
    watermark_found = (extracted is not None and extracted == expected_text)

    # 5) Cleanup
    if os.path.exists(tmp_in): os.remove(tmp_in)

    return VerifyResponse(
        watermark_found=bool(watermark_found),
        matches_expected=bool(watermark_found),
        extracted_watermark=extracted if watermark_found else None,
        details=details if details else None
    )

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8001, reload=True)
