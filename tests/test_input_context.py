"""Tests for input_context module."""

from unittest.mock import patch


class TestInputContext:
    """Tests for InputContext dataclass and formatting methods."""

    def test_default_all_none(self):
        from wenzi.input_context import InputContext
        ctx = InputContext()
        assert ctx.app_name is None
        assert ctx.bundle_id is None
        assert ctx.window_title is None
        assert ctx.focused_role is None
        assert ctx.focused_description is None
        assert ctx.browser_domain is None

    def test_format_for_prompt_off(self):
        from wenzi.input_context import InputContext
        ctx = InputContext(app_name="Terminal", bundle_id="com.apple.Terminal")
        assert ctx.format_for_prompt("off") is None

    def test_format_for_prompt_basic(self):
        from wenzi.input_context import InputContext
        ctx = InputContext(app_name="Terminal", bundle_id="com.apple.Terminal")
        result = ctx.format_for_prompt("basic")
        assert "Terminal" in result
        assert "com.apple.Terminal" not in result  # bundle_id never in prompt

    def test_format_for_prompt_basic_no_app_name(self):
        from wenzi.input_context import InputContext
        ctx = InputContext()
        assert ctx.format_for_prompt("basic") is None

    def test_format_for_prompt_detailed(self):
        from wenzi.input_context import InputContext
        ctx = InputContext(
            app_name="Google Chrome",
            bundle_id="com.google.Chrome",
            window_title="GitHub - PR #42",
            focused_role="AXTextArea",
            focused_description="Comment body",
            browser_domain="github.com",
        )
        result = ctx.format_for_prompt("detailed")
        assert "Google Chrome" in result
        assert "GitHub - PR #42" in result
        assert "AXTextArea" in result
        assert "github.com" in result
        assert "com.google.Chrome" not in result

    def test_format_for_prompt_detailed_partial_fields(self):
        from wenzi.input_context import InputContext
        ctx = InputContext(app_name="Terminal", bundle_id="com.apple.Terminal")
        result = ctx.format_for_prompt("detailed")
        assert "Terminal" in result
        # Should not crash with None fields

    def test_format_for_display(self):
        from wenzi.input_context import InputContext
        ctx = InputContext(
            app_name="VS Code",
            window_title="main.py",
            focused_role="AXTextArea",
        )
        result = ctx.format_for_display()
        assert "VS Code" in result
        assert "main.py" in result
        assert "AXTextArea" in result

    def test_format_for_history_tag_off(self):
        from wenzi.input_context import InputContext
        ctx = InputContext(app_name="Terminal")
        assert ctx.format_for_history_tag("off") is None

    def test_format_for_history_tag_basic(self):
        from wenzi.input_context import InputContext
        ctx = InputContext(app_name="Terminal", bundle_id="com.apple.Terminal")
        result = ctx.format_for_history_tag("basic")
        assert result == "Terminal"

    def test_format_for_history_tag_detailed_with_domain(self):
        from wenzi.input_context import InputContext
        ctx = InputContext(
            app_name="Chrome",
            browser_domain="github.com",
            window_title="GitHub - Some Page",
        )
        result = ctx.format_for_history_tag("detailed")
        assert "Chrome" in result
        assert "github.com" in result

    def test_format_for_history_tag_detailed_with_title(self):
        from wenzi.input_context import InputContext
        ctx = InputContext(
            app_name="VS Code",
            window_title="main.py - MyProject",
        )
        result = ctx.format_for_history_tag("detailed")
        assert "VS Code" in result
        assert "main.py - MyProject" in result

    def test_to_dict_omits_none(self):
        from wenzi.input_context import InputContext
        ctx = InputContext(app_name="Terminal", bundle_id="com.apple.Terminal")
        d = ctx.to_dict()
        assert d == {"app_name": "Terminal", "bundle_id": "com.apple.Terminal"}
        assert "window_title" not in d

    def test_from_dict(self):
        from wenzi.input_context import InputContext
        d = {"app_name": "Terminal", "bundle_id": "com.apple.Terminal", "focused_role": "AXTextArea"}
        ctx = InputContext.from_dict(d)
        assert ctx.app_name == "Terminal"
        assert ctx.bundle_id == "com.apple.Terminal"
        assert ctx.focused_role == "AXTextArea"
        assert ctx.window_title is None

    def test_from_dict_none(self):
        from wenzi.input_context import InputContext
        assert InputContext.from_dict(None) is None

    def test_from_dict_empty(self):
        from wenzi.input_context import InputContext
        ctx = InputContext.from_dict({})
        assert ctx is not None
        assert ctx.app_name is None


class TestCaptureInputContext:
    """Tests for capture_input_context() function."""

    def test_off_returns_none(self):
        from wenzi.input_context import capture_input_context
        assert capture_input_context("off") is None

    @patch("wenzi.input_context._get_frontmost_app_info")
    def test_basic_collects_app_only(self, mock_info):
        from wenzi.input_context import capture_input_context
        mock_info.return_value = ("Terminal", "com.apple.Terminal", 1234)
        ctx = capture_input_context("basic")
        assert ctx is not None
        assert ctx.app_name == "Terminal"
        assert ctx.bundle_id == "com.apple.Terminal"
        assert ctx.window_title is None
        assert ctx.focused_role is None

    @patch("wenzi.input_context._get_ax_focused_element")
    @patch("wenzi.input_context._get_window_title")
    @patch("wenzi.input_context._get_frontmost_app_info")
    def test_detailed_collects_all(self, mock_info, mock_title, mock_ax):
        from wenzi.input_context import capture_input_context
        mock_info.return_value = ("Terminal", "com.apple.Terminal", 1234)
        mock_title.return_value = "zsh"
        mock_ax.return_value = ("AXTextArea", None)
        ctx = capture_input_context("detailed")
        assert ctx is not None
        assert ctx.app_name == "Terminal"
        assert ctx.window_title == "zsh"
        assert ctx.focused_role == "AXTextArea"

    @patch("wenzi.input_context._get_frontmost_app_info")
    def test_returns_none_when_no_app(self, mock_info):
        from wenzi.input_context import capture_input_context
        mock_info.return_value = (None, None, None)
        assert capture_input_context("basic") is None

    @patch("wenzi.input_context._get_browser_domain")
    @patch("wenzi.input_context._get_ax_focused_element")
    @patch("wenzi.input_context._get_window_title")
    @patch("wenzi.input_context._get_frontmost_app_info")
    def test_detailed_browser_domain(self, mock_info, mock_title, mock_ax, mock_domain):
        from wenzi.input_context import capture_input_context
        mock_info.return_value = ("Google Chrome", "com.google.Chrome", 5678)
        mock_title.return_value = "GitHub - My Repo"
        mock_ax.return_value = ("AXTextField", "Search or type a URL")
        mock_domain.return_value = "github.com"
        ctx = capture_input_context("detailed")
        assert ctx.browser_domain == "github.com"
        assert ctx.focused_description == "Search or type a URL"

    @patch("wenzi.input_context._get_frontmost_app_info")
    def test_invalid_level_treated_as_basic(self, mock_info):
        from wenzi.input_context import capture_input_context
        mock_info.return_value = ("Terminal", "com.apple.Terminal", 1234)
        ctx = capture_input_context("invalid")
        assert ctx is not None
        assert ctx.app_name == "Terminal"
        assert ctx.window_title is None  # basic level
