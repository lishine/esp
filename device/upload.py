from microdot import Response
import json
import os
from log import log


def error_response(message, status=400):
    return json.dumps({"success": False, "error": message}), status


def success_response(data=None):
    if data is None:
        data = {}
    result = {"success": True}
    result.update(data)
    return json.dumps(result), 200


def save_file(path: str, content: bytes) -> int:
    if path and "/" in path:
        dir_path = path.rsplit("/", 1)[0]
        try:
            os.mkdir(dir_path)
        except:
            pass

    with open(path, "wb") as f:
        f.write(content)
    size = len(content)
    log(f"Saved file: {path} ({size} bytes)")
    return size


def handle_direct_upload(request, target_path: str | None) -> tuple[str, int]:
    if target_path is None:
        return error_response("Missing target path")

    size = save_file(target_path, request.body)
    return success_response({"path": target_path, "size": size})


def combine_chunks(target_path: str, total_chunks: int) -> tuple[str, int]:
    total_size = 0

    with open(target_path, "wb") as final_file:
        for i in range(total_chunks):
            part_path = f"{target_path}.part{i}"

            try:
                with open(part_path, "rb"):
                    pass
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

                    if bytes_processed % 1024 == 0 or bytes_processed == part_size:
                        percent = (bytes_processed / part_size) * 100
                        log(
                            f"Combining chunk {i+1}/{total_chunks}: {percent:.1f}% ({bytes_processed}/{part_size} bytes)"
                        )
            try:
                os.remove(part_path)
            except:
                log(f"Warning: Could not delete temporary file {part_path}")

    try:
        file_size = os.stat(target_path)[6]
    except:
        file_size = total_size

    log(
        f"Successfully combined {total_chunks} chunks into {target_path} (Total: {total_size} bytes)"
    )
    return success_response(
        {"path": target_path, "size": file_size, "chunks": total_chunks}
    )


def handle_chunked_upload(
    request,
    target_path: str | None,
    chunk_index: int,
    total_chunks: int,
    is_complete: bool,
) -> tuple[str, int]:
    if target_path is None:
        return error_response("Missing target path")

    if total_chunks == 1:
        log("Single chunk upload detected, handling as regular upload")
        return handle_direct_upload(request, target_path)

    temp_path = f"{target_path}.part{chunk_index}"
    size = save_file(temp_path, request.body)
    log(f"Saved chunk {chunk_index+1}/{total_chunks} ({size} bytes) to {temp_path}")
    if chunk_index == total_chunks - 1 or is_complete:
        try:
            return combine_chunks(target_path, total_chunks)
        except Exception as e:
            log(f"Error combining chunks: {str(e)}")
            for i in range(total_chunks):
                try:
                    os.remove(f"{target_path}.part{i}")
                except:
                    pass
            return error_response(f"Error combining chunks: {str(e)}", 500)
    return success_response(
        {"chunk": chunk_index, "total": total_chunks, "path": temp_path}
    )


async def handle_upload(request, target_path: str | None = None) -> tuple[str, int]:
    try:
        if target_path is None:
            return error_response("Missing target path")

        chunk_index = request.headers.get("X-Chunk-Index")
        total_chunks = request.headers.get("X-Total-Chunks")
        is_complete = request.headers.get("X-Is-Complete") == "true"
        content_type = request.headers.get("Content-Type", "").lower()

        if "multipart/form-data" in content_type:
            log(f"Form upload not supported, use binary upload")
            return error_response("Only binary uploads supported")

        if chunk_index is not None and total_chunks is not None:
            return handle_chunked_upload(
                request, target_path, int(chunk_index), int(total_chunks), is_complete
            )
        log(f"Direct binary upload detected for {target_path}")
        return handle_direct_upload(request, target_path)

    except Exception as e:
        log(f"Upload error: {str(e)}")
        return error_response(str(e), 500)
