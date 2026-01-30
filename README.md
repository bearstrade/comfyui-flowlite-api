# FlowLite API Plugin for ComfyUI

Lightweight API endpoints for FlowLite integration with ComfyUI.

## Features

- **`/flowlite/catalog`** - Slim model/lora/vae/sampler lists (~5KB instead of ~3MB from `/object_info`)
- **`/flowlite/image`** - Image download with optional PNG→JPEG compression (5-8x smaller files)
- **`/flowlite/health`** - Health check endpoint

## Installation

### Via ComfyUI Manager (Recommended)

1. Open ComfyUI Manager
2. Click **"Install via Git URL"**
3. Enter: `https://github.com/aspect-build/comfyui-flowlite-api`
4. Restart ComfyUI

### Manual Installation

```bash
cd ComfyUI/custom_nodes
git clone https://github.com/aspect-build/comfyui-flowlite-api flowlite_api
```

Or copy the folder manually:

```bash
cp -r comfyui_flowlite_plugin /path/to/ComfyUI/custom_nodes/flowlite_api
```

Restart ComfyUI. You should see in the logs:
```
[FlowLite] API plugin loaded: /flowlite/catalog, /flowlite/image, /flowlite/health
```

## Configuration (Environment Variables)

| Variable | Default | Description |
|----------|---------|-------------|
| `FLOWLITE_CATALOG_TTL` | `30` | Catalog cache TTL in seconds |
| `FLOWLITE_JPEG_QUALITY` | `85` | JPEG compression quality (1-100) |
| `FLOWLITE_DELETE_AFTER_SEND` | `1` | Delete original PNG after sending compressed JPEG |

## API Endpoints

### GET /flowlite/catalog

Returns slim catalog with model/lora/vae/sampler lists.

**Query params:**
- `refresh=1` - Force refresh cache (default: use cache for 30s)
- `debug=1` - Include extraction debug info

**Response:**
```json
{
  "ok": true,
  "ts": 1706612345.123,
  "models": {
    "all": ["model1.safetensors", "model2.safetensors"],
    "ckpt": ["model1.safetensors"],
    "unet": ["flux1-dev.safetensors"]
  },
  "loras": ["lora1.safetensors", "lora2.safetensors"],
  "vae": ["vae1.safetensors"],
  "samplers": ["euler", "euler_ancestral", "dpmpp_2m"],
  "schedulers": ["normal", "karras", "sgm_uniform"]
}
```

### GET /flowlite/image

Download image with optional PNG→JPEG compression for faster transfer over slow connections.

**Query params:**
- `filename` - Image filename (required)
- `subfolder` - Subfolder (default: "")
- `type` - Image type: output/input/temp (default: "output")
- `compress` - 1=compress to JPEG, 0=original (default: 1)
- `quality` - JPEG quality 1-100 (default: 85)

**Response headers:**
- `X-Original-Size` - Original file size in bytes
- `X-Compressed-Size` - Compressed size in bytes

**Example:**
```
GET /flowlite/image?filename=ComfyUI_00001_.png&compress=1&quality=85
```

Typical compression: 1.7MB PNG → 200-300KB JPEG (5-8x reduction)

### GET /flowlite/health

Health check endpoint.

**Response:**
```json
{"ok": true, "plugin": "flowlite"}
```

## Configuration

Environment variables:

- `FLOWLITE_CATALOG_TTL` - Catalog cache TTL in seconds (default: 30)
- `FLOWLITE_JPEG_QUALITY` - Default JPEG compression quality (default: 85)

## Requirements

- ComfyUI (any recent version)
- Pillow (for JPEG compression, usually already installed with ComfyUI)

## Usage from FlowLite

FlowLite backend will automatically detect and use these endpoints when available on the same ComfyUI instance. No additional proxy server needed!

Configure in FlowLite:
- Set ComfyUI URL as usual (e.g., `http://10.62.180.6:8188`)
- The backend will try `/flowlite/catalog` and `/flowlite/image` automatically
