// S4 email change (A9): the signed-in person's own change, and the public confirmation link.
import { lmsFetch } from "./client";

/** A plausible full address; the server checks it properly. */
export const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export interface MyEmail {
  email: string;
  pending: { new_email: string; expires_at: string; by_admin: boolean } | null;
}

export const getMyEmail = () => lmsFetch<MyEmail>("/me/email-change");
/** Needs the current password; a link goes to the new address and nothing changes until it is opened. */
export const requestEmailChange = (newEmail: string, password: string, lang: string, code?: string) =>
  lmsFetch<MyEmail>("/me/email-change", { method: "POST", body: { new_email: newEmail, password, lang, ...(code ? { code } : {}) } });
export const cancelEmailChange = () => lmsFetch<void>("/me/email-change", { method: "DELETE" });
/** Public: the token from the emailed link is the proof. Every session of the account ends. */
export const confirmEmailChange = (token: string) =>
  lmsFetch<{ user_id: string; email: string }>("/auth/email-change/confirm", { method: "POST", body: { token } });
