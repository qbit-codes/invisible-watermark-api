# Node.js/Express Integration Guide

This guide shows how to integrate a Node.js/Express backend with the Invisible Watermark API.

## Prerequisites

- Node.js/Express backend application
- The Invisible Watermark API running on `http://localhost:8000`
- Required npm packages: `axios`, `form-data`, `multer` (for file uploads)

## Installation

```bash
npm install axios form-data multer
```

## Basic Integration

### 1. Embed Watermark

```javascript
const axios = require('axios');
const FormData = require('form-data');
const fs = require('fs');

async function embedWatermark(imagePath, watermarkText = null) {
    try {
        const form = new FormData();
        form.append('file', fs.createReadStream(imagePath));
        
        if (watermarkText) {
            form.append('wm_text', watermarkText);
        }

        const response = await axios.post('http://localhost:8000/embed', form, {
            headers: {
                ...form.getHeaders(),
            },
        });

        return response.data;
        // Returns: { watermark_id, wm_len, watermarked_image_base64, message, file_url }
    } catch (error) {
        console.error('Embed error:', error.response?.data || error.message);
        throw error;
    }
}
```

### 2. Verify Watermark

```javascript
async function verifyWatermark(imagePath, watermarkId, tryRecover = true) {
    try {
        const form = new FormData();
        form.append('file', fs.createReadStream(imagePath));
        form.append('watermark_id', watermarkId);
        form.append('try_recover', tryRecover.toString());

        const response = await axios.post('http://localhost:8000/verify', form, {
            headers: {
                ...form.getHeaders(),
            },
        });

        return response.data;
        // Returns: { watermark_found, matches_expected, extracted_watermark, details }
    } catch (error) {
        console.error('Verify error:', error.response?.data || error.message);
        throw error;
    }
}
```

## Express Route Examples

### Complete Express Server Example

```javascript
const express = require('express');
const multer = require('multer');
const axios = require('axios');
const FormData = require('form-data');
const fs = require('fs');
const path = require('path');

const app = express();
const port = 3000;

// Configure multer for file uploads
const upload = multer({
    dest: 'uploads/',
    fileFilter: (req, file, cb) => {
        // Accept only image files
        if (file.mimetype.startsWith('image/')) {
            cb(null, true);
        } else {
            cb(new Error('Only image files are allowed'));
        }
    },
    limits: {
        fileSize: 10 * 1024 * 1024, // 10MB limit
    }
});

// Watermarking API base URL
const WATERMARK_API_BASE = 'http://localhost:8000';

// Route: Embed watermark
app.post('/api/watermark/embed', upload.single('image'), async (req, res) => {
    try {
        if (!req.file) {
            return res.status(400).json({ error: 'No image file provided' });
        }

        const { watermark_text } = req.body;
        
        const form = new FormData();
        form.append('file', fs.createReadStream(req.file.path));
        
        if (watermark_text) {
            form.append('wm_text', watermark_text);
        }

        const response = await axios.post(`${WATERMARK_API_BASE}/embed`, form, {
            headers: {
                ...form.getHeaders(),
            },
        });

        // Clean up uploaded file
        fs.unlinkSync(req.file.path);

        res.json({
            success: true,
            data: response.data
        });

    } catch (error) {
        // Clean up uploaded file on error
        if (req.file) {
            fs.unlinkSync(req.file.path);
        }

        res.status(500).json({
            success: false,
            error: error.response?.data?.detail || error.message
        });
    }
});

// Route: Verify watermark
app.post('/api/watermark/verify', upload.single('image'), async (req, res) => {
    try {
        if (!req.file) {
            return res.status(400).json({ error: 'No image file provided' });
        }

        const { watermark_id, try_recover = 'true' } = req.body;

        if (!watermark_id) {
            return res.status(400).json({ error: 'watermark_id is required' });
        }

        const form = new FormData();
        form.append('file', fs.createReadStream(req.file.path));
        form.append('watermark_id', watermark_id);
        form.append('try_recover', try_recover);

        const response = await axios.post(`${WATERMARK_API_BASE}/verify`, form, {
            headers: {
                ...form.getHeaders(),
            },
        });

        // Clean up uploaded file
        fs.unlinkSync(req.file.path);

        res.json({
            success: true,
            data: response.data
        });

    } catch (error) {
        // Clean up uploaded file on error
        if (req.file) {
            fs.unlinkSync(req.file.path);
        }

        res.status(500).json({
            success: false,
            error: error.response?.data?.detail || error.message
        });
    }
});

// Route: Get watermarked image by URL
app.get('/api/watermark/image/:watermark_id', async (req, res) => {
    try {
        const { watermark_id } = req.params;
        const imageUrl = `${WATERMARK_API_BASE}/files/embeds/${watermark_id}.png`;
        
        const response = await axios.get(imageUrl, {
            responseType: 'stream'
        });

        res.set({
            'Content-Type': 'image/png',
            'Content-Disposition': `attachment; filename="${watermark_id}.png"`
        });

        response.data.pipe(res);

    } catch (error) {
        res.status(404).json({
            success: false,
            error: 'Image not found'
        });
    }
});

// Error handling middleware
app.use((error, req, res, next) => {
    if (error instanceof multer.MulterError) {
        if (error.code === 'LIMIT_FILE_SIZE') {
            return res.status(400).json({ error: 'File too large' });
        }
    }
    res.status(500).json({ error: error.message });
});

app.listen(port, () => {
    console.log(`Express server running on port ${port}`);
    console.log(`Make sure Watermark API is running on ${WATERMARK_API_BASE}`);
});
```

## Usage Examples

### Frontend Integration (with HTML form)

```html
<!DOCTYPE html>
<html>
<head>
    <title>Watermark Integration</title>
</head>
<body>
    <h2>Embed Watermark</h2>
    <form id="embedForm" enctype="multipart/form-data">
        <input type="file" name="image" accept="image/*" required>
        <input type="text" name="watermark_text" placeholder="Watermark text (optional)">
        <button type="submit">Embed Watermark</button>
    </form>

    <h2>Verify Watermark</h2>
    <form id="verifyForm" enctype="multipart/form-data">
        <input type="file" name="image" accept="image/*" required>
        <input type="text" name="watermark_id" placeholder="Watermark ID" required>
        <label>
            <input type="checkbox" name="try_recover" checked> Try recovery
        </label>
        <button type="submit">Verify Watermark</button>
    </form>

    <div id="results"></div>

    <script>
        document.getElementById('embedForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            
            try {
                const response = await fetch('/api/watermark/embed', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                document.getElementById('results').innerHTML = 
                    '<h3>Embed Result:</h3><pre>' + JSON.stringify(result, null, 2) + '</pre>';
            } catch (error) {
                console.error('Error:', error);
            }
        });

        document.getElementById('verifyForm').addEventListener('submit', async (e) => {
            e.preventDefault();
            const formData = new FormData(e.target);
            
            try {
                const response = await fetch('/api/watermark/verify', {
                    method: 'POST',
                    body: formData
                });
                const result = await response.json();
                document.getElementById('results').innerHTML = 
                    '<h3>Verify Result:</h3><pre>' + JSON.stringify(result, null, 2) + '</pre>';
            } catch (error) {
                console.error('Error:', error);
            }
        });
    </script>
</body>
</html>
```

### Service Class Example

```javascript
class WatermarkService {
    constructor(apiBaseUrl = 'http://localhost:8000') {
        this.apiBaseUrl = apiBaseUrl;
    }

    async embed(imagePath, watermarkText = null) {
        const form = new FormData();
        form.append('file', fs.createReadStream(imagePath));
        
        if (watermarkText) {
            form.append('wm_text', watermarkText);
        }

        const response = await axios.post(`${this.apiBaseUrl}/embed`, form, {
            headers: { ...form.getHeaders() },
        });

        return response.data;
    }

    async verify(imagePath, watermarkId, tryRecover = true) {
        const form = new FormData();
        form.append('file', fs.createReadStream(imagePath));
        form.append('watermark_id', watermarkId);
        form.append('try_recover', tryRecover.toString());

        const response = await axios.post(`${this.apiBaseUrl}/verify`, form, {
            headers: { ...form.getHeaders() },
        });

        return response.data;
    }

    async downloadWatermarkedImage(watermarkId, outputPath) {
        const imageUrl = `${this.apiBaseUrl}/files/embeds/${watermarkId}.png`;
        const response = await axios.get(imageUrl, { responseType: 'stream' });
        
        const writer = fs.createWriteStream(outputPath);
        response.data.pipe(writer);
        
        return new Promise((resolve, reject) => {
            writer.on('finish', resolve);
            writer.on('error', reject);
        });
    }
}

// Usage
const watermarkService = new WatermarkService();

async function example() {
    // Embed watermark
    const embedResult = await watermarkService.embed('input.jpg', 'My watermark');
    console.log('Embedded:', embedResult);

    // Verify watermark
    const verifyResult = await watermarkService.verify('test.jpg', embedResult.watermark_id);
    console.log('Verification:', verifyResult);

    // Download watermarked image
    await watermarkService.downloadWatermarkedImage(embedResult.watermark_id, 'watermarked.png');
}
```

## Configuration

### Environment Variables (.env)

```env
# Watermark API Configuration
WATERMARK_API_URL=http://localhost:8000
UPLOAD_DIR=uploads/
MAX_FILE_SIZE=10485760  # 10MB in bytes
```

### With Environment Variables

```javascript
require('dotenv').config();

const WATERMARK_API_BASE = process.env.WATERMARK_API_URL || 'http://localhost:8000';
const UPLOAD_DIR = process.env.UPLOAD_DIR || 'uploads/';
const MAX_FILE_SIZE = parseInt(process.env.MAX_FILE_SIZE) || 10 * 1024 * 1024;

const upload = multer({
    dest: UPLOAD_DIR,
    limits: { fileSize: MAX_FILE_SIZE }
});
```

## Error Handling

```javascript
// Comprehensive error handling
app.post('/api/watermark/embed', upload.single('image'), async (req, res) => {
    try {
        // ... embed logic
    } catch (error) {
        let statusCode = 500;
        let errorMessage = 'Internal server error';

        if (error.response) {
            // Axios error with response
            statusCode = error.response.status;
            errorMessage = error.response.data?.detail || error.response.statusText;
        } else if (error.code === 'ECONNREFUSED') {
            statusCode = 503;
            errorMessage = 'Watermark service unavailable';
        } else if (error.code === 'ENOENT') {
            statusCode = 404;
            errorMessage = 'File not found';
        }

        res.status(statusCode).json({
            success: false,
            error: errorMessage
        });
    }
});
```

## Testing

### Unit Test Example (with Jest)

```javascript
const request = require('supertest');
const app = require('./app');

describe('Watermark API Integration', () => {
    test('should embed watermark successfully', async () => {
        const response = await request(app)
            .post('/api/watermark/embed')
            .attach('image', 'test/fixtures/test-image.jpg')
            .field('watermark_text', 'Test watermark');

        expect(response.status).toBe(200);
        expect(response.body.success).toBe(true);
        expect(response.body.data).toHaveProperty('watermark_id');
    });

    test('should verify watermark successfully', async () => {
        // First embed a watermark
        const embedResponse = await request(app)
            .post('/api/watermark/embed')
            .attach('image', 'test/fixtures/test-image.jpg')
            .field('watermark_text', 'Test watermark');

        const watermarkId = embedResponse.body.data.watermark_id;

        // Then verify it
        const verifyResponse = await request(app)
            .post('/api/watermark/verify')
            .attach('image', 'test/fixtures/test-image.jpg')
            .field('watermark_id', watermarkId);

        expect(verifyResponse.status).toBe(200);
        expect(verifyResponse.body.success).toBe(true);
        expect(verifyResponse.body.data.watermark_found).toBe(true);
    });
});
```

## Notes

1. **File Cleanup**: Always clean up uploaded temporary files after processing
2. **Error Handling**: Implement comprehensive error handling for network and file operations
3. **Security**: Validate file types and sizes to prevent abuse
4. **Performance**: Consider implementing request queuing for high-volume scenarios
5. **Monitoring**: Add logging and monitoring for API requests
6. **Scaling**: For production, consider using a reverse proxy and load balancing