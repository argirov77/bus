"""Admin endpoints for downloading a database backup and restoring from one."""
from __future__ import annotations

import datetime as _dt
import gzip
import os
import subprocess
from typing import Iterator

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from ..auth import require_admin_token

router = APIRouter(
    prefix="/admin/backup",
    tags=["admin_backup"],
    dependencies=[Depends(require_admin_token)],
)


def _db_env() -> dict[str, str]:
    user = os.getenv("POSTGRES_USER")
    password = os.getenv("POSTGRES_PASSWORD")
    db = os.getenv("POSTGRES_DB")
    host = os.getenv("DB_HOST", "db")
    port = os.getenv("POSTGRES_PORT", "5432")
    if not (user and password and db):
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Database credentials are not configured",
        )
    return {
        "user": user,
        "password": password,
        "db": db,
        "host": host,
        "port": port,
    }


def _stream_dump(chunk_size: int = 64 * 1024) -> Iterator[bytes]:
    cfg = _db_env()
    pg_dump_cmd = [
        "pg_dump",
        "-h", cfg["host"],
        "-p", cfg["port"],
        "-U", cfg["user"],
        "--clean",
        "--if-exists",
        "--no-owner",
        "--no-privileges",
        cfg["db"],
    ]
    env = {**os.environ, "PGPASSWORD": cfg["password"]}

    dump_proc = subprocess.Popen(
        pg_dump_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    gzip_proc = subprocess.Popen(
        ["gzip", "-c"],
        stdin=dump_proc.stdout,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    # Allow dump_proc to receive SIGPIPE if gzip exits early.
    assert dump_proc.stdout is not None
    dump_proc.stdout.close()
    assert gzip_proc.stdout is not None

    try:
        while True:
            chunk = gzip_proc.stdout.read(chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        gzip_proc.stdout.close()
        gzip_rc = gzip_proc.wait()
        dump_rc = dump_proc.wait()
        dump_err = dump_proc.stderr.read().decode("utf-8", errors="replace") if dump_proc.stderr else ""
        gzip_err = gzip_proc.stderr.read().decode("utf-8", errors="replace") if gzip_proc.stderr else ""
        if dump_proc.stderr:
            dump_proc.stderr.close()
        if gzip_proc.stderr:
            gzip_proc.stderr.close()
        if dump_rc != 0 or gzip_rc != 0:
            # Response already started — log so it can be diagnosed.
            print(
                f"[admin_backup] pg_dump rc={dump_rc} gzip rc={gzip_rc}; "
                f"pg_dump stderr: {dump_err}; gzip stderr: {gzip_err}"
            )


@router.get("/download")
def download_backup() -> StreamingResponse:
    cfg = _db_env()
    timestamp = _dt.datetime.now().strftime("%Y-%m-%d-%H%M")
    filename = f"{cfg['db']}-{timestamp}.sql.gz"
    return StreamingResponse(
        _stream_dump(),
        media_type="application/gzip",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Cache-Control": "no-store",
        },
    )


@router.post("/restore")
async def restore_backup(file: UploadFile = File(...)) -> dict:
    cfg = _db_env()

    raw = await file.read()
    if not raw:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Uploaded file is empty",
        )

    # Accept either gzipped or plain SQL.
    filename = (file.filename or "").lower()
    is_gzipped = filename.endswith(".gz") or raw[:2] == b"\x1f\x8b"
    try:
        sql_bytes = gzip.decompress(raw) if is_gzipped else raw
    except OSError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not decompress uploaded file: {exc}",
        )

    cmd = [
        "psql",
        "-h", cfg["host"],
        "-p", cfg["port"],
        "-U", cfg["user"],
        "-d", cfg["db"],
        "-v", "ON_ERROR_STOP=1",
        "--quiet",
    ]
    env = {**os.environ, "PGPASSWORD": cfg["password"]}
    proc = subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=env,
    )
    stdout, stderr = proc.communicate(input=sql_bytes)

    if proc.returncode != 0:
        tail = stderr.decode("utf-8", errors="replace")[-2000:]
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"psql exited with code {proc.returncode}: {tail}",
        )

    return {
        "status": "ok",
        "size_bytes": len(sql_bytes),
        "stderr_tail": stderr.decode("utf-8", errors="replace")[-500:],
    }
