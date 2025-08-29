# main.py
# FastAPI: blind_watermark ile embed + verify (server-side persist + URL)
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import uvicorn
import os, base64, uuid, tempfile
from typing import Dict, Any
import numpy as np
import cv2

from blind_watermark import WaterMark
from blind_watermark import att  # (opsiyonel: saldırı simülasyonları için)
from blind_watermark.recover import estimate_crop_parameters, recover_crop

from dotenv import load_dotenv
load_dotenv()

WM_PASS_IMG = int(os.getenv("WM_PASS_IMG", "1"))
WM_PASS_WM  = int(os.getenv("WM_PASS_WM", "1"))

app = FastAPI(title="Invisible Watermark API")

# --- storage klasörü ve statik servis (kalıcı dosyalar için) ---
os.makedirs("storage/embeds", exist_ok=True)
app.mount("/files", StaticFiles(directory="storage"), name="files")

# --- In-memory DB (demo) ---
# watermark_id -> {"wm_text": str, "wm_len": int, "phash": str, "shape": (h,w), "file_path": str}
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

def phash(img_bgr: np.ndarray) -> str:
    """Simple pHash: resize(32x32)->gray->DCT->8x8->median->bits->hex(16 chars)"""
    img_gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    small = cv2.resize(img_gray, (32, 32), interpolation=cv2.INTER_AREA)
    dct = cv2.dct(np.float32(small))
    block = dct[:8, :8]
    med = np.median(block[1:])  # skip DC term
    bits = (block > med).astype(np.uint8).flatten()
    v = 0
    for b in bits:
        v = (v << 1) | int(b)
    return f"{v:016x}"

def hamming_distance_hex(a: str, b: str) -> int:
    xa, xb = int(a, 16), int(b, 16)
    return (xa ^ xb).bit_count()

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
    status: str
    extracted_watermark: str | None
    phash_distance: int | None
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

    # 4) Embed
    bwm = WaterMark(password_img=WM_PASS_IMG, password_wm=WM_PASS_WM)
    bwm.read_img(in_path)
    bwm.read_wm(wm_text, mode='str')
    bwm.embed(out_path)
    wm_len = len(bwm.wm_bit)

    # 5) Read embedded result, compute pHash
    embedded = cv2.imread(out_path, cv2.IMREAD_COLOR)
    if embedded is None:
        # temizlik
        if os.path.exists(in_path): os.remove(in_path)
        if os.path.exists(out_path): os.remove(out_path)
        raise HTTPException(status_code=500, detail="Embedded image not readable")
    ref_ph = phash(embedded)

    # 6) Create watermark_id & persist embedded PNG on server
    watermark_id = str(uuid.uuid4())
    persist_path = os.path.join("storage", "embeds", f"{watermark_id}.png")
    cv2.imwrite(persist_path, embedded)

    # absolute URL (Swagger kullanırken rahat)
    base = str(request.base_url).rstrip("/")
    file_url = f"{base}/files/embeds/{watermark_id}.png"

    # 7) Save metadata
    DB[watermark_id] = {
        "wm_text": wm_text,
        "wm_len": wm_len,
        "phash": ref_ph,
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
        wm_len=wm_len,
        watermarked_image_base64=b64,
        message="Watermark embedded successfully.",
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

    expected_text = meta["wm_text"]
    wm_len        = meta["wm_len"]
    ref_phash     = meta["phash"]
    ori_shape     = meta["shape"]          # (h, w)
    ref_path      = meta.get("file_path")  # persisted reference

    # 1) Read uploaded edited image
    edited = imread_from_upload(file)

    # 2) Direct extraction
    tmp_in = save_temp_png(edited)
    bwm1 = WaterMark(password_img=WM_PASS_IMG, password_wm=WM_PASS_WM)
    try:
        extracted = bwm1.extract(tmp_in, wm_shape=wm_len, mode='str')
    except Exception:
        extracted = None

    # 3) Optional geometric recovery (crop/scale) using persisted reference
    recovered_path = None
    details = {}
    if (extracted != expected_text) and try_recover and ref_path and os.path.exists(ref_path):
        try:
            (x1, y1, x2, y2), image_o_shape, score, scale_infer = estimate_crop_parameters(
                original_file=ref_path,   # reference embedded PNG
                template_file=tmp_in,     # user's edited image
                scale=(0.5, 2.0),
                search_num=120
            )
            details["estimated"] = dict(
                x1=int(x1), y1=int(y1), x2=int(x2), y2=int(y2),
                score=float(score), scale=float(scale_infer)
            )

            recovered_path = tempfile.mktemp(suffix=".png")
            recover_crop(
                template_file=tmp_in,
                output_file_name=recovered_path,
                loc=(x1, y1, x2, y2),
                image_o_shape=image_o_shape
            )

            extracted_re = bwm1.extract(recovered_path, wm_shape=wm_len, mode='str')
            if extracted_re == expected_text:
                extracted = extracted_re
                details["recovered"] = True
        except Exception as e:
            details["recovery_error"] = str(e)
    elif (extracted != expected_text) and try_recover and not (ref_path and os.path.exists(ref_path)):
        details["recovery_error"] = "Reference embedded PNG not found on server."

    # 4) Decide status & pHash distance
    dist = hamming_distance_hex(ref_phash, phash(edited))
    watermark_found = (extracted == expected_text)
    if watermark_found:
        status = "same" if dist == 0 else "modified_but_watermark_intact"
    else:
        status = "tampered_or_not_watermarked"

    # 5) Cleanup
    if os.path.exists(tmp_in): os.remove(tmp_in)
    if recovered_path and os.path.exists(recovered_path):
        os.remove(recovered_path)

    return VerifyResponse(
        watermark_found=bool(watermark_found),
        matches_expected=bool(watermark_found),
        status=status,
        extracted_watermark=extracted if watermark_found else None,
        phash_distance=int(dist),
        details=details if details else None
    )

if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)
