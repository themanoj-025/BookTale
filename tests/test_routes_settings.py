"""Tests for Book-Tale settings pages and helpers."""




class TestSettingsHelpers:
    """Test settings page helper functions."""

    def test_h_escapes_html(self) -> None:
        from app.routes.settings_pages import _h

        assert _h("<script>alert(1)</script>") == "&lt;script&gt;alert(1)&lt;/script&gt;"
        assert _h("a & b") == "a &amp; b"
        assert _h("normal text") == "normal text"
        assert _h(123) == "123"
        assert _h("") == ""

    def test_h_escapes_quotes(self) -> None:
        from app.routes.settings_pages import _h

        assert _h('value="x"') == "value=&quot;x&quot;"
        assert _h("it's") == "it&#x27;s"

    def test_h_none_value(self) -> None:
        from app.routes.settings_pages import _h

        assert _h(None) == "None"


class TestSecurityPage:
    """Test security page rendering."""

    def test_security_page_contains_items(self) -> None:
        """Security page should mention key security features."""
        from app.routes.settings_pages import security_page

        rendered = security_page(lambda content: content)
        assert "Password hashing" in rendered
        assert "CSRF protection" in rendered
        assert "Rate limiting" in rendered
        assert "Audit trail" in rendered

    def test_security_page_escapes_html(self) -> None:
        """Security page should escape HTML in content."""
        from app.routes.settings_pages import security_page

        rendered = security_page(lambda content: content)
        # Should not contain unescaped HTML tags from user content
        assert "&lt;" in rendered or "script" not in rendered


class TestSettingsPages:
    """Test settings page rendering."""

    def test_settings_page_returns_response(self, app_client: object) -> None:
        """Settings page should return a valid response."""
        client = app_client  # type: ignore[assignment]
        resp = client.get("/settings")
        assert resp.status_code in (200, 302, 401, 403)

    def test_help_page_returns_response(self, app_client: object) -> None:
        """Help page should return a valid response."""
        client = app_client  # type: ignore[assignment]
        resp = client.get("/help")
        assert resp.status_code in (200, 302, 401, 403)
