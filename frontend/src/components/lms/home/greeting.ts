"use client";

// Student UI U3: the home's greeting by the device's hour (moved out of `ExamPrepHome` in step 3a S3, so the hub does
// not load the old home).
import { useTranslation } from "@/lib/i18n/context";
import { useLmsMe } from "@/lib/lms/useLmsMe";

type GreetingPart = "morning" | "afternoon" | "evening";
function partOfDay(hour: number): GreetingPart {
  if (hour >= 5 && hour < 12) return "morning";
  if (hour >= 12 && hour < 18) return "afternoon";
  return "evening";
}

/** "Добрый день, Айбек" by the device's hour; the first word of the display name. */
export function useGreeting(): string {
  const { t } = useTranslation();
  const { me } = useLmsMe();
  const part = partOfDay(new Date().getHours());
  const first = (me?.display_name ?? "").trim().split(/\s+/)[0] ?? "";
  return first ? t(`home.greeting.${part}`, { name: first }) : t(`home.greeting.${part}Plain`);
}
