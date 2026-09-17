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
)
from Foundation import NSMakePoint

_SECRET_KEYS = {"PROXY_API_KEY"}

_ICON_DIR = os.path.join(os.path.dirname(__file__), "resources")


def _load_icon(name: str) -> NSImage:
    path = os.path.join(_ICON_DIR, f"{name}.png")
    img = NSImage.imageWithSystemSymbolName_accessibilityDescription_(name.replace("-", "."), None)
    if img:
        return img
    if os.path.exists(path):
        return NSImage.alloc().initWithContentsOfFile_(path)
    return None


class SettingsWindowController:

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
        self.window: Optional[NSWindow] = None

    def show(self) -> None:
        app = NSApplication.sharedApplication()
        if app.activationPolicy() != NSApplicationActivationPolicyAccessory:
            app.setActivationPolicy_(NSApplicationActivationPolicyAccessory)

        content_width = 560.0
        row_height = 24.0
        spacing = 8.0
        fields_height = len(self.keys) * (row_height + spacing) + spacing
        buttons_height = 32.0
        window_height = fields_height + buttons_height + 24.0

        window = NSWindow.alloc().initWithContentRect_styleMask_backing_defer_(
            NSMakeRect(0, 0, content_width, window_height),
            1 << 2 | 1 << 3,  # titled | closable
            2,  # buffered
            False,
        )
        window.setTitle_("Kiro Gateway Settings")
        window.setReleasedWhenClosed_(False)

        container = NSView.alloc().initWithFrame_(
            NSMakeRect(0, 0, content_width, window_height)
        )

        stack = NSStackView.alloc().initWithFrame_(
            NSMakeRect(12, 12, content_width - 24, fields_height)
        )
        stack.setOrientation_(NSUserInterfaceLayoutOrientationVertical)
        stack.setSpacing_(spacing)

        for key in self.keys:
            label_text = self.labels.get(key, key)
            row = self._make_row(key, label_text, content_width)
            stack.addArrangedSubview_(row)

        container.addSubview_(stack)

        save_button = NSButton.alloc().initWithFrame_(
            NSMakeRect(content_width - 180, 8, 80, 28)
        )
        save_button.setTitle_("Save")
        save_button.setBezelStyle_(1)
        save_button.setTarget_(self)
        save_button.setAction_("saveClicked:")

        cancel_button = NSButton.alloc().initWithFrame_(
            NSMakeRect(content_width - 92, 8, 80, 28)
        )
        cancel_button.setTitle_("Cancel")
        cancel_button.setBezelStyle_(1)
        cancel_button.setTarget_(self)
        cancel_button.setAction_("cancelClicked:")

        container.addSubview_(save_button)
        container.addSubview_(cancel_button)
        window.setContentView_(container)

        self.window = window
        window.center()
        window.makeKeyAndOrderFront_(None)
        NSApp.activateIgnoringOtherApps_(True)

    def _make_row(self, key: str, label_text: str, content_width: float) -> NSView:
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
            field = NSTextField.alloc().initWithFrame_(NSMakeRect(0, 0, 300, row_height))
            field.setStringValue_(self.initial_values.get(key, ""))
            field.setPlaceholderString_(f"{label_text} — empty clears the entry")
            row.addArrangedSubview_(field)
            self.fields[key] = field

        return row

    def _make_secret_field(self, key: str) -> tuple:
        row_height = 24.0
        initial = self.initial_values.get(key, "")
        placeholder = f"{self.labels.get(key, key)} — empty clears the entry"

        secure = NSSecureTextField.alloc().initWithFrame_(
            NSMakeRect(0, 0, 300, row_height)
        )
        secure.setStringValue_(initial)
        secure.setPlaceholderString_(placeholder)

        plain = NSTextField.alloc().initWithFrame_(
            NSMakeRect(0, 0, 300, row_height)
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

    def toggleReveal_(self, sender) -> None:  # noqa: N802
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

    def saveClicked_(self, sender) -> None:  # noqa: N802 (AppKit selector)
        collected = {key: field.stringValue() for key, field in self.fields.items()}
        self._close()
        self.on_save(collected)

    def cancelClicked_(self, sender) -> None:  # noqa: N802 (AppKit selector)
        self._close()

    def windowWillClose_(self, notification) -> None:  # noqa: N802
        self.window = None

    def _close(self) -> None:
        if self.window is not None:
            self.window.orderOut_(None)
            self.window = None
