from typing import List, Dict, Optional, Any
from pydantic import BaseModel


class SectionMastery(BaseModel):
    section: str
    totalAttempted: int
    correctCount: int
    accuracyPercentage: float
    averageTimePerQuestionSeconds: float


class TopicWeakSpot(BaseModel):
    topic: str
    section: str
    totalAttempted: int
    accuracyPercentage: float
    recommendedAction: str


class StudentAnalyticsResponse(BaseModel):
    userId: str
    currentEstimatedScore: int
    targetScore: int
    scoreGap: int
    streak: int = 0
    totalTestsCompleted: int
    exams_taken: int = 0
    starting_score: int = 0
    totalQuestionsPracticed: int
    overallAccuracy: float
    sectionsMastery: Dict[str, SectionMastery]
    mainSectionsMastery: Dict[str, SectionMastery] = {}
    subjectSectionsMastery: Dict[str, SectionMastery] = {}
    topWeakSpots: List[TopicWeakSpot]
    recentScores: List[Dict[str, Any]] = []


class QuestionDiscriminationStat(BaseModel):
    questionId: str
    section: str
    topic: str
    totalAttempts: int
    accuracyRate: float
    discriminationIndex: float
    flaggedHard: bool


class InstructorAnalyticsResponse(BaseModel):
    totalStudents: int
    totalTestsTaken: int
    averageScaledScore: float
    goldenCertificateEligibleCount: int
    scoreDistribution: Dict[str, int]  # e.g., "<110": 12, "110-140": 45, "140-175": 110, "175-200": 80, "200-218": 35, "219+": 18
    hardestQuestions: List[QuestionDiscriminationStat]
