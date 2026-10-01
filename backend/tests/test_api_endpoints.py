import pytest
import io
from httpx import AsyncClient, ASGITransport
from app.main import app


@pytest.mark.asyncio
async def test_health_check():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert data["firebase_mock_mode"] is True


@pytest.mark.asyncio
async def test_auth_me_and_update_target_score():
    headers = {"Authorization": "Bearer mock_student_token"}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Get profile
        res = await client.get("/api/v1/auth/me", headers=headers)
        assert res.status_code == 200
        data = res.json()
        assert data["role"] == "student"
        assert data["displayName"] == "Айбек Жумабеков"

        # Update target score to 225 (Golden Certificate level)
        res_update = await client.put(
            "/api/v1/auth/target-score",
            headers=headers,
            json={"overall": 225, "math": 58},
        )
        assert res_update.status_code == 200
        target = res_update.json()
        assert target["overall"] == 225
        assert target["math"] == 58


@pytest.mark.asyncio
async def test_question_crud_and_practice_projection():
    inst_headers = {"Authorization": "Bearer mock_instructor_token"}
    student_headers = {"Authorization": "Bearer mock_student_token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create a monolingual math question as instructor
        payload = {
            "language": "ky",
            "section": "math_1",
            "topic": "fractions",
            "difficulty": "medium",
            "stem": "1/2 + 1/4 барабар канчага?",
            "option_a": "3/4",
            "option_b": "2/6",
            "option_c": "1/4",
            "option_d": "1",
            "correct_option": "A",
            "explanation": "1/2 = 2/4. 2/4 + 1/4 = 3/4.",
            "tags": ["math", "fractions"],
        }
        res_create = await client.post("/api/v1/questions", headers=inst_headers, json=payload)
        assert res_create.status_code == 200
        created = res_create.json()
        q_id = created["id"]
        assert created["correct_option"] == "A"
        assert created["language"] == "ky"

        # 2. Student queries practice questions
        res_practice = await client.get("/api/v1/questions/practice/math_1", headers=student_headers)
        assert res_practice.status_code == 200
        practice_items = res_practice.json()
        assert len(practice_items) >= 1
        # Crucial security check: answers and explanations are stripped
        first_item = practice_items[0]
        assert "correct_option" not in first_item
        assert "explanation" not in first_item

        # 3. Instructor deletes question
        res_del = await client.delete(f"/api/v1/questions/{q_id}", headers=inst_headers)
        assert res_del.status_code == 200


@pytest.mark.asyncio
async def test_csv_dry_run_validation_and_bulk_upload():
    headers = {"Authorization": "Bearer mock_instructor_token"}
    csv_content = """section,topic,difficulty,stem,option_a,option_b,option_c,option_d,correct_option,explanation,tags
math_1,algebra,easy,$x + 5 = 10$,5,10,15,0,A,x=5,алгебра
analogies,vocab,medium,Уста : Бака,Врач : Оорукана,Мугалим : Мектеп,Жазуучу : Калем,Учкуч : Самолет,C,Уста аспабы менен,аналогия
"""
    files = {"file": ("test_questions.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Dry-run validation
        res_val = await client.post("/api/v1/bulk/validate-csv", headers=headers, files=files, data={"language": "ky"})
        assert res_val.status_code == 200
        val_data = res_val.json()
        assert val_data["totalRows"] == 2
        assert val_data["validRowsCount"] == 2
        assert val_data["invalidRowsCount"] == 0

        # Reset buffer and commit upload
        files_upload = {"file": ("test_questions.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        res_upload = await client.post(
            "/api/v1/bulk/upload-csv",
            headers=headers,
            files=files_upload,
            data={"language": "ky", "exam_type": "practice_bank"},
        )
        assert res_upload.status_code == 200
        upload_data = res_upload.json()
        assert upload_data["success"] is True
        assert upload_data["importedCount"] == 2


@pytest.mark.asyncio
async def test_bulk_endpoints_accept_exam_id_and_bulletproof_error_handling():
    headers = {"Authorization": "Bearer mock_instructor_token"}
    # 1. Test validate and upload accepting exam_id Form parameter
    csv_content = """section,stem,option_a,option_b,option_c,option_d,correct_option
math_1,Вопрос 1,1,2,3,4,A
math_2,Вопрос 2,5,6,7,8,B
"""
    files_val = {"file": ("test_exam_id.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        res_val = await client.post(
            "/api/v1/bulk/validate-csv",
            headers=headers,
            files=files_val,
            data={"language": "ru", "exam_id": "exam_bound_test"},
        )
        assert res_val.status_code == 200
        val_data = res_val.json()
        assert val_data["validRowsCount"] == 2
        assert val_data["previewQuestions"][0]["exam_set_id"] == "exam_bound_test"
        assert val_data["previewQuestions"][0]["language"] == "ru"

        # 2. Test uploading with exam_id
        files_up = {"file": ("test_exam_id.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        res_up = await client.post(
            "/api/v1/bulk/upload-csv",
            headers=headers,
            files=files_up,
            data={"language": "ru", "exam_id": "exam_bound_test"},
        )
        assert res_up.status_code == 200
        up_data = res_up.json()
        assert up_data["success"] is True
        assert up_data["importedCount"] == 2
        assert up_data["examSetId"] == "exam_bound_test"

        # 3. Test bulletproof error handling on broken CSV - must return 200 OK with errors, NEVER 500 crash
        broken_content = "invalid_header,foo,bar\n1,2,3"
        files_broken = {"file": ("broken.csv", io.BytesIO(broken_content.encode("utf-8")), "text/csv")}
        res_broken = await client.post(
            "/api/v1/bulk/validate-csv",
            headers=headers,
            files=files_broken,
            data={"language": "ky"},
        )
        assert res_broken.status_code == 200
        broken_data = res_broken.json()
        assert broken_data["validRowsCount"] == 0
        assert broken_data["invalidRowsCount"] == 1
        assert len(broken_data["errors"]) > 0


@pytest.mark.asyncio
async def test_exam_set_lms_management_and_attempts():
    student_headers = {"Authorization": "Bearer mock_student_token"}
    inst_headers = {"Authorization": "Bearer mock_instructor_token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Instructor creates an ExamSet
        create_payload = {
            "title": "Сыноо Экзамени 2026",
            "description": "Машыгуу тести",
            "language": "ky",
            "status": "draft",
            "access_code": "9876",
            "max_attempts": 3,
            "sections": [
                {"section": "math_1", "questionCount": 5, "timeLimitMinutes": 10},
            ],
        }
        res_create = await client.post("/api/v1/mock-tests/exam-sets", headers=inst_headers, json=create_payload)
        assert res_create.status_code == 200
        created = res_create.json()
        exam_id = created["id"]
        assert created["status"] == "draft"

        # 2. Student queries exam-sets; draft should NOT be returned
        res_list_student = await client.get("/api/v1/mock-tests/exam-sets?lang=ky", headers=student_headers)
        assert res_list_student.status_code == 200
        student_exams = res_list_student.json()
        assert exam_id not in [e["id"] for e in student_exams]

        # 3. Instructor publishes the exam
        res_pub = await client.put(
            f"/api/v1/mock-tests/exam-sets/{exam_id}",
            headers=inst_headers,
            json={"status": "published"},
        )
        assert res_pub.status_code == 200
        assert res_pub.json()["status"] == "published"

        # 4. Student queries exam-sets; published exam IS returned
        res_list_pub = await client.get("/api/v1/mock-tests/exam-sets?lang=ky", headers=student_headers)
        assert res_list_pub.status_code == 200
        pub_exams = res_list_pub.json()
        assert exam_id in [e["id"] for e in pub_exams]

        # 5. Student attempts without PIN => 403 Forbidden
        res_fail = await client.post(
            "/api/v1/mock-tests/start",
            headers=student_headers,
            json={"templateId": exam_id, "language": "ky", "access_code": "0000"},
        )
        assert res_fail.status_code == 403


@pytest.mark.asyncio
async def test_mock_test_full_workflow():
    headers = {"Authorization": "Bearer mock_student_token"}
    inst_headers = {"Authorization": "Bearer mock_instructor_token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Preload 5 questions (one for each section)
        for s in ["math_1", "analogies", "reading", "grammar", "math_2"]:
            await client.post(
                "/api/v1/questions",
                headers=inst_headers,
                json={
                    "language": "ky",
                    "section": s,
                    "topic": "test",
                    "difficulty": "medium",
                    "stem": f"Суроо {s}",
                    "option_a": "A",
                    "option_b": "B",
                    "option_c": "C",
                    "option_d": "D",
                    "correct_option": "A",
                },
            )

        # 1. List exam-sets
        res_templates = await client.get("/api/v1/mock-tests/exam-sets?lang=ky", headers=headers)
        assert res_templates.status_code == 200
        templates = res_templates.json()
        assert len(templates) >= 2

        # 2. Start speed drill session
        res_start = await client.post(
            "/api/v1/mock-tests/start",
            headers=headers,
            json={"templateId": "ort_speed_drill", "language": "ky"},
        )
        assert res_start.status_code == 200
        session_data = res_start.json()
        attempt_id = session_data["attemptId"]

        # Collect question IDs from session
        all_q_ids = []
        for sec_questions in session_data["questions"].values():
            for q in sec_questions:
                all_q_ids.append(q["id"])

        # 3. Autosave progress
        answers_payload = {
            q_id: {"selectedOptionId": "A", "timeSpentSeconds": 15, "flagged": False}
            for q_id in all_q_ids
        }
        res_save = await client.post(
            f"/api/v1/mock-tests/{attempt_id}/save",
            headers=headers,
            json={"answers": answers_payload},
        )
        assert res_save.status_code == 200

        # 4. Final submit and instant normative scoring
        res_submit = await client.post(
            f"/api/v1/mock-tests/{attempt_id}/submit",
            headers=headers,
            json={"answers": answers_payload},
        )
        assert res_submit.status_code == 200
        score_report = res_submit.json()
        assert score_report["attemptId"] == attempt_id
        assert score_report["totalRawScore"] == len(all_q_ids)
        assert score_report["totalScaledScore"] >= 200
        assert "sectionScores" in score_report
        assert len(score_report["review"]) == len(all_q_ids)

        # 5. List completed attempts
        res_attempts = await client.get("/api/v1/mock-tests/attempts", headers=headers)
        assert res_attempts.status_code == 200
        attempts = res_attempts.json()
        assert len(attempts) >= 1
        assert attempts[0]["attemptId"] == attempt_id


@pytest.mark.asyncio
async def test_planner_and_analytics_endpoints():
    student_headers = {"Authorization": "Bearer mock_student_token"}
    inst_headers = {"Authorization": "Bearer mock_instructor_token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Planner
        res_plan = await client.get("/api/v1/planner/daily", headers=student_headers)
        assert res_plan.status_code == 200
        plan = res_plan.json()
        assert len(plan["tasks"]) == 3
        assert plan["streakCount"] >= 7

        # Toggle task
        res_toggle = await client.post(
            "/api/v1/planner/toggle-task",
            headers=student_headers,
            json={"taskId": "task_1", "isCompleted": True},
        )
        assert res_toggle.status_code == 200
        assert res_toggle.json()["isCompleted"] is True

        # Student Analytics
        res_s_analytics = await client.get("/api/v1/analytics/student", headers=student_headers)
        assert res_s_analytics.status_code == 200
        s_data = res_s_analytics.json()
        assert "sectionsMastery" in s_data
        assert "topWeakSpots" in s_data

        # Instructor Analytics
        res_i_analytics = await client.get("/api/v1/analytics/instructor", headers=inst_headers)
        assert res_i_analytics.status_code == 200
        i_data = res_i_analytics.json()
        assert i_data["totalStudents"] > 0
        assert "scoreDistribution" in i_data


@pytest.mark.asyncio
async def test_dynamic_student_analytics_reflects_mock_test_attempt():
    student_headers = {"Authorization": "Bearer mock_student_token"}
    inst_headers = {"Authorization": "Bearer mock_instructor_token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Seed questions across sections
        for s in ["math_1", "analogies", "reading", "grammar", "math_2"]:
            await client.post(
                "/api/v1/questions",
                headers=inst_headers,
                json={
                    "language": "ky",
                    "section": s,
                    "topic": "test",
                    "difficulty": "medium",
                    "exam_set_id": "exam_practice_bank_ky",
                    "stem": f"Суроо {s}",
                    "option_a": "A",
                    "option_b": "B",
                    "option_c": "C",
                    "option_d": "D",
                    "correct_option": "A",
                },
            )

        # 1. Start a speed drill test session
        res_start = await client.post(
            "/api/v1/mock-tests/start",
            headers=student_headers,
            json={"templateId": "ort_speed_drill", "language": "ky"},
        )
        assert res_start.status_code == 200
        session_data = res_start.json()
        attempt_id = session_data["attemptId"]

        # Collect question IDs from session
        all_q_ids = []
        for sec_questions in session_data["questions"].values():
            for q in sec_questions:
                all_q_ids.append(q["id"])

        # 2. Submit test answers
        answers_payload = {
            q_id: {"selectedOptionId": "A", "timeSpentSeconds": 15, "flagged": False}
            for q_id in all_q_ids
        }

        res_submit = await client.post(
            f"/api/v1/mock-tests/{attempt_id}/submit",
            headers=student_headers,
            json={"answers": answers_payload},
        )
        assert res_submit.status_code == 200
        result_data = res_submit.json()

        # 3. Check student analytics reflects this completed test
        res_analytics = await client.get("/api/v1/analytics/student", headers=student_headers)
        assert res_analytics.status_code == 200
        analytics_data = res_analytics.json()

        assert analytics_data["totalTestsCompleted"] >= 1
        assert analytics_data["totalQuestionsPracticed"] > 0
        assert analytics_data["currentEstimatedScore"] == result_data["totalScaledScore"]
        assert len(analytics_data["recentScores"]) >= 1
        latest_score = analytics_data["recentScores"][-1]
        assert latest_score["scaled"] == result_data["totalScaledScore"]


@pytest.mark.asyncio
async def test_upload_and_section_sequencing_workflow():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        instructor_headers = {"Authorization": "Bearer mock_instructor_token"}
        student_headers = {"Authorization": "Bearer mock_student_token"}

        # 1. Test image upload endpoint
        file_content = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4"
        files = {"file": ("test_diagram.png", file_content, "image/png")}
        res_upload = await client.post("/api/v1/upload", headers=instructor_headers, files=files)
        assert res_upload.status_code == 200
        upload_data = res_upload.json()
        assert "url" in upload_data
        assert upload_data["url"].startswith("/uploads/")
        uploaded_url = upload_data["url"]

        # Verify static file serving
        res_static = await client.get(uploaded_url)
        assert res_static.status_code == 200
        assert res_static.content == file_content

        # 2. Test dedicated exam-sets endpoint mounted at /api/v1/exam-sets
        res_exam_create = await client.post(
            "/api/v1/exam-sets",
            headers=instructor_headers,
            json={
                "title": "Sequencing Test Exam",
                "language": "ky",
                "status": "published",
                "sections": [
                    {"section": "grammar", "questionCount": 1, "timeLimitMinutes": 5},
                    {"section": "math_1", "questionCount": 1, "timeLimitMinutes": 5},
                    {"section": "reading", "questionCount": 1, "timeLimitMinutes": 5},
                ],
            },
        )
        assert res_exam_create.status_code == 200
        created_exam = res_exam_create.json()
        exam_id = created_exam["id"]

        # Create 1 question for math_1 and 1 question for grammar with the uploaded image (0 questions for reading)
        await client.post(
            "/api/v1/questions",
            headers=instructor_headers,
            json={
                "language": "ky",
                "section": "math_1",
                "topic": "Geometry",
                "difficulty": "medium",
                "exam_set_id": exam_id,
                "stem": "Solve for x in diagram",
                "image_url": uploaded_url,
                "option_a": "10",
                "option_b": "20",
                "option_c": "30",
                "option_d": "40",
                "correct_option": "A",
            },
        )
        await client.post(
            "/api/v1/questions",
            headers=instructor_headers,
            json={
                "language": "ky",
                "section": "grammar",
                "topic": "Syntax",
                "difficulty": "medium",
                "exam_set_id": exam_id,
                "stem": "Кайсы сүйлөм туура түзүлгөн?",
                "option_a": "Биринчи",
                "option_b": "Экинчи",
                "option_c": "Үчүнчү",
                "option_d": "Төртүнчү",
                "correct_option": "A",
            },
        )

        # Grant student access to the newly created full_main exam
        await client.post(
            f"/api/v1/admin/students/usr_student_01/access",
            headers=instructor_headers,
            json={"exam_set_id": exam_id, "granted": True},
        )

        # 3. Start test session and verify STRICT_SECTION_ORDER and 0-question section skipping
        res_start = await client.post(
            "/api/v1/mock-tests/start",
            headers=student_headers,
            json={"templateId": exam_id, "language": "ky"},
        )
        assert res_start.status_code == 200
        session_data = res_start.json()

        # The sections served should strictly be math_1 first, then grammar (reading skipped because 0 questions)
        section_codes = [s["section"] for s in session_data["sections"]]
        assert section_codes == ["math_1", "grammar"]
        assert "math_1" in session_data["questions"]
        assert session_data["questions"]["math_1"][0]["image_url"] == uploaded_url


@pytest.mark.asyncio
async def test_student_exam_sets_endpoint():
    student_headers = {"Authorization": "Bearer mock_student_token"}
    inst_headers = {"Authorization": "Bearer mock_instructor_token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Create published full_main exam
        res_fm = await client.post(
            "/api/v1/exam-sets",
            headers=inst_headers,
            json={
                "title": "Республикалык Сыноо Тест 2026",
                "language": "ky",
                "exam_type": "full_main",
                "status": "published",
                "sections": [],
            },
        )
        fm_id = res_fm.json()["id"]

        # Create published subject exam
        res_sub = await client.post(
            "/api/v1/exam-sets",
            headers=inst_headers,
            json={
                "title": "Химия Предметтик Тест 2026",
                "language": "ky",
                "exam_type": "subject",
                "status": "published",
                "sections": [],
            },
        )
        sub_id = res_sub.json()["id"]

        # Call GET /api/v1/exam-sets/student before access is granted:
        # Full_main and subject exams (fm_id, sub_id) MUST NOT be visible yet
        res_initial = await client.get("/api/v1/exam-sets/student?lang=ky", headers=student_headers)
        assert res_initial.status_code == 200
        exams_initial = res_initial.json()
        assert fm_id not in [e["id"] for e in exams_initial]
        assert sub_id not in [e["id"] for e in exams_initial]

        # Now admin grants access to both exams for usr_student_01
        await client.post(
            "/api/v1/admin/students/usr_student_01/access",
            headers=inst_headers,
            json={"exam_set_id": fm_id, "granted": True},
        )
        await client.post(
            "/api/v1/admin/students/usr_student_01/access",
            headers=inst_headers,
            json={"exam_set_id": sub_id, "granted": True},
        )

        # Call GET /api/v1/exam-sets/student after access is granted:
        res = await client.get("/api/v1/exam-sets/student?lang=ky", headers=student_headers)
        assert res.status_code == 200
        exams = res.json()
        assert len(exams) >= 2
        for e in exams:
            assert e["status"] == "published"
            assert "user_attempts_count" in e
            assert e["user_attempts_count"] is not None

        # Filter by exam_type=subject
        res_subject = await client.get("/api/v1/exam-sets/student?lang=ky&exam_type=subject", headers=student_headers)
        assert res_subject.status_code == 200
        subject_exams = res_subject.json()
        assert all(e["exam_type"] == "subject" for e in subject_exams)
        assert any(e["id"] == sub_id for e in subject_exams)


@pytest.mark.asyncio
async def test_exam_set_dynamic_question_count_and_custom_timer():
    inst_headers = {"Authorization": "Bearer mock_instructor_token"}
    student_headers = {"Authorization": "Bearer mock_student_token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create exam set with custom 40-minute timer
        res_create = await client.post(
            "/api/v1/exam-sets",
            headers=inst_headers,
            json={
                "title": "Химия Экспресс 40",
                "language": "ky",
                "exam_type": "subject",
                "status": "published",
                "time_limit_minutes": 40,
                "sections": [],
            },
        )
        assert res_create.status_code == 200
        exam_data = res_create.json()
        exam_id = exam_data["id"]
        assert exam_data["time_limit_minutes"] == 40

        # 2. Add 2 questions specifically for this exam_set
        for i in range(2):
            res_q = await client.post(
                "/api/v1/questions",
                headers=inst_headers,
                json={
                    "language": "ky",
                    "section": "chemistry",
                    "topic": "organic",
                    "difficulty": "medium",
                    "exam_set_id": exam_id,
                    "stem": f"Химия суроосу #{i+1}",
                    "option_a": "A",
                    "option_b": "B",
                    "option_c": "C",
                    "option_d": "D",
                    "correct_option": "A",
                },
            )
            assert res_q.status_code == 200

        # 3. Check GET /api/v1/exam-sets/{id} dynamically computes question count = 2
        res_get = await client.get(f"/api/v1/exam-sets/{exam_id}", headers=inst_headers)
        assert res_get.status_code == 200
        fetched = res_get.json()
        assert fetched["question_count"] == 2
        assert fetched["totalQuestions"] == 2
        assert fetched["time_limit_minutes"] == 40

        # 4. Check list /api/v1/exam-sets returns question_count = 2
        res_list = await client.get("/api/v1/exam-sets?lang=ky", headers=inst_headers)
        assert res_list.status_code == 200
        matching = [e for e in res_list.json() if e["id"] == exam_id]
        assert len(matching) == 1
        assert matching[0]["question_count"] == 2

        # Grant student access to the exam
        await client.post(
            f"/api/v1/admin/students/usr_student_01/access",
            headers=inst_headers,
            json={"exam_set_id": exam_id, "granted": True},
        )

        # 5. Start test session as student: verify timer is strictly 40 minutes (2400 seconds)
        res_start = await client.post(
            "/api/v1/mock-tests/start",
            headers=student_headers,
            json={"templateId": exam_id, "language": "ky"},
        )
        assert res_start.status_code == 200
        session_data = res_start.json()
        assert session_data["totalTimeSeconds"] == 40 * 60
        assert session_data["sections"][0]["timeLimitMinutes"] == 40


@pytest.mark.asyncio
async def test_user_target_score_endpoint():
    student_headers = {"Authorization": "Bearer mock_student_token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Update target score via /api/v1/users/me/target-score
        res = await client.put(
            "/api/v1/users/me/target-score",
            headers=student_headers,
            json={"target_score": 224},
        )
        assert res.status_code == 200
        data = res.json()
        assert data["target_score"] == 224
        assert data["overall"] == 224

        # Verify GET /api/v1/users/me reflects this target score
        res_me = await client.get("/api/v1/users/me", headers=student_headers)
        assert res_me.status_code == 200
        me_data = res_me.json()
        assert me_data["target_score"] == 224


@pytest.mark.asyncio
async def test_live_analytics_split_sections_and_instructor_metrics():
    student_headers = {"Authorization": "Bearer mock_student_token"}
    inst_headers = {"Authorization": "Bearer mock_instructor_token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Student analytics: split sections
        res_s = await client.get("/api/v1/analytics/student", headers=student_headers)
        assert res_s.status_code == 200
        s_data = res_s.json()
        assert "mainSectionsMastery" in s_data
        assert "subjectSectionsMastery" in s_data
        for ms in ["math_1", "math_2", "reading", "analogies", "grammar"]:
            assert ms in s_data["mainSectionsMastery"]
        assert s_data["targetScore"] >= 60

        # Instructor analytics: live data
        res_i = await client.get("/api/v1/analytics/instructor", headers=inst_headers)
        assert res_i.status_code == 200
        i_data = res_i.json()
        assert i_data["totalStudents"] >= 1
        assert "scoreDistribution" in i_data
        assert "<110" in i_data["scoreDistribution"]
        assert "219+" in i_data["scoreDistribution"]
        assert isinstance(i_data["hardestQuestions"], list)


@pytest.mark.asyncio
async def test_pin_validation_and_fast_practice_exemption():
    student_headers = {"Authorization": "Bearer mock_student_token"}
    inst_headers = {"Authorization": "Bearer mock_instructor_token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create a proctored exam set requiring a 4-digit PIN: '7788'
        res_create = await client.post(
            "/api/v1/exam-sets",
            headers=inst_headers,
            json={
                "title": "Proctored Main Exam with PIN",
                "language": "ky",
                "exam_type": "full_main",
                "status": "published",
                "access_code": "7788",
                "sections": [],
            },
        )
        assert res_create.status_code == 200
        exam_id = res_create.json()["id"]

        # Add a question so session can initialize
        await client.post(
            "/api/v1/questions",
            headers=inst_headers,
            json={
                "language": "ky",
                "section": "math_1",
                "topic": "Algebra",
                "difficulty": "medium",
                "exam_set_id": exam_id,
                "stem": "x + 5 = 10 болсо, x = ?",
                "option_a": "5",
                "option_b": "10",
                "option_c": "15",
                "option_d": "20",
                "correct_option": "A",
            },
        )

        # 1.5 Try starting without access grant -> 403 Access Denied
        res_no_access = await client.post(
            "/api/v1/mock-tests/start",
            headers=student_headers,
            json={"templateId": exam_id, "language": "ky"},
        )
        assert res_no_access.status_code == 403
        assert "доступа" in res_no_access.json()["detail"] or "мүмкүнчүлүгүңүз" in res_no_access.json()["detail"]

        # Admin grants access to student
        await client.post(
            f"/api/v1/admin/students/usr_student_01/access",
            headers=inst_headers,
            json={"exam_set_id": exam_id, "granted": True},
        )

        # 2. Try starting without PIN -> 403
        res_no_pin = await client.post(
            "/api/v1/mock-tests/start",
            headers=student_headers,
            json={"templateId": exam_id, "language": "ky"},
        )
        assert res_no_pin.status_code == 403
        assert "PIN" in res_no_pin.json()["detail"] or "коду" in res_no_pin.json()["detail"]

        # 3. Try starting with wrong PIN -> 403
        res_wrong_pin = await client.post(
            "/api/v1/mock-tests/start",
            headers=student_headers,
            json={"templateId": exam_id, "language": "ky", "pin": "0000"},
        )
        assert res_wrong_pin.status_code == 403
        assert "Туура эмес" in res_wrong_pin.json()["detail"]

        # 4. Start with correct PIN via body -> 200
        res_ok_pin = await client.post(
            "/api/v1/mock-tests/start",
            headers=student_headers,
            json={"templateId": exam_id, "language": "ky", "pin": "7788"},
        )
        assert res_ok_pin.status_code == 200
        assert "attemptId" in res_ok_pin.json()

        # 5. Start with correct PIN via /{test_id}/start?pin=7788 query param -> 200
        res_ok_param = await client.post(
            f"/api/v1/mock-tests/{exam_id}/start?pin=7788",
            headers=student_headers,
        )
        assert res_ok_param.status_code == 200
        assert "attemptId" in res_ok_param.json()

        # 6. Test Fast Practice explicitly bypasses PIN validation
        # Create a practice bank with a PIN set by instructor
        res_prac = await client.post(
            "/api/v1/exam-sets",
            headers=inst_headers,
            json={
                "title": "Practice Bank with Accidental PIN",
                "language": "ky",
                "exam_type": "practice_bank",
                "status": "published",
                "access_code": "9999",
                "sections": [],
            },
        )
        prac_id = res_prac.json()["id"]

        # Add question to practice bank
        await client.post(
            "/api/v1/questions",
            headers=inst_headers,
            json={
                "language": "ky",
                "section": "grammar",
                "topic": "Nouns",
                "difficulty": "easy",
                "exam_set_id": prac_id,
                "stem": "Зат атооч кайсы?",
                "option_a": "Китеп",
                "option_b": "Окуу",
                "option_c": "Кызыл",
                "option_d": "Бүгүн",
                "correct_option": "A",
            },
        )

        # Fast practice should NEVER ask for PIN
        res_fast = await client.post(
            f"/api/v1/mock-tests/{prac_id}/start",
            headers=student_headers,
        )
        assert res_fast.status_code == 200
        assert "attemptId" in res_fast.json()


@pytest.mark.asyncio
async def test_sql_auth_registration_and_login_flow():
    import uuid
    from app.db.init_db import init_db
    init_db()

    test_email = f"newstudent_{uuid.uuid4().hex[:6]}@ort.kg"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Register a new student
        reg_payload = {
            "email": test_email,
            "password": "securepassword123",
            "displayName": "Жаңы Окуучу",
        }
        res_reg = await client.post("/api/v1/auth/register", json=reg_payload)
        assert res_reg.status_code == 200
        reg_data = res_reg.json()
        assert reg_data["role"] == "student"
        assert "access_token" in reg_data
        jwt_token = reg_data["access_token"]

        # 2. Duplicate registration should be rejected
        res_dup = await client.post("/api/v1/auth/register", json=reg_payload)
        assert res_dup.status_code == 400

        # 3. Login with newly created student
        login_payload = {
            "email": test_email,
            "password": "securepassword123",
        }
        res_login = await client.post("/api/v1/auth/login", json=login_payload)
        assert res_login.status_code == 200
        login_data = res_login.json()
        assert login_data["role"] == "student"
        assert login_data["user"]["email"] == test_email

        # 4. Use JWT token to fetch /auth/me
        headers = {"Authorization": f"Bearer {jwt_token}"}
        res_me = await client.get("/api/v1/auth/me", headers=headers)
        assert res_me.status_code == 200
        me_data = res_me.json()
        assert me_data["role"] == "student"
        assert me_data["email"] == test_email

        # 5. Student cannot access admin-only endpoint
        res_admin_block = await client.post(
            "/api/v1/exam-sets",
            headers=headers,
            json={"title": "Hack Attempt", "language": "ky", "exam_type": "full_main"},
        )
        assert res_admin_block.status_code == 403

        # 6. Admin login works with seeded account
        admin_login = {
            "email": "admin@ort.kg",
            "password": "admin123",
        }
        res_admin = await client.post("/api/v1/auth/login", json=admin_login)
        assert res_admin.status_code == 200
        admin_data = res_admin.json()
        assert admin_data["role"] == "admin"
        admin_jwt = admin_data["access_token"]

        # 7. Admin CAN access admin-only endpoint
        admin_headers = {"Authorization": f"Bearer {admin_jwt}"}
        res_admin_create = await client.post(
            "/api/v1/exam-sets",
            headers=admin_headers,
            json={"title": "Official Admin Exam", "language": "ky", "exam_type": "full_main"},
        )
        assert res_admin_create.status_code == 200


@pytest.mark.asyncio
async def test_admin_student_management_and_access_control():
    student_headers = {"Authorization": "Bearer mock_student_token"}
    admin_headers = {"Authorization": "Bearer mock_admin_token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Student cannot access GET /api/v1/admin/students -> 403 Forbidden
        res_forbidden = await client.get("/api/v1/admin/students", headers=student_headers)
        assert res_forbidden.status_code == 403

        # 2. Admin can access GET /api/v1/admin/students
        res_students = await client.get("/api/v1/admin/students", headers=admin_headers)
        assert res_students.status_code == 200
        students = res_students.json()
        assert len(students) >= 1
        student_01 = next((s for s in students if s["id"] == "usr_student_01"), None)
        assert student_01 is not None
        assert student_01["email"] == "student@ort.kg"
        assert "grantedExamIds" in student_01

        # 3. Create a locked full_main exam
        res_create_exam = await client.post(
            "/api/v1/exam-sets",
            headers=admin_headers,
            json={
                "title": "Strictly Locked Exam",
                "language": "ky",
                "exam_type": "full_main",
                "status": "published",
                "sections": [],
            },
        )
        assert res_create_exam.status_code == 200
        locked_exam_id = res_create_exam.json()["id"]

        # 4. Student queries their exams: locked_exam_id is NOT in the list
        res_student_exams = await client.get("/api/v1/exam-sets/student?lang=ky", headers=student_headers)
        assert res_student_exams.status_code == 200
        visible_ids = [e["id"] for e in res_student_exams.json()]
        assert locked_exam_id not in visible_ids

        # 5. Admin grants access to locked_exam_id for usr_student_01
        res_grant = await client.post(
            f"/api/v1/admin/students/usr_student_01/access",
            headers=admin_headers,
            json={"exam_set_id": locked_exam_id, "granted": True},
        )
        assert res_grant.status_code == 200
        grant_data = res_grant.json()
        assert grant_data["granted"] is True
        assert locked_exam_id in grant_data["grantedExamIds"]

        # 6. Student queries their exams again: locked_exam_id IS NOW VISIBLE
        res_student_exams_after = await client.get("/api/v1/exam-sets/student?lang=ky", headers=student_headers)
        assert res_student_exams_after.status_code == 200
        visible_ids_after = [e["id"] for e in res_student_exams_after.json()]
        assert locked_exam_id in visible_ids_after

        # 7. Check GET /api/v1/admin/students/{user_id}/access
        res_access_list = await client.get(
            "/api/v1/admin/students/usr_student_01/access",
            headers=admin_headers,
        )
        assert res_access_list.status_code == 200
        assert locked_exam_id in res_access_list.json()

        # 8. Admin revokes access
        res_revoke = await client.post(
            f"/api/v1/admin/students/usr_student_01/access",
            headers=admin_headers,
            json={"exam_set_id": locked_exam_id, "granted": False},
        )
        assert res_revoke.status_code == 200
        assert res_revoke.json()["granted"] is False
        assert locked_exam_id not in res_revoke.json()["grantedExamIds"]

        # 9. Student queries their exams: locked_exam_id is hidden again
        res_final = await client.get("/api/v1/exam-sets/student?lang=ky", headers=student_headers)
        assert res_final.status_code == 200
        assert locked_exam_id not in [e["id"] for e in res_final.json()]


@pytest.mark.asyncio
async def test_exam_set_cascading_deletion():
    """
    Tests that deleting an ExamSet cascades and deletes its linked
    Questions, ExamAccess records, and TestAttempts without foreign key errors.
    """
    from datetime import datetime, timezone
    from app.db.session import SessionLocal
    from app.models.exam_set import ExamSet as ExamSetModel
    from app.models.question import Question as QuestionModel
    from app.models.exam_access import ExamAccess as ExamAccessModel
    from app.models.test_attempt import TestAttempt as TestAttemptModel

    admin_headers = {"Authorization": "Bearer mock_admin_token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Create new exam set
        res_create = await client.post(
            "/api/v1/exam-sets",
            headers=admin_headers,
            json={
                "title": "Cascade Test Exam",
                "description": "Testing cascading deletes",
                "language": "ky",
                "exam_type": "full_main",
                "status": "published",
                "time_limit_minutes": 60,
                "sections": [],
            },
        )
        assert res_create.status_code == 200
        exam_id = res_create.json()["id"]

        # 2. Attach a Question, ExamAccess, and TestAttempt directly in SQL
        db = SessionLocal()
        try:
            q_id = f"q_casc_{exam_id[:8]}"
            db.add(
                QuestionModel(
                    id=q_id,
                    language="ky",
                    section="math_1",
                    topic="cascade",
                    difficulty="easy",
                    stem="Cascade Q",
                    option_a="1",
                    option_b="2",
                    option_c="3",
                    option_d="4",
                    correct_option="A",
                    exam_set_id=exam_id,
                    created_at=datetime.now(timezone.utc),
                )
            )

            acc_id = f"acc_casc_{exam_id[:8]}"
            db.add(
                ExamAccessModel(
                    id=acc_id,
                    user_id="usr_student_01",
                    exam_set_id=exam_id,
                    granted_at=datetime.now(timezone.utc),
                )
            )

            att_id = f"att_casc_{exam_id[:8]}"
            db.add(
                TestAttemptModel(
                    id=att_id,
                    user_id="usr_student_01",
                    template_id=exam_id,
                    language="ky",
                    status="in_progress",
                    started_at=datetime.now(timezone.utc),
                )
            )
            db.commit()

            # Verify rows exist
            assert db.query(QuestionModel).filter(QuestionModel.id == q_id).first() is not None
            assert db.query(ExamAccessModel).filter(ExamAccessModel.id == acc_id).first() is not None
            assert db.query(TestAttemptModel).filter(TestAttemptModel.id == att_id).first() is not None
        finally:
            db.close()

        # 3. Delete ExamSet via DELETE endpoint
        res_del = await client.delete(f"/api/v1/exam-sets/{exam_id}", headers=admin_headers)
        assert res_del.status_code == 200
        assert res_del.json()["success"] is True

        # 4. Verify in DB that ExamSet AND all cascading records are deleted
        db = SessionLocal()
        try:
            assert db.query(ExamSetModel).filter(ExamSetModel.id == exam_id).first() is None
            assert db.query(QuestionModel).filter(QuestionModel.id == q_id).first() is None
            assert db.query(ExamAccessModel).filter(ExamAccessModel.id == acc_id).first() is None
            assert db.query(TestAttemptModel).filter(TestAttemptModel.id == att_id).first() is None
        finally:
            db.close()


@pytest.mark.asyncio
async def test_registration_phone_and_admin_students_display():
    """
    Tests that phone number is accepted during registration, stored in DB,
    and returned in GET /api/v1/admin/students.
    """
    import uuid
    rand_email = f"phone_user_{uuid.uuid4().hex[:6]}@example.com"
    phone_num = "+996 700 889900"

    admin_headers = {"Authorization": "Bearer mock_admin_token"}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # Register user with phone
        res_reg = await client.post(
            "/api/v1/auth/register",
            json={
                "email": rand_email,
                "password": "securepassword123",
                "displayName": "Телефондуу Окуучу",
                "phone": phone_num,
            },
        )
        assert res_reg.status_code == 200
        reg_data = res_reg.json()
        assert reg_data["user"]["phone"] == phone_num

        # Admin lists students
        res_students = await client.get("/api/v1/admin/students", headers=admin_headers)
        assert res_students.status_code == 200
        students = res_students.json()

        matched = next((s for s in students if s["email"] == rand_email), None)
        assert matched is not None
        assert matched["phone"] == phone_num


@pytest.mark.asyncio
async def test_forgot_and_reset_password_flow():
    """
    Tests self-service password reset flow:
    1. Register user
    2. Request reset link (generates token in DB)
    3. Reset password using token
    4. Verify old password fails and new password succeeds
    """
    import uuid
    from app.db.session import SessionLocal
    from app.models.user import User as UserModel

    rand_email = f"reset_test_{uuid.uuid4().hex[:6]}@example.com"
    initial_pass = "oldPassword123"
    new_pass = "newSuperSecretPassword456"

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        # 1. Register
        res_reg = await client.post(
            "/api/v1/auth/register",
            json={
                "email": rand_email,
                "password": initial_pass,
                "displayName": "Reset Test User",
            },
        )
        assert res_reg.status_code == 200

        # 2. Request forgot password
        res_forgot = await client.post(
            "/api/v1/auth/forgot-password",
            json={"email": rand_email, "lang": "ru"},
        )
        assert res_forgot.status_code == 200
        assert res_forgot.json()["success"] is True

        # 3. Retrieve token from DB
        db = SessionLocal()
        try:
            db_user = db.query(UserModel).filter(UserModel.email == rand_email).first()
            assert db_user is not None
            assert db_user.reset_token is not None
            token = db_user.reset_token
        finally:
            db.close()

        # 4. Submit reset password
        res_reset = await client.post(
            "/api/v1/auth/reset-password",
            json={"token": token, "new_password": new_pass},
        )
        assert res_reset.status_code == 200
        assert res_reset.json()["success"] is True

        # 5. Verify old password fails
        res_old_login = await client.post(
            "/api/v1/auth/login",
            json={"email": rand_email, "password": initial_pass},
        )
        assert res_old_login.status_code == 401

        # 6. Verify new password succeeds
        res_new_login = await client.post(
            "/api/v1/auth/login",
            json={"email": rand_email, "password": new_pass},
        )
        assert res_new_login.status_code == 200
        assert "access_token" in res_new_login.json()




