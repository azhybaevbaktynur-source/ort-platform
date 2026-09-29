from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from app.core.security import get_current_user
from app.schemas.user import UserProfile
from app.schemas.planner import DailyPlannerData, DailyTaskItem, ToggleTaskRequest
from app.schemas.question import SectionType, BilingualText

router = APIRouter()

# In-memory daily task storage for user sessions
USER_DAILY_TASKS = {}


@router.get("/daily", response_model=DailyPlannerData)
async def get_daily_planner(
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Returns today's study plan tasks, current streak count, and daily goal status.
    """
    today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    user_id = current_user.id

    if user_id not in USER_DAILY_TASKS:
        USER_DAILY_TASKS[user_id] = [
            DailyTaskItem(
                id="task_1",
                title=BilingualText(
                    ky="Математика I: 15 сызыктуу теңдеме суроолорун чыгаргыла",
                    ru="Математика I: Решите 15 задач на линейные уравнения",
                ),
                section=SectionType.MATH_1,
                questionCount=15,
                isCompleted=False,
            ),
            DailyTaskItem(
                id="task_2",
                title=BilingualText(
                    ky="Аналогиялар: 20 сөз айкашы боюнча машыгуу",
                    ru="Аналогии: 20 заданий на сопоставление слов",
                ),
                section=SectionType.ANALOGIES,
                questionCount=20,
                isCompleted=False,
            ),
            DailyTaskItem(
                id="task_3",
                title=BilingualText(
                    ky="Окуу жана түшүнүү: 1 текстти талдап, суроолоруна жооп бергиле",
                    ru="Чтение и понимание: Проанализируйте 1 текст и ответьте на вопросы",
                ),
                section=SectionType.READING,
                questionCount=10,
                isCompleted=False,
            ),
        ]

    tasks = USER_DAILY_TASKS[user_id]
    completed_count = sum(1 for t in tasks if t.isCompleted)

    return DailyPlannerData(
        date=today_str,
        streakCount=max(current_user.streak.current, 7),
        tasks=tasks,
        dailyGoalCompleted=(completed_count == len(tasks)),
        estimatedStudyMinutes=45,
    )


@router.post("/toggle-task", response_model=dict)
async def toggle_planner_task(
    payload: ToggleTaskRequest,
    current_user: UserProfile = Depends(get_current_user),
):
    """
    Toggles a daily planner task.
    """
    user_id = current_user.id
    tasks = USER_DAILY_TASKS.get(user_id, [])
    now_iso = datetime.now(timezone.utc).isoformat()

    for t in tasks:
        if t.id == payload.taskId:
            t.isCompleted = payload.isCompleted
            t.completedAt = now_iso if payload.isCompleted else None
            return {"success": True, "taskId": t.id, "isCompleted": t.isCompleted}

    return {"success": False, "message": "Task not found"}

