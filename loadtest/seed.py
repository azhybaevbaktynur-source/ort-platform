"""Seed the loadtest Neon branch (run from <worktree>/backend with DATABASE_URL set, LMS_STORAGE_DRIVER=db).

Creates: 1 approved teacher, 1 published invite-code course, 1 bank with 150 questions, 5 public images,
N students sharing one random password. Writes connection-free state to $LT_STATE (outside the repo).
"""
import json, os, secrets, sys, uuid
sys.path.insert(0, os.getcwd())
from app.core.security import hash_password
from app.db.session import SessionLocal
from app.models.user import User
from app.lms.core.models import utcnow
from app.lms.files import service as fsvc
from tests.lms.factories import make_user, make_course, make_bank, make_question, png_bytes
from PIL import Image
import io

N = int(sys.argv[1]) if len(sys.argv) > 1 else 2000
db = SessionLocal()
teacher = make_user(db, teacher_status="approved")
course = make_course(db, teacher, status="published", title={"en": "Load test course"})
bank = make_bank(db, course, teacher, title="Load bank")
for i in range(150):
    make_question(db, bank, teacher, stem=f"Question {i}: what is {i} + {i}? " + "Lorem ipsum dolor sit amet. " * 8,
                  data={"choices": [{"id": c, "text": f"{c} {i*2} option"} for c in "ABCD"], "correct": "B"})
shas = []
for k in range(5):
    img = Image.effect_noise((400, 300), 60 + k).convert("RGB")
    buf = io.BytesIO(); img.save(buf, "PNG")
    asset, _ = fsvc.ingest_image(db, teacher, buf.getvalue(), course_id=course.id, visibility="public")
    db.commit(); db.refresh(asset); shas.append(asset.sha256)
pw = secrets.token_urlsafe(12)
ph = hash_password(pw)
ids = []
rows = []
for i in range(N):
    uid = f"usr_{uuid.uuid4().hex[:12]}"
    ids.append(uid)
    rows.append(User(id=uid, email=f"lt_{uid}@loadtest.example", password_hash=ph,
                     email_verified=True, teacher_status="none", is_platform_admin=False))
db.add_all(rows); db.commit()
state = {"course_id": str(course.id), "join_code": course.join_code, "bank_id": str(bank.id),
         "teacher_id": teacher.id, "media_shas": shas, "password": pw,
         "students": [{"id": u.id, "email": u.email} for u in rows]}
json.dump(state, open(os.environ["LT_STATE"], "w"))
print("seeded", N, "students; course", course.id, "bank", bank.id)
