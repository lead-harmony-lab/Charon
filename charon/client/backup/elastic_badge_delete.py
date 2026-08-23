from gi.repository import Gtk


class ElasticBadge(Gtk.Button):
    def __init__(self):
        super().__init__()
        # Base transparent container to manage sizing and drop-shadows
        self.add_css_class("elastic-badge-container")
        self.set_halign(Gtk.Align.END)
        self.set_valign(Gtk.Align.END)

        self.overlay = Gtk.Overlay()

        # 1. The Main Bubble Body
        self.body = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL)
        self.body.add_css_class("badge-body")
        self.body.set_halign(Gtk.Align.FILL)
        self.body.set_valign(Gtk.Align.FILL)

        # 2. The Text Payload
        self.label = Gtk.Label()
        self.label.set_wrap(True)
        self.label.set_max_width_chars(30)
        self.label.add_css_class("badge-text")
        self.label.set_visible(False)
        self.label.set_opacity(0.0)

        self.body.set_halign(Gtk.Align.CENTER)
        self.body.set_valign(Gtk.Align.CENTER)
        self.body.append(self.label)

        # 3. The Tail (Rotated Square)
        self.tail = Gtk.Box()
        self.tail.add_css_class("badge-tail")
        self.tail.set_halign(Gtk.Align.END)
        self.tail.set_valign(Gtk.Align.END)

        # Assemble: The tail goes on top so its background erases the body's inner border
        self.overlay.set_child(self.body)
        self.overlay.add_overlay(self.tail)

        self.set_child(self.overlay)

    def show_message(self, text: str):
        self.label.set_text(text)
        self.label.set_visible(True)
        self.add_css_class("expanded")
        self.label.set_opacity(1.0)

    def collapse(self):
        self.remove_css_class("expanded")
        self.label.set_opacity(0.0)
        self.label.set_visible(False)
        self.label.set_text("")