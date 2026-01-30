"""
FlowLite API Plugin for ComfyUI

Adds lightweight endpoints for FlowLite integration:
- /flowlite/catalog - Slim model/lora/vae/sampler lists (instead of heavy /object_info)
- /flowlite/image - Image download with optional PNG→JPEG compression

Install: Copy this folder to ComfyUI/custom_nodes/flowlite_api/
"""

import time
import os
import io

# Global cache for catalog
_catalog_cache = {"ts": 0, "data": None}
CACHE_TTL = float(os.environ.get("FLOWLITE_CATALOG_TTL", "30"))
JPEG_QUALITY = int(os.environ.get("FLOWLITE_JPEG_QUALITY", "85"))
# Delete original file after successful transfer (saves disk space)
DELETE_AFTER_SEND = os.environ.get("FLOWLITE_DELETE_AFTER_SEND", "1").lower() in ("1", "true", "yes")


def _extract_list(object_info, keys, debug_info=None):
    """Extract unique values from object_info for given input keys."""
    out = []
    for node_name, spec in object_info.items():
        if not isinstance(spec, dict):
            continue
        inp = spec.get("input")
        if not isinstance(inp, dict):
            continue
        req = inp.get("required") if isinstance(inp.get("required"), dict) else {}
        opt = inp.get("optional") if isinstance(inp.get("optional"), dict) else {}
        for k in keys:
            lspec = req.get(k) or opt.get(k)
            if not lspec:
                continue
            if isinstance(lspec, (list, tuple)) and lspec:
                first = lspec[0]
                if isinstance(first, (list, tuple)):
                    for item in first:
                        if isinstance(item, str) and item.strip():
                            out.append(item.strip())
                    # Debug: log what we found
                    if debug_info is not None and first:
                        debug_info.append({"node": node_name, "key": k, "count": len(first), "sample": list(first)[:3]})
    seen = set()
    deduped = []
    for name in out:
        if name not in seen:
            seen.add(name)
            deduped.append(name)
    return deduped


def _extract_loras(object_info, debug_info=None):
    """Extract LoRA names from LoRA-related nodes."""
    out = []
    for key, spec in object_info.items():
        if not isinstance(key, str) or "lora" not in key.lower():
            continue
        if not isinstance(spec, dict):
            continue
        inp = spec.get("input")
        if not isinstance(inp, dict):
            continue
        req = inp.get("required") if isinstance(inp.get("required"), dict) else {}
        opt = inp.get("optional") if isinstance(inp.get("optional"), dict) else {}
        lspec = req.get("lora_name") or opt.get("lora_name")
        if not lspec:
            continue
        if isinstance(lspec, (list, tuple)) and lspec:
            first = lspec[0]
            if isinstance(first, (list, tuple)):
                for item in first:
                    if isinstance(item, str) and item.strip():
                        out.append(item.strip())
                # Debug
                if debug_info is not None and first:
                    debug_info.append({"node": key, "key": "lora_name", "count": len(first), "sample": list(first)[:3]})
    seen = set()
    deduped = []
    for name in out:
        if name not in seen:
            seen.add(name)
            deduped.append(name)
    return deduped


def _build_catalog(object_info, debug=False):
    """Build slim catalog from object_info."""
    debug_info = [] if debug else None
    
    result = {
        "ts": time.time(),
        "models": {
            "all": _extract_list(object_info, ["unet_name", "ckpt_name", "model_name"], debug_info),
            "ckpt": _extract_list(object_info, ["ckpt_name", "model_name"], debug_info),
            "unet": _extract_list(object_info, ["unet_name"], debug_info),
        },
        "loras": _extract_loras(object_info, debug_info),
        "vae": _extract_list(object_info, ["vae_name", "vae"], debug_info),
        "samplers": _extract_list(object_info, ["sampler_name"], debug_info),
        "schedulers": _extract_list(object_info, ["scheduler"], debug_info),
    }
    
    if debug:
        result["extraction_debug"] = debug_info
    
    return result


def _compress_to_jpeg(data, quality=85):
    """Convert PNG/image to JPEG with specified quality."""
    try:
        from PIL import Image
    except ImportError:
        return data, "image/png"
    
    try:
        img = Image.open(io.BytesIO(data))
        if img.mode in ("RGBA", "LA", "P"):
            background = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            if img.mode in ("RGBA", "LA"):
                background.paste(img, mask=img.split()[-1])
            else:
                background.paste(img)
            img = background
        elif img.mode != "RGB":
            img = img.convert("RGB")
        
        output = io.BytesIO()
        img.save(output, format="JPEG", quality=quality, optimize=True)
        return output.getvalue(), "image/jpeg"
    except Exception as e:
        print(f"[FlowLite] JPEG compression failed: {e}")
        return data, "image/png"


# ============================================================================
# ComfyUI integration - register routes
# ============================================================================

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

try:
    from aiohttp import web
    from server import PromptServer
    import folder_paths
    
    @PromptServer.instance.routes.get("/flowlite/catalog")
    async def flowlite_catalog(request):
        """Return slim catalog with model/lora/vae/sampler lists."""
        global _catalog_cache
        
        refresh = request.query.get("refresh", "0") == "1"
        debug = request.query.get("debug", "0") == "1"
        now = time.time()
        
        if not refresh and _catalog_cache["data"] and (now - _catalog_cache["ts"]) < CACHE_TTL:
            return web.json_response({"ok": True, **_catalog_cache["data"]})
        
        try:
            from nodes import NODE_CLASS_MAPPINGS as NCM
            
            object_info = {}
            sample_inputs = []  # For debug
            for name, cls in NCM.items():
                try:
                    inp = cls.INPUT_TYPES() if hasattr(cls, "INPUT_TYPES") else {}
                    object_info[name] = {"input": inp}
                    # Capture a few samples for debug
                    if len(sample_inputs) < 3 and inp:
                        sample_inputs.append({"node": name, "input": inp})
                except Exception as e:
                    pass
            
            catalog = _build_catalog(object_info, debug=debug)
            _catalog_cache = {"ts": now, "data": _build_catalog(object_info, debug=False)}
            
            if debug:
                return web.json_response({
                    "ok": True,
                    "node_count": len(NCM),
                    "sample_inputs": sample_inputs,
                    **catalog
                })
            
            return web.json_response({"ok": True, **catalog})
        except Exception as e:
            print(f"[FlowLite] catalog error: {e}")
            import traceback
            traceback.print_exc()
            return web.json_response({"ok": False, "error": str(e)}, status=500)
    
    
    @PromptServer.instance.routes.get("/flowlite/image")
    async def flowlite_image(request):
        """Download image with optional PNG→JPEG compression."""
        filename = request.query.get("filename", "")
        subfolder = request.query.get("subfolder", "")
        img_type = request.query.get("type", "output")
        compress = request.query.get("compress", "1") == "1"
        delete_after = request.query.get("delete", "1" if DELETE_AFTER_SEND else "0") == "1"
        quality = int(request.query.get("quality", str(JPEG_QUALITY)))
        quality = max(1, min(100, quality))
        
        if not filename:
            return web.json_response({"error": "filename required"}, status=400)
        
        try:
            if img_type == "output":
                base_dir = folder_paths.get_output_directory()
            elif img_type == "input":
                base_dir = folder_paths.get_input_directory()
            elif img_type == "temp":
                base_dir = folder_paths.get_temp_directory()
            else:
                base_dir = folder_paths.get_output_directory()
            
            if subfolder:
                full_path = os.path.join(base_dir, subfolder, filename)
            else:
                full_path = os.path.join(base_dir, filename)
            
            full_path = os.path.realpath(full_path)
            base_real = os.path.realpath(base_dir)
            if not full_path.startswith(base_real):
                return web.json_response({"error": "Invalid path"}, status=403)
            
            if not os.path.exists(full_path):
                return web.json_response({"error": "File not found"}, status=404)
            
            with open(full_path, "rb") as f:
                data = f.read()
            
            original_size = len(data)
            content_type = "image/png"
            
            was_compressed = False
            if compress and (filename.lower().endswith(".png") or data[:8] == b'\x89PNG\r\n\x1a\n'):
                data, content_type = _compress_to_jpeg(data, quality)
                compressed_size = len(data)
                ratio = original_size / compressed_size if compressed_size > 0 else 1
                was_compressed = True
                print(f"[FlowLite] 📤 Image sent: {filename}")
                print(f"[FlowLite]    PNG→JPEG: {original_size//1024}KB → {compressed_size//1024}KB ({ratio:.1f}x compression)")
            else:
                print(f"[FlowLite] 📤 Image sent: {filename} ({original_size//1024}KB, no compression)")
            
            # Delete original file after successful compression and send
            deleted = False
            if delete_after and was_compressed and os.path.exists(full_path):
                try:
                    os.remove(full_path)
                    deleted = True
                    print(f"[FlowLite]    🗑️ Deleted original: {filename}")
                except Exception as del_err:
                    print(f"[FlowLite]    ⚠️ Failed to delete {filename}: {del_err}")
            
            return web.Response(
                body=data,
                content_type=content_type,
                headers={
                    "X-Original-Size": str(original_size),
                    "X-Compressed-Size": str(len(data)),
                    "X-Deleted": "1" if deleted else "0",
                }
            )
        except Exception as e:
            print(f"[FlowLite] image error: {e}")
            return web.json_response({"error": str(e)}, status=500)
    
    
    @PromptServer.instance.routes.get("/flowlite/health")
    async def flowlite_health(request):
        """Health check endpoint."""
        return web.json_response({"ok": True, "plugin": "flowlite"})
    
    print("[FlowLite] API plugin loaded: /flowlite/catalog, /flowlite/image, /flowlite/health")

except Exception as e:
    print(f"[FlowLite] Failed to register routes: {e}")
