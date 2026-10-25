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
    property string ocrLanguages: "eng+ces"
    property string postSaveHook: ""
    property string postCopyHook: ""

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
