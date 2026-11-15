pragma Singleton

import QtQuick
import Quickshell
import Quickshell.Io

Singleton {
    id: root

    readonly property string repoDir: Quickshell.env("SMARTSHOT_DIR")
        || (Quickshell.env("XDG_DATA_HOME") ? (Quickshell.env("XDG_DATA_HOME") + "/hyprsmartshot") : (Quickshell.env("HOME") + "/.local/share/hyprsmartshot"))
    readonly property string configDir: (Quickshell.env("XDG_CONFIG_HOME") || (Quickshell.env("HOME") + "/.config")) + "/hyprsmartshot"
    readonly property string configJsonPath: Quickshell.env("SMARTSHOT_CONFIG") || (configDir + "/config.json")
    readonly property string defaultJsonPath: repoDir + "/config/hyprsmartshot/config.json"
    readonly property string mergedDropinPath: Quickshell.env("SMARTSHOT_MERGED_CONFIG") || ""

    property int configRevision: 0
    property string language: "en"

    // Legacy top-level configuration properties
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
        "librewolf": "browser",
        "google-chrome": "browser",
        "chromium": "browser",
        "brave-browser": "browser",
        "vivaldi": "browser",
        "floorp": "browser",
        "zen-browser": "browser",
        "discord": "browser",
        "vesktop": "browser",
        "webcord": "browser",
        "equibop": "browser",
        "obsidian": "browser",
        "com.mojang.minecraft": "game",
        "minecraft": "game",
        "steam_app": "game",
        "gamescope": "game",
        "lutris": "game",
        "prismlauncher": "game",
        "kitty": "terminal",
        "alacritty": "terminal",
        "foot": "terminal",
        "ghostty": "terminal",
        "wezterm": "terminal",
        "konsole": "terminal",
        "gnome-terminal": "terminal"
    })

    // Modular sections
    property var theme: ({
        mode: "pywal",
        pywalPath: "~/.cache/wal/colors.json",
        liveWatch: true,
        syncSatty: false,
        syncPinWindow: true,
        dimOpacity: 0.65,
        borderRadius: 10,
        outlineThickness: 2,
        pinBorderWidth: 2,
        fontFamily: "JetBrainsMono Nerd Font",
        pywalMap: {
            accent: "color1",
            accentHover: "color9",
            selectionBorder: "color2",
            snapBorder: "color3",
            aiAccent: "color5",
            pinBorder: "color4",
            danger: "color1",
            barBorder: "color8",
            textSubtle: "color7"
        },
        overrides: ({})
    })

    property var detection: ({
        enableText: true,
        enablePanels: true,
        enableGrids: true,
        enableWindowContent: true,
        minArea: 64,
        maxAreaRatio: 0.98,
        tinyContrastMin: 4.5,
        adaptiveTextThreshold: true,
        filterIconsFromText: true,
        multiColumnParagraphs: true,
        maxHeaderHeight: 96
    })

    property var rating: ({
        enabled: true,
        minConfidence: 0.30,
        adaptiveLearning: true,
        learningRate: 0.08,
        profilePath: "",
        weights: {
            contrast: 0.24,
            geometry: 0.18,
            edge: 0.22,
            interior: 0.14,
            semantic: 0.12,
            presetFit: 0.10
        }
    })

    property var ai: ({
        enabled: false,
        trigger: "manual",
        provider: "openai_compatible",
        timeoutMs: 15000,
        maxImageDim: 1280,
        defaultAction: "ocr",
        prompt: "Detect interactive UI regions, panels, dialogs, buttons, inputs, and readable text blocks. Return strict JSON array of objects: [{\"label\":\"...\",\"type\":\"panel|button|input|slot|text_block|text|detected\",\"bbox_2d\":[ymin,xmin,ymax,xmax],\"confidence\":0.9}] using normalized coordinates 0..1000.",
        providers: {
            openai_compatible: {
                baseUrl: "http://127.0.0.1:8080/v1",
                model: "",
                apiKeyEnv: "OPENAI_API_KEY",
                apiKey: ""
            },
            gemini: {
                baseUrl: "https://generativelanguage.googleapis.com/v1beta",
                model: "gemini-2.5-flash",
                apiKeyEnv: "GEMINI_API_KEY",
                apiKey: ""
            }
        }
    })

    property var ui: ({
        showConfidenceBadge: true,
        sortByRating: true,
        showMagnifierByDefault: false,
        magnifierZoom: 3.0,
        magnifierSize: 180,
        showHints: true,
        animations: true
    })

    property var capture: ({
        imageFormat: "png",
        pngCompression: 4,
        defaultSaveDir: "",
        copyAfterSave: true
    })

    function deepMerge(baseObj, patchObj) {
        if (!patchObj || typeof patchObj !== "object" || Array.isArray(patchObj)) return baseObj;
        const out = Object.assign({}, baseObj || {});
        for (let k in patchObj) {
            const pv = patchObj[k];
            const bv = out[k];
            if (pv && typeof pv === "object" && !Array.isArray(pv) && bv && typeof bv === "object" && !Array.isArray(bv)) {
                out[k] = deepMerge(bv, pv);
            } else {
                out[k] = pv;
            }
        }
        return out;
    }

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
    property var _baseDefaultsSnapshot: null
    property var _userMainSnapshot: null
    property var _moduleSnapshots: ({})
    property var _mergedDropinSnapshot: null

    function applyConfig(data) {
        if (!data || typeof data !== "object") return;
        if (typeof data.language === "string" && data.language.trim().length > 0) {
            root.language = data.language.trim();
        }
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
        if (data.theme && typeof data.theme === "object") {
            root.theme = root.deepMerge(root.theme, data.theme);
        }
        if (data.detection && typeof data.detection === "object") {
            root.detection = root.deepMerge(root.detection, data.detection);
        }
        if (data.rating && typeof data.rating === "object") {
            root.rating = root.deepMerge(root.rating, data.rating);
        }
        if (data.ai && typeof data.ai === "object") {
            root.ai = root.deepMerge(root.ai, data.ai);
        }
        if (data.ui && typeof data.ui === "object") {
            root.ui = root.deepMerge(root.ui, data.ui);
        }
        if (data.capture && typeof data.capture === "object") {
            root.capture = root.deepMerge(root.capture, data.capture);
        }
        root.configRevision++;
    }

    function _reapplyLayered() {
        if (root._mergedDropinSnapshot) {
            root.applyConfig(root._mergedDropinSnapshot);
            return;
        }
        if (root._baseDefaultsSnapshot) root.applyConfig(root._baseDefaultsSnapshot);
        if (root._userMainSnapshot) root.applyConfig(root._userMainSnapshot);
        const modOrder = ["theme", "detection", "rating", "ai", "ui", "capture", "presets", "appRules"];
        for (let i = 0; i < modOrder.length; i++) {
            const key = modOrder[i];
            const modObj = root._moduleSnapshots[key];
            if (!modObj) continue;
            if (modObj[key] && Object.keys(modObj).length === 1) {
                root.applyConfig(modObj);
            } else {
                const wrapped = {};
                wrapped[key] = modObj;
                root.applyConfig(wrapped);
            }
        }
    }

    function pythonBin() {
        const venvPy = root.repoDir + "/.venv/bin/python";
        return venvPy;
    }

    function savePatch(patchObj) {
        if (!patchObj || typeof patchObj !== "object") return;
        root.applyConfig(patchObj);
        if (typeof patchObj.language === "string" && patchObj.language.trim().length > 0 && typeof I18n !== "undefined") {
            I18n.language = I18n.sanitizeLang(patchObj.language);
        }
        const jsonPayload = JSON.stringify(patchObj);
        const cfgArg = root.configJsonPath;
        const loaderScript = root.repoDir + "/vision/config_loader.py";
        const b64 = Qt.btoa(unescape(encodeURIComponent(jsonPayload)));
        const cmd = `PY="${root.pythonBin()}"; [ -x "$PY" ] || PY=python3; printf '%s' '${b64}' | base64 -d | "$PY" "${loaderScript}" --config "${cfgArg}" --patch-stdin`;
        Quickshell.execDetached(["sh", "-c", cmd]);
    }

    // 1. Optional pre-merged config written by bin/hyprsmartshot (includes config.d/*.json)
    FileView {
        id: mergedDropinFile
        path: root.mergedDropinPath
        printErrors: false
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            try {
                root._mergedDropinSnapshot = JSON.parse(text());
                root._reapplyLayered();
            } catch (e) {}
        }
    }

    // 2. Watch user config.json (~/.config/hyprsmartshot/config.json)
    FileView {
        id: configFile
        path: root.configJsonPath
        printErrors: false
        watchChanges: true
        onFileChanged: reload()
        onLoaded: {
            try {
                root._userMainSnapshot = JSON.parse(text());
                root.configJsonLoaded = true;
                root._reapplyLayered();
            } catch (e) {}
        }
    }

    // 3. Fallback to bundled config.json
    FileView {
        id: defaultConfigFile
        path: root.defaultJsonPath
        printErrors: false
        onLoaded: {
            try {
                root._baseDefaultsSnapshot = JSON.parse(text());
                root._reapplyLayered();
            } catch (e) {}
        }
    }

    // 4. Optional per-module drop-in JSON watchers in ~/.config/hyprsmartshot/
    Instantiator {
        model: ["theme", "detection", "rating", "ai", "ui", "capture", "presets", "appRules"]
        FileView {
            required property string modelData
            path: root.configDir + "/" + modelData + ".json"
            printErrors: false
            watchChanges: true
            onFileChanged: reload()
            onLoaded: {
                try {
                    const parsed = JSON.parse(text());
                    const next = Object.assign({}, root._moduleSnapshots);
                    next[modelData] = parsed;
                    root._moduleSnapshots = next;
                    root._reapplyLayered();
                } catch (e) {}
            }
        }
    }
}
