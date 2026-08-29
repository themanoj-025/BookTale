"""
auth_routes.py - Authentication routes (login, register, forgot-password,
verify-email, reset-password, logout).

Extracted from web_app.py to reduce file size and improve maintainability.
"""

import html
from functools import wraps

from flask import g, redirect, render_template, request, session, url_for


def init_auth_routes(app, storage, lib, auth, notif_mgr) -> None:
    """Register authentication routes on the Flask app."""

    def _rate_limit(limit_value: str, **kwargs: Any) -> Any:
        """Rate-limit decorator; no-op fallback if flask-limiter is missing."""
        _lim = app.extensions.get("booktale_limiter")
        if _lim is None:
            return lambda f: f
        return _lim.limit(limit_value, **kwargs)

    def h(text: object) -> str:
        return html.escape(str(text))

    def render_auth_page(title: str, content: str, **kw: Any) -> str:
        """Render an auth page using the split-screen auth_base.html template."""
        return render_template("auth_base.html", title=title, auth_content=content, session={}, **kw)

    def get_current_user() -> Any:
        if "user_id" not in session:
            return None
        return storage.load_users().get(session["user_id"])

    def render_page(title: str, content: str, **kw: Any) -> str:
        user = get_current_user()
        return render_template(
            "base.html",
            title=title,
            content=content,
            notif_count=notif_mgr.get_unread_count(user.user_id) if user else 0,
            **kw,
        )

    def login_required(f: Callable[..., Any]) -> Callable[..., Any]:
        @wraps(f)
        def d(*a: Any, **k: Any) -> Any:
            if "user_id" not in session:
                return redirect(url_for("login_page"))
            return f(*a, **k)
        return d

    # ── Logout ──────────────────────────────────────────────────────────────

    @app.route("/logout")
    def logout() -> Any:
        session.clear()
        return redirect(url_for("login_page"))

    # ── Login ───────────────────────────────────────────────────────────────

    @app.route("/login", methods=["GET", "POST"])
    @_rate_limit(
        "10 per minute",
        methods=["POST"],
        exempt_when=lambda: request.method == "GET",
        deduct_when=lambda response: getattr(g, "_login_failed", False),
    )
    def login_page() -> str:
        if request.method == "GET":
            return render_template("auth/login.html", title="Login", form_aria_label="Login form")

        from app.core.exceptions import AuthenticationError

        try:
            user = auth.login(request.form["user_id"], request.form["password"])
            session["user_id"] = user.user_id
            session["user_name"] = user.name
            session["role"] = user.role
            from app.core.logger import log
            log("Web login", user.user_id)
            return redirect(url_for("feed_page"))
        except AuthenticationError:
            g._login_failed = True
            return render_template(
                "auth/login.html", title="Login", error=True, form_aria_label="Login form"
            )

    # ── Register ────────────────────────────────────────────────────────────

    @app.route("/register", methods=["GET", "POST"])
    @_rate_limit("5 per minute", methods=["POST"], exempt_when=lambda: request.method == "GET")
    def register_page() -> str:
        if request.method == "GET":
            return render_template(
                "auth/register.html", title="Register", form_aria_label="Registration form"
            )

        user_id = request.form.get("user_id", "").strip()
        name = request.form.get("name", "").strip()
        password = request.form.get("password", "")
        confirm_pw = request.form.get("confirm_password", "")
        email = request.form.get("email", "").strip()
        role = request.form.get("role", "user")
        if role not in ("user",):
            role = "user"

        errors = []
        if not user_id or not name or not password:
            errors.append("All required fields must be filled")
        if password != confirm_pw:
            errors.append("Passwords do not match")
        if len(password) < 12:
            errors.append("Password must be at least 12 characters")
        if user_id and not user_id.startswith("MEM-"):
            errors.append("User ID must follow MEM-XXXX format")

        if errors:
            return render_template(
                "auth/register.html",
                title="Register",
                errors=errors,
                form_aria_label="Registration form",
            )

        users = storage.load_users()
        if user_id in users:
            return render_template(
                "auth/register.html",
                title="Register",
                error="User ID already exists",
                form_aria_label="Registration form",
            )

        from app.services.auth.auth import generate_verify_token as _gvt
        from app.services.auth.auth import hash_password as _hp

        lib.register_user(user_id, name, email, "", role, _hp(password), actor="registration")

        if email:
            try:
                from app.services.email.email_notifier import send_email

                token = _gvt(user_id)
                verify_url = request.host_url.rstrip("/") + "/verify-email?token=" + token
                send_email(
                    email,
                    "Welcome to BookTale!",
                    (
                        "<h2>Welcome to BookTale!</h2>"
                        "<p>Thanks for joining, " + name + "!</p>"
                        "<p>Please verify your email address:</p>"
                        '<p><a href="'
                        + verify_url
                        + '" style="display:inline-block;padding:.6rem 1.2rem;background:#4f46e5;color:white;text-decoration:none;border-radius:8px;">Verify Email</a></p>'
                        "<p>Or copy this link: " + verify_url + "</p>"
                        "<p>Happy reading!</p>"
                    ),
                )
            except (ValueError, KeyError) as e:
                from app.core.logger import log
                log("Welcome email error", extra=str(e))

        return render_template(
            "auth/registered.html", title="Registered", name=name, email=email or None
        )

    # ── Forgot Password ─────────────────────────────────────────────────────

    @app.route("/forgot-password", methods=["GET", "POST"])
    @_rate_limit("5 per minute", methods=["POST"], exempt_when=lambda: request.method == "GET")
    def forgot_password_page() -> str:
        if request.method == "GET":
            return render_template(
                "auth/forgot_password.html",
                title="Forgot Password",
                form_aria_label="Password reset form",
            )

        identity = request.form.get("identity", "").strip()
        if identity:
            try:
                from app.services.auth.auth import generate_reset_token as _grt

                users = storage.load_users()
                target_user = None
                for u in users.values():
                    if u.user_id == identity or u.email == identity:
                        target_user = u
                        break
                if target_user and target_user.email:
                    from app.services.email.email_notifier import send_email

                    token = _grt(target_user.user_id)
                    reset_url = request.host_url.rstrip("/") + "/reset-password?token=" + token
                    send_email(
                        target_user.email,
                        "Reset your BookTale password",
                        (
                            "<h2>Password Reset Request</h2>"
                            "<p>Hi " + target_user.name + ",</p>"
                            "<p>Click the button below to reset your password:</p>"
                            '<p><a href="'
                            + reset_url
                            + '" style="display:inline-block;padding:.6rem 1.2rem;background:#4f46e5;color:white;text-decoration:none;border-radius:8px;">Reset Password</a></p>'
                            "<p>Or copy this link: " + reset_url + "</p>"
                            "<p>This link expires in 15 minutes.</p>"
                            "<p>If you did not request this, you can safely ignore this email.</p>"
                        ),
                    )
            except (ValueError, KeyError) as e:
                from app.core.logger import log
                log("Reset email error", extra=str(e))

        return render_template(
            "auth/forgot_password.html",
            title="Email Sent",
            sent=True,
            form_aria_label="Password reset form",
        )

    # ── Verify Email ────────────────────────────────────────────────────────

    @app.route("/verify-email")
    def verify_email_page() -> str:
        token = request.args.get("token", "")
        if not token:
            CONTENT = (
                '<div class="text-center">'
                '<div style="font-size:4rem;margin-bottom:1rem;">🔗</div>'
                "<h2>Invalid Link</h2>"
                '<p class="auth-subtitle">No verification token provided.</p>'
                "</div>"
                '<a href="/login" class="btn btn-primary"><i class="bi bi-arrow-left me-2"></i> Back to Login</a>'
            )
            return render_auth_page("Verify Email", CONTENT)

        from app.services.auth.auth import consume_verify_token as _cvt

        user_id = _cvt(token)

        if not user_id:
            CONTENT = (
                '<div class="text-center">'
                '<div style="font-size:4rem;margin-bottom:1rem;">⏰</div>'
                "<h2>Invalid or Expired Link</h2>"
                '<p class="auth-subtitle">This verification link has expired or is invalid. Please register again for a new link.</p>'
                "</div>"
                '<a href="/register" class="btn btn-primary"><i class="bi bi-person-plus-fill me-2"></i> Register Again</a>'
            )
            return render_auth_page("Verify Email", CONTENT)

        users = storage.load_users()
        if user_id in users:
            users[user_id].email_verified = True
            storage.save_users(users)

        CONTENT = (
            '<div class="text-center">'
            '<div style="font-size:4rem;margin-bottom:1rem;">✅</div>'
            "<h2>Email Verified!</h2>"
            '<p class="auth-subtitle">Your email has been verified. You can now access all features.</p>'
            "</div>"
            '<a href="/login" class="btn btn-primary"><i class="bi bi-shield-lock-fill me-2"></i> Sign In</a>'
        )
        return render_auth_page("Email Verified", CONTENT)

    # ── Reset Password ──────────────────────────────────────────────────────

    @app.route("/reset-password", methods=["GET", "POST"])
    @_rate_limit("5 per minute", methods=["POST"], exempt_when=lambda: request.method == "GET")
    def reset_password_page() -> str:
        if request.method == "GET":
            token = request.args.get("token", "")
            if not token:
                return render_auth_page(
                    "Reset Password",
                    (
                        '<div class="text-center">'
                        '<div style="font-size:4rem;margin-bottom:1rem;">🔗</div>'
                        "<h2>Invalid Link</h2>"
                        '<p class="auth-subtitle">This reset link is missing or invalid.</p>'
                        '<a href="/forgot-password" class="btn btn-primary mt-3">Request New Link</a>'
                        "</div>"
                    ),
                )
            from app.services.auth.auth import verify_reset_token as _vrt

            uid = _vrt(token)
            if not uid:
                return render_auth_page(
                    "Reset Password",
                    (
                        '<div class="text-center">'
                        '<div style="font-size:4rem;margin-bottom:1rem;">⏰</div>'
                        "<h2>Link Expired</h2>"
                        '<p class="auth-subtitle">This reset link has expired. Please request a new one.</p>'
                        '<a href="/forgot-password" class="btn btn-primary mt-3">Request New Link</a>'
                        "</div>"
                    ),
                )

            try:
                from flask_wtf.csrf import generate_csrf as _gen_csrf
            except ImportError:
                _gen_csrf = None
            _csrf_hidden = ""
            if _gen_csrf is not None:
                try:
                    _csrf_hidden = (
                        '<input type="hidden" name="csrf_token" ' 'value="' + _gen_csrf() + '">'
                    )
                except (ImportError, RuntimeError):
                    _csrf_hidden = ""

            CONTENT = (
                "<h2>Set New Password</h2>"
                '<p class="auth-subtitle">Enter your new password for account <strong>'
                + h(uid)
                + "</strong></p>"
                '<form method="POST" onsubmit="return validateResetForm()">'
                + _csrf_hidden
                + '<input type="hidden" name="token" value="'
                + token
                + '">'
                '<div class="mb-3"><label class="form-label">New Password *</label>'
                '<div class="input-group"><span class="input-group-text"><i class="bi bi-lock-fill"></i></span>'
                '<input type="password" name="password" class="form-control" placeholder="Min 12 characters" required id="resetPw" minlength="12" oninput="checkPwStrength(this.value)"></div>'
                '<div class="password-strength" id="resetPwStrength"></div>'
                '<small class="text-muted" id="resetPwHelp">At least 12 characters</small></div>'
                '<div class="mb-3"><label class="form-label">Confirm Password *</label>'
                '<div class="input-group"><span class="input-group-text"><i class="bi bi-lock-fill"></i></span>'
                '<input type="password" name="confirm_password" class="form-control" placeholder="Repeat password" required id="resetConfirmPw"></div></div>'
                '<button type="submit" class="btn btn-primary"><i class="bi bi-check-lg me-1"></i> Reset Password</button>'
                "</form>"
                '<div class="auth-divider">Remember your password?</div>'
                '<a href="/login" class="btn btn-outline"><i class="bi bi-box-arrow-in-right me-1"></i> Sign In</a>'
                "<script>"
                "function checkPwStrength(pw) {"
                'var bar = document.getElementById("resetPwStrength");'
                'var help = document.getElementById("resetPwHelp");'
                "if (!bar) return;"
                'if (pw.length === 0) { bar.className = "password-strength"; help.textContent = "At least 12 characters"; return; }'
                "var score = 0;"
                "if (pw.length >= 12) score++;"
                "if (pw.length >= 16) score++;"
                "if (/[A-Z]/.test(pw) && /[a-z]/.test(pw)) score++;"
                "if (/[0-9]/.test(pw)) score++;"
                "if (/[^A-Za-z0-9]/.test(pw)) score++;"
                'var classes = ["", "weak", "medium", "strong", "very-strong"];'
                'bar.className = "password-strength " + classes[Math.min(score, 4)];'
                'var labels = ["", "Weak", "Medium", "Strong", "Very Strong"];'
                "help.textContent = labels[Math.min(score, 4)];"
                "}"
                "function validateResetForm() {"
                'var pw = document.getElementById("resetPw").value;'
                'var cpw = document.getElementById("resetConfirmPw").value;'
                'if (pw !== cpw) { showToast("Passwords do not match", "error"); return false; }'
                'if (pw.length < 12) { showToast("Password must be at least 12 characters", "error"); return false; }'
                "return true;"
                "}"
                "</script>"
            )
            return render_auth_page("Reset Password", CONTENT)

        # POST - process password reset
        token = request.form.get("token", "")
        password = request.form.get("password", "")
        confirm_pw = request.form.get("confirm_password", "")

        if not token or not password:
            return render_auth_page(
                "Reset Password",
                '<div class="alert alert-danger">Invalid request</div><a href="/forgot-password" class="btn btn-primary">Request New Link</a>',
            )
        if password != confirm_pw:
            return render_auth_page(
                "Reset Password",
                '<div class="alert alert-danger">Passwords do not match</div><a href="/forgot-password" class="btn btn-primary">Request New Link</a>',
            )
        if len(password) < 12:
            return render_auth_page(
                "Reset Password",
                '<div class="alert alert-danger">Password must be at least 12 characters</div><a href="/forgot-password" class="btn btn-primary">Request New Link</a>',
            )

        from app.services.auth.auth import consume_reset_token as _crt
        from app.services.auth.auth import hash_password as _hp

        user_id = _crt(token)
        if not user_id:
            return render_auth_page(
                "Reset Password",
                '<div class="alert alert-danger">Invalid or expired reset link</div><a href="/forgot-password" class="btn btn-primary">Request New Link</a>',
            )

        users = storage.load_users()
        user = users.get(user_id)
        if not user:
            return render_auth_page(
                "Reset Password",
                '<div class="alert alert-danger">User not found</div><a href="/forgot-password" class="btn btn-primary">Request New Link</a>',
            )

        user.password_hash = _hp(password)
        storage.save_users(users)
        from app.core.logger import log
        log("Password reset", user_id)

        return render_auth_page(
            "Password Reset",
            (
                '<div class="text-center">'
                '<div style="font-size:4rem;margin-bottom:1rem;">🔐</div>'
                "<h2>Password Reset!</h2>"
                '<p class="auth-subtitle">Your password has been successfully changed.</p>'
                '<a href="/login" class="btn btn-primary mt-3"><i class="bi bi-box-arrow-in-right me-1"></i> Sign In</a>'
                "</div>"
            ),
        )
