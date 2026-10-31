pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    readonly property string repoDir: Quickshell.env("SMARTSHOT_DIR")
        || (Quickshell.env("XDG_DATA_HOME") ? (Quickshell.env("XDG_DATA_HOME") + "/hyprsmartshot") : (Quickshell.env("HOME") + "/.local/share/hyprsmartshot"))
    readonly property string configDir: (Quickshell.env("XDG_CONFIG_HOME") || (Quickshell.env("HOME") + "/.config")) + "/hyprsmartshot"
    readonly property string configJsonPath: configDir + "/config.json"
    readonly property string defaultJsonPath: repoDir + "/config/hyprsmartshot/config.json"

    // Configuration properties
    property string ocrLanguages: "eng"
    property string postSaveHook: ""
    property string postCopyHook: ""
    property string activePreset: "default"

    property var presets: ({
        "default":  { name: "Default",  offsetX: 0, offsetY: 0, inset: 0, filter: "all" },
        "browser":  { name: "Browser",  offsetX: 0, offsetY: 0, inset: 0, filter: "content" },
        "terminal": { name: "Terminal", offsetX: 0, offsetY: 0, inset: 1, filter: "window" },
        "game":     { name: "Game",     offsetX: 0, offsetY: 0, inset: 0, filter: "dense" }
    })

    property var appRules: ({
        "firefox": "browser",
        "google-chrome": "browser",
        "chromium": "browser",
        "brave-browser": "browser",
        "zen-browser": "browser",
        "discord": "browser",
        "vesktop": "browser",
        "webcord": "browser",
        "kitty": "terminal",
        "alacritty": "terminal",
        "foot": "terminal"
    })

    function resolvePresetForApp(appClass) {
        if (!appClass) return root.activePreset;
        const low = String(appClass).toLowerCase();
        for (let rule in root.appRules) {
            if (low.indexOf(rule.toLowerCase()) !== -1) {
                return root.appRules[rule];
            }
        }
        return root.activePreset;
    }

    function getPreset(presetKey) {
        if (root.presets && root.presets[presetKey]) {
            return root.presets[presetKey];
        }
        return root.presets["default"] || { name: "Default", offsetX: 0, offsetY: 0, inset: 0, filter: "all" };
    }

    property bool configJsonLoaded: false

    function applyConfig(data) {
        if (!data || typeof data !== "object") return;
        if (typeof data.ocrLanguages === "string" && data.ocrLanguages.trim().length > 0) {
            root.ocrLanguages = data.ocrLanguages.trim();
        }
        if (typeof data.postSaveHook === "string") {
            root.postSaveHook = data.postSaveHook.trim();
        }
        if (typeof data.postCopyHook === "string") {
            root.postCopyHook = data.postCopyHook.trim();
        }
        if (typeof data.activePreset === "string" && data.activePreset.trim().length > 0) {
            root.activePreset = data.activePreset.trim();
        }
        if (data.presets && typeof data.presets === "object") {
            const merged = Object.assign({}, root.presets);
            for (let k in data.presets) {
                merged[k] = Object.assign({}, merged[k] || {}, data.presets[k]);
            }
            root.presets = merged;
        }
        if (data.appRules && typeof data.appRules === "object") {
            root.appRules = Object.assign({}, root.appRules, data.appRules);
        }
    }

    // 1. Watch user config.json (~/.config/hyprsmartshot/config.json)
    FileView {
        id: configFile
        path: root.configJsonPath
        printErrors: false
        onLoaded: {
            try {
                const data = JSON.parse(text());
                root.applyConfig(data);
                root.configJsonLoaded = true;
            } catch (e) {}
        }
    }

    // 2. Fallback to bundled config.json
    FileView {
        id: defaultConfigFile
        path: root.defaultJsonPath
        printErrors: false
        onLoaded: {
            if (root.configJsonLoaded) return;
            try {
                const data = JSON.parse(text());
                root.applyConfig(data);
            } catch (e) {}
        }
    }
}
