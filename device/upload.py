from microdot import Response
import json
import os
from log import log


async def handle_upload(request, target_path=None):
    """Handle file uploads, including chunked uploads"""
    try:
        # Check if this is a chunked upload
        chunk_index = request.headers.get("X-Chunk-Index")
        total_chunks = request.headers.get("X-Total-Chunks")
        is_complete = request.headers.get("X-Is-Complete") == "true"

        if chunk_index is not None and total_chunks is not None:
            # Handle chunked upload
            chunk_index = int(chunk_index)
            total_chunks = int(total_chunks)

            # MicroPython-compatible directory creation
            if target_path and "/" in target_path:
                try:
                    dir_path = target_path.rsplit("/", 1)[0]
                    try:
                        os.mkdir(dir_path)
                    except:
                        # Directory might already exist
                        pass
                except:
                    # If any error occurs, continue anyway
                    pass

            # Save this chunk to a temporary file
            temp_path = f"{target_path}.part{chunk_index}"
            f = open(temp_path, "wb")
            f.write(request.body)
            f.close()

            log(
                f"Saved chunk {chunk_index+1}/{total_chunks} ({len(request.body)} bytes) to {temp_path}"
            )

            # If this is the last chunk or we received a completion request, combine chunks
            if chunk_index == total_chunks - 1 or is_complete:
                try:
                    # Combine all chunks
                    final_file = open(target_path, "wb")
                    total_size = 0
                    for i in range(total_chunks):
                        part_path = f"{target_path}.part{i}"
                        # Skip if part file doesn't exist
                        try:
                            # Check if file exists by trying to open it
                            part_file = open(part_path, "rb")
                            part_file.close()
                        except:
                            log(f"Warning: Chunk {i+1}/{total_chunks} is missing")
                            continue

                        # Get file size
                        try:
                            part_size = os.stat(part_path)[6]  # st_size is at index 6
                        except:
                            part_size = 0

                        total_size += part_size

                        # Read in small chunks to avoid memory issues
                        part_file = open(part_path, "rb")
                        bytes_processed = 0
                        while True:
                            data = part_file.read(512)  # Read in 512-byte blocks
                            if not data:
                                break
                            final_file.write(data)
                            bytes_processed += len(data)

                            # Log progress percentage for this chunk
                            if (
                                bytes_processed % 1024 == 0
                                or bytes_processed == part_size
                            ):
                                percent = (bytes_processed / part_size) * 100
                                log(
                                    f"Combining chunk {i+1}/{total_chunks}: {percent:.1f}% ({bytes_processed}/{part_size} bytes)"
                                )

                        part_file.close()

                        # Delete this part file
                        try:
                            os.remove(part_path)
                        except:
                            log(f"Warning: Could not delete temporary file {part_path}")

                    final_file.close()

                    # Get final file size
                    try:
                        file_size = os.stat(target_path)[6]  # st_size is at index 6
                    except:
                        file_size = total_size

                    log(
                        f"Successfully combined {total_chunks} chunks into {target_path} (Total: {total_size} bytes)"
                    )

                    return (
                        json.dumps(
                            {
                                "success": True,
                                "path": target_path,
                                "size": file_size,
                                "chunks": total_chunks,
                            }
                        ),
                        200,
                    )
                except Exception as e:
                    log(f"Error combining chunks: {str(e)}")
                    # Clean up any temporary files
                    for i in range(total_chunks):
                        try:
                            os.remove(f"{target_path}.part{i}")
                        except:
                            pass
                    return (
                        json.dumps(
                            {
                                "success": False,
                                "error": f"Error combining chunks: {str(e)}",
                            }
                        ),
                        500,
                    )
            else:
                # Return success for this chunk
                return (
                    json.dumps(
                        {
                            "success": True,
                            "chunk": chunk_index,
                            "total": total_chunks,
                            "path": temp_path,
                        }
                    ),
                    200,
                )

        # Original upload code for non-chunked uploads
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
                f = open(target_path, "wb")
                f.write(clean_content)
                f.close()

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
