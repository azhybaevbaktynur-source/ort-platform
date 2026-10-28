"""Course files API shapes (PHASE_8A_DESIGN 7.2, 5.3). S1 defines the shapes; S3 adds the service validation
(folder rules 422 `folder_invalid`, PDF and size checks, `course_files_quota`, `storage_full`) and builds the outputs.

Upload is multipart (`file, folder, title, published`), so it has no JSON input model here. Student models are
allow-lists: no `asset_id`, storage keys, author ids or unpublished rows."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.lms.course_files import ids


class _In(BaseModel):
    model_config = ConfigDict(extra="forbid")


class CourseFileUpdateIn(_In):
    """`PATCH _C/course-files/{fid}`: rename, move to another folder (`""` = top level), publish."""
    title: Optional[str] = Field(default=None, min_length=1, max_length=ids.FILE_TITLE_MAX)
    folder: Optional[str] = Field(default=None, max_length=ids.FOLDER_MAX)
    published: Optional[bool] = None

    @model_validator(mode="after")
    def _not_null(self):
        for f in ("title", "folder", "published"):
            if f in self.model_fields_set and getattr(self, f) is None:
                raise ValueError(f"{f} cannot be null")
        return self


class CourseFileStaffOut(BaseModel):
    id: uuid.UUID
    course_id: uuid.UUID
    folder: str
    title: str
    published: bool
    bytes: int
    mime: str
    filename: Optional[str] = None
    used_in_modules: int = 0
    created_at: datetime
    updated_at: datetime
    deleted_at: Optional[datetime] = None


class CourseFileStudentOut(BaseModel):
    id: uuid.UUID
    folder: str
    title: str
    bytes: int
    created_at: datetime


class CourseFilesQuotaOut(BaseModel):
    """Bytes of live course files against `COURSE_FILES_MAX_BYTES` (also the 413 `course_files_quota` details)."""
    used: int
    max: int


class CourseFilesStaffPageOut(BaseModel):
    """`GET _C/course-files` for staff: one cursor page plus the course quota bar."""
    items: list[CourseFileStaffOut] = []
    next_cursor: Optional[str] = None
    quota: CourseFilesQuotaOut


class CourseFilesStudentPageOut(BaseModel):
    items: list[CourseFileStudentOut] = []
    next_cursor: Optional[str] = None


class DownloadOut(BaseModel):
    """`GET _C/course-files/{fid}/download` (after the module gate): a presigned R2 GET (120 s) or the
    authenticated content route on the `db`/`local` drivers."""
    url: str
    expires_at: Optional[datetime] = None
