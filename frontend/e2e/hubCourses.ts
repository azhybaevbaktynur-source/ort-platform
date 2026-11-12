import { api, seed, type SeedUser } from "./helpers";

/**
 * Step 3a S3: eight courses for the hub with many courses (STUDENT_IA_DESIGN §7.2): the two ORT courses, three ORT
 * subject courses (one of them a lesson course attached to ORT (Russian), with a lesson), two НЦТ subject courses and
 * one teacher course (the modules walk's, joined by code). The student joins all of them. `cleanup` deletes the
 * courses made here (the two ORT courses and the teacher course stay; the student's enrolments in them are left).
 * Fake titles only.
 */
export interface HubCourses {
  ortRu: string;
  ortKy: string;
  maths: string;
  mathsModule: string;
  chemistry: string;
  physics: string;
  nctPhysics: string;
  nctChemistry: string;
  teacher: string;
  made: string[];
  cleanup: () => Promise<void>;
}

export async function ortKyrgyzId(admin: SeedUser): Promise<string> {
  const page = await api(admin, "GET", "/platform/courses?q=ORT&limit=50");
  const ky = (page.items as { id: string; title?: Record<string, string> }[]).find((c) => c.title?.en === "ORT (Kyrgyz)");
  if (!ky) throw new Error("the ORT (Kyrgyz) course was not seeded");
  return ky.id;
}

export async function joinEightCourses(student: SeedUser): Promise<HubCourses> {
  const s = seed();
  const admin = s.admin;
  const ort = await api(admin, "GET", `/courses/${s.course_id}`);
  const made: string[] = [];
  const mk = async (title: string, patch: Record<string, unknown>) => {
    const c = await api(admin, "POST", "/courses", {
      title: { ru: title }, languages: ["ru"], default_language: "ru", organization_id: ort.organization_id, enrollment_mode: "open",
    });
    made.push(c.id);
    await api(admin, "POST", `/courses/${c.id}/publish`);
    await api(admin, "PATCH", `/courses/${c.id}`, { enrollment_mode: "open", visibility: "catalog", ...patch });
    return c.id as string;
  };
  const ortKy = await ortKyrgyzId(admin);
  const nctChemistry = await mk("НЦТ: Химия", { exam_family: "nct", subject: "chemistry" });
  const nctPhysics = await mk("НЦТ: Физика", { exam_family: "nct", subject: "physics" });
  const physics = await mk("ОРТ: Физика", { exam_family: "ort", subject: "physics" });
  const chemistry = await mk("ОРТ: Химия", { exam_family: "ort", subject: "chemistry" });
  const maths = await mk("ОРТ: Математика", { exam_course_id: s.course_id });
  const mod = await api(admin, "POST", `/courses/${maths}/modules`, { title: { ru: "Проценты" }, published: true });
  for (const [title, minutes] of [["Урок 1 · Что такое процент", 6], ["Урок 2 · Задачи на проценты", 10]] as const) {
    const pg = await api(admin, "POST", `/courses/${maths}/pages`, { title, language: "ru", body_md: `Текст урока «${title}».`, published: true });
    const it = await api(admin, "POST", `/courses/${maths}/modules/${mod.id}/items`, { kind: "page", page_id: pg.id, published: true, duration_s: minutes * 60 });
    await api(admin, "PUT", `/courses/${maths}/modules/${mod.id}/items/${it.id}/requirement`, { type: "view" });
  }
  // (the hub orders by the server's course order, newest course first: the subject courses before the seeded ORT ones)
  for (const id of [nctChemistry, nctPhysics, physics, chemistry, maths]) await api(student, "POST", `/courses/${id}/join`, {});
  await api(student, "POST", "/courses/join", { code: s.modules.join_code });
  await api(student, "POST", `/courses/${ortKy}/join`, {});
  await api(student, "POST", `/courses/${s.course_id}/join`, {});
  return {
    ortRu: s.course_id, ortKy, maths, mathsModule: mod.id, chemistry, physics, nctPhysics, nctChemistry, teacher: s.modules.course_id, made,
    cleanup: async () => { for (const id of made) await api(admin, "DELETE", `/courses/${id}`); },
  };
}
