"use client";

import React from "react";
import { BankGate } from "@/components/lms/content/StaffGate";

export default function BankLayout({ children }: { children: React.ReactNode }) {
  return <BankGate>{children}</BankGate>;
}
