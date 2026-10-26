"""Stylesheet applied on top of the normal theme while Jarvis is switched on.

Jarvis looks deliberately different from EV: a warm black background with a
faint grid, sharp square corners, gold wire-frame panels, monospace type and
bracketed section titles - a monitoring console rather than a glass dashboard.
"""

JARVIS_QSS = """
* { font-family: "Consolas", "Cascadia Mono", monospace; color: #F2E4B8; }

#RootBackground {
    background-color: qlineargradient(x1:0, y1:0, x2:0, y2:1,
        stop: 0 #120D02, stop: 0.5 #0B0801, stop: 1 #060400);
}

#TopBar {
    background-color: rgba(18, 12, 2, 235);
    border-bottom: 2px solid #FFC400;
}

#LogoLabel { color: #FFC400; font-size: 20px; font-weight: 700; letter-spacing: 7px; }
#SystemStatusLabel { color: #FFC400; letter-spacing: 3px; }

QFrame#GlassPanel, QFrame#GlassPanel[accent="red"], QFrame#GlassPanel[accent="blue"], QFrame#GlassPanel[accent="gold"] {
    background-color: rgba(20, 14, 2, 215);
    border: 1px solid rgba(255, 196, 0, 150);
    border-left: 4px solid #FFC400;
    border-radius: 0px;
}

QLabel#SectionTitle { color: #FFC400; font-size: 11px; font-weight: 700; letter-spacing: 3px; }
QLabel#StateLabel { color: #FFE066; letter-spacing: 4px; }
QLabel#MetricValue { color: #FFE066; }
QLabel#MetricCaption { color: #B89A3C; }

QTextEdit#ConversationPanel {
    background-color: rgba(8, 5, 0, 235);
    border: 1px solid rgba(255, 196, 0, 90);
    border-radius: 0px;
    font-size: 12px;
}

QLineEdit#CommandInput {
    background-color: rgba(8, 5, 0, 240);
    border: 1px solid rgba(255, 196, 0, 130);
    border-radius: 0px;
    color: #FFE066;
}
QLineEdit#CommandInput:focus { border: 1px solid #FFC400; }

QPushButton {
    background-color: rgba(255, 196, 0, 18);
    border: 1px solid rgba(255, 196, 0, 130);
    border-radius: 0px;
    color: #FFD84D;
    letter-spacing: 2px;
}
QPushButton:hover { background-color: rgba(255, 196, 0, 80); color: #120D02; }
QPushButton:pressed { background-color: rgba(255, 196, 0, 140); color: #120D02; }
QPushButton#SendButton { background-color: rgba(255, 196, 0, 150); border: 1px solid #FFC400; color: #120D02; }
QPushButton#SettingsButton { border-radius: 0px; }

QScrollBar::handle:vertical { background: rgba(255, 196, 0, 110); border-radius: 0px; }
"""
