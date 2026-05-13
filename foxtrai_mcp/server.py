"""
Foxtrai AI Painting Platform MCP Server

Provides tools for AI image generation via the Foxtrai API:
- Upload reference images
- Create drawing tasks with various models
- Query task status and results
- Manage image assets
"""

from __future__ import annotations

import hashlib
import os
from typing import Annotated

import httpx
from fastmcp import FastMCP
from pydantic import Field

API_BASE = "https://www.foxtrai.com/api/generate"
TOKEN = os.environ.get("FOXTRAI_TOKEN", "")

VALID_MODELS = {"nano-banana-pro", "nano-banana-pro-ultra", "nano-banana-2", "nano-banana", "gpt-image-2"}

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
SEC_CH_UA = '"Chromium";v="125", "Not.A/Brand";v="24", "Google Chrome";v="125"'

mcp = FastMCP(
    "Foxtrai AI Painting",
    instructions=(
        "This server connects to the Foxtrai AI painting platform. "
        "You can upload reference images, create AI drawing tasks with different models "
        "(nano-banana, nano-banana-pro, nano-banana-pro-ultra, nano-banana-2, gpt-image-2), "
        "check task progress, and manage generated assets."
    ),
)


def _headers() -> dict[str, str]:
    return {
        "Authorization": f"Bearer {TOKEN}",
        "Content-Type": "application/json",
        "User-Agent": USER_AGENT,
        "sec-ch-ua": SEC_CH_UA,
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
    }


def _check_response(resp: httpx.Response) -> dict:
    data = resp.json()
    if data.get("code", 0) != 0:
        raise RuntimeError(f"API error ({data.get('code')}): {data.get('msg') or data.get('message', 'unknown error')}")
    resp.raise_for_status()
    return data


# ---------------------------------------------------------------------------
# Upload tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def upload_image(
    file_path: Annotated[str, Field(description="Local image file path to upload")],
) -> str:
    """
    Upload a local image to Foxtrai platform as a reference/input image.
    Returns the asset_id that can be used in drawing tasks.
    Supports PNG, JPEG, WebP formats. Max 4MB, min 256x256 pixels.
    """
    from PIL import Image as PILImage

    img = PILImage.open(file_path)
    width, height = img.size

    with open(file_path, "rb") as f:
        file_bytes = f.read()

    file_size = len(file_bytes)
    if file_size > 4 * 1024 * 1024:
        return "Error: file exceeds 4MB limit"
    if width < 256 or height < 256:
        return f"Error: image dimensions {width}x{height} too small (min 256x256)"

    file_hash = hashlib.sha256(file_bytes).hexdigest()
    filename = os.path.basename(file_path)

    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else "png"
    mime_map = {"png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "webp": "image/webp"}
    mime_type = mime_map.get(ext, "image/png")

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{API_BASE}/image/upload",
            headers=_headers(),
            json={
                "filename": filename,
                "mime_type": mime_type,
                "size": file_size,
                "hash": file_hash,
                "width": width,
                "height": height,
            },
        )
        result = _check_response(resp)
        data = result.get("data", {})
        asset_id = data.get("asset_id", "")
        upload_url = data.get("upload_url", "")
        is_hit = data.get("is_hit", False)

        if is_hit or not upload_url:
            return f"Upload complete (instant). asset_id: {asset_id}"

        put_resp = await client.put(
            upload_url,
            content=file_bytes,
            headers={"Content-Type": mime_type, "User-Agent": USER_AGENT},
        )
        put_resp.raise_for_status()

        check_resp = await client.get(
            f"{API_BASE}/image",
            headers=_headers(),
            params={"asset_id": asset_id},
        )
        check_resp.raise_for_status()

    return f"Upload complete. asset_id: {asset_id}"


# ---------------------------------------------------------------------------
# Drawing task tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def create_drawing_task(
    prompt: Annotated[str, Field(description="Text prompt describing the image to generate (max 20000 chars)")],
    model: Annotated[
        str,
        Field(
            description="Model identifier: nano-banana-pro (default), nano-banana-pro-ultra, nano-banana-2, nano-banana, or gpt-image-2",
            default="nano-banana-pro",
        ),
    ] = "nano-banana-pro",
    input_asset_ids: Annotated[
        list[str] | None,
        Field(description="Reference image asset IDs (from upload_image), max 5"),
    ] = None,
    aspect_ratio: Annotated[
        str | None,
        Field(description="Aspect ratio: 1:1, 16:9, 9:16, 3:4, 4:3, or auto"),
    ] = None,
    resolution: Annotated[
        str | None,
        Field(description="Resolution/quality: 1K (default), 2K, or 4K"),
    ] = None,
    safe_generation: Annotated[
        bool,
        Field(description="Enable safe generation mode (refund if blocked by content filter)"),
    ] = False,
) -> str:
    """
    Submit an AI drawing task to generate an image.
    Returns a task_id for tracking progress via get_task_status.
    """
    if model not in VALID_MODELS:
        return f"Error: invalid model '{model}'. Must be one of: {', '.join(sorted(VALID_MODELS))}"

    body: dict = {"prompt": prompt, "model": model, "safe_generation": safe_generation}
    if input_asset_ids:
        body["input_asset_ids"] = input_asset_ids[:5]
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if resolution:
        body["resolution"] = resolution

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{API_BASE}/image/task/create",
            headers=_headers(),
            json=body,
        )
        result = _check_response(resp)
        task_id = result.get("data", {}).get("task_id", "")

    return f"Task created. task_id: {task_id}. Use get_task_status to check progress."


@mcp.tool()
async def get_task_status(
    task_id: Annotated[str, Field(description="The task ID returned by create_drawing_task")],
) -> dict:
    """
    Query the status and result of a drawing task.
    Status flow: pending -> processing -> success/failed.
    When status is 'success', the result includes output image URLs.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API_BASE}/image/task",
            headers=_headers(),
            params={"task_id": task_id},
        )
        result = _check_response(resp)

    task_data = result.get("data", result)
    return {
        "id": task_data.get("id"),
        "status": task_data.get("status"),
        "progress": task_data.get("progress"),
        "prompt": task_data.get("prompt"),
        "model": task_data.get("model"),
        "error_msg": task_data.get("error_msg", ""),
        "outputs": [
            {
                "asset_id": o.get("asset_id") or o.get("id"),
                "width": o.get("width"),
                "height": o.get("height"),
                "mime_type": o.get("mime_type"),
            }
            for o in task_data.get("edges", {}).get("outputs", [])
        ],
    }


@mcp.tool()
async def list_tasks(
    page: Annotated[int, Field(description="Page number")] = 1,
    size: Annotated[int, Field(description="Items per page (max 50)")] = 10,
    status: Annotated[
        str | None,
        Field(description="Filter by status: pending, processing, success, or failed"),
    ] = None,
    model: Annotated[str | None, Field(description="Filter by model name (fuzzy match)")] = None,
    start_time: Annotated[int | None, Field(description="Start time as Unix timestamp")] = None,
    end_time: Annotated[int | None, Field(description="End time as Unix timestamp")] = None,
) -> dict:
    """
    List historical drawing tasks with pagination and optional filters.
    """
    params: dict = {"page": page, "size": min(size, 50)}
    if status:
        params["status"] = status
    if model:
        params["model"] = model
    if start_time is not None:
        params["start_time"] = start_time
    if end_time is not None:
        params["end_time"] = end_time

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API_BASE}/image/tasks",
            headers=_headers(),
            params=params,
        )
        result = _check_response(resp)

    data = result.get("data", result)
    return {
        "total": data.get("total", 0),
        "items": [
            {
                "id": item.get("id"),
                "status": item.get("status"),
                "prompt": item.get("prompt"),
                "model": item.get("model"),
                "outputs": [
                    {
                        "asset_id": o.get("asset_id") or o.get("id"),
                        "width": o.get("width"),
                        "height": o.get("height"),
                    }
                    for o in item.get("edges", {}).get("outputs", [])
                ],
            }
            for item in data.get("items", [])
        ],
    }


# ---------------------------------------------------------------------------
# Asset management tools
# ---------------------------------------------------------------------------


@mcp.tool()
async def list_assets(
    page: Annotated[int, Field(description="Page number")] = 1,
    size: Annotated[int, Field(description="Items per page (max 60)")] = 10,
    source: Annotated[
        str | None,
        Field(description="Filter by source: 'generated' or 'uploaded'"),
    ] = None,
    asset_id: Annotated[str | None, Field(description="Query a specific asset by ID")] = None,
) -> dict:
    """
    List image assets (uploaded references and generated results).
    """
    params: dict = {"page": page, "size": min(size, 60), "media_type": "image"}
    if source:
        params["source"] = source
    if asset_id:
        params["asset_id"] = asset_id

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{API_BASE}/image/assets",
            headers=_headers(),
            params=params,
        )
        result = _check_response(resp)

    data = result.get("data", result)
    return {
        "total": data.get("total", 0),
        "items": [
            {
                "asset_id": item.get("id"),
                "width": item.get("width"),
                "height": item.get("height"),
                "created_at": item.get("created_at"),
            }
            for item in data.get("items", [])
        ],
    }


@mcp.tool()
async def download_asset(
    asset_id: Annotated[str, Field(description="The asset ID to download")],
    output_path: Annotated[
        str | None,
        Field(description="Output file path. If not provided, returns base64-encoded image data"),
    ] = None,
) -> str:
    """Download an image asset by its asset_id."""
    import base64

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.get(
            f"{API_BASE}/image/assets",
            headers=_headers(),
            params={"media_type": "image", "size": 60},
        )
        result = _check_response(resp)

    data = result.get("data", {})
    items = data.get("items", [])
    asset = next((item for item in items if item.get("id") == asset_id), None)

    if not asset:
        return f"Error: Asset {asset_id} not found"

    download_url = asset.get("url", "")
    if not download_url:
        return f"Error: No download URL found for asset {asset_id}"

    download_headers = {
        "User-Agent": USER_AGENT,
        "Accept": "image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://www.foxtrai.com/",
    }
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(download_url, headers=download_headers)
        resp.raise_for_status()
        content = resp.content

    if output_path:
        with open(output_path, "wb") as f:
            f.write(content)
        return f"Image downloaded to: {output_path}"
    else:
        b64_data = base64.b64encode(content).decode("utf-8")
        return b64_data


@mcp.tool()
async def delete_asset(
    asset_id: Annotated[str, Field(description="The asset ID to delete")],
) -> str:
    """
    Delete an image asset (both database record and cloud storage file).
    This action is irreversible.
    """
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.request(
            "DELETE",
            f"{API_BASE}/image/asset",
            headers=_headers(),
            json={"asset_id": asset_id},
        )
        resp.raise_for_status()

    return f"Asset {asset_id} deleted successfully."


# ---------------------------------------------------------------------------
# Convenience: generate and wait
# ---------------------------------------------------------------------------


@mcp.tool()
async def generate_image(
    prompt: Annotated[str, Field(description="Text prompt describing the image to generate")],
    model: Annotated[str, Field(description="Model identifier")] = "nano-banana-pro",
    input_asset_ids: Annotated[list[str] | None, Field(description="Reference image asset IDs")] = None,
    aspect_ratio: Annotated[str | None, Field(description="Aspect ratio")] = None,
    resolution: Annotated[str | None, Field(description="Resolution: 1K, 2K, 4K")] = None,
    safe_generation: Annotated[bool, Field(description="Safe generation mode")] = False,
    poll_interval: Annotated[int, Field(description="Seconds between status checks")] = 3,
    max_wait: Annotated[int, Field(description="Max seconds to wait before timeout")] = 300,
) -> dict:
    """
    All-in-one: create a drawing task, poll until done, and return the result.
    Combines create_drawing_task + get_task_status with automatic polling.
    """
    import asyncio

    if model not in VALID_MODELS:
        return {"status": "failed", "error_msg": f"Invalid model '{model}'. Must be one of: {', '.join(sorted(VALID_MODELS))}"}

    body: dict = {"prompt": prompt, "model": model, "safe_generation": safe_generation}
    if input_asset_ids:
        body["input_asset_ids"] = input_asset_ids[:5]
    if aspect_ratio:
        body["aspect_ratio"] = aspect_ratio
    if resolution:
        body["resolution"] = resolution

    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{API_BASE}/image/task/create",
            headers=_headers(),
            json=body,
        )
        result = _check_response(resp)
        task_id = result.get("data", {}).get("task_id", "")

    elapsed = 0
    while elapsed < max_wait:
        await asyncio.sleep(poll_interval)
        elapsed += poll_interval

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{API_BASE}/image/task",
                headers=_headers(),
                params={"task_id": task_id},
            )
            result = _check_response(resp)

        task_data = result.get("data", result)
        status = task_data.get("status")

        if status == "success":
            outputs = task_data.get("edges", {}).get("outputs", [])
            return {
                "task_id": task_id,
                "status": "success",
                "prompt": task_data.get("prompt"),
                "model": task_data.get("model"),
                "outputs": [
                    {
                        "asset_id": o.get("asset_id") or o.get("id"),
                        "width": o.get("width"),
                        "height": o.get("height"),
                        "mime_type": o.get("mime_type"),
                    }
                    for o in outputs
                ],
            }

        if status == "failed":
            return {
                "task_id": task_id,
                "status": "failed",
                "error_msg": task_data.get("error_msg", "Unknown error"),
            }

    return {"task_id": task_id, "status": "timeout", "error_msg": f"Task did not finish within {max_wait}s"}


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    mcp.run()


if __name__ == "__main__":
    main()
