# Security Policy for Book-Tale

## Reporting a Vulnerability

If you discover a security vulnerability in Book-Tale, please report it privately. We take security seriously and will respond promptly.

**How to report:**
- Open a private security advisory on GitHub (if this repository is public).
- Email **manojjana.0025@gmail.com** directly. This contact is also listed in our [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- If neither channel works, open a standard issue with the label `security` without including exploit details.

**Expectations:**
- We will acknowledge receipt within 5 business days.
- We will provide an assessment and expected fix timeline within 10 business days.
- Please refrain from public disclosure until a fix is released.

## Security Measures

### Implemented
- **Password hashing:** All passwords are hashed using werkzeug's `generate_password_hash` (pbkdf2:sha256). Plain-text passwords are never stored.
- **Session-based authentication:** Flask sessions with a server-side secret key from environment variable.
- **Login decorators:** `@login_required` and `@admin_required` decorators protect sensitive routes. Unauthorized access returns a redirect or 403 response.
- **Role-based access control:** Three tiers — member, librarian, admin — each with different permissions.
- **Email verification:** Token-based email verification flow with time-limited tokens.
- **Password reset tokens:** Time-limited reset links (1-hour expiry) with verification.
- **Anti-enumeration:** The forgot-password endpoint does not reveal whether an account exists.
- **Input validation:** Email format validation, password strength requirements (min 12 characters), User ID format enforcement (MEM-XXXX).
- **File upload restrictions:** Allowed extensions and max file size are enforced.
- **Token management:** Dedicated token generation and consumption utilities in `auth.py`.

### Not Implemented
- **No HTTPS enforcement:** The application does not enforce HTTPS — recommended when deploying behind a reverse proxy.
- **No OAuth/JWT:** Authentication is session-based only for the web interface.
- **No 2FA:** Two-factor authentication is not implemented.
- **No CORS:** CORS is not configured (acceptable for same-origin Flask app).
- **No rate limiting on login:** There is no rate limiting on login attempts (risk of brute-force attack).
- **No CSRF protection:** CSRF tokens are not implemented for form submissions.

## Data Storage Security

Book-Tale uses JSON file-based storage. Important security considerations:

- **JSON files are unencrypted** — any user with filesystem access can read them.
- **No ACID transactions** — concurrent write operations risk data corruption.
- **Sensitive data in JSON:** User records include password hashes. Ensure the `DATA_DIR` directory has appropriate filesystem permissions.
- **JSON file permissions:** Restrict access to the data directory to the application user only.

## Environment Security

| Variable | Sensitivity | Notes |
| --- | --- | --- |
| `SECRET_KEY` | Critical | Used for Flask session signing. Generate a strong random value. |
| `SMTP_PASSWORD` | High | SMTP email account password. Use app-specific passwords. |
| `SMTP_SERVER` / `SMTP_PORT` / `SMTP_USERNAME` | Low | Connection details only. |

**Rotate your `SECRET_KEY` immediately if it is exposed.**

## Deployment Security

- **No built-in HTTPS:** Deploy behind a reverse proxy (nginx, Caddy) with TLS termination.
- **Default admin credentials:** The application may have default admin credentials defined in config — change these on first deployment.
- **Data directory:** Ensure the `DATA_DIR` is not publicly accessible via the web server.
- **Uploads directory:** User uploads (images) should be served with appropriate content-type headers and not executable.

## Dependency Security

Regularly audit dependencies for known vulnerabilities:

```bash
pip-audit -r requirements.txt
pip install --upgrade flask flask-socketio  # keep web framework updated
```
