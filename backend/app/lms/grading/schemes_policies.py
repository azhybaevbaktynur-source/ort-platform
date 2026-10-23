"""Route policies for the grading scheme library (/grading-schemes...). Teacher check and write rate limit
are enforced inside the write services; the preview limit in the router."""
_S = "/api/v1/grading-schemes"
_G = _S + "/{scheme_id}"
SCHEME_POLICIES: dict[tuple[str, str], str] = {
    ("GET", _S): "authenticated",
    ("POST", _S): "teacher_approved+ratelimit",
    ("POST", f"{_S}/preview"): "authenticated+ratelimit",
    ("GET", _G): "authenticated",
    ("PATCH", _G): "teacher_approved+ratelimit",
    ("DELETE", _G): "teacher_approved+ratelimit",
    ("POST", f"{_G}/restore"): "teacher_approved+ratelimit",
    ("POST", f"{_G}/versions"): "teacher_approved+ratelimit",
}
