"""Tests for the Quick Look preview panel (QLPreviewPanel-based)."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture
def _mock_appkit():
    """Patch AppKit / Quartz imports used by QuickLookPanel."""
    mock_panel = MagicMock()
    mock_panel.isVisible.return_value = False

    mock_ql_preview_panel = MagicMock()
    mock_ql_preview_panel.sharedPreviewPanel.return_value = mock_panel

    mock_data_source_cls = MagicMock()
    mock_data_source = MagicMock()
    mock_data_source._url = None
    mock_data_source_cls.alloc.return_value.init.return_value = mock_data_source

    mock_delegate_cls = MagicMock()
    mock_delegate = MagicMock()
    mock_delegate_cls.alloc.return_value.init.return_value = mock_delegate

    with patch(
        "wenzi.scripting.ui.quicklook_panel._get_ql_data_source_class",
        return_value=mock_data_source_cls,
    ), patch(
        "wenzi.scripting.ui.quicklook_panel._get_ql_delegate_class",
        return_value=mock_delegate_cls,
    ), patch.dict("sys.modules", {
        "AppKit": MagicMock(),
        "Foundation": MagicMock(),
        "Quartz": MagicMock(**{"QLPreviewPanel": mock_ql_preview_panel}),
    }):
        yield {
            "panel": mock_panel,
            "data_source": mock_data_source,
            "delegate": mock_delegate,
        }


class TestQuickLookPanel:
    def test_initial_state(self):
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        ql = QuickLookPanel()
        assert not ql.is_visible
        assert ql._native_panel is None
        assert ql._current_path is None
        assert not ql._configured

    def test_show_nonexistent_path_is_noop(self):
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        ql = QuickLookPanel()
        with patch("os.path.exists", return_value=False):
            ql.show("/no/such/file", anchor_panel=MagicMock())
        assert not ql._configured

    def test_show_configures_and_displays(self, _mock_appkit):
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        ql = QuickLookPanel()
        with patch("os.path.exists", return_value=True):
            ql.show("/tmp/test.pdf", anchor_panel=MagicMock())

        assert ql._configured
        assert ql._native_panel is not None
        assert ql._data_source is not None
        _mock_appkit["panel"].orderFront_.assert_called_once_with(None)
        _mock_appkit["panel"].setDataSource_.assert_called_once()
        _mock_appkit["panel"].setDelegate_.assert_called_once()

    def test_show_sets_data_source_url(self, _mock_appkit):
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        ql = QuickLookPanel()
        with patch("os.path.exists", return_value=True):
            ql.show("/tmp/test.pdf", anchor_panel=MagicMock())

        assert ql._current_path == "/tmp/test.pdf"
        _mock_appkit["panel"].reloadData.assert_called()

    def test_show_again_does_not_reconfigure(self, _mock_appkit):
        """Showing again should reuse the existing configuration."""
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        ql = QuickLookPanel()
        with patch("os.path.exists", return_value=True):
            ql.show("/tmp/a.pdf", anchor_panel=MagicMock())
            _mock_appkit["panel"].setDataSource_.reset_mock()
            ql.show("/tmp/b.pdf", anchor_panel=MagicMock())

        # setDataSource_ should not be called again
        _mock_appkit["panel"].setDataSource_.assert_not_called()
        assert ql._current_path == "/tmp/b.pdf"

    def test_update_reloads_data(self, _mock_appkit):
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        ql = QuickLookPanel()
        with patch("os.path.exists", return_value=True):
            ql.show("/tmp/a.pdf", anchor_panel=MagicMock())
            _mock_appkit["panel"].reloadData.reset_mock()
            ql.update("/tmp/b.pdf")

        assert ql._current_path == "/tmp/b.pdf"
        _mock_appkit["panel"].reloadData.assert_called_once()

    def test_update_same_path_is_noop(self, _mock_appkit):
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        ql = QuickLookPanel()
        with patch("os.path.exists", return_value=True):
            ql.show("/tmp/a.pdf", anchor_panel=MagicMock())
            _mock_appkit["panel"].reloadData.reset_mock()
            ql.update("/tmp/a.pdf")

        _mock_appkit["panel"].reloadData.assert_not_called()

    def test_update_when_not_configured_is_noop(self):
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        ql = QuickLookPanel()
        with patch("os.path.exists", return_value=True):
            ql.update("/tmp/test.pdf")  # Should not raise
        assert ql._current_path is None

    def test_close_cleans_up(self, _mock_appkit):
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        ql = QuickLookPanel()
        with patch("os.path.exists", return_value=True):
            ql.show("/tmp/test.pdf", anchor_panel=MagicMock())

        panel_ref = ql._native_panel
        delegate_ref = ql._delegate
        ql.close()

        panel_ref.setDelegate_.assert_called_with(None)
        panel_ref.setDataSource_.assert_called_with(None)
        panel_ref.orderOut_.assert_called_once_with(None)
        assert delegate_ref._panel_ref is None
        assert ql._native_panel is None
        assert ql._data_source is None
        assert ql._delegate is None
        assert ql._current_path is None
        assert not ql._configured

    def test_close_when_not_configured_is_noop(self):
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        ql = QuickLookPanel()
        ql.close()  # Should not raise

    def test_on_resign_key_callback(self):
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        callback = MagicMock()
        ql = QuickLookPanel(on_resign_key=callback)
        assert ql._on_resign_key is callback

    def test_on_shift_toggle_callback(self):
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        callback = MagicMock()
        ql = QuickLookPanel(on_shift_toggle=callback)
        assert ql._on_shift_toggle is callback

    def test_is_key_window(self, _mock_appkit):
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        ql = QuickLookPanel()
        with patch("os.path.exists", return_value=True):
            ql.show("/tmp/test.pdf", anchor_panel=MagicMock())

        mock_nsapp = MagicMock()
        mock_nsapp.keyWindow.return_value = ql._native_panel
        with patch("AppKit.NSApp", mock_nsapp):
            assert ql.is_key_window

    def test_is_key_window_false_when_not_shown(self):
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        ql = QuickLookPanel()
        assert not ql.is_key_window

    def test_close_removes_key_monitor(self, _mock_appkit):
        from wenzi.scripting.ui.quicklook_panel import QuickLookPanel

        ql = QuickLookPanel()
        with patch("os.path.exists", return_value=True):
            ql.show("/tmp/test.pdf", anchor_panel=MagicMock())

        ql._key_monitor = MagicMock()
        with patch("AppKit.NSEvent.removeMonitor_") as mock_remove:
            ql.close()
            mock_remove.assert_called_once()
        assert ql._key_monitor is None
