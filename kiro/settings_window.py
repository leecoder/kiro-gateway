# -*- coding: utf-8 -*-

# Kiro Gateway
# https://github.com/jwadow/kiro-gateway
# Copyright (C) 2025 Jwadow
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.

"""Single-panel settings window for Kiro Gateway."""

from typing import Callable, Dict, List, Optional, Tuple

import os

import objc
from AppKit import (
    NSApplication,
    NSMakeRect,
    NSView,
    NSWindow,
    NSTextField,
    NSSecureTextField,
    NSButton,
    NSStackView,
    NSUserInterfaceLayoutOrientationVertical,
    NSUserInterfaceLayoutOrientationHorizontal,
    NSApplicationActivationPolicyAccessory,
    NSApp,
    NSBezelStyleRegularSquare,
    NSImage,
    NSButtonTypeSwitch,
    NSColor,
    NSFont,
    NSBox,
    NSBoxSeparator,
)
from Foundation import NSMakePoint

_SECRET_KEYS = {"PROXY_API_KEY"}

# Keys that live inside the Advanced / HTTPS section
_HTTPS_KEYS = {"SSL_CERTFILE", "SSL_KEYFILE"}

_ICON_DIR = os.path.join(os.path.dirname(__file__), "resources")


def _load_icon(name: str) -> Optional[NSImage]:
    """Load an icon by SF Symbol name, falling back to a bundled PNG.

    Args:
        name: Icon name using dash notation (e.g. ``eye-slash``).
              The SF Symbol lookup converts dashes to dots automatically.

    Returns:
        An ``NSImage`` instance, or ``None`` when neither source is available.
    """
    img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(
        name.replace("-", "."), None
    )
    if img:
        return img
    path = os.path.join(_ICON_DIR, f"{name}.png")
    if os.path.exists(path):
        return NSImage.alloc().initWithContentsOfFile_(path)
    return None


class SettingsWindowController:
    """Controller that builds and manages the Settings NSWindow.

    The window layout is:
    - One labelled row per regular key.
    - A separator + collapsible **Advanced** section containing:
      - ``[ ] Enable HTTPS`` checkbox
      - ``SSL_CERTFILE`` / ``SSL_KEYFILE`` text fields (enabled only when
        the checkbox is checked).

    Args:
        keys: Ordered list of all editable .env key names.
        labels: Human-readable label for each key.
        values: Current values for each key.
        on_save: Callback invoked with the new values dict on Save.
    """

    # Keys excluded from the "regular" top section (handled in Advanced)
    _ADVANCED_KEYS = _HTTPS_KEYS

    def __init__(
        self,
        keys: List[str],
        labels: Dict[str, str],
        values: Dict[str, str],
        on_save: Callable[[Dict[str, str]], None],
    ):
        self.keys = keys
        self.labels = labels
        self.initial_values = dict(values)
        self.on_save = on_save
        self.fields: Dict[str, NSTextField] = {}
        self._secret_pairs: Dict[str, Tuple[NSSecureTextField, NSTextField]] = {}
        self._secret_rows: Dict[str, NSView] = {}

        # Advanced section state
        self._advanced_visible: bool = False
        self._advanced_stack: Optional[NSStackView] = None
        self._https_checkbox: Optional[NSButton] = None
        self._advanced_toggle_btn: Optional[NSButton] = None

        self.window: Optional[NSWindow] = None
        self._container: Optional[NSView] = None
        self._outer_stack: Optional[NSStackView] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def show(self) -> None:
        """Build and display the settings window."""
        app = NSApplication.sharedApplication()
        if app.activationPolicy() != NSApplicationActivationPolicyAccessory:
            app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        window = self._build_window()
        self.window = window
        window.center()
        window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    # ------------------------------------------------------------------
    # Window / layout construction
    # ------------------------------------------------------------------

    def _build_window(self) -> NSWindow:
        """Construct the full NSWindow with all subviews.

        Returns:
            A configured, ready-to-show NSWindow.
        """
        content_width = 580.0
        row_height = 24.0
        spacing = 8.0

        regular_keys = [k for k in self.keys if k not in self._ADVANCED_KEYS]
        n_regular = len(regular_keys)

        # Estimate initial height (advanced section collapsed)
        fields_height = n_regular * (row_height + spacing) + spacing
        advanced_header_height = row_height + spacing  # toggle row
        buttons_height = 40.0
        window_height = fields_height + advanced_header_height + buttons_height + 24.0

        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, content_width, window_height),
            1 << 2 | 1 << 3,  # titled | closable
            2,  # buffered
            False,
        )
        window.setTitle_("Kiro Gateway — Settings")
        window.setReleasedWhenClosed_(False)

        container = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, content_width, window_height)
        )
        self._container = container

        # ── Outer vertical stack ──────────────────────────────────────
        outer_stack = NSStackView.alloc().initWithFrame_(
            NSMakeRect(12, buttons_height + 8, content_width - 24, window_height - buttons_height - 20)
        )
        outer_stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
        outer_stack.setSpacing_(spacing)
        self._outer_stack = outer_stack

        # Regular rows
        for key in regular_keys:
            row = self._make_row(key, self.labels.get(key, key), content_width)
            outer_stack.addArrangedSubview_(row)

        # Advanced toggle row
        adv_toggle_row = self._make_advanced_toggle_row(content_width)
        outer_stack.addArrangedSubview_(adv_toggle_row)

        # Advanced content stack (hidden by default)
        adv_stack = self._make_advanced_stack(content_width)
        adv_stack.setHidden_(True)
        self._advanced_stack = adv_stack
        outer_stack.addArrangedSubview_(adv_stack)

        container.addSubview_(outer_stack)

        # ── Save / Cancel buttons ─────────────────────────────────────
        save_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(content_width - 180, 8, 80, 28)
        )
        save_btn.setTitle_("Save")
        save_btn.setBezelStyle_(1)
        save_btn.setTarget_(self)
        save_btn.setAction_("saveClicked:")

        cancel_btn = NSButton.alloc().initWithFrame_(
            NSMakeRect(content_width - 92, 8, 80, 28)
        )
        cancel_btn.setTitle_("Cancel")
        cancel_btn.setBezelStyle_(1)
        cancel_btn.setTarget_(self)
        cancel_btn.setAction_("cancelClicked:")

        container.addSubview_(save_btn)
        container.addSubview_(cancel_btn)
        window.setContentView_(container)
        return window

    def _make_advanced_toggle_row(self, content_width: float) -> NSView:
        """Build the '▶ Advanced' disclosure button row.

        Args:
            content_width: Total content area width for layout.

        Returns:
            An NSView containing the toggle button and a separator line.
        """
        row_height = 24.0
        row = NSStackView.alloc().initWithFrame_(
            NSMakeRect(0, 0, content_width - 24, row_height)
        )
        row.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
        row.setSpacing_(6)

        btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 120, row_height))
        btn.setTitle_("▶  Advanced")
        btn.setBezelStyle_(NSBezelStyleRegularSquare)
        btn.setBordered_(False)
        btn.setTarget_(self)
        btn.setAction_("toggleAdvanced:")
        self._advanced_toggle_btn = btn
        row.addArrangedSubview_(btn)

        # Spacer / separator
        sep = NSTextField.labelWithString_("")
        sep.setFrame_(NSMakeRect(0, 0, content_width - 24 - 126, row_height))
        row.addArrangedSubview_(sep)

        return row

    def _make_advanced_stack(self, content_width: float) -> NSStackView:
        """Build the collapsible Advanced content stack.

        Contains:
        - 'Enable HTTPS' checkbox
        - SSL_CERTFILE row (conditionally enabled)
        - SSL_KEYFILE row (conditionally enabled)

        Args:
            content_width: Total content area width for layout.

        Returns:
            A configured NSStackView (initially hidden).
        """
        row_height = 24.0
        spacing = 8.0

        stack = NSStackView.alloc().initWithFrame_(
            NSMakeRect(0, 0, content_width - 24, 3 * (row_height + spacing))
        )
        stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
        stack.setSpacing_(spacing)

        # ── HTTPS checkbox ────────────────────────────────────────────
        https_enabled = bool(
            self.initial_values.get("SSL_CERTFILE", "").strip()
            or self.initial_values.get("SSL_KEYFILE", "").strip()
        )

        cb = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, content_width - 24, row_height))
        cb.setButtonType_(NSButtonTypeSwitch)
        cb.setTitle_("  Enable HTTPS (TLS)")
        cb.setState_(1 if https_enabled else 0)
        cb.setTarget_(self)
        cb.setAction_("httpsToggled:")
        self._https_checkbox = cb
        stack.addArrangedSubview_(cb)

        # ── SSL_CERTFILE / SSL_KEYFILE rows ───────────────────────────
        for key in ("SSL_CERTFILE", "SSL_KEYFILE"):
            if key not in self.keys:
                continue
            row = self._make_row(key, self.labels.get(key, key), content_width)
            # Disable the field initially if HTTPS is off
            field = self.fields.get(key)
            if field is not None:
                field.setEnabled_(https_enabled)
                field.setTextColor_(
                    NSColor.controlTextColor() if https_enabled else NSColor.disabledControlTextColor()
                )
            stack.addArrangedSubview_(row)

        return stack

    # ------------------------------------------------------------------
    # Row builders
    # ------------------------------------------------------------------

    def _make_row(self, key: str, label_text: str, content_width: float) -> NSView:
        """Build a single label + input field row.

        Args:
            key: .env key name.
            label_text: Human-readable label shown to the left.
            content_width: Total content area width.

        Returns:
            An NSStackView configured as a horizontal row.
        """
        row_height = 24.0
        row = NSStackView.alloc().initWithFrame_(
            NSMakeRect(0, 0, content_width - 24, row_height)
        )
        row.setOrientation_(NSUserInterfaceLayoutOrientationHorizontal)
        row.setSpacing_(6)

        label = NSTextField.labelWithString_(label_text)
        label.setFrame_(NSMakeRect(0, 0, 180, row_height))
        row.addArrangedSubview_(label)

        if key in _SECRET_KEYS:
            secure_field, plain_field, toggle_btn = self._make_secret_field(key)
            row.addArrangedSubview_(secure_field)
            row.addArrangedSubview_(toggle_btn)
            self._secret_pairs[key] = (secure_field, plain_field)
            self._secret_rows[key] = row
            self.fields[key] = secure_field
        else:
            field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 340, row_height))
            field.setStringValue_(self.initial_values.get(key, ""))
            field.setPlaceholderString_(f"{label_text} — empty clears the entry")
            row.addArrangedSubview_(field)
            self.fields[key] = field

        return row

    def _make_secret_field(self, key: str) -> Tuple[NSSecureTextField, NSTextField, NSButton]:
        """Build a masked text field with an eye-toggle reveal button.

        Args:
            key: .env key name (must be in ``_SECRET_KEYS``).

        Returns:
            A 3-tuple of (secure_field, plain_field, toggle_button).
        """
        row_height = 24.0
        initial = self.initial_values.get(key, "")
        placeholder = f"{self.labels.get(key, key)} — empty clears the entry"

        secure = NSSecureTextField.alloc().initWithFrame_(
            NSMakeRect(0, 0, 340, row_height)
        )
        secure.setStringValue_(initial)
        secure.setPlaceholderString_(placeholder)

        plain = NSTextField.alloc().initWithFrame_(
            NSMakeRect(0, 0, 340, row_height)
        )
        plain.setStringValue_(initial)
        plain.setPlaceholderString_(placeholder)

        btn = NSButton.alloc().initWithFrame_(NSMakeRect(0, 0, 28, row_height))
        btn.setBezelStyle_(NSBezelStyleRegularSquare)
        btn.setBordered_(False)
        eye_img = _load_icon("eye")
        if eye_img:
            btn.setImage_(eye_img)
        btn.setToolTip_("Show / hide")
        btn.setTarget_(self)
        objc.setAssociatedObject(btn, b"secret_key", key, objc.OBJC_ASSOCIATION_RETAIN)
        btn.setAction_("toggleReveal:")

        return secure, plain, btn

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def toggleAdvanced_(self, sender) -> None:  # noqa: N802
        """Show or hide the Advanced section.

        Args:
            sender: The disclosure button that was clicked.
        """
        self._advanced_visible = not self._advanced_visible
        self._advanced_stack.setHidden_(not self._advanced_visible)
        if self._advanced_toggle_btn is not None:
            arrow = "▼" if self._advanced_visible else "▶"
            self._advanced_toggle_btn.setTitle_(f"{arrow}  Advanced")

    def httpsToggled_(self, sender) -> None:  # noqa: N802
        """Enable or disable the SSL_CERTFILE / SSL_KEYFILE fields.

        Args:
            sender: The HTTPS checkbox button.
        """
        enabled = sender.state() == 1
        for key in ("SSL_CERTFILE", "SSL_KEYFILE"):
            field = self.fields.get(key)
            if field is None:
                continue
            field.setEnabled_(enabled)
            field.setTextColor_(
                NSColor.controlTextColor() if enabled else NSColor.disabledControlTextColor()
            )

    def toggleReveal_(self, sender) -> None:  # noqa: N802
        """Swap secure ↔ plain text field for a secret key.

        Args:
            sender: The eye-icon button that was clicked.
        """
        key = objc.getAssociatedObject(sender, b"secret_key")
        if key is None or key not in self._secret_pairs:
            return

        secure, plain = self._secret_pairs[key]
        row = self._secret_rows[key]
        currently_secure = self.fields[key] is secure

        if currently_secure:
            plain.setStringValue_(secure.stringValue())
        else:
            secure.setStringValue_(plain.stringValue())

        row.removeArrangedSubview_(secure if currently_secure else plain)
        (secure if currently_secure else plain).removeFromSuperview()
        row.insertArrangedSubview_atIndex_(plain if currently_secure else secure, 1)
        self.fields[key] = plain if currently_secure else secure

        new_icon = _load_icon("eye-slash" if currently_secure else "eye")
        if new_icon:
            sender.setImage_(new_icon)

    def saveClicked_(self, sender) -> None:  # noqa: N802
        """Collect field values and invoke the on_save callback.

        Args:
            sender: The Save button.
        """
        collected = {key: field.stringValue() for key, field in self.fields.items()}
        # When HTTPS is disabled, clear the TLS paths so they don't linger in .env
        if self._https_checkbox is not None and self._https_checkbox.state() == 0:
            for key in _HTTPS_KEYS:
                if key in collected:
                    collected[key] = ""
        self._close()
        self.on_save(collected)

    def cancelClicked_(self, sender) -> None:  # noqa: N802
        """Dismiss the window without saving.

        Args:
            sender: The Cancel button.
        """
        self._close()

    def windowWillClose_(self, notification) -> None:  # noqa: N802
        """Handle window close notification.

        Args:
            notification: The NSNotification from AppKit.
        """
        self.window = None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _close(self) -> None:
        """Order out and release the window reference."""
        if self.window is not None:
            self.window.orderOut_(None)
            self.window = None
