"""Route policies for asset and media routes (design section 5)."""
ASSET_POLICIES: dict[tuple[str, str], str] = {
    ("POST", "/api/v1/courses/{course_id}/assets"): "course:content.manage+ratelimit",
    # F7a course cover: course.update (settings); platform courses: platform admins only (users.is_platform_admin)
    ("POST", "/api/v1/courses/{course_id}/cover"): "course:course.update+ratelimit",
    ("DELETE", "/api/v1/courses/{course_id}/cover"): "course:course.update",
    ("GET", "/api/v1/assets"): "authenticated",
    ("DELETE", "/api/v1/assets/{asset_id}"): "authenticated",
    ("GET", "/api/v1/assets/{asset_id}/content"): "authenticated",
}
MEDIA_POLICIES: dict[tuple[str, str], str] = {
    ("GET", "/api/v1/media/{name}"): "public",
}
