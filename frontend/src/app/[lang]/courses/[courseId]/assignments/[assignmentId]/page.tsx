"use client";

// Phase 7a S5: the assignment page. Students hand in here. Phase 8c S3 (PHASE_8C_DESIGN §5.1): staff land on the
// object page (Details, Submissions/Results, Settings by `?tab=`); the old redirect to `/edit` is gone.
import React, { Suspense } from "react";
import { useParams } from "next/navigation";
import { useCourse } from "@/components/lms/CourseContext";
import { AssignmentPage } from "@/components/lms/assignments/AssignmentPage";
import { StudentAssignmentView } from "@/components/lms/assignments/StudentAssignmentView";
import { LoadingState } from "@/components/ui";

export default function AssignmentRoute() {
  const { course } = useCourse();
  const params = useParams<{ assignmentId: string }>();
  const role = course.my_enrollment.role;
  if (role === "teacher" || role === "assistant") {
    return (
      <Suspense fallback={<LoadingState rows={3} />}>
        <AssignmentPage key={params.assignmentId} assignmentId={params.assignmentId} />
      </Suspense>
    );
  }
  return <StudentAssignmentView assignmentId={params.assignmentId} />;
}
