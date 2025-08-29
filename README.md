# Invisible Watermark API

A FastAPI service for embedding and verifying invisible watermarks in images using blind watermarking techniques.

## Features

- **Embed Watermarks**: Add invisible watermarks to images with text-based watermarks
- **Verify Watermarks**: Extract and verify watermarks from potentially modified images
- **Geometric Recovery**: Automatic recovery of watermarks from cropped or scaled images
- **Persistent Storage**: Server-side storage of watermarked images with unique URLs
- **RESTful API**: Easy-to-use HTTP endpoints with automatic documentation

## Technology Stack

- **FastAPI**: Modern, fast web framework for building APIs
- **OpenCV**: Computer vision library for image processing
- **NumPy**: Numerical computing library
- **blind-watermark**: Core watermarking algorithms

## Installation

1. Clone the repository:
```bash
git clone https://github.com/qbit-codes/invisible-watermark-api.git
cd invisible-watermark-api
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env file with your preferred settings
```

4. Run the application:
```bash
python main.py
```

The API will be available at `http://localhost:8000` with interactive documentation at `http://localhost:8000/docs`.

## API Endpoints

### POST /embed
Embed an invisible watermark into an image.

**Parameters:**
- `file`: Image file (multipart/form-data)
- `wm_text`: Watermark text (optional, auto-generated if not provided)

**Response:**
- `watermark_id`: Unique identifier for the watermark
- `watermarked_image_base64`: Base64 encoded watermarked image
- `file_url`: Persistent URL to access the watermarked image
- `wm_len`: Length of the watermark bits

### POST /verify
Verify and extract watermark from an image.

**Parameters:**
- `file`: Image file to verify (multipart/form-data)
- `watermark_id`: ID of the original watermark
- `try_recover`: Attempt geometric recovery (default: true)

**Response:**
- `watermark_found`: Boolean indicating if watermark was detected
- `matches_expected`: Boolean indicating if extracted watermark matches original
- `status`: Status description ("same", "modified_but_watermark_intact", or "tampered_or_not_watermarked")
- `extracted_watermark`: The extracted watermark text
- `phash_distance`: Perceptual hash distance from original

## Environment Variables

- `WM_PASS_IMG`: Password for image processing (default: 1)
- `WM_PASS_WM`: Password for watermark processing (default: 1)

## Credits

This project uses the [blind-watermark](https://github.com/guofei9987/blind_watermark) library for core watermarking functionality.
