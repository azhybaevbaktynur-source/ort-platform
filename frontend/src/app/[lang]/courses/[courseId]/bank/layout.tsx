"use client";

import React from "react";
import { StaffGate } from "@/components/lms/content/StaffGate";

export default function BankLayout({ children }: { children: React.ReactNode }) {
  return <StaffGate>{children}</StaffGate>;
}
