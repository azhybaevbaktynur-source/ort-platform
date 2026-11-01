"use client";

import { useParams } from "next/navigation";
import { ParentLinkView } from "@/components/guardian/ParentLinkView";

export default function ParentLinkPage() {
  const { linkId } = useParams<{ linkId: string }>();
  return <ParentLinkView linkId={linkId} />;
}
