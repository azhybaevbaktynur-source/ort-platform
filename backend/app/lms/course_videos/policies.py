"""Route policies of the lesson videos routes (docs/phases/LESSON_VIDEOS.md V2, V3), registered by
`app/core/route_inventory.py`. No new policy names: staff routes `course:content.manage`, playback
`course:content.read` (+ the syllabus visibility in the service), and the dev stream `public`: a `<video>` element sends
no bearer token, so the HMAC token in its query (video id + expiry, minted by `/play`) is the only authorization."""
_C = "/api/v1/courses/{course_id}"
_V = _C + "/videos/{video_id}"
_I = _C + "/modules/{module_id}/items/{item_id}"

COURSE_VIDEO_POLICIES: dict[tuple[str, str], str] = {
    ("GET", f"{_C}/videos"): "course:content.manage",
    ("POST", f"{_C}/videos"): "course:content.manage+ratelimit",
    ("GET", _V): "course:content.manage",
    ("PATCH", _V): "course:content.manage",
    ("DELETE", _V): "course:content.manage",
    ("PUT", f"{_V}/captions"): "course:content.manage",
    ("DELETE", f"{_V}/captions"): "course:content.manage",
    ("GET", f"{_V}/stream"): "public",  # HMAC token (db/local drivers only; R2 plays from a presigned URL)
    ("GET", f"{_I}/play"): "course:content.read+ratelimit",
    ("GET", f"{_I}/captions.vtt"): "course:content.read+ratelimit",
}
