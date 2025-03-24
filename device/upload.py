from microdot import Response
import json
import os
from log import log


async def handle_upload(request, target_path: str | None = None) -> tuple[str, int]:
    try:
        chunk_index = request.headers.get("X-Chunk-Index")
        total_chunks = request.headers.get("X-Total-Chunks")
        is_complete = request.headers.get("X-Is-Complete") == "true"

        content_type = request.headers.get("Content-Type", "").lower()
        if (
            content_type == "application/octet-stream"
            and chunk_index is None
            and total_chunks is None
        ):
            log(f"Direct binary upload detected for {target_path}")

            if target_path and "/" in target_path:
                try:
                    dir_path = target_path.rsplit("/", 1)[0]
                    try:
                        os.mkdir(dir_path)
                    except:
                        pass
                except:
                    pass

            if target_path is None:
                return (
                    json.dumps({"success": False, "error": "Missing target path"}),
                    400,
                )
            with open(target_path, "wb") as f:
                f.write(request.body)

            file_size = len(request.body)
            log(f"Saved file: {target_path} ({file_size} bytes)")

            return (
                json.dumps(
                    {
                        "success": True,
                        "path": target_path,
                        "size": file_size,
                    }
                ),
                200,
            )

        if (
            chunk_index is not None
            and total_chunks is not None
            and int(total_chunks) == 1
        ):
            log(f"Single chunk upload detected, handling as regular upload")

            if target_path and "/" in target_path:
                try:
                    dir_path = target_path.rsplit("/", 1)[0]
                    try:
                        os.mkdir(dir_path)
                    except:
                        pass
                except:
                    pass

            if target_path is None:
                return (
                    json.dumps({"success": False, "error": "Missing target path"}),
                    400,
                )
            with open(target_path, "wb") as f:
                f.write(request.body)

            file_size = len(request.body)
            log(f"Saved file: {target_path} ({file_size} bytes)")

            return (
                json.dumps(
                    {
                        "success": True,
                        "path": target_path,
                        "size": file_size,
                    }
                ),
                200,
            )

        elif chunk_index is not None and total_chunks is not None:
            chunk_index = int(chunk_index)
            total_chunks = int(total_chunks)

            if target_path and "/" in target_path:
                try:
                    dir_path = target_path.rsplit("/", 1)[0]
                    try:
                        os.mkdir(dir_path)
                    except:
                        pass
                except:
                    pass

            if target_path is None:
                return (
                    json.dumps({"success": False, "error": "Missing target path"}),
                    400,
                )
            temp_path = f"{target_path}.part{chunk_index}"
            with open(temp_path, "wb") as f:
                f.write(request.body)

            log(
                f"Saved chunk {chunk_index+1}/{total_chunks} ({len(request.body)} bytes) to {temp_path}"
            )

            if chunk_index == total_chunks - 1 or is_complete:
                try:
                    if target_path is None:
                        return (
                            json.dumps(
                                {"success": False, "error": "Missing target path"}
                            ),
                            400,
                        )
                    total_size = 0
                    with open(target_path, "wb") as final_file:
                        for i in range(total_chunks):
                            part_path = f"{target_path}.part{i}"
                            try:
                                part_file = open(part_path, "rb")
                                part_file.close()
                            except:
                                log(f"Warning: Chunk {i+1}/{total_chunks} is missing")
                                continue

                            try:
                                part_size = os.stat(part_path)[6]
                            except:
                                part_size = 0

                            total_size += part_size

                            bytes_processed = 0
                            with open(part_path, "rb") as part_file:
                                while True:
                                    data = part_file.read(512)
                                    if not data:
                                        break
                                    final_file.write(data)
                                    bytes_processed += len(data)

                                    if (
                                        bytes_processed % 1024 == 0
                                        or bytes_processed == part_size
                                    ):
                                        percent = (bytes_processed / part_size) * 100
                                        log(
                                            f"Combining chunk {i+1}/{total_chunks}: {percent:.1f}% ({bytes_processed}/{part_size} bytes)"
                                        )

                            try:
                                os.remove(part_path)
                            except:
                                log(
                                    f"Warning: Could not delete temporary file {part_path}"
                                )

                    try:
                        file_size = os.stat(target_path)[6]
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

        content_type = request.headers.get("Content-Type", "").lower()
        log(f"Content-Type: {content_type}")

        if (
            "multipart/form-data" not in content_type
            and content_type != "application/octet-stream"
        ):
            return (
                json.dumps(
                    {
                        "success": False,
                        "error": "Only form uploads or binary uploads supported",
                    }
                ),
                400,
            )

        if not target_path:
            return (
                json.dumps(
                    {"success": False, "error": "URL path must specify filename"}
                ),
                400,
            )

        log(f"Form upload request for {target_path}")

        boundary = "--" + content_type.split("boundary=")[-1].strip()
        log(f"Boundary: {boundary}")

        content = request.body
        log(f"Request body size: {len(content)} bytes")

        log(f"Body start: {content[:100]}")

        parts = content.split(boundary.encode())
        log(f"Found {len(parts)} parts")

        for i, part in enumerate(parts):
            if len(part) < 10:
                continue

            header_end = part.find(b"\r\n\r\n")
            if header_end == -1:
                continue

            headers_part = part[:header_end]
            content_part = part[header_end + 4 :]

            if b'name="file"' in headers_part or b"filename=" in headers_part:
                log(f"Found file part in part {i}")

                if b"\r\n--" in content_part:
                    clean_content = content_part.split(b"\r\n--")[0]
                else:
                    last_crlf = content_part.rfind(b"\r\n")
                    if last_crlf > 0:
                        clean_content = content_part[:last_crlf]
                    else:
                        clean_content = content_part

                log(f"Clean content size: {len(clean_content)} bytes")
                if len(clean_content) < 100:
                    log(f"Clean content: {clean_content}")

                if target_path is None:
                    return (
                        json.dumps({"success": False, "error": "Missing target path"}),
                        400,
                    )
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

        log("No file part found in the form data")
        return json.dumps({"success": False, "error": "No file found in form"}), 400

    except Exception as e:
        log(f"Upload error: {str(e)}")
        return json.dumps({"success": False, "error": str(e)}), 500
