"use client";

import React from "react";
import { AddItemsDialog, type AddItemsTab } from "@/components/lms/assessments/AddItemsDialog";

/**
 * "Find questions" of the quiz editor (PHASE_7C_DESIGN 8.2, amended by 16): the builder's add dialog (questions,
 * passage, random group) listing **shared banks only**; this quiz's own bank is never offered (its questions are
 * already cards, and a quiz bank is private to its quiz). The editor places what was added after the chosen card.
 */
export function FindQuestionsDrawer({
  open, courseId, assessmentId, sectionId, tab, onClose, onAdded,
}: {
  open: boolean;
  courseId: string;
  assessmentId: string;
  sectionId: string;
  tab: AddItemsTab;
  onClose: () => void;
  onAdded: () => void | Promise<void>;
}) {
  return (
    <AddItemsDialog open={open} courseId={courseId} assessmentId={assessmentId} sectionId={sectionId}
      initialTab={tab} onClose={onClose} onAdded={onAdded} quizEditor />
  );
}
