import os
import random
import string
import time

from fastapi import APIRouter, Request, UploadFile
from fastapi.responses import JSONResponse

from ..db import db
from ..util import new_id
from ..config import resolve_upload_dir
from ..services.users import resolve_acting_user_id

router = APIRouter()

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB (J-10)


@router.post('/issues/{issue_id}', status_code=201)
async def upload(issue_id: str, request: Request, file: UploadFile | None = None):
    if file is None:
        return JSONResponse({'error': 'No file uploaded.'}, 400)
    data = await file.read()
    if len(data) > MAX_FILE_SIZE:
        return JSONResponse(
            {'error': 'File exceeds the maximum allowed size of 10 MB. Current file rejected.'}, 400)

    upload_dir = resolve_upload_dir()
    os.makedirs(upload_dir, exist_ok=True)

    original = file.filename or 'file'
    ext = os.path.splitext(original)[1]
    rand = ''.join(random.choices(string.ascii_lowercase + string.digits, k=6))
    filename = f'{int(time.time() * 1000)}-{rand}{ext}'
    with open(os.path.join(upload_dir, filename), 'wb') as f:
        f.write(data)

    user_id = resolve_acting_user_id(request)
    att_id = new_id('att')
    db.run(
        """INSERT INTO attachments (id, issue_id, filename, original_name, mime_type, size, uploaded_by)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        att_id, issue_id, filename, original, file.content_type or 'application/octet-stream',
        len(data), user_id,
    )
    return db.q1(
        """SELECT a.*, u.name as uploader_name
           FROM attachments a JOIN users u ON a.uploaded_by = u.id WHERE a.id = ?""",
        att_id,
    )


@router.get('/issues/{issue_id}')
def list_attachments(issue_id: str):
    return db.q(
        """SELECT a.*, u.name as uploader_name
           FROM attachments a JOIN users u ON a.uploaded_by = u.id
           WHERE a.issue_id = ? ORDER BY a.created_at DESC""",
        issue_id,
    )


@router.delete('/{id}')
def delete_attachment(id: str):
    att = db.q1('SELECT filename FROM attachments WHERE id = ?', id)
    if att:
        path = os.path.join(resolve_upload_dir(), att['filename'])
        if os.path.exists(path):
            try:
                os.remove(path)
            except OSError:
                pass
        db.run('DELETE FROM attachments WHERE id = ?', id)
    return {'success': True}
