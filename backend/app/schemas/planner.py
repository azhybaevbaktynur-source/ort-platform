from typing import List, Optional
from pydantic import BaseModel, Field
from app.schemas.question import SectionType, BilingualText


class DailyTaskItem(BaseModel):
    id: str
    title: BilingualText
    section: SectionType
    questionCount: int
    isCompleted: bool = False
    completedAt: Optional[str] = None


class DailyPlannerData(BaseModel):
    date: str
    streakCount: int
    tasks: List[DailyTaskItem]
    dailyGoalCompleted: bool = False
    estimatedStudyMinutes: int = 45


class ToggleTaskRequest(BaseModel):
    taskId: str
    isCompleted: bool

