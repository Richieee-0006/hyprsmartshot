pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    function resolvePywalPath() {
        const home = Quickshell.env("HOME") || "";
        let raw = "~/.cache/wal/colors.json";
        if (typeof Config !== "undefined" && Config && Config.theme && Config.theme.pywalPath) {
            raw = String(Config.theme.pywalPath);
        }
        if (raw.indexOf("~/") === 0) {
            return home + raw.slice(1);
        }
        return raw;
    }

    readonly property string pywalPath: resolvePywalPath()

    property bool isLightTheme: false
    property string themeSource: "static"
    property var pywalData: null

    // Semantic theme tokens (dynamically driven by Pywal + Config overrides)
    property color background: Qt.rgba(0.08, 0.08, 0.10, 0.88)
    property color barBackground: Qt.rgba(0.12, 0.12, 0.15, 0.92)
    property color barBorder: Qt.rgba(1.0, 1.0, 1.0, 0.16)
    property color cardBackground: Qt.rgba(0.16, 0.16, 0.20, 0.94)
    property color surfaceSoft: Qt.rgba(1.0, 1.0, 1.0, 0.10)
    property color surfaceHover: Qt.rgba(1.0, 1.0, 1.0, 0.20)
    property color accent: "#eb6960"
    property color accentHover: "#f2857d"
    property color accentText: "#ffffff"
    property color text: "#ffffff"
    property color textSubtle: Qt.rgba(1.0, 1.0, 1.0, 0.72)
    property color selectionBorder: "#68df93"
    property color snapBorder: "#f3c568"
    property color aiAccent: "#955eed"
    property color pinBorder: "#6496ff"
    property color danger: "#ff6b6b"
    property color backdropDim: Qt.rgba(0.0, 0.0, 0.0, dimOpacity)

    property real dimOpacity: 0.65
    property real borderRadius: 10
    property real outlineThickness: 2
    property real pinBorderWidth: 2
    property string fontFamily: "JetBrainsMono Nerd Font"

    function hexRgb(hexStr) {
        const clean = String(hexStr || "").trim().replace(/^#/, "");
        if (clean.length < 6) return { r: 20 / 255, g: 20 / 255, b: 25 / 255 };
        const r = parseInt(clean.slice(0, 2), 16) / 255.0;
        const g = parseInt(clean.slice(2, 4), 16) / 255.0;
        const b = parseInt(clean.slice(4, 6), 16) / 255.0;
        if (isNaN(r) || isNaN(g) || isNaN(b)) return { r: 20 / 255, g: 20 / 255, b: 25 / 255 };
        return { r: r, g: g, b: b };
    }

    function luminance(c) {
        return 0.299 * c.r + 0.587 * c.g + 0.114 * c.b;
    }

    function mixRgba(hexA, hexB, t, alpha) {
        const a = hexRgb(hexA);
        const b = hexRgb(hexB);
        return Qt.rgba(
            a.r + (b.r - a.r) * t,
            a.g + (b.g - a.g) * t,
            a.b + (b.b - a.b) * t,
            alpha
        );
    }

    function alphaColor(col, alpha) {
        return Qt.rgba(col.r, col.g, col.b, alpha);
    }

    function resetStaticDefaults() {
        root.isLightTheme = false;
        root.themeSource = "static";
        root.background = Qt.rgba(0.08, 0.08, 0.10, 0.88);
        root.barBackground = Qt.rgba(0.12, 0.12, 0.15, 0.92);
        root.barBorder = Qt.rgba(1.0, 1.0, 1.0, 0.16);
        root.cardBackground = Qt.rgba(0.16, 0.16, 0.20, 0.94);
        root.surfaceSoft = Qt.rgba(1.0, 1.0, 1.0, 0.10);
        root.surfaceHover = Qt.rgba(1.0, 1.0, 1.0, 0.20);
        root.accent = "#eb6960";
        root.accentHover = "#f2857d";
        root.accentText = "#ffffff";
        root.text = "#ffffff";
        root.textSubtle = Qt.rgba(1.0, 1.0, 1.0, 0.72);
        root.selectionBorder = "#68df93";
        root.snapBorder = "#f3c568";
        root.aiAccent = "#955eed";
        root.pinBorder = "#6496ff";
        root.danger = "#ff6b6b";
    }

    function applyTheme() {
        root.resetStaticDefaults();

        const tcfg = (typeof Config !== "undefined" && Config && Config.theme) ? Config.theme : ({});
        if (typeof tcfg.dimOpacity === "number") root.dimOpacity = Math.max(0.0, Math.min(0.95, tcfg.dimOpacity));
        if (typeof tcfg.borderRadius === "number") root.borderRadius = Math.max(0, Math.min(24, tcfg.borderRadius));
        if (typeof tcfg.outlineThickness === "number") root.outlineThickness = Math.max(1, Math.min(8, tcfg.outlineThickness));
        if (typeof tcfg.pinBorderWidth === "number") root.pinBorderWidth = Math.max(0, Math.min(8, tcfg.pinBorderWidth));
        if (typeof tcfg.fontFamily === "string" && tcfg.fontFamily.trim().length > 0) root.fontFamily = tcfg.fontFamily.trim();

        const mode = String(tcfg.mode || "pywal").toLowerCase();
        const data = root.pywalData;
        if ((mode === "pywal" || mode === "auto") && data && data.colors) {
            const colors = data.colors;
            const special = data.special || ({});
            const bgHex = special.background || colors.color0 || "#141419";
            const fgHex = special.foreground || colors.color15 || "#ffffff";
            const bgRgb = root.hexRgb(bgHex);
            const fgRgb = root.hexRgb(fgHex);
            const light = root.luminance(bgRgb) > 0.55;

            root.themeSource = "pywal";
            root.isLightTheme = light;
            root.background = Qt.rgba(bgRgb.r, bgRgb.g, bgRgb.b, 0.90);
            root.barBackground = root.mixRgba(bgHex, fgHex, 0.08, 0.93);
            root.cardBackground = root.mixRgba(bgHex, fgHex, 0.14, 0.96);
            root.text = Qt.rgba(fgRgb.r, fgRgb.g, fgRgb.b, 1.0);
            root.surfaceSoft = Qt.rgba(fgRgb.r, fgRgb.g, fgRgb.b, light ? 0.08 : 0.11);
            root.surfaceHover = Qt.rgba(fgRgb.r, fgRgb.g, fgRgb.b, light ? 0.16 : 0.21);

            const walMap = tcfg.pywalMap || ({});
            const resolveRole = (token, defRole) => {
                const role = walMap[token] || defRole;
                if (typeof role === "string") {
                    if (role.indexOf("#") === 0) return role;
                    if (colors[role]) return colors[role];
                }
                return null;
            };

            const accHex = resolveRole("accent", "color1");
            if (accHex) {
                root.accent = accHex;
                root.accentText = root.luminance(root.hexRgb(accHex)) > 0.58 ? "#111116" : "#ffffff";
            }
            const accHoverHex = resolveRole("accentHover", "color9");
            if (accHoverHex) root.accentHover = accHoverHex;

            const selHex = resolveRole("selectionBorder", "color2");
            if (selHex) root.selectionBorder = selHex;

            const snapHex = resolveRole("snapBorder", "color3");
            if (snapHex) root.snapBorder = snapHex;

            const aiHex = resolveRole("aiAccent", "color5");
            if (aiHex) root.aiAccent = aiHex;

            const pinHex = resolveRole("pinBorder", "color4");
            if (pinHex) root.pinBorder = pinHex;

            const dangerHex = resolveRole("danger", "color1");
            if (dangerHex) root.danger = dangerHex;

            const borderHex = resolveRole("barBorder", "color8");
            if (borderHex) {
                const br = root.hexRgb(borderHex);
                root.barBorder = Qt.rgba(br.r, br.g, br.b, 0.45);
            } else {
                root.barBorder = Qt.rgba(fgRgb.r, fgRgb.g, fgRgb.b, 0.18);
            }

            const subtleHex = resolveRole("textSubtle", "color7");
            if (subtleHex) {
                const sr = root.hexRgb(subtleHex);
                root.textSubtle = Qt.rgba(sr.r, sr.g, sr.b, 0.85);
            } else {
                root.textSubtle = Qt.rgba(fgRgb.r, fgRgb.g, fgRgb.b, 0.72);
            }
        }

        const ov = tcfg.overrides;
        if (ov && typeof ov === "object") {
            const colorKeys = [
                "background", "barBackground", "barBorder", "cardBackground",
                "surfaceSoft", "surfaceHover", "accent", "accentHover", "accentText",
                "text", "textSubtle", "selectionBorder", "snapBorder", "aiAccent",
                "pinBorder", "danger"
            ];
            for (let i = 0; i < colorKeys.length; i++) {
                const k = colorKeys[i];
                if (typeof ov[k] === "string" && ov[k].trim().length > 0) {
                    root[k] = ov[k].trim();
                }
            }
            if (typeof ov["onAccent"] === "string" && ov["onAccent"].trim().length > 0) {
                root.accentText = ov["onAccent"].trim();
            }
        }

        const brBg = root.background;
        root.backdropDim = Qt.rgba(brBg.r, brBg.g, brBg.b, root.dimOpacity);
    }

    Connections {
        target: Config
        function onConfigRevisionChanged() {
            root.applyTheme();
        }
    }

    FileView {
        id: pywalFile
        path: root.pywalPath
        printErrors: false
        watchChanges: (typeof Config === "undefined" || !Config || !Config.theme || Config.theme.liveWatch !== false)
        onFileChanged: reload()
        onLoaded: {
            try {
                root.pywalData = JSON.parse(text());
                root.applyTheme();
            } catch (e) {}
        }
    }

    Component.onCompleted: root.applyTheme()
}
