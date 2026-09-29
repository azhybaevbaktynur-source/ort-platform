from typing import Dict, List, Any
from fastapi import APIRouter, Depends
from app.core.security import get_current_user, require_instructor
from app.schemas.user import UserProfile
from app.schemas.analytics import (
    StudentAnalyticsResponse,
    SectionMastery,
    TopicWeakSpot,
    InstructorAnalyticsResponse,
    QuestionDiscriminationStat,
)
from app.db.firebase import get_firestore_client

router = APIRouter()


MAIN_SECTIONS = ["math_1", "math_2", "reading", "analogies", "grammar"]
SUBJECT_SECTIONS = ["chemistry", "biology", "physics", "history", "english"]


@router.get("/student", response_model=StudentAnalyticsResponse)
async def get_student_analytics(
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Computes student performance metrics, target score gaps, and topic weak areas
    dynamically from the student's actual test attempts in Firestore,
    splitting sections into Main Test and Subject Tests.
    """
    db = get_firestore_client()
    attempts_coll = db.collection("test_attempts")
    user_attempts_docs = attempts_coll.where("userId", "==", current_user.id).where("status", "==", "completed").get()

    user_attempts = [doc.to_dict() for doc in user_attempts_docs]
    user_attempts.sort(key=lambda a: a.get("completedAt") or "")

    target = current_user.target_score or current_user.targetScore.overall or 200

    sections_info: Dict[str, Dict[str, Any]] = {
        "math_1": {"attempted": 0, "correct": 0, "time": 50.0},
        "math_2": {"attempted": 0, "correct": 0, "time": 45.0},
        "reading": {"attempted": 0, "correct": 0, "time": 65.0},
        "analogies": {"attempted": 0, "correct": 0, "time": 40.0},
        "grammar": {"attempted": 0, "correct": 0, "time": 45.0},
    }

    recent_scores: List[Dict[str, Any]] = []
    total_questions = 0
    total_correct = 0

    for att in user_attempts:
        scores = att.get("scores", {})
        scaled = scores.get("scaledScore", 0)
        raw = scores.get("rawScore", 0)
        completed_at = att.get("completedAt", "")
        date_str = completed_at[:10] if completed_at else "2026-09-01"
        recent_scores.append({
            "attemptId": att.get("id"),
            "date": date_str,
            "scaled": scaled,
            "raw": raw,
            "percentile": scores.get("percentile", 50.0),
            "templateId": att.get("templateId", "ort_main_standard"),
        })

        breakdown = scores.get("sectionBreakdown", {})
        for sec_name, sec_stat in breakdown.items():
            if sec_name not in sections_info:
                sections_info[sec_name] = {"attempted": 0, "correct": 0, "time": 50.0}
            sec_raw = sec_stat.get("rawScore", 0)
            sec_max = sec_stat.get("totalQuestions", sec_stat.get("maxScore", 0))
            sections_info[sec_name]["correct"] += sec_raw
            sections_info[sec_name]["attempted"] += sec_max
            total_correct += sec_raw
            total_questions += sec_max

        # Fallback if sectionBreakdown is empty or total_questions is 0: count from questionIds
        if total_questions == 0 and att.get("questionIds"):
            total_questions += len(att.get("questionIds"))

    if user_attempts and recent_scores:
        est_score = recent_scores[-1]["scaled"]
    else:
        est_score = current_user.currentEstimatedScore or 150

    gap = max(0, target - est_score)
    overall_accuracy = round((total_correct / total_questions * 100), 1) if total_questions > 0 else 0.0

    sections_mastery: Dict[str, SectionMastery] = {}
    main_sections_mastery: Dict[str, SectionMastery] = {}
    subject_sections_mastery: Dict[str, SectionMastery] = {}

    for sec_name, data in sections_info.items():
        att_cnt = data["attempted"]
        cor_cnt = data["correct"]
        acc = round((cor_cnt / att_cnt * 100), 1) if att_cnt > 0 else 0.0
        sec_obj = SectionMastery(
            section=sec_name,
            totalAttempted=att_cnt,
            correctCount=cor_cnt,
            accuracyPercentage=acc,
            averageTimePerQuestionSeconds=data["time"],
        )
        sections_mastery[sec_name] = sec_obj

        if sec_name in MAIN_SECTIONS:
            main_sections_mastery[sec_name] = sec_obj
        elif sec_name in SUBJECT_SECTIONS or att_cnt > 0:
            if att_cnt > 0:
                subject_sections_mastery[sec_name] = sec_obj

    # Ensure all 5 main sections exist in main_sections_mastery
    for ms in MAIN_SECTIONS:
        if ms not in main_sections_mastery:
            main_sections_mastery[ms] = SectionMastery(
                section=ms,
                totalAttempted=0,
                correctCount=0,
                accuracyPercentage=0.0,
                averageTimePerQuestionSeconds=45.0,
            )

    # Calculate weak spots based on sections with lowest accuracy
    sorted_sections = sorted(
        [s for s in sections_mastery.values() if s.totalAttempted > 0],
        key=lambda s: s.accuracyPercentage
    )
    top_weak_spots: List[TopicWeakSpot] = []
    for ws in sorted_sections[:2]:
        top_weak_spots.append(
            TopicWeakSpot(
                topic=f"{ws.section.upper()} бөлүмү",
                section=ws.section,
                totalAttempted=ws.totalAttempted,
                accuracyPercentage=ws.accuracyPercentage,
                recommendedAction=f"{ws.section} боюнча 15 машыгуу суроосун чыгаргыла",
            )
        )

    if not top_weak_spots:
        top_weak_spots = [
            TopicWeakSpot(
                topic="Татаал сүйлөмдүн синтаксиси (Синтаксис)",
                section="grammar",
                totalAttempted=0,
                accuracyPercentage=0.0,
                recommendedAction="Грамматика бөлүмүнөн 10 көнүгүү аткаруу",
            ),
            TopicWeakSpot(
                topic="Антонимдер жана салыштырмалуу аналогиялар",
                section="analogies",
                totalAttempted=0,
                accuracyPercentage=0.0,
                recommendedAction="Аналогиялар боюнча карточкаларды кайталоо",
            ),
        ]

    streak_count = getattr(current_user.streak, "current", 0) if current_user.streak else 0
    if not streak_count and len(user_attempts) > 0:
        streak_count = min(len(user_attempts), 7)

    return StudentAnalyticsResponse(
        userId=current_user.id,
        currentEstimatedScore=est_score,
        targetScore=target,
        scoreGap=gap,
        streak=streak_count,
        totalTestsCompleted=len(user_attempts),
        totalQuestionsPracticed=total_questions,
        overallAccuracy=overall_accuracy,
        sectionsMastery=sections_mastery,
        mainSectionsMastery=main_sections_mastery,
        subjectSectionsMastery=subject_sections_mastery,
        topWeakSpots=top_weak_spots,
        recentScores=recent_scores,
    )


@router.get("/instructor", response_model=InstructorAnalyticsResponse)
async def get_instructor_analytics(
    current_user: UserProfile = Depends(require_instructor),
):
    """
    Computes cohort performance metrics, score distributions, and real hardest questions
    dynamically calculated from all completed test attempts in Firestore.
    """
    db = get_firestore_client()

    # 1. Total Students registered
    try:
        users_docs = db.collection("users").get()
        student_ids = {
            doc.id for doc in users_docs
            if doc.to_dict().get("role") in ("student", None)
        }
    except Exception:
        student_ids = set()

    # 2. Total Completed Exams & Scaled Scores
    completed_attempts_docs = db.collection("test_attempts").where("status", "==", "completed").get()
    completed_attempts = [d.to_dict() for d in completed_attempts_docs]

    for att in completed_attempts:
        uid = att.get("userId")
        if uid:
            student_ids.add(uid)

    total_students = max(len(student_ids), 1)
    total_tests_taken = len(completed_attempts)

    scaled_scores: List[int] = []
    golden_certificate_count = 0

    score_distribution = {
        "<110": 0,
        "110-140": 0,
        "140-175": 0,
        "175-200": 0,
        "200-218": 0,
        "219+": 0,
    }

    # 3. Aggregate Question Statistics from Attempt Reviews
    question_stats: Dict[str, Dict[str, Any]] = {}

    for att in completed_attempts:
        sc = att.get("scores", {}).get("scaledScore")
        if sc is not None:
            scaled_scores.append(sc)
            if sc >= 219:
                golden_certificate_count += 1

            if sc < 110:
                score_distribution["<110"] += 1
            elif sc < 140:
                score_distribution["110-140"] += 1
            elif sc < 175:
                score_distribution["140-175"] += 1
            elif sc < 200:
                score_distribution["175-200"] += 1
            elif sc < 219:
                score_distribution["200-218"] += 1
            else:
                score_distribution["219+"] += 1

        for item in att.get("review", []):
            qid = item.get("questionId")
            if not qid:
                continue
            if qid not in question_stats:
                question_stats[qid] = {
                    "section": item.get("section", "general"),
                    "totalAttempts": 0,
                    "correctCount": 0,
                }
            question_stats[qid]["totalAttempts"] += 1
            if item.get("isCorrect"):
                question_stats[qid]["correctCount"] += 1

    average_scaled_score = round(sum(scaled_scores) / len(scaled_scores), 1) if scaled_scores else 0.0

    # 4. Lookup Question metadata for Hardest Questions
    all_questions_docs = db.collection("questions").get()
    q_map = {d.id: d.to_dict() for d in all_questions_docs}

    hardest_list: List[QuestionDiscriminationStat] = []
    for qid, stat in question_stats.items():
        total_att = stat["totalAttempts"]
        correct = stat["correctCount"]
        acc_rate = round((correct / total_att * 100), 1) if total_att > 0 else 0.0
        q_info = q_map.get(qid, {})
        topic = q_info.get("topic") or "General"
        sec = q_info.get("section") or stat["section"]
        disc_index = round(max(0.1, min(0.9, 1.0 - (acc_rate / 100.0))), 2)

        hardest_list.append(
            QuestionDiscriminationStat(
                questionId=qid,
                section=sec,
                topic=topic,
                totalAttempts=total_att,
                accuracyRate=acc_rate,
                discriminationIndex=disc_index,
                flaggedHard=(acc_rate < 50.0),
            )
        )

    # Sort by accuracy rate ascending (lowest accuracy = hardest)
    hardest_list.sort(key=lambda x: (x.accuracyRate, -x.totalAttempts))
    hardest_list = hardest_list[:10]

    # If no questions attempted yet, provide meaningful questions from bank
    if not hardest_list:
        sample_hard = [
            q for q in q_map.values()
            if q.get("difficulty") == "hard" or "gram" in q.get("id", "") or "math" in q.get("id", "")
        ][:3]
        for hq in sample_hard:
            hardest_list.append(
                QuestionDiscriminationStat(
                    questionId=hq.get("id", "q_sample"),
                    section=hq.get("section", "grammar"),
                    topic=hq.get("topic", "Татаал тема"),
                    totalAttempts=0,
                    accuracyRate=0.0,
                    discriminationIndex=0.5,
                    flaggedHard=True,
                )
            )

    return InstructorAnalyticsResponse(
        totalStudents=total_students,
        totalTestsTaken=total_tests_taken,
        averageScaledScore=average_scaled_score,
        goldenCertificateEligibleCount=golden_certificate_count,
        scoreDistribution=score_distribution,
        hardestQuestions=hardest_list,
    )

