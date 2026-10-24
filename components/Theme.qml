pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    // File path to pywal colors
    readonly property string pywalPath: Quickshell.env("HOME") + "/.cache/wal/colors.json"

    // Default palette fallbacks (modern dark glassmorphism)
    property color background: Qt.rgba(0.08, 0.08, 0.10, 0.85)
    property color barBackground: Qt.rgba(0.12, 0.12, 0.15, 0.90)
    property color barBorder: Qt.rgba(1.0, 1.0, 1.0, 0.15)
    property color cardBackground: Qt.rgba(0.16, 0.16, 0.20, 0.92)
    property color accent: "#eb6960"
    property color accentHover: "#f2857d"
    property color text: "#ffffff"
    property color textSubtle: Qt.rgba(1.0, 1.0, 1.0, 0.70)
    property color selectionBorder: "#68df93"
    property color snapBorder: "#f3c568"
    
    property real dimOpacity: 0.65
    property real borderRadius: 10
    property real outlineThickness: 2
    property string fontFamily: "JetBrainsMono Nerd Font"

    // Load pywal colors dynamically if available
    FileView {
        id: pywalFile
        path: root.pywalPath
        onLoaded: {
            try {
                const data = JSON.parse(text());
                if (data && data.colors) {
                    if (data.special && data.special.background) {
                        root.background = Qt.rgba(
                            parseInt(data.special.background.slice(1, 3), 16) / 255.0,
                            parseInt(data.special.background.slice(3, 5), 16) / 255.0,
                            parseInt(data.special.background.slice(5, 7), 16) / 255.0,
                            0.88
                        );
                    }
                    if (data.colors.color1) root.accent = data.colors.color1;
                    if (data.colors.color2) root.selectionBorder = data.colors.color2;
                    if (data.colors.color3) root.snapBorder = data.colors.color3;
                    if (data.colors.color9) root.accentHover = data.colors.color9;
                    if (data.special && data.special.foreground) root.text = data.special.foreground;
                }
            } catch (e) {
                // Keep default fallbacks
            }
        }
    }
}
