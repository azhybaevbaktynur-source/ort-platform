// F5c (COURSE_LESSONS_DESIGN §6): a TS port of `backend/app/lms/modules/video.py` `parse_video`, used only for the
// editor's "YouTube / Vimeo detected" hint in the Video dialog. The server stays the judge: a `url` item is a video
// lesson only when the backend's parser accepts it. Same strict rules: https only, an exact host from the list, no user
// info or port, no whitespace, backslash or control characters, one path shape per host, a validated id.

export type VideoProvider = "youtube" | "vimeo";
export interface ParsedVideo { provider: VideoProvider; id: string }

const YT_ID = /^[A-Za-z0-9_-]{11}$/;
const VIMEO_ID = /^[0-9]{1,12}$/;
// eslint-disable-next-line no-control-regex
const BAD_CHARS = /[\s\\\x00-\x1f\x7f]/;
const YT_HOSTS = new Set(["youtube.com", "www.youtube.com", "m.youtube.com"]);
const YT_SHORT_HOSTS = new Set(["youtu.be"]);
const YT_NOCOOKIE_HOSTS = new Set(["youtube-nocookie.com", "www.youtube-nocookie.com"]);
const VIMEO_HOSTS = new Set(["vimeo.com", "www.vimeo.com"]);
const VIMEO_PLAYER_HOSTS = new Set(["player.vimeo.com"]);
const URL_MAX = 2048;

/** `/embed/abc/` -> ["embed", "abc"]; an empty segment in the middle (`//`) makes the path invalid. */
function segments(path: string): string[] {
  const parts = path.split("/");
  if (parts.length === 0 || parts[0] !== "") return [];
  let rest = parts.slice(1);
  if (rest.length > 0 && rest[rest.length - 1] === "") rest = rest.slice(0, -1);
  return rest.some((p) => p === "") ? [] : rest;
}

const yt = (id: string | undefined): ParsedVideo | null => (id && YT_ID.test(id) ? { provider: "youtube", id } : null);
const vimeo = (id: string | undefined): ParsedVideo | null => (id && VIMEO_ID.test(id) ? { provider: "vimeo", id } : null);

/** `{provider, id}` for an allowlisted video address, else null (the item stays a plain link). */
export function parseVideo(url: string | null | undefined): ParsedVideo | null {
  if (typeof url !== "string" || !url || url.length > URL_MAX || BAD_CHARS.test(url)) return null;
  // the authority as typed (URL() lowercases and drops the default port, so check it on the raw text)
  const m = /^https:\/\/([^/?#]*)([^?#]*)(\?[^#]*)?(#.*)?$/i.exec(url);
  if (!m) return null;
  const netloc = m[1];
  if (!netloc || netloc.includes("@") || netloc.includes(":")) return null;
  const host = netloc.toLowerCase();
  if (host !== netloc) return null;
  const seg = segments(m[2]);
  const query = m[3] ? m[3].slice(1) : "";

  if (YT_HOSTS.has(host)) {
    if (seg.length === 1 && seg[0] === "watch") {
      const values = new URLSearchParams(query).getAll("v");
      return values.length === 1 ? yt(values[0]) : null;
    }
    if (seg.length === 2 && (seg[0] === "embed" || seg[0] === "shorts")) return yt(seg[1]);
    return null;
  }
  if (YT_SHORT_HOSTS.has(host)) return seg.length === 1 ? yt(seg[0]) : null;
  if (YT_NOCOOKIE_HOSTS.has(host)) return seg.length === 2 && seg[0] === "embed" ? yt(seg[1]) : null;
  if (VIMEO_HOSTS.has(host)) return seg.length === 1 ? vimeo(seg[0]) : null;
  if (VIMEO_PLAYER_HOSTS.has(host)) return seg.length === 2 && seg[0] === "video" ? vimeo(seg[1]) : null;
  return null;
}
