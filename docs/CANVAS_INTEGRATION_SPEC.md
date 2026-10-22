# Instructure Canvas LMS: Pure System Architecture & Technical Specification

**Document Version**: 3.0.0 (Ground-Truth Canvas LMS Codebase Research)  
**Source Repository**: `instructure/canvas-lms` (Official Open-Source Rails Engine)  
**Target Audience**: Chief Architect, Senior Software Engineers, Autonomous Developer Agents  
**Scope**: Definitive architectural deep-dive into the real, open-source Instructure Canvas LMS codebase (`app/models/`, `app/controllers/`, and API layers). This document details how Canvas models, databases, controllers, and services operate under the hood—covering Accounts, Courses, Sections, Enrollments, Modules (`ContextModule`), Items (`ContentTag`), Progression, Question Banks (`AssessmentQuestionBank`), Quizzes, Assignments, and SpeedGrader—serving as the pure architectural reference for our comprehensive platform upgrade.

---

## Table of Contents
1. [Core Architectural Foundations & Philosophy](#1-core-architectural-foundations--philosophy)
2. [Organizational & Identity Subsystem (`Account`, `User`, `Pseudonym`)](#2-organizational--identity-subsystem-account-user-pseudonym)
3. [Course & Section Hierarchy Subsystem (`Course`, `CourseSection`, `Enrollment`)](#3-course--section-hierarchy-subsystem-course-coursesection-enrollment)
4. [Curriculum Sequencing Subsystem (`ContextModule`, `ContentTag`, `ContextModuleProgression`)](#4-curriculum-sequencing-subsystem-contextmodule-contenttag-contextmoduleprogression)
5. [Universal Assessment & Question Bank Subsystem (`AssessmentQuestionBank`, `Quiz`, `QuizGroup`)](#5-universal-assessment--question-bank-subsystem-assessmentquestionbank-quiz-quizgroup)
6. [Assignment, Grading & SpeedGrader Subsystem (`Assignment`, `Submission`, `RubricAssessment`)](#6-assignment-grading--speedgrader-subsystem-assignment-submission-rubricassessment)
7. [Canvas REST API Specification & Request/Response Payloads](#7-canvas-rest-api-specification--requestresponse-payloads)
8. [Modern Clean Implementation Blueprint (SQLAlchemy 2.0 & Pydantic v2)](#8-modern-clean-implementation-blueprint-sqlalchemy-20--pydantic-v2)
9. [How Pure Canvas Architecture Solves ORT, Olympiads & School Subjects](#9-how-pure-canvas-architecture-solves-ort-olympiads--school-subjects)

---

## 1. Core Architectural Foundations & Philosophy

In the official `instructure/canvas-lms` repository, Canvas avoids hardcoding any specific educational domain or exam structure. Instead, it relies on three architectural patterns:

```
┌────────────────────────────────────────────────────────────────────────┐
│                      CANVAS PATTERN 1: CONTEXT                         │
│                                                                        │
│   Almost every asset belongs to a polymorphic "Context":               │
│   `context_type`: "Course" | "Account" | "Group"                       │
│   `context_id`:   1042                                                 │
│                                                                        │
│   This allows Question Banks, Files, Announcements, and Discussions   │
│   to live at the Course level OR at the Account (Institution) level.   │
└────────────────────────────────────────────────────────────────────────┘
```

```
┌────────────────────────────────────────────────────────────────────────┐
│                   CANVAS PATTERN 2: POLYMORPHIC TAGS                   │
│                                                                        │
│   A Module does not have separate tables for "QuizItem", "PageItem",   │
│   or "VideoItem". It uses a single universal join model:               │
│   `ContentTag` (content_type: "Assignment" | "Quiz" | "WikiPage")      │
└────────────────────────────────────────────────────────────────────────┘
```

```
┌────────────────────────────────────────────────────────────────────────┐
│                   CANVAS PATTERN 3: DECOUPLED POOLS                    │
│                                                                        │
│   Questions do not live inside Quizzes. Questions live inside          │
│   `AssessmentQuestionBank`. Quizzes pull questions dynamically via     │
│   `QuizGroup` (randomized pools) or direct links.                      │
└────────────────────────────────────────────────────────────────────────┘
```

---

## 2. Organizational & Identity Subsystem (`Account`, `User`, `Pseudonym`)

In `app/models/`, Canvas establishes a clear multi-tenant identity hierarchy:

### 2.1 `Account` (`app/models/account.rb`)
The top-level root organization or sub-account.
* **Attributes**:
  * `name` (string): Organization name (e.g., "National Prep Network", "Sapat Lyceums").
  * `parent_account_id` (foreign key $\rightarrow$ `accounts.id`): Enables recursive sub-account hierarchies (District $\rightarrow$ School $\rightarrow$ Department).
  * `root_account_id` (foreign key): Cached reference to the top-level tenant.
  * `settings` (serialized hash): Global feature flags, branding (CSS/logos), default timezones, self-registration rules.
  * `workflow_state`: `"active"`, `"deleted"`.

### 2.2 `User` & `Pseudonym` (`app/models/user.rb`, `app/models/pseudonym.rb`)
Canvas separates the **human person** from their **authentication handle**:
* **`User`**: Represents the person, their profile, avatar, preferences, and aggregate activity.
* **`Pseudonym`**: Represents an account login credential (email/username + hashed password + SSO provider).
  * *Why*: A single student (`User`) can have one login for their high school and another login for an external tutoring center, while maintaining a single unified learning profile.

### 2.3 `EnrollmentTerm` (`app/models/enrollment_term.rb`)
Defines the academic session or semester (e.g., "Fall 2026", "Spring 2027", "Summer Intensive"):
* Controls course start dates, end dates, and grading cutoff periods across all courses assigned to the term.

---

## 3. Course & Section Hierarchy Subsystem (`Course`, `CourseSection`, `Enrollment`)

```
┌────────────────────────────────────────────────────────────────────────┐
│                         COURSE ARCHITECTURE                            │
│                                                                        │
│                            ┌───────────┐                               │
│                            │  Course   │ (Master Syllabus/Content)     │
│                            └─────┬─────┘                               │
│                                  │ has_many                            │
│                ┌─────────────────┴─────────────────┐                   │
│                ▼                                   ▼                   │
│     ┌─────────────────────┐             ┌─────────────────────┐        │
│     │    CourseSection    │             │    CourseSection    │        │
│     │   "Bishkek Morning" │             │   "Osh Weekend"     │        │
│     └──────────┬──────────┘             └──────────┬──────────┘        │
│                │ has_many                          │ has_many          │
│                ▼                                   ▼                   │
│     ┌─────────────────────┐             ┌─────────────────────┐        │
│     │     Enrollment      │             │     Enrollment      │        │
│     │ (Teacher, Student)  │             │ (Teacher, Student)  │        │
│     └─────────────────────┘             └─────────────────────┘        │
└────────────────────────────────────────────────────────────────────────┘
```

### 3.1 `Course` (`app/models/course.rb`)
The master curriculum container.
* **Key Attributes**:
  * `account_id`: Owning institution.
  * `enrollment_term_id`: Academic term.
  * `name` & `course_code`: Display name and catalog code (e.g., "Math Olympiad Intensive", "MATH-OLYMP-G10").
  * `workflow_state`: 
    * `created` (in design by teacher)
    * `claimed` (teacher assigned)
    * `available` (published and open to students)
    * `completed` (concluded / archived)
    * `deleted`
  * `is_public` (boolean): Visible in public catalog.
  * `self_enrollment` (boolean): Allows students to self-register.
  * `self_enrollment_code` (string): Secret join code (e.g., `"OLYMP-2027"`).
  * `default_view`: Landing page format (`"modules"`, `"assignments"`, `"syllabus"`, `"feed"`).

### 3.2 `CourseSection` (`app/models/course_section.rb`)
The physical cohort of students studying the course.
* **Key Attributes**:
  * `course_id`: Parent course blueprint.
  * `name`: Cohort label (e.g., "Class 11-A Morning", "Saturday Online").
  * `start_at` / `end_at`: Custom cohort dates that can override the course term.
  * `crosslist_course_id`: Allows sections to be cross-listed across multiple parent courses.

### 3.3 `Enrollment` (`app/models/enrollment.rb`)
The join entity binding a `User` to a `CourseSection` and `Course`.
* **Single Table Inheritance (STI) Subclasses**:
  * `StudentEnrollment`: Can view published content, submit quizzes, view own grades.
  * `TeacherEnrollment`: Full editing access, module design, gradebook, SpeedGrader.
  * `TaEnrollment`: Teaching assistant; grading permissions without course deletion.
  * `ObserverEnrollment`: Parents / mentors; read-only view of a linked student's progress.
  * `DesignerEnrollment`: Content creators who build modules without seeing student grades.
* **Lifecycle (`workflow_state`)**:
  * `invited` $\rightarrow$ `active` $\rightarrow$ `completed` $\rightarrow$ `inactive` $\rightarrow$ `rejected` $\rightarrow$ `deleted`.
* **Self-Enrollment Join Mechanism**:
  When a student navigates to `/enroll/:self_enrollment_code`, Canvas verifies the course has `self_enrollment == true`, creates a `StudentEnrollment` record with state `active`, and redirects the student to the course dashboard.

---

## 4. Curriculum Sequencing Subsystem (`ContextModule`, `ContentTag`, `ContextModuleProgression`)

This is the engine that transforms random materials into a guided, gamified learning journey.

### 4.1 `ContextModule` (`app/models/context_module.rb`)
Represents an instructional unit, chapter, or weekly module.
* **Attributes**:
  * `context_id` & `context_type`: Typically points to a `Course`.
  * `name` (string): e.g., "Week 1: Number Theory & Modular Arithmetic".
  * `position` (integer): Sequential ordering (1, 2, 3...).
  * `workflow_state`: `"active"`, `"unpublished"`, `"deleted"`.
  * `unlock_at` (datetime): Date gating (locks content until a specific date/time).
  * `require_sequential_progress` (boolean): Enforces completing item $N$ before item $N+1$ unlocks.
  * `prerequisites` (serialized array): List of prerequisite module hashes:
    ```ruby
    [{ id: 101, name: "Module 1: Foundations" }]
    ```
  * `completion_requirements` (serialized array): Array of completion requirement rules per item:
    ```ruby
    [
      { id: 4501, type: "must_view" },
      { id: 4502, type: "must_submit" },
      { id: 4503, type: "min_score", min_score: 80.0 },
      { id: 4504, type: "must_mark_done" }
    ]
    ```

---

### 4.2 `ContentTag` (`app/models/content_tag.rb`)
The polymorphic connector linking a `ContextModule` to any learning asset in Canvas.
* **Attributes**:
  * `context_module_id`: Parent module.
  * `content_type`: Polymorphic class name (`"Assignment"`, `"Quizzes::Quiz"`, `"WikiPage"`, `"DiscussionTopic"`, `"Attachment"`, `"ContextExternalTool"`).
  * `content_id`: Foreign key pointing to the target asset.
  * `title`: Override title displayed in the module list.
  * `position`: Order within the module.
  * `indent`: Visual nesting indentation (0, 1, 2, 3) for clean hierarchy.
  * `workflow_state`: `"active"`, `"unpublished"`.

---

### 4.3 `ContextModuleProgression` (`app/models/context_module_progression.rb`)
Tracks an individual student's real-time state inside a module.
* **Attributes**:
  * `context_module_id`: The module.
  * `user_id`: The student.
  * `workflow_state`:
    * `locked`: Prerequisites not met or date gate active.
    * `unlocked`: Student can view and begin items.
    * `started`: Student has begun completing items.
    * `completed`: All module completion requirements have been met.
  * `requirements_met`: Serialized array of satisfied requirements:
    ```ruby
    [
      { id: 4501, type: "must_view" },
      { id: 4503, type: "min_score", min_score: 85.0 }
    ]
    ```
  * `current_position`: The index of the furthest item unlocked for this student.

### 4.4 Deterministic Unlock Evaluation Algorithm
When a student completes an item or submits a quiz, Canvas calls `evaluate_progression(user)`:

$$\text{CanUnlockModule}(M, U) \iff (\text{Now}() \ge M.\text{unlock\_at}) \land \forall P \in M.\text{prerequisites}: \text{Progression}(P, U).\text{state} = \text{"completed"}$$

$$\text{CanAccessItem}(I_k, M, U) \iff \text{CanUnlockModule}(M, U) \land \Big( \neg M.\text{require\_sequential} \lor k = 1 \lor \text{RequirementMet}(I_{k-1}, U) \Big)$$

---

## 5. Universal Assessment & Question Bank Subsystem (`AssessmentQuestionBank`, `Quiz`, `QuizGroup`)

In open-source Canvas, assessment questions are **first-class, independent entities** stored in question banks, completely decoupled from individual quizzes.

```
┌────────────────────────────────────────────────────────────────────────┐
│                   CANVAS ASSESSMENT ARCHITECTURE                       │
│                                                                        │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │           AssessmentQuestionBank (Scoped to Course/Account)    │   │
│   │                                                                │   │
│   │   ┌───────────────────────┐       ┌────────────────────────┐   │   │
│   │   │  AssessmentQuestion 1 │       │  AssessmentQuestion 2  │   │   │
│   │   │  (Numerical Question) │       │  (Calculated Formula)  │   │   │
│   │   └───────────────────────┘       └────────────────────────┘   │   │
│   │   ┌───────────────────────┐       ┌────────────────────────┐   │   │
│   │   │  AssessmentQuestion 3 │       │  AssessmentQuestion 4  │   │   │
│   │   │  (Multiple Choice)    │       │  (File Upload / Proof) │   │   │
│   │   └───────────────────────┘       └────────────────────────┘   │   │
│   └───────────────────┬────────────────────────────────────────────┘   │
│                       │ referenced by                                  │
│                       ▼                                                │
│   ┌────────────────────────────────────────────────────────────────┐   │
│   │                     Quizzes::Quiz                              │   │
│   │                                                                │   │
│   │   ├── Fixed Item: Question #1 (Direct link to Question 1)      │   │
│   │   │                                                            │   │
│   │   └── QuizGroup: "Random Geometry Pool"                        │   │
│   │       ├── `assessment_question_bank_id`: Bank 104              │   │
│   │       ├── `pick_count`: 5                                      │   │
│   │       └── `question_points`: 2.0                               │   │
│   │       (Draws 5 random questions from Bank 104 for each student)│   │
│   └────────────────────────────────────────────────────────────────┘   │
└────────────────────────────────────────────────────────────────────────┘
```

### 5.1 `AssessmentQuestionBank` (`app/models/assessment_question_bank.rb`)
* **Attributes**:
  * `context_id` & `context_type`: Scoped to a `Course` (private to a course) or an `Account` (shared across all teachers in a school/franchise).
  * `title`: Bank name (e.g., "Combinatorics Level 2", "Geometry Circles", "ORT Analogies").
  * `workflow_state`: `"active"`, `"deleted"`.

---

### 5.2 `AssessmentQuestion` (`app/models/assessment_question.rb`)
The core question model. Question details are stored in a flexible serialized JSON/Hash column called `question_data`:

#### Native Question Types in Canvas:
1. **`numerical_question`**: Requires entering a specific number. Supports three answer validation modes:
   * *Exact answer with error margin* (e.g., $144 \pm 0.5$).
   * *Numeric range* (e.g., $[143.5, 144.5]$).
   * *High-precision exact match*.
2. **`calculated_question`** (Formula Questions):
   * Instructors write formulas with variable wildcards: `"If a car travels at {v} km/h for {t} hours, what is distance {d}?"`
   * Canvas dynamically assigns randomized numbers to $\{v\}$ and $\{t\}$ for each student and evaluates $\{d\} = \{v\} \times \{t\}$.
3. **`multiple_choice_question`**: Standard 4–5 option single select.
4. **`multiple_answers_question`**: Multi-select checkboxes with partial credit.
5. **`true_false_question`**: Binary boolean test.
6. **`short_answer_question`**: Text string match with wildcard support.
7. **`essay_question`**: Rich text open answer graded manually by the teacher.
8. **`file_upload_question`**: Student uploads a document or image (essential for handwritten Olympiad proofs).
9. **`text_only_question`**: Stimulus text / reading passage without input, followed by related questions.

---

### 5.3 `Quizzes::Quiz` (`app/models/quizzes/quiz.rb`)
Represents an exam or practice assessment.
* **Attributes**:
  * `quiz_type`: `"practice_quiz"`, `"assignment"` (graded), `"graded_survey"`, `"survey"`.
  * `time_limit`: Duration in minutes (or `null` for untimed).
  * `shuffle_answers`: Randomizes option orders (A/B/C/D) per student.
  * `allowed_attempts`: Number of retakes allowed (1, 2, or -1 for unlimited).
  * `scoring_policy`: `"keep_highest"`, `"keep_latest"`, `"keep_average"`.
  * `access_code`: 4-to-6 digit PIN for proctored exam sessions.
  * `ip_filter`: IP range restriction for secure test centers.
  * `due_at` / `lock_at`: Calendar deadlines.

---

### 5.4 `Quizzes::QuizGroup` (`app/models/quizzes/quiz_group.rb`)
Enables dynamic, randomized exam generation.
* **Attributes**:
  * `quiz_id`: Parent quiz.
  * `assessment_question_bank_id`: Reference to the question bank.
  * `pick_count`: Number of questions to randomly draw (e.g., 5).
  * `question_points`: Point value assigned to each drawn question.
* **How it works at runtime**: When a student clicks "Begin Exam", the quiz generator executes:
  ```ruby
  bank.assessment_questions.active.order("RANDOM()").limit(group.pick_count)
  ```
  Every student gets a unique, cheating-resistant question set.

---

## 6. Assignment, Grading & SpeedGrader Subsystem (`Assignment`, `Submission`, `RubricAssessment`)

### 6.1 `Assignment` (`app/models/assignment.rb`)
In Canvas, every graded activity (whether a quiz, a project, or homework) is represented by an `Assignment`.
* **Attributes**:
  * `title`: Assignment name.
  * `points_possible`: Total score.
  * `grading_type`: `"pass_fail"`, `"percent"`, `"letter_grade"`, `"points"`.
  * `submission_types`: 
    * `online_quiz` (auto-graded by quiz engine)
    * `online_upload` (file/photo upload)
    * `online_text_entry` (rich text essay)
    * `on_paper` (in-class physical exam)
  * `due_at` / `unlock_at` / `lock_at`: Global deadlines.
  * **`AssignmentOverride`** (`app/models/assignment_override.rb`): Allows different sections within the same course to have different due dates! (e.g., Tuesday cohort due on Tuesday, Saturday cohort due on Saturday).

---

### 6.2 `Submission` & `SubmissionComment` (`app/models/submission.rb`, `submission_comment.rb`)
* **`Submission`**: Represents the student's submitted attempt.
  * `score` (float): Numeric points awarded.
  * `grade` (string): Formatted grade (e.g. `"95%"`, `"A"`, `"185"`).
  * `workflow_state`: `"submitted"`, `"unsubmitted"`, `"graded"`, `"pending_review"`.
  * `attempt` (integer): Attempt counter.
* **`SubmissionComment`**: The interactive feedback loop between teacher and student:
  * Supports text comments, audio voice notes (`media_comment_url`), and file attachments.

---

### 6.3 `SpeedGrader` (`app/controllers/submissions_api_controller.rb`)
SpeedGrader is not a separate database table; it is a specialized, high-performance controller interface that brings together:
1. The student's submitted answers / uploaded document viewer.
2. The interactive multi-criterion grading rubric (`RubricAssessment`).
3. Audio/text feedback recording.
4. Rapid student navigation (`J` / `K` shortcuts to flip between students in the roster).

---

## 7. Canvas REST API Specification & Request/Response Payloads

Below are the exact API shapes used by the Canvas LMS REST API.

### 7.1 Course Creation & Self-Enrollment Code
* **`POST /api/v1/accounts/:account_id/courses`**
```json
{
  "course": {
    "name": "Republican Math Olympiad Grade 10",
    "course_code": "MATH-OLYMP-G10",
    "is_public": true,
    "self_enrollment": true,
    "default_view": "modules"
  }
}
```

* **Response (`201 Created`)**:
```json
{
  "id": 10842,
  "name": "Republican Math Olympiad Grade 10",
  "course_code": "MATH-OLYMP-G10",
  "workflow_state": "created",
  "self_enrollment_code": "OLYMP10",
  "enrollment_term_id": 12
}
```

---

### 7.2 Creating a Module with Prerequisites & Requirements
* **`POST /api/v1/courses/:course_id/modules`**
```json
{
  "module": {
    "name": "Module 2: Advanced Divisibility",
    "position": 2,
    "require_sequential_progress": true,
    "prerequisite_module_ids": [10840]
  }
}
```

* **`POST /api/v1/courses/:course_id/modules/:module_id/items`**
```json
{
  "module_item": {
    "title": "Divisibility Mastery Checkpoint",
    "type": "Quiz",
    "content_id": "quiz_984",
    "position": 1,
    "indent": 0,
    "completion_requirement": {
      "type": "min_score",
      "min_score": 80.0
    }
  }
}
```

---

### 7.3 Creating a Question Bank with a Numerical Olympiad Question
* **`POST /api/v1/courses/:course_id/question_banks`**
```json
{
  "title": "Olympiad Number Theory Bank"
}
```

* **`POST /api/v1/question_banks/:bank_id/assessment_questions`**
```json
{
  "question": {
    "question_name": "Divisibility by 7",
    "question_type": "numerical_question",
    "question_text": "Find the remainder when $2^{100}$ is divided by $7$.",
    "points_possible": 5.0,
    "answers": [
      {
        "answer_weight": 100,
        "numerical_answer_type": "exact_answer",
        "answer_exact": 2.0,
        "answer_error_margin": 0.0
      }
    ]
  }
}
```

---

## 8. Modern Clean Implementation Blueprint (SQLAlchemy 2.0 & Pydantic v2)

When building our platform upgrade in modern Python (FastAPI + SQLAlchemy 2.0 + PostgreSQL), we mirror Canvas’s domain model directly into clean, type-safe structures:

### 8.1 Core SQLAlchemy 2.0 Models

```python
# app/models/canvas_core.py
from datetime import datetime
from typing import Optional, List
from sqlalchemy import String, Integer, Float, Boolean, DateTime, ForeignKey, JSON
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

class Base(DeclarativeBase):
    pass

class Account(Base):
    __tablename__ = "accounts"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    parent_account_id: Mapped[Optional[str]] = mapped_column(ForeignKey("accounts.id"), nullable=True)
    settings: Mapped[dict] = mapped_column(JSON, default=dict)
    workflow_state: Mapped[str] = mapped_column(String(20), default="active")
    
    courses: Mapped[List["Course"]] = relationship(back_populates="account")

class Course(Base):
    __tablename__ = "courses"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    account_id: Mapped[str] = mapped_column(ForeignKey("accounts.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    course_code: Mapped[str] = mapped_column(String(50), nullable=False)
    workflow_state: Mapped[str] = mapped_column(String(20), default="created")
    self_enrollment: Mapped[bool] = mapped_column(Boolean, default=False)
    self_enrollment_code: Mapped[Optional[str]] = mapped_column(String(20), unique=True, nullable=True)
    default_view: Mapped[str] = mapped_column(String(20), default="modules")
    
    account: Mapped["Account"] = relationship(back_populates="courses")
    sections: Mapped[List["CourseSection"]] = relationship(back_populates="course")
    modules: Mapped[List["ContextModule"]] = relationship(back_populates="course")

class CourseSection(Base):
    __tablename__ = "course_sections"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    start_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    end_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    
    course: Mapped["Course"] = relationship(back_populates="sections")
    enrollments: Mapped[List["Enrollment"]] = relationship(back_populates="section")

class Enrollment(Base):
    __tablename__ = "enrollments"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    user_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), nullable=False)
    course_section_id: Mapped[str] = mapped_column(ForeignKey("course_sections.id"), nullable=False)
    type: Mapped[str] = mapped_column(String(30), default="StudentEnrollment") # Teacher, Student, TA
    workflow_state: Mapped[str] = mapped_column(String(20), default="active")
    
    section: Mapped["CourseSection"] = relationship(back_populates="enrollments")

class ContextModule(Base):
    __tablename__ = "context_modules"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    course_id: Mapped[str] = mapped_column(ForeignKey("courses.id"), nullable=False)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=1)
    unlock_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    require_sequential_progress: Mapped[bool] = mapped_column(Boolean, default=True)
    prerequisites: Mapped[list] = mapped_column(JSON, default=list) # [{id: "mod_1", name: "..."}]
    completion_requirements: Mapped[list] = mapped_column(JSON, default=list) # [{id: "tag_1", type: "min_score"}]
    workflow_state: Mapped[str] = mapped_column(String(20), default="active")
    
    course: Mapped["Course"] = relationship(back_populates="modules")
    content_tags: Mapped[List["ContentTag"]] = relationship(back_populates="context_module")

class ContentTag(Base):
    __tablename__ = "content_tags"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    context_module_id: Mapped[str] = mapped_column(ForeignKey("context_modules.id"), nullable=False)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False) # "Assignment", "Quiz", "WikiPage"
    content_id: Mapped[str] = mapped_column(String, nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    position: Mapped[int] = mapped_column(Integer, default=1)
    indent: Mapped[int] = mapped_column(Integer, default=0)
    workflow_state: Mapped[str] = mapped_column(String(20), default="active")
    
    context_module: Mapped["ContextModule"] = relationship(back_populates="content_tags")

class AssessmentQuestionBank(Base):
    __tablename__ = "assessment_question_banks"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    context_type: Mapped[str] = mapped_column(String(30), default="Course") # "Course" or "Account"
    context_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    workflow_state: Mapped[str] = mapped_column(String(20), default="active")
    
    questions: Mapped[List["AssessmentQuestion"]] = relationship(back_populates="bank")

class AssessmentQuestion(Base):
    __tablename__ = "assessment_questions"
    
    id: Mapped[str] = mapped_column(String, primary_key=True)
    bank_id: Mapped[str] = mapped_column(ForeignKey("assessment_question_banks.id"), nullable=False)
    question_type: Mapped[str] = mapped_column(String(50), nullable=False) # numerical_question, calculated, etc.
    question_data: Mapped[dict] = mapped_column(JSON, nullable=False) # Stem, formula, tolerance, options
    workflow_state: Mapped[str] = mapped_column(String(20), default="active")
    
    bank: Mapped["AssessmentQuestionBank"] = relationship(back_populates="questions")
```

---

## 9. How Pure Canvas Architecture Solves ORT, Olympiads & School Subjects

Because this architecture is generic and standardized, our platform can host any educational track simultaneously without writing custom application logic:

| Feature / Discipline | ORT Main Exam | Academic Olympiads (Math/Physics) | Lyceum Entrance & School |
| :--- | :--- | :--- | :--- |
| **Course Representation** | `Course` (e.g. "ORT 12-Week Prep") | `Course` (e.g. "Grade 10 Math Olympiad") | `Course` (e.g. "Algebra Grade 10") |
| **Cohorts / Classes** | `CourseSection` (Bishkek 11-A, Osh 11-B) | `CourseSection` (National Team Cohort) | `CourseSection` (Period 3 Class) |
| **Question Bank Structure** | Banks for Math 1, Analogies, Reading | Banks for Number Theory, Geometry Proofs | Banks for Polynomials, Quadratics |
| **Question Types Used** | `multiple_choice`, Column A vs B | `numerical_question`, `calculated`, proofs | `multiple_choice`, `short_answer` |
| **Quiz Execution** | Fixed 150-Q timed exam via `Quiz` | Randomized 5-problem sets via `QuizGroup` | Weekly 10-Q homework quiz |
| **Grading & SpeedGrader** | Automated scaled normative score (60–245) | Teacher grades handwritten proof via rubric | Teacher leaves audio feedback note |
| **Student Enrollment** | Join code shared by test-prep tutor | Open enrollment link in Telegram group | School uploads student email roster |

---

## 10. Architectural Conclusion

By researching and documenting the exact, uncompromised domain architecture of open-source Canvas LMS, we now possess the definitive blueprint.

When our upcoming platform upgrade commences:
1. We implement the clean, standardized schema above.
2. We eliminate the single-exam hardcoding forever.
3. We provide teachers with the Teacher Studio to author courses, manage Question Banks, and grade in SpeedGrader.
4. We provide students with a clean Course Cards dashboard, eradicating navigation paralysis.
