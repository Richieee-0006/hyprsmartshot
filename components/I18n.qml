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

    function sanitizeLang(code) {
        if (!code || typeof code !== "string") return "en";
        let clean = code.trim().split(".")[0];
        clean = clean.replace(/[^a-zA-Z0-9_-]/g, "");
        return clean.length > 0 ? clean : "en";
    }

    // Active language preference (default: "en", dynamically supports any language code)
    property string language: sanitizeLang(Quickshell.env("SMARTSHOT_LANG"))

    // Base language (e.g. "cs" if language is "cs_CZ" or "cs-CZ")
    readonly property string baseLanguage: {
        const parts = root.language.split(/[_-]/);
        return (parts.length > 1 && parts[0].length > 0 && parts[0] !== root.language) ? parts[0] : "";
    }

    // Dynamic loaded translations
    property var userTranslations: ({})
    property var repoTranslations: ({})
    property var userBaseTranslations: ({})
    property var repoBaseTranslations: ({})
    property var userFallbackTranslations: ({})
    property var fallbackTranslations: ({})
    property int updateRevision: 0

    // Merged translations for backward compatibility
    readonly property var currentTranslations: Object.assign({},
        root.fallbackTranslations,
        root.userFallbackTranslations,
        root.repoBaseTranslations,
        root.userBaseTranslations,
        root.repoTranslations,
        root.userTranslations
    )

    // Reset translations when language changes so stale keys do not bleed through
    onLanguageChanged: {
        root.userTranslations = {};
        root.repoTranslations = {};
        root.userBaseTranslations = {};
        root.repoBaseTranslations = {};
        root.updateRevision++;
    }

    property bool configJsonLoaded: false

    // 1. Watch user config.json
    FileView {
        id: configFile
        path: root.configJsonPath
        printErrors: false
        onLoaded: {
            if (Quickshell.env("SMARTSHOT_LANG")) return;
            try {
                const data = JSON.parse(text());
                if (data && typeof data.language === "string" && data.language.trim().length > 0) {
                    root.configJsonLoaded = true;
                    root.language = root.sanitizeLang(data.language);
                }
            } catch (e) {}
        }
    }

    // 2. Fallback to bundled config.json if user has no config
    FileView {
        id: defaultConfigFile
        path: root.defaultJsonPath
        printErrors: false
        onLoaded: {
            if (Quickshell.env("SMARTSHOT_LANG") || root.configJsonLoaded) return;
            try {
                const data = JSON.parse(text());
                if (data && typeof data.language === "string" && data.language.trim().length > 0 && root.language === "en") {
                    root.language = root.sanitizeLang(data.language);
                }
            } catch (e) {}
        }
    }

    // 4. Watch user override localization file (~/.config/hyprsmartshot/localization/{lang}.json)
    FileView {
        id: userTranslationFile
        path: root.configDir + "/localization/" + root.language + ".json"
        printErrors: false
        onLoaded: {
            try {
                const data = JSON.parse(text());
                if (data && typeof data === "object") {
                    root.userTranslations = data;
                    root.updateRevision++;
                }
            } catch (e) {}
        }
    }

    // 5. Watch active language translation file from repo localization/{lang}.json
    FileView {
        id: repoTranslationFile
        path: root.repoDir + "/localization/" + root.language + ".json"
        printErrors: false
        onLoaded: {
            try {
                const data = JSON.parse(text());
                if (data && typeof data === "object") {
                    root.repoTranslations = data;
                    root.updateRevision++;
                }
            } catch (e) {
                // If missing or unparseable, cleanly falls back to fallbackTranslations
            }
        }
    }

    // 6. Watch user base language override file (e.g. ~/.config/hyprsmartshot/localization/cs.json if lang is cs_CZ)
    FileView {
        id: userBaseTranslationFile
        path: root.baseLanguage.length > 0 ? (root.configDir + "/localization/" + root.baseLanguage + ".json") : ""
        printErrors: false
        onLoaded: {
            try {
                const data = JSON.parse(text());
                if (data && typeof data === "object") {
                    root.userBaseTranslations = data;
                    root.updateRevision++;
                }
            } catch (e) {}
        }
    }

    // 7. Watch repo base language file (e.g. localization/cs.json if lang is cs_CZ)
    FileView {
        id: repoBaseTranslationFile
        path: root.baseLanguage.length > 0 ? (root.repoDir + "/localization/" + root.baseLanguage + ".json") : ""
        printErrors: false
        onLoaded: {
            try {
                const data = JSON.parse(text());
                if (data && typeof data === "object") {
                    root.repoBaseTranslations = data;
                    root.updateRevision++;
                }
            } catch (e) {}
        }
    }

    // 8. Watch user fallback file (~/.config/hyprsmartshot/localization/en.json)
    FileView {
        id: userFallbackFile
        path: root.configDir + "/localization/en.json"
        printErrors: false
        onLoaded: {
            try {
                const data = JSON.parse(text());
                if (data && typeof data === "object") {
                    root.userFallbackTranslations = data;
                    root.updateRevision++;
                }
            } catch (e) {}
        }
    }

    // 9. Watch and load English fallback translation file from repo
    FileView {
        id: fallbackFile
        path: root.repoDir + "/localization/en.json"
        printErrors: false
        onLoaded: {
            try {
                const data = JSON.parse(text());
                if (data && typeof data === "object") {
                    root.fallbackTranslations = data;
                    root.updateRevision++;
                }
            } catch (e) {}
        }
    }

    // Embedded initial fallbacks ensuring instant non-empty labels before disk I/O completes
    readonly property var embeddedFallback: ({
        "en": {
            "modeSmart": "Smart",
            "modeScreen": "Screen",
            "copy": "Copy",
            "save": "Save",
            "annotate": "Annotate",
            "ocr": "OCR",
            "cancel": "Cancel",
            "close": "Close",
            "hintConfirmed": "󰆏 [Enter/Ctrl+C] Copy  •  󰆓 [Ctrl+S] Save  •  󰏫 [A] Annotate  •  󰉐 [O] OCR  •  󰒉 [Arrows] Fine-tune  •  [Alt+Arrows] Resize  •  [Esc] Cancel",
            "hintUnconfirmed": "󰓥 [Click] Confirm  •  [Drag] Custom region  •  󰒉 [Scroll] Depth / Grid  •  󰍉 [Alt] Magnifier  •  [1-2] Modes  •  [Esc] Close",
            "tagGrid": "Grid 󰕰 • ",
            "tagRow": "Row 󰒉 • ",
            "tagFloating": "Floating",
            "tagWindow": "Window",
            "tagSlot": "Slot 󰏫 • ",
            "tagItem": "Item 󰆦 • ",
            "tagPanel": "Panel 󱂬 • ",
            "tagButton": "Button 󰐥 • ",
            "tagScreen": "Screen 󰍹 • ",
            "scrollHint": "[Scroll 󰒉]",
            "copyTitle": "Screenshot Copied",
            "copyDesc": "Selection copied to clipboard",
            "saveTitle": "Screenshot Saved",
            "saveDesc": "Saved to {path} and copied to clipboard",
            "fullscreenTitle": "Fullscreen Captured",
            "fullscreenDesc": "Saved to {path} and copied to clipboard",
            "annotateNotFoundTitle": "Annotation Editor Not Found",
            "annotateNotFoundDesc": "Selection copied to clipboard.",
            "ocrTitle": "OCR Completed",
            "ocrDesc": "Recognized text copied to clipboard",
            "ocrNoTextTitle": "OCR Result",
            "ocrNoTextDesc": "No text detected in selection",
            "ocrNotFoundTitle": "OCR Tool Not Found",
            "ocrNotFoundDesc": "Tesseract not installed. Image copied to clipboard."
        },
        "cs": {
            "modeSmart": "Smart",
            "modeScreen": "Obrazovka",
            "copy": "Kopírovat",
            "save": "Uložit",
            "annotate": "Anotovat",
            "ocr": "OCR",
            "cancel": "Zrušit",
            "close": "Zavřít",
            "hintConfirmed": "󰆏 [Enter/Ctrl+C] Kopírovat  •  󰆓 [Ctrl+S] Uložit  •  󰏫 [A] Anotovat  •  󰉐 [O] OCR  •  󰒉 [Šipky] Doladit  •  [Alt+Šipky] Velikost  •  [Esc] Zrušit",
            "hintUnconfirmed": "󰓥 [Klik] Potvrdit výběr  •  [Tažení] Vlastní oblast  •  󰒉 [Kolečko] Hloubka / Grid  •  󰍉 [Alt] Lupa  •  [1-2] Režimy  •  [Esc] Zavřít",
            "tagGrid": "Grid 󰕰 • ",
            "tagRow": "Řádek 󰒉 • ",
            "tagFloating": "Plovoucí",
            "tagWindow": "Okno",
            "tagSlot": "Slot 󰏫 • ",
            "tagItem": "Předmět 󰆦 • ",
            "tagPanel": "Panel 󱂬 • ",
            "tagButton": "Tlačítko 󰐥 • ",
            "tagScreen": "Obrazovka 󰍹 • ",
            "scrollHint": "[Kolečko 󰒉]",
            "copyTitle": "Screenshot zkopírován",
            "copyDesc": "Výřez byl zkopírován do schránky",
            "saveTitle": "Screenshot uložen",
            "saveDesc": "Uloženo do {path} a zkopírováno",
            "fullscreenTitle": "Fullscreen zachycen",
            "fullscreenDesc": "Uloženo do {path} a zkopírováno",
            "annotateNotFoundTitle": "Anotační editor nenalezen",
            "annotateNotFoundDesc": "Výřez byl zkopírován do schránky.",
            "ocrTitle": "OCR dokončeno",
            "ocrDesc": "Rozpoznaný text byl zkopírován do schránky",
            "ocrNoTextTitle": "Výsledek OCR",
            "ocrNoTextDesc": "Ve výběru nebyl rozpoznán žádný text",
            "ocrNotFoundTitle": "OCR nástroj nenalezen",
            "ocrNotFoundDesc": "Tesseract není nainstalován. Výřez byl zkopírován jako obrázek."
        }
    })

    function t(key) {
        // Touch reactive properties so bindings update when language or translations change
        const _rev = root.updateRevision;
        const _l = root.language;
        const _base = root.baseLanguage;
        const userDict = root.userTranslations;
        const repoDict = root.repoTranslations;
        const userBase = root.userBaseTranslations;
        const repoBase = root.repoBaseTranslations;
        const userFb = root.userFallbackTranslations;
        const fb = root.fallbackTranslations;

        // 1. User active language override (~/.config/hyprsmartshot/localization/{lang}.json)
        if (userDict && typeof userDict[key] === "string" && userDict[key].length > 0) {
            return userDict[key];
        }
        // 2. Bundled repository active language ($REPO/localization/{lang}.json)
        if (repoDict && typeof repoDict[key] === "string" && repoDict[key].length > 0) {
            return repoDict[key];
        }
        // 3. User base language override (~/.config/hyprsmartshot/localization/{baseLang}.json)
        if (userBase && typeof userBase[key] === "string" && userBase[key].length > 0) {
            return userBase[key];
        }
        // 4. Bundled repository base language ($REPO/localization/{baseLang}.json)
        if (repoBase && typeof repoBase[key] === "string" && repoBase[key].length > 0) {
            return repoBase[key];
        }
        // 5. User English fallback override (~/.config/hyprsmartshot/localization/en.json)
        if (userFb && typeof userFb[key] === "string" && userFb[key].length > 0) {
            return userFb[key];
        }
        // 6. Bundled English fallback ($REPO/localization/en.json)
        if (fb && typeof fb[key] === "string" && fb[key].length > 0) {
            return fb[key];
        }
        // 7. Embedded defaults for active language if defined
        if (root.embeddedFallback[_l] && typeof root.embeddedFallback[_l][key] === "string" && root.embeddedFallback[_l][key].length > 0) {
            return root.embeddedFallback[_l][key];
        }
        // 8. Embedded defaults for base language if defined
        if (_base && root.embeddedFallback[_base] && typeof root.embeddedFallback[_base][key] === "string" && root.embeddedFallback[_base][key].length > 0) {
            return root.embeddedFallback[_base][key];
        }
        // 9. Embedded defaults for English
        if (root.embeddedFallback["en"] && typeof root.embeddedFallback["en"][key] === "string" && root.embeddedFallback["en"][key].length > 0) {
            return root.embeddedFallback["en"][key];
        }
        // 10. Last resort: raw key
        return key;
    }

    function formatCandidatePrefix(cur) {
        if (!cur) return "";
        switch (cur.type) {
            case "grid_container": return t("tagGrid");
            case "grid_row": return t("tagRow");
            case "floating_window": {
                const fb = t("tagFloating");
                const name = cur.title ? cur.title.slice(0, 16) : (cur.class || fb);
                return `${fb} [${name}] 󱂬 • `;
            }
            case "window": {
                const fb = t("tagWindow");
                const name = cur.title ? cur.title.slice(0, 16) : (cur.class || fb);
                return `${fb} [${name}] 󱂬 • `;
            }
            case "slot": return t("tagSlot");
            case "item": return t("tagItem");
            case "panel": return t("tagPanel");
            case "button": return t("tagButton");
            case "screen": return t("tagScreen");
            default: return "";
        }
    }
}
