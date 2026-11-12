"use client";

import React from "react";
import Link from "next/link";
import { ArrowRight, Check } from "lucide-react";
import { useTranslation } from "@/lib/i18n/context";
import { useAuth } from "@/lib/auth-context";
import { LinkButton, Mascot, buttonClasses, cn, type MascotPose } from "@/components/ui";
import { PublicShell } from "@/components/landing/PublicShell";
import { LANDING_INNER, ROLE_ENTRIES } from "@/components/landing/roles";
import { Screenshot, type LandingShot } from "@/components/landing/Screenshot";

const H2 = "text-2xl font-bold leading-tight tracking-tight text-slate-900 sm:text-3xl lg:text-4xl";
const arrow = <ArrowRight aria-hidden="true" className="h-5 w-5" />;

function Hero() {
  const { lang, t } = useTranslation();
  const { user } = useAuth();
  return (
    <section className="bg-brand-50">
      <div className={cn(LANDING_INNER, "grid items-center gap-4 py-6 sm:py-12 lg:grid-cols-[minmax(0,1fr)_minmax(0,27rem)] lg:gap-12 lg:py-20")}>
        <div className="order-2 lg:order-1">
          <h1 className="text-[2rem] font-extrabold leading-[1.15] tracking-tight text-slate-900 sm:text-5xl lg:text-[3.5rem] lg:leading-[1.1]">
            {t("landing.hero.title")}
          </h1>
          <p className="mt-3 max-w-xl text-base leading-7 text-slate-600 sm:mt-5 sm:text-xl sm:leading-8">{t("landing.hero.subtitle")}</p>
          {user ? (
            <div className="mt-6 sm:mt-8">
              <LinkButton size="lg" href={`/${lang}/home`} className="w-full sm:w-auto sm:min-w-[14rem]" rightIcon={arrow}>
                {t("landing.hero.continue")}
              </LinkButton>
            </div>
          ) : (
            <div className="mt-5 sm:mt-8">
              <p className="text-sm font-semibold text-slate-700">{t("landing.hero.rolesLabel")}</p>
              <div className="mt-2 flex flex-col gap-3 sm:mt-3 sm:flex-row sm:flex-wrap">
                {ROLE_ENTRIES.map((role, i) => (
                  <LinkButton key={role.key} size="lg" variant={i === 0 ? "primary" : "secondary"} href={`/${lang}${role.href}`}
                    className="w-full justify-between sm:w-auto sm:min-w-[14rem]" rightIcon={arrow}>
                    {t(`landing.hero.roles.${role.key}`)}
                  </LinkButton>
                ))}
              </div>
            </div>
          )}
        </div>
        <div className="order-1 flex justify-center lg:order-2 lg:justify-end">
          <Mascot pose="hello" eager size={400} className="h-24 w-auto sm:h-48 lg:h-[26rem]" />
        </div>
      </div>
    </section>
  );
}

const WHY: { key: string; pose: MascotPose }[] = [
  { key: "structure", pose: "reading" },
  { key: "practice", pose: "thinking" },
  { key: "teachers", pose: "working" },
];

function WhyItWorks() {
  const { t } = useTranslation();
  return (
    <section aria-labelledby="landing-why" className="bg-white">
      <div className={cn(LANDING_INNER, "py-12 sm:py-16 lg:py-24")}>
        <h2 id="landing-why" className={cn(H2, "text-center")}>{t("landing.why.title")}</h2>
        <ul className="mt-8 grid gap-8 md:grid-cols-3 md:gap-10 lg:mt-14 lg:gap-14">
          {WHY.map(({ key, pose }) => (
            <li key={key} className="grid grid-cols-[5.5rem_minmax(0,1fr)] items-start gap-4 md:block md:text-center">
              {/* the wrapper: Mascot's <picture> is display: contents, so its <source> would take a grid cell */}
              <div className="flex justify-center md:mb-5">
                <Mascot pose={pose} size={400} className="h-24 w-auto md:h-40" />
              </div>
              <div>
                <h3 className="text-lg font-bold leading-6 text-slate-900 md:text-xl">{t(`landing.why.${key}.title`)}</h3>
                <p className="mt-2 text-base leading-7 text-slate-600">{t(`landing.why.${key}.text`)}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

interface BandProps {
  id: string;
  title: string;
  body: string;
  points?: string[];
  shot: LandingShot;
  alt: string;
  /** Picture left, text right from `lg` up. On phones the text always comes first. */
  flip?: boolean;
  tinted?: boolean;
  mascot?: MascotPose;
  action?: React.ReactNode;
}

function Band({ id, title, body, points, shot, alt, flip, tinted, mascot, action }: BandProps) {
  return (
    <section aria-labelledby={id} className={tinted ? "bg-slate-50" : "bg-white"}>
      <div className={cn(LANDING_INNER, "grid items-center gap-8 py-12 sm:py-16 lg:grid-cols-12 lg:gap-14 lg:py-24")}>
        <div className={cn("lg:col-span-5", flip && "lg:order-2")}>
          <h2 id={id} className={H2}>{title}</h2>
          <p className="mt-4 text-base leading-7 text-slate-600 sm:text-lg sm:leading-8">{body}</p>
          {points && (
            <ul className="mt-5 space-y-3">
              {points.map((p) => (
                <li key={p} className="flex items-start gap-3 text-base leading-6 text-slate-700">
                  <span aria-hidden="true" className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-brand-100 text-brand-700">
                    <Check className="h-3.5 w-3.5" strokeWidth={3} />
                  </span>
                  {p}
                </li>
              ))}
            </ul>
          )}
          {action && <div className="mt-7">{action}</div>}
        </div>
        <div className={cn("relative lg:col-span-7", mascot && "pb-12 lg:pb-0", flip && "lg:order-1")}>
          <Screenshot name={shot} alt={alt} />
          {mascot && <Mascot pose={mascot} size={400} className="absolute -bottom-1 right-0 h-20 w-auto sm:h-24 lg:-bottom-14 lg:-right-8 lg:h-32" />}
        </div>
      </div>
    </section>
  );
}

function FinalBlock() {
  const { lang, t } = useTranslation();
  const { user } = useAuth();
  return (
    <section aria-labelledby="landing-final" className="bg-brand-700">
      <div className={cn(LANDING_INNER, "flex flex-col items-center gap-6 py-12 text-center sm:py-16 lg:flex-row lg:justify-between lg:py-20 lg:text-left")}>
        <div className="flex flex-col items-center gap-5 lg:flex-row lg:gap-8">
          <div className="shrink-0">
            <Mascot pose="encouraging" size={400} className="h-28 w-auto rounded-full bg-white p-2 lg:h-40 lg:p-3" />
          </div>
          <div>
            <h2 id="landing-final" className="text-2xl font-bold leading-tight tracking-tight text-white sm:text-3xl lg:text-4xl">
              {t(user ? "landing.final.titleSignedIn" : "landing.final.title")}
            </h2>
            <p className="mt-3 text-base leading-7 text-brand-100 sm:text-lg">{t(user ? "landing.final.bodySignedIn" : "landing.final.body")}</p>
          </div>
        </div>
        <Link href={user ? `/${lang}/home` : `/${lang}/register`}
          className={buttonClasses({ variant: "secondary", size: "lg", className: "w-full shrink-0 border-white sm:w-auto sm:min-w-[14rem]" })}>
          {t(user ? "landing.hero.continue" : "landing.final.button")}
        </Link>
      </div>
    </section>
  );
}

export default function HomePage() {
  const { lang, t } = useTranslation();
  const startClass = "w-full sm:w-auto sm:min-w-[14rem]";
  return (
    <PublicShell>
      <Hero />
      <WhyItWorks />
      <Band id="landing-students" tinted title={t("landing.students.title")} body={t("landing.students.body")}
        points={[t("landing.students.p1"), t("landing.students.p2"), t("landing.students.p3")]}
        shot="student-dashboard" alt={t("landing.shots.studentDashboard")} mascot="celebrating"
        action={<LinkButton size="lg" href={`/${lang}/register`} className={startClass} rightIcon={arrow}>{t("landing.students.button")}</LinkButton>} />
      <Band id="landing-exam" flip title={t("landing.exam.title")} body={t("landing.exam.body")}
        shot="exam-player" alt={t("landing.shots.examPlayer")} />
      <Band id="landing-teachers" tinted title={t("landing.teachers.title")} body={t("landing.teachers.body")}
        points={[t("landing.teachers.p1"), t("landing.teachers.p2"), t("landing.teachers.p3")]}
        shot="teacher-course" alt={t("landing.shots.teacherCourse")} mascot="working"
        action={<LinkButton size="lg" href={`/${lang}/for-teachers`} className={startClass} rightIcon={arrow}>{t("landing.teachers.button")}</LinkButton>} />
      <FinalBlock />
    </PublicShell>
  );
}
