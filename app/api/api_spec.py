"""api_spec.py - OpenAPI 3.1 document for the BookTale HTTP API.

Served at /api/openapi.json and rendered by Swagger UI at /api/docs (pinned
CDN), making the README's API-docs claim real: every documented endpoint can
be executed from the Swagger UI "Try it out" button against a running
instance. The spec describes the app's ACTUAL routes (paths, methods,
parameters, envelopes) — documented endpoints are all live code; endpoints
not yet documented simply don't appear (the full route list lives in the
route modules). This is deliberately honest: no `/api/v1` claims, no
endpoints that don't exist.
"""

# Response envelope used across the app's JSON endpoints.
# Success: {"success": true, ...payload...}
# Error:   {"success": false, "error": "..."} (or, for centralized handlers,
#          {"data": null, "error": {"code": N, "message": "..."}})


def _error_response_component() -> dict:
    return {
        "type": "object",
        "properties": {
            "success": {"type": "boolean", "example": False},
            "error": {"type": "string", "example": "Something went wrong"},
        },
    }


def _envelope_success(schema: dict) -> dict:
    return {
        "type": "object",
        "properties": {"success": {"type": "boolean"}, **schema["properties"]},
    }


def build_openapi_spec() -> dict:
    """Return the OpenAPI 3.1 document describing the live endpoints."""
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "BookTale API",
            "description": (
                "HTTP API for the BookTale library-management platform. "
                "JSON endpoints return a payload; errors return "
                '{"success": false, "error": "..."} (centralized handlers '
                'use {"data": null, "error": {"code", "message"}}).'
            ),
            "version": "2.0.0",
        },
        "servers": [{"url": "/", "description": "Same-origin (relative)"}],
        "tags": [
            {"name": "Health", "description": "Liveness / readiness probes"},
            {"name": "Auth", "description": "Registration, login, password reset"},
            {"name": "Books", "description": "Catalog search"},
            {"name": "Social", "description": "Feed, posts, comments, follows"},
            {"name": "Profile", "description": "User profile and settings"},
            {"name": "Uploads", "description": "Image uploads (magic-byte verified)"},
            {"name": "Admin", "description": "Admin-only operations"},
        ],
        "paths": {
            # ── Health ─────────────────────────────────────────────
            "/healthz": {
                "get": {
                    "tags": ["Health"],
                    "summary": "Liveness probe",
                    "responses": {"200": {"description": "Process alive"}},
                }
            },
            "/readyz": {
                "get": {
                    "tags": ["Health"],
                    "summary": "Readiness probe (DB reachable)",
                    "responses": {
                        "200": {"description": "Database connected"},
                        "503": {"description": "Database unreachable"},
                    },
                }
            },
            # ── Auth ───────────────────────────────────────────────
            "/login": {
                "post": {
                    "tags": ["Auth"],
                    "summary": "Log in (rate-limited to failed attempts)",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "type": "object",
                                    "required": ["user_id", "password"],
                                    "properties": {
                                        "user_id": {"type": "string"},
                                        "password": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "302": {"description": "Redirect to the feed"},
                        "401": {"description": "Bad credentials"},
                        "429": {"description": "Too many failed attempts"},
                    },
                }
            },
            "/register": {
                "post": {
                    "tags": ["Auth"],
                    "summary": "Self-service registration (role always 'user')",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/x-www-form-urlencoded": {
                                "schema": {
                                    "type": "object",
                                    "required": ["user_id", "name", "password"],
                                    "properties": {
                                        "user_id": {
                                            "type": "string",
                                            "example": "MEM-1001",
                                        },
                                        "name": {"type": "string"},
                                        "email": {"type": "string", "format": "email"},
                                        "password": {"type": "string", "minLength": 12},
                                        "confirm_password": {
                                            "type": "string",
                                            "minLength": 12,
                                        },
                                        # role is accepted but ALWAYS downgraded to "user".
                                        "role": {"type": "string", "enum": ["user"]},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {"200": {"description": "Registered page"}},
                }
            },
            "/forgot-password": {
                "post": {
                    "tags": ["Auth"],
                    "summary": "Request a password reset email (anti-enumeration: always 200)",
                    "responses": {"200": {"description": "Generic success screen"}},
                }
            },
            "/reset-password": {
                "get": {
                    "tags": ["Auth"],
                    "summary": "Show the reset form for a token",
                    "parameters": [
                        {
                            "name": "token",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Reset form"}},
                },
                "post": {
                    "tags": ["Auth"],
                    "summary": "Set a new password (token consumed, single-use)",
                    "responses": {"200": {"description": "Password reset"}},
                },
            },
            "/verify-email": {
                "get": {
                    "tags": ["Auth"],
                    "summary": "Verify an email address with a one-time token (24h TTL)",
                    "parameters": [
                        {
                            "name": "token",
                            "in": "query",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Verification result page"}},
                }
            },
            "/logout": {
                "get": {
                    "tags": ["Auth"],
                    "summary": "End the session",
                    "responses": {"302": {"description": "Redirect to login"}},
                }
            },
            # ── Books ──────────────────────────────────────────────
            "/api/search": {
                "get": {
                    "tags": ["Books"],
                    "summary": "Advanced search across books/users/posts",
                    "parameters": [
                        {"name": "q", "in": "query", "schema": {"type": "string"}},
                        {
                            "name": "entity",
                            "in": "query",
                            "schema": {
                                "type": "string",
                                "enum": ["all", "books", "users", "posts"],
                            },
                        },
                        {
                            "name": "page",
                            "in": "query",
                            "schema": {"type": "integer", "minimum": 1},
                        },
                        {
                            "name": "per_page",
                            "in": "query",
                            "schema": {"type": "integer", "minimum": 10, "maximum": 50},
                        },
                    ],
                    "responses": {"200": {"description": "Search result object"}},
                }
            },
            "/api/search/suggestions": {
                "get": {
                    "tags": ["Books"],
                    "summary": "Autocomplete suggestions (books/authors/users)",
                    "parameters": [
                        {"name": "q", "in": "query", "schema": {"type": "string"}}
                    ],
                    "responses": {"200": {"description": "Suggestion list"}},
                }
            },
            # ── Social ─────────────────────────────────────────────
            "/api/feed": {
                "get": {
                    "tags": ["Social"],
                    "summary": "Feed posts (following/trending/discover)",
                    "parameters": [
                        {"name": "page", "in": "query", "schema": {"type": "integer"}},
                        {
                            "name": "tab",
                            "in": "query",
                            "schema": {
                                "type": "string",
                                "enum": ["following", "trending", "discover"],
                            },
                        },
                    ],
                    "responses": {"200": {"description": "Posts page"}},
                }
            },
            "/api/posts": {
                "post": {
                    "tags": ["Social"],
                    "summary": "Create a post (30/min)",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "required": ["content"],
                                    "properties": {
                                        "content": {"type": "string", "maxLength": 500},
                                        "type": {"type": "string", "default": "post"},
                                        "book_ids": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                        "image_urls": {
                                            "type": "array",
                                            "items": {"type": "string"},
                                        },
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Created post payload"}},
                }
            },
            "/api/posts/{post_id}/comments": {
                "get": {
                    "tags": ["Social"],
                    "summary": "List comments on a post",
                    "parameters": [
                        {
                            "name": "post_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Comment list"}},
                },
                "post": {
                    "tags": ["Social"],
                    "summary": "Add a comment (30/min)",
                    "parameters": [
                        {
                            "name": "post_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Created comment"}},
                },
            },
            "/api/posts/{post_id}/like": {
                "post": {
                    "tags": ["Social"],
                    "summary": "Like / unlike a post (60/min)",
                    "parameters": [
                        {
                            "name": "post_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Like state"}},
                }
            },
            "/api/posts/{post_id}/vote": {
                "post": {
                    "tags": ["Social"],
                    "summary": "Up/down vote a post (60/min)",
                    "parameters": [
                        {
                            "name": "post_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Net score"}},
                }
            },
            "/api/follow/{user_id}": {
                "post": {
                    "tags": ["Social"],
                    "summary": "Follow / unfollow a user (60/min)",
                    "parameters": [
                        {
                            "name": "user_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {"200": {"description": "Follow state"}},
                }
            },
            "/api/hashtags/trending": {
                "get": {
                    "tags": ["Social"],
                    "summary": "Trending hashtags",
                    "responses": {"200": {"description": "Hashtag list"}},
                }
            },
            # ── Profile / settings ─────────────────────────────────
            "/api/profile/update": {
                "post": {
                    "tags": ["Profile"],
                    "summary": "Update own profile (email changes rate-limited)",
                    "responses": {"200": {"description": "Update result"}},
                }
            },
            "/api/settings/save": {
                "post": {
                    "tags": ["Profile"],
                    "summary": "Save settings / change password (per-account rate limit)",
                    "requestBody": {
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "name": {"type": "string"},
                                        "email": {"type": "string", "format": "email"},
                                        "theme": {
                                            "type": "string",
                                            "enum": ["light", "dark"],
                                        },
                                        "current_password": {"type": "string"},
                                        "new_password": {
                                            "type": "string",
                                            "minLength": 12,
                                        },
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Save result"}},
                }
            },
            "/api/upload": {
                "post": {
                    "tags": ["Uploads"],
                    "summary": (
                        "Upload an image (magic-byte verified + re-encoded; "
                        "renamed HTML/JS is rejected) — multipart/form-data, 10/min"
                    ),
                    "requestBody": {
                        "content": {
                            "multipart/form-data": {
                                "schema": {
                                    "type": "object",
                                    "required": ["file"],
                                    "properties": {
                                        "file": {"type": "string", "format": "binary"},
                                        "type": {
                                            "type": "string",
                                            "enum": ["avatar", "post"],
                                        },
                                    },
                                }
                            }
                        }
                    },
                    "responses": {"200": {"description": "Upload result with url"}},
                }
            },
            # ── Admin ──────────────────────────────────────────────
            "/admin/audit": {
                "get": {
                    "tags": ["Admin"],
                    "summary": "Searchable admin audit trail (admin only)",
                    "responses": {"200": {"description": "Audit page"}},
                }
            },
            "/api/admin/settings/save": {
                "post": {
                    "tags": ["Admin"],
                    "summary": (
                        "Save admin settings (admin password verified; "
                        "every change audit-logged; per-account rate limit)"
                    ),
                    "responses": {"200": {"description": "Save result"}},
                }
            },
        },
        "components": {
            "schemas": {
                "ErrorResponse": _error_response_component(),
                "SuccessEnvelope": _envelope_success(
                    {"properties": {"data": {"type": "object"}}}
                ),
            },
            "securitySchemes": {
                "sessionCookie": {
                    "type": "apiKey",
                    "in": "cookie",
                    "name": "session",
                    "description": "Flask session cookie set by /login",
                }
            },
        },
        "security": [{"sessionCookie": []}],
    }
