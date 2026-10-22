"""Route policies for asset and media routes (design section 5)."""
ASSET_POLICIES: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/courses/{course_id}/assets"): "course:content.manage+ratelimit",
    ("GET", "/api/v1/assets"): "authenticated",
    ("DELETE", "/api/v1/assets/{asset_id}"): "authenticated",
    ("GET", "/api/v1/assets/{asset_id}/content"): "authenticated",
}
MEDIA_POLICIES: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/media/{name}"): "public",
}
