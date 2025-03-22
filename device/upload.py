from microdot import Response
import json
import os
from log import log


async def handle_upload(request, target_path=None):
    """Handle multipart/form-data file uploads"""
    try:
        # Get content type and validate
        content_type = request.headers.get("Content-Type", "").lower()
        log(f"Content-Type: {content_type}")

        if "multipart/form-data" not in content_type:
            return (
                json.dumps({"success": False, "error": "Only form uploads supported"}),
                400,
            )

        # Get target filename from URL path
        if not target_path:
            return (
                json.dumps(
                    {"success": False, "error": "URL path must specify filename"}
                ),
                400,
            )

        log(f"Form upload request for {target_path}")

        # Extract boundary from content type
        boundary = "--" + content_type.split("boundary=")[-1].strip()
        log(f"Boundary: {boundary}")

        # Process multipart data
        content = request.body
        log(f"Request body size: {len(content)} bytes")

        # Debug: Log the first 100 bytes of the body
        log(f"Body start: {content[:100]}")

        # Split by boundary
        parts = content.split(boundary.encode())
        log(f"Found {len(parts)} parts")

        # Process each part
        for i, part in enumerate(parts):
            # Skip empty parts
            if len(part) < 10:
                continue

            # Find header/body separator
            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue

            # Extract headers and content
            headers_part = part[:header_end]
            content_part = part[header_end + 4 :]  # Skip header separator

            # Check if this is a file part
            if b'name="file"' in headers_part or b"filename=" in headers_part:
                log(f"Found file part in part {i}")

                # Extract just the file content
                # Find the end of the content (before the next boundary or end of part)
                # The content ends with \r\n-- or just \r\n at the end of the request
                if b"\r\n--" in content_part:
                    clean_content = content_part.split(b"\r\n--")[0]
                else:
                    # If no boundary marker, find the last \r\n
                    last_crlf = content_part.rfind(b"\r\n")
                    if last_crlf > 0:
                        clean_content = content_part[:last_crlf]
                    else:
                        clean_content = content_part

                # Debug: Log the content
                log(f"Clean content size: {len(clean_content)} bytes")
                if len(clean_content) < 100:
                    log(f"Clean content: {clean_content}")

                # Write the file
                with open(target_path, "wb") as f:
                    f.write(clean_content)

                log(f"Saved file: {target_path} ({len(clean_content)} bytes)")
                return (
                    json.dumps(
                        {
                            "success": True,
                            "path": target_path,
                            "size": len(clean_content),
                        }
                    ),
                    200,
                )

        # If we get here, no file part was found
        log("No file part found in the form data")
        return json.dumps({"success": False, "error": "No file found in form"}), 400

    except Exception as e:
        log(f"Upload error: {str(e)}")
        return json.dumps({"success": False, "error": str(e)}), 500
