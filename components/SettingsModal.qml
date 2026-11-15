import QtQuick

FocusScope {
    id: root

    property bool open: false
    property string activeTab: "theme" // "theme" | "detection" | "ai" | "capture"
    property string statusMessage: ""
    property var draft: ({})

    signal closeRequested()
    signal applied(var patch)

    visible: open
    focus: open
    anchors.fill: parent
    z: 80

    Keys.onEscapePressed: (event) => {
        event.accepted = true;
        root.closeRequested();
    }

    function isCzech() {
        const lang = (typeof I18n !== "undefined" && I18n && I18n.language)
            ? String(I18n.language)
            : ((typeof Config !== "undefined" && Config && Config.language) ? String(Config.language) : "en");
        return lang.toLowerCase().indexOf("cs") === 0;
    }

    function label(en, cs) {
        return isCzech() ? cs : en;
    }

    function loadDraftFromConfig() {
        const t = (typeof Config !== "undefined" && Config && Config.theme) ? Config.theme : {};
        const d = (typeof Config !== "undefined" && Config && Config.detection) ? Config.detection : {};
        const r = (typeof Config !== "undefined" && Config && Config.rating) ? Config.rating : {};
        const a = (typeof Config !== "undefined" && Config && Config.ai) ? Config.ai : {};
        const u = (typeof Config !== "undefined" && Config && Config.ui) ? Config.ui : {};
        const c = (typeof Config !== "undefined" && Config && Config.capture) ? Config.capture : {};

        const aProvs = (a && a.providers && typeof a.providers === "object") ? a.providers : {};
        const oai = aProvs.openai_compatible || {};
        const gem = aProvs.gemini || {};

        root.draft = {
            language: (Config && Config.language) || "en",
            ocrLanguages: (Config && Config.ocrLanguages) || "eng",
            activePreset: (Config && Config.activePreset) || "default",
            postSaveHook: (Config && Config.postSaveHook) || "",
            postCopyHook: (Config && Config.postCopyHook) || "",
            theme: {
                mode: t.mode || "pywal",
                pywalPath: t.pywalPath || "~/.cache/wal/colors.json",
                syncSatty: t.syncSatty === true,
                syncPinWindow: t.syncPinWindow !== false,
                dimOpacity: (t.dimOpacity !== undefined) ? Number(t.dimOpacity) : 0.65,
                borderRadius: (t.borderRadius !== undefined) ? Number(t.borderRadius) : 10,
                outlineThickness: (t.outlineThickness !== undefined) ? Number(t.outlineThickness) : 2.0
            },
            detection: {
                enableText: d.enableText !== false,
                enablePanels: d.enablePanels !== false,
                enableGrids: d.enableGrids !== false,
                adaptiveTextThreshold: d.adaptiveTextThreshold !== false,
                filterIconsFromText: d.filterIconsFromText !== false,
                multiColumnParagraphs: d.multiColumnParagraphs !== false
            },
            rating: {
                enabled: r.enabled !== false,
                minConfidence: (r.minConfidence !== undefined) ? Number(r.minConfidence) : 0.30,
                adaptiveLearning: r.adaptiveLearning !== false
            },
            ai: {
                enabled: a.enabled === true,
                trigger: a.trigger || "manual",
                provider: a.provider || "openai_compatible",
                prompt: a.prompt || "",
                providers: {
                    openai_compatible: {
                        baseUrl: oai.baseUrl || "http://127.0.0.1:8080/v1",
                        model: oai.model || "",
                        apiKeyEnv: oai.apiKeyEnv || "OPENAI_API_KEY"
                    },
                    gemini: {
                        baseUrl: gem.baseUrl || "https://generativelanguage.googleapis.com/v1beta",
                        model: gem.model || "gemini-2.5-flash",
                        apiKeyEnv: gem.apiKeyEnv || "GEMINI_API_KEY"
                    }
                }
            },
            ui: {
                showConfidenceBadge: u.showConfidenceBadge !== false,
                magnifierSize: (u.magnifierSize !== undefined) ? Number(u.magnifierSize) : 180,
                magnifierZoom: (u.magnifierZoom !== undefined) ? Number(u.magnifierZoom) : 3.0,
                showHints: u.showHints !== false
            },
            capture: {
                pngCompression: (c.pngCompression !== undefined) ? Number(c.pngCompression) : 4,
                defaultSaveDir: c.defaultSaveDir || "",
                copyAfterSave: c.copyAfterSave !== false
            }
        };
        root.statusMessage = "";
    }

    function activeAiProviderKey() {
        return (root.draft && root.draft.ai && root.draft.ai.provider) || "openai_compatible";
    }

    function activeAiProviderCfg() {
        const prov = activeAiProviderKey();
        if (root.draft && root.draft.ai && root.draft.ai.providers && root.draft.ai.providers[prov]) {
            return root.draft.ai.providers[prov];
        }
        return {};
    }

    function setAiProviderField(key, value) {
        const prov = activeAiProviderKey();
        const copy = JSON.parse(JSON.stringify(root.draft));
        if (!copy.ai) copy.ai = {};
        if (!copy.ai.providers) copy.ai.providers = {};
        if (!copy.ai.providers[prov]) copy.ai.providers[prov] = {};
        copy.ai.providers[prov][key] = value;
        root.draft = copy;
        root.statusMessage = "";
    }

    function setNested(section, key, value) {
        const copy = JSON.parse(JSON.stringify(root.draft));
        if (section) {
            if (!copy[section]) copy[section] = {};
            copy[section][key] = value;
        } else {
            copy[key] = value;
        }
        root.draft = copy;
        root.statusMessage = "";
    }

    function applyAndSave() {
        if (typeof Config !== "undefined" && Config && typeof Config.savePatch === "function") {
            Config.savePatch(root.draft);
        }
        root.statusMessage = label("Saved", "Uloženo");
        root.applied(root.draft);
    }

    onOpenChanged: {
        if (open) {
            loadDraftFromConfig();
            forceActiveFocus();
        }
    }

    Component.onCompleted: {
        if (open) {
            loadDraftFromConfig();
            forceActiveFocus();
        }
    }

    // Backdrop dismiss click (absorbs hover, clicks, and wheel so underlying canvas stays untouched)
    Rectangle {
        anchors.fill: parent
        color: Theme.alphaColor(Theme.backdropDim, 0.55)

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
            onPressed: (mouse) => mouse.accepted = true
            onReleased: (mouse) => mouse.accepted = true
            onClicked: root.closeRequested()
            onWheel: (wheel) => wheel.accepted = true
        }
    }

    // Modal card
    Rectangle {
        id: modalCard
        width: Math.min(parent.width - 48, 620)
        height: Math.min(parent.height - 64, 540)
        anchors.centerIn: parent
        radius: Math.max(12, Theme.borderRadius + 4)
        color: Theme.cardBackground
        border.color: Theme.selectionBorder
        border.width: 1.5

        MouseArea {
            anchors.fill: parent
            hoverEnabled: true
            acceptedButtons: Qt.LeftButton | Qt.RightButton | Qt.MiddleButton
            onPressed: (mouse) => mouse.accepted = true
            onReleased: (mouse) => mouse.accepted = true
            onClicked: (mouse) => mouse.accepted = true
            onWheel: (wheel) => wheel.accepted = true
        }

        Column {
            anchors.fill: parent
            anchors.margins: 16
            spacing: 12

            // Header
            Row {
                width: parent.width
                height: 32
                spacing: 8

                Text {
                    id: headerTitle
                    text: "󰒓  " + I18n.t("settings")
                    font.family: Theme.fontFamily
                    font.pixelSize: 15
                    font.weight: Font.Bold
                    color: Theme.text
                    anchors.verticalCenter: parent.verticalCenter
                }

                Item {
                    width: Math.max(8, parent.width - headerTitle.implicitWidth - (statusLbl.visible ? statusLbl.implicitWidth + 8 : 0) - 28 - 24)
                    height: 1
                }

                Text {
                    id: statusLbl
                    visible: root.statusMessage.length > 0
                    text: root.statusMessage
                    font.family: Theme.fontFamily
                    font.pixelSize: 11
                    font.weight: Font.DemiBold
                    color: Theme.accent
                    anchors.verticalCenter: parent.verticalCenter
                }

                Rectangle {
                    width: 28
                    height: 28
                    radius: 14
                    color: modalCloseMouse.containsMouse ? Theme.alphaColor(Theme.danger, 0.25) : Theme.surfaceSoft
                    anchors.verticalCenter: parent.verticalCenter
                    MouseArea {
                        id: modalCloseMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.closeRequested()
                    }
                    Text {
                        anchors.centerIn: parent
                        text: "✕"
                        font.pixelSize: 12
                        font.weight: Font.Bold
                        color: modalCloseMouse.containsMouse ? Theme.danger : Theme.textSubtle
                    }
                }
            }

            // Tab Bar
            Row {
                id: tabBar
                width: parent.width
                spacing: 6

                readonly property var tabs: [
                    { id: "theme",     icon: "󰏘", en: "Theme & Pywal", cs: "Vzhled & Pywal" },
                    { id: "detection", icon: "󰍉", en: "CV & Rating",   cs: "Detekce & Rating" },
                    { id: "ai",        icon: "󰚩", en: "AI Vision",     cs: "AI Vize" },
                    { id: "capture",   icon: "󰄀", en: "Capture & UI",  cs: "Záznam & UI" }
                ]

                Repeater {
                    model: tabBar.tabs
                    Rectangle {
                        height: 30
                        width: (tabBar.width - (tabBar.tabs.length - 1) * tabBar.spacing) / tabBar.tabs.length
                        radius: 8
                        readonly property bool active: root.activeTab === modelData.id
                        color: active ? (modelData.id === "ai" ? Theme.aiAccent : Theme.accent) : (tabMouse.containsMouse ? Theme.surfaceHover : Theme.surfaceSoft)
                        MouseArea {
                            id: tabMouse
                            anchors.fill: parent
                            hoverEnabled: true
                            cursorShape: Qt.PointingHandCursor
                            onClicked: root.activeTab = modelData.id
                        }
                        Text {
                            anchors.centerIn: parent
                            text: modelData.icon + " " + root.label(modelData.en, modelData.cs)
                            font.family: Theme.fontFamily
                            font.pixelSize: 11
                            font.weight: active ? Font.DemiBold : Font.Medium
                            color: active ? Theme.accentText : Theme.text
                            elide: Text.ElideRight
                        }
                    }
                }
            }

            Rectangle {
                width: parent.width
                height: 1
                color: Theme.barBorder
            }

            // Scrollable section body
            Flickable {
                width: parent.width
                height: parent.height - 134
                clip: true
                boundsBehavior: Flickable.StopAtBounds
                contentHeight: sectionCol.implicitHeight + 8

                Column {
                    id: sectionCol
                    width: parent.width
                    spacing: 8

                    // --- Inline Reusable Row Components ---
                    component BoolSettingRow: Rectangle {
                        property string title: ""
                        property bool checked: false
                        signal toggled(bool nextVal)

                        width: sectionCol.width
                        height: 36
                        radius: 8
                        color: Theme.surfaceSoft

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 10
                            Text {
                                width: parent.width - 52
                                text: title
                                font.family: Theme.fontFamily
                                font.pixelSize: 12
                                color: Theme.text
                                elide: Text.ElideRight
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Rectangle {
                                width: 42
                                height: 22
                                radius: 11
                                color: checked ? Theme.accent : Theme.barBorder
                                anchors.verticalCenter: parent.verticalCenter
                                Rectangle {
                                    width: 16
                                    height: 16
                                    radius: 8
                                    y: 3
                                    x: checked ? parent.width - width - 3 : 3
                                    color: checked ? Theme.accentText : Theme.text
                                    Behavior on x { NumberAnimation { duration: 100 } }
                                }
                                MouseArea {
                                    anchors.fill: parent
                                    hoverEnabled: true
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: toggled(!checked)
                                }
                            }
                        }
                    }

                    component ChoiceSettingRow: Rectangle {
                        property string title: ""
                        property string current: ""
                        property var choices: []
                        signal chosen(string value)

                        width: sectionCol.width
                        height: 38
                        radius: 8
                        color: Theme.surfaceSoft

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 10
                            spacing: 6
                            Text {
                                width: Math.max(120, parent.width - choiceRow.implicitWidth - 10)
                                text: title
                                font.family: Theme.fontFamily
                                font.pixelSize: 12
                                color: Theme.text
                                elide: Text.ElideRight
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Row {
                                id: choiceRow
                                spacing: 4
                                anchors.verticalCenter: parent.verticalCenter
                                Repeater {
                                    model: choices
                                    Rectangle {
                                        height: 24
                                        width: choiceTxt.implicitWidth + 14
                                        radius: 6
                                        readonly property bool sel: current === modelData
                                        color: sel ? Theme.accent : Theme.barBackground
                                        border.color: sel ? Theme.accent : Theme.barBorder
                                        border.width: 1
                                        MouseArea {
                                            anchors.fill: parent
                                            hoverEnabled: true
                                            cursorShape: Qt.PointingHandCursor
                                            onClicked: chosen(modelData)
                                        }
                                        Text {
                                            id: choiceTxt
                                            anchors.centerIn: parent
                                            text: modelData
                                            font.family: Theme.fontFamily
                                            font.pixelSize: 11
                                            font.weight: sel ? Font.DemiBold : Font.Normal
                                            color: sel ? Theme.accentText : Theme.text
                                        }
                                    }
                                }
                            }
                        }
                    }

                    component NumberSettingRow: Rectangle {
                        property string title: ""
                        property real value: 0
                        property real minVal: 0
                        property real maxVal: 100
                        property real stepVal: 1
                        property int decimals: 0
                        signal updated(real nextVal)

                        width: sectionCol.width
                        height: 36
                        radius: 8
                        color: Theme.surfaceSoft

                        Row {
                            anchors.fill: parent
                            anchors.leftMargin: 12
                            anchors.rightMargin: 10
                            spacing: 6
                            Text {
                                width: parent.width - 116
                                text: title
                                font.family: Theme.fontFamily
                                font.pixelSize: 12
                                color: Theme.text
                                elide: Text.ElideRight
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Rectangle {
                                width: 24; height: 24; radius: 6
                                color: Theme.barBackground
                                border.color: Theme.barBorder
                                anchors.verticalCenter: parent.verticalCenter
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        const next = Math.max(minVal, Number((value - stepVal).toFixed(decimals)));
                                        updated(next);
                                    }
                                }
                                Text { anchors.centerIn: parent; text: "−"; color: Theme.text; font.pixelSize: 12 }
                            }
                            Text {
                                width: 48
                                horizontalAlignment: Text.AlignHCenter
                                text: value.toFixed(decimals)
                                font.family: Theme.fontFamily
                                font.pixelSize: 12
                                font.weight: Font.DemiBold
                                color: Theme.accent
                                anchors.verticalCenter: parent.verticalCenter
                            }
                            Rectangle {
                                width: 24; height: 24; radius: 6
                                color: Theme.barBackground
                                border.color: Theme.barBorder
                                anchors.verticalCenter: parent.verticalCenter
                                MouseArea {
                                    anchors.fill: parent
                                    cursorShape: Qt.PointingHandCursor
                                    onClicked: {
                                        const next = Math.min(maxVal, Number((value + stepVal).toFixed(decimals)));
                                        updated(next);
                                    }
                                }
                                Text { anchors.centerIn: parent; text: "+"; color: Theme.text; font.pixelSize: 12 }
                            }
                        }
                    }

                    component TextSettingRow: Rectangle {
                        id: textRow
                        property string title: ""
                        property string value: ""
                        property string placeholder: ""
                        signal edited(string nextText)

                        width: sectionCol.width
                        height: 56
                        radius: 8
                        color: Theme.surfaceSoft

                        Column {
                            anchors.fill: parent
                            anchors.margins: 8
                            anchors.leftMargin: 12
                            anchors.rightMargin: 12
                            spacing: 4
                            Text {
                                text: textRow.title
                                font.family: Theme.fontFamily
                                font.pixelSize: 11
                                color: Theme.textSubtle
                            }
                            Rectangle {
                                width: parent.width
                                height: 24
                                radius: 5
                                color: Theme.barBackground
                                border.color: fieldInput.activeFocus ? Theme.accent : Theme.barBorder
                                border.width: 1
                                TextInput {
                                    id: fieldInput
                                    property bool _editing: false
                                    anchors.fill: parent
                                    anchors.leftMargin: 6
                                    anchors.rightMargin: 6
                                    verticalAlignment: TextInput.AlignVCenter
                                    color: Theme.text
                                    selectionColor: Theme.accent
                                    selectedTextColor: Theme.accentText
                                    selectByMouse: true
                                    font.family: Theme.fontFamily
                                    font.pixelSize: 11
                                    clip: true
                                    Component.onCompleted: text = textRow.value
                                    onTextEdited: {
                                        _editing = true;
                                        textRow.edited(text);
                                        _editing = false;
                                    }
                                    Keys.onReturnPressed: (event) => {
                                        event.accepted = true;
                                        fieldInput.focus = false;
                                        root.forceActiveFocus();
                                    }
                                    Keys.onEscapePressed: (event) => {
                                        event.accepted = true;
                                        root.closeRequested();
                                    }
                                    Connections {
                                        target: textRow
                                        function onValueChanged() {
                                            if (!fieldInput._editing && fieldInput.text !== textRow.value) {
                                                fieldInput.text = textRow.value;
                                            }
                                        }
                                    }
                                    Text {
                                        visible: parent.text.length === 0 && textRow.placeholder.length > 0
                                        text: textRow.placeholder
                                        color: Theme.textSubtle
                                        font.family: Theme.fontFamily
                                        font.pixelSize: 11
                                        anchors.verticalCenter: parent.verticalCenter
                                    }
                                }
                            }
                        }
                    }

                    // === TAB 1: THEME & PYWAL ===
                    Column {
                        visible: root.activeTab === "theme"
                        width: sectionCol.width
                        spacing: 6

                        ChoiceSettingRow {
                            title: root.label("Palette Mode", "Režim palety")
                            current: (root.draft.theme && root.draft.theme.mode) || "pywal"
                            choices: ["pywal", "auto", "static"]
                            onChosen: (v) => root.setNested("theme", "mode", v)
                        }
                        TextSettingRow {
                            title: root.label("Pywal colors.json Path", "Cesta k Pywal colors.json")
                            value: (root.draft.theme && root.draft.theme.pywalPath) || ""
                            placeholder: "~/.cache/wal/colors.json"
                            onEdited: (t) => root.setNested("theme", "pywalPath", t)
                        }
                        BoolSettingRow {
                            title: root.label("Sync Pin Window with Pywal", "Synchronizovat Pin okno s Pywal")
                            checked: !(root.draft.theme && root.draft.theme.syncPinWindow === false)
                            onToggled: (v) => root.setNested("theme", "syncPinWindow", v)
                        }
                        BoolSettingRow {
                            title: root.label("Sync Satty Palette Export", "Exportovat paletu pro Satty")
                            checked: !!(root.draft.theme && root.draft.theme.syncSatty === true)
                            onToggled: (v) => root.setNested("theme", "syncSatty", v)
                        }
                        NumberSettingRow {
                            title: root.label("Backdrop Dim Opacity", "Ztmavení pozadí")
                            value: (root.draft.theme && root.draft.theme.dimOpacity !== undefined) ? root.draft.theme.dimOpacity : 0.65
                            minVal: 0.0; maxVal: 0.90; stepVal: 0.05; decimals: 2
                            onUpdated: (v) => root.setNested("theme", "dimOpacity", v)
                        }
                        NumberSettingRow {
                            title: root.label("Selection Corner Radius", "Zaoblení výběru")
                            value: (root.draft.theme && root.draft.theme.borderRadius !== undefined) ? root.draft.theme.borderRadius : 10
                            minVal: 0; maxVal: 24; stepVal: 1; decimals: 0
                            onUpdated: (v) => root.setNested("theme", "borderRadius", v)
                        }
                        NumberSettingRow {
                            title: root.label("Outline Thickness", "Tloušťka rámečku")
                            value: (root.draft.theme && root.draft.theme.outlineThickness !== undefined) ? root.draft.theme.outlineThickness : 2
                            minVal: 1; maxVal: 6; stepVal: 0.5; decimals: 1
                            onUpdated: (v) => root.setNested("theme", "outlineThickness", v)
                        }
                    }

                    // === TAB 2: DETECTION & RATING ===
                    Column {
                        visible: root.activeTab === "detection"
                        width: sectionCol.width
                        spacing: 6

                        BoolSettingRow {
                            title: root.label("Detect Text & Paragraphs", "Detekovat text a odstavce")
                            checked: !(root.draft.detection && root.draft.detection.enableText === false)
                            onToggled: (v) => root.setNested("detection", "enableText", v)
                        }
                        BoolSettingRow {
                            title: root.label("Adaptive Local Text Contrast", "Adaptivní kontrast textu (CLAHE)")
                            checked: !(root.draft.detection && root.draft.detection.adaptiveTextThreshold === false)
                            onToggled: (v) => root.setNested("detection", "adaptiveTextThreshold", v)
                        }
                        BoolSettingRow {
                            title: root.label("Filter Icons Out of Text", "Filtrovat ikony z textu")
                            checked: !(root.draft.detection && root.draft.detection.filterIconsFromText === false)
                            onToggled: (v) => root.setNested("detection", "filterIconsFromText", v)
                        }
                        BoolSettingRow {
                            title: root.label("Separate Multi-Column Paragraphs", "Oddělovat sloupce textu")
                            checked: !(root.draft.detection && root.draft.detection.multiColumnParagraphs === false)
                            onToggled: (v) => root.setNested("detection", "multiColumnParagraphs", v)
                        }
                        BoolSettingRow {
                            title: root.label("Detect Panels & Inputs", "Detekovat panely a vstupy")
                            checked: !(root.draft.detection && root.draft.detection.enablePanels === false)
                            onToggled: (v) => root.setNested("detection", "enablePanels", v)
                        }
                        BoolSettingRow {
                            title: root.label("Detect Grids & Slots", "Detekovat mřížky a sloty")
                            checked: !(root.draft.detection && root.draft.detection.enableGrids === false)
                            onToggled: (v) => root.setNested("detection", "enableGrids", v)
                        }
                        BoolSettingRow {
                            title: root.label("Enable Candidate Rating System", "Zapnout hodnocení boxů")
                            checked: !(root.draft.rating && root.draft.rating.enabled === false)
                            onToggled: (v) => root.setNested("rating", "enabled", v)
                        }
                        NumberSettingRow {
                            title: root.label("Min Confidence Filter", "Minimální spolehlivost boxů")
                            value: (root.draft.rating && root.draft.rating.minConfidence !== undefined) ? root.draft.rating.minConfidence : 0.30
                            minVal: 0.0; maxVal: 0.90; stepVal: 0.05; decimals: 2
                            onUpdated: (v) => root.setNested("rating", "minConfidence", v)
                        }
                        BoolSettingRow {
                            title: root.label("Show Confidence Badge", "Zobrazit % skóre v tagu")
                            checked: !(root.draft.ui && root.draft.ui.showConfidenceBadge === false)
                            onToggled: (v) => root.setNested("ui", "showConfidenceBadge", v)
                        }
                        BoolSettingRow {
                            title: root.label("Adaptive Learning from +/- Feedback", "Adaptivní učení z +/- feedbacku")
                            checked: !(root.draft.rating && root.draft.rating.adaptiveLearning === false)
                            onToggled: (v) => root.setNested("rating", "adaptiveLearning", v)
                        }
                    }

                    // === TAB 3: AI PROVIDER ===
                    Column {
                        visible: root.activeTab === "ai"
                        width: sectionCol.width
                        spacing: 6

                        BoolSettingRow {
                            title: root.label("Enable AI Vision Integration", "Povolit AI Vision funkce")
                            checked: !!(root.draft.ai && root.draft.ai.enabled === true)
                            onToggled: (v) => root.setNested("ai", "enabled", v)
                        }
                        ChoiceSettingRow {
                            title: root.label("AI Detection Trigger", "Spouštění AI boxů")
                            current: (root.draft.ai && root.draft.ai.trigger) || "manual"
                            choices: ["manual", "auto"]
                            onChosen: (v) => root.setNested("ai", "trigger", v)
                        }
                        ChoiceSettingRow {
                            title: root.label("AI Provider Protocol", "Protokol poskytovatele AI")
                            current: (root.draft.ai && root.draft.ai.provider) || "openai_compatible"
                            choices: ["openai_compatible", "gemini"]
                            onChosen: (v) => root.setNested("ai", "provider", v)
                        }
                        TextSettingRow {
                            title: root.label("Endpoint Base URL", "Adresa API endpointu")
                            value: root.activeAiProviderCfg().baseUrl || ""
                            placeholder: root.activeAiProviderKey() === "gemini" ? "https://generativelanguage.googleapis.com/v1beta" : "http://127.0.0.1:8080/v1"
                            onEdited: (t) => root.setAiProviderField("baseUrl", t)
                        }
                        TextSettingRow {
                            title: root.label("Vision Model Name", "Název vision modelu")
                            value: root.activeAiProviderCfg().model || ""
                            placeholder: root.activeAiProviderKey() === "gemini" ? "gemini-2.5-flash" : "qwen2.5-vl / custom-model"
                            onEdited: (t) => root.setAiProviderField("model", t)
                        }
                        TextSettingRow {
                            title: root.label("API Key Environment Var", "Proměnná prostředí s klíčem")
                            value: root.activeAiProviderCfg().apiKeyEnv || ""
                            placeholder: root.activeAiProviderKey() === "gemini" ? "GEMINI_API_KEY" : "OPENAI_API_KEY"
                            onEdited: (t) => root.setAiProviderField("apiKeyEnv", t)
                        }
                        TextSettingRow {
                            title: root.label("Custom Bounding Box Prompt (optional)", "Vlastní prompt pro AI boxy")
                            value: (root.draft.ai && root.draft.ai.prompt) || ""
                            placeholder: "Detect interactive UI regions..."
                            onEdited: (t) => root.setNested("ai", "prompt", t)
                        }
                    }

                    // === TAB 4: CAPTURE & UI ===
                    Column {
                        visible: root.activeTab === "capture"
                        width: sectionCol.width
                        spacing: 6

                        ChoiceSettingRow {
                            title: root.label("UI Language", "Jazyk rozhraní")
                            current: root.draft.language || "en"
                            choices: ["en", "cs"]
                            onChosen: (v) => root.setNested(null, "language", v)
                        }
                        ChoiceSettingRow {
                            title: root.label("Tesseract OCR Languages", "Jazyky pro Tesseract OCR")
                            current: root.draft.ocrLanguages || "eng"
                            choices: ["eng", "ces", "eng+ces"]
                            onChosen: (v) => root.setNested(null, "ocrLanguages", v)
                        }
                        TextSettingRow {
                            title: root.label("Default Save Directory (empty = XDG Pictures)", "Výchozí složka ukládání")
                            value: (root.draft.capture && root.draft.capture.defaultSaveDir) || ""
                            placeholder: "~/Pictures/Screenshots"
                            onEdited: (t) => root.setNested("capture", "defaultSaveDir", t)
                        }
                        NumberSettingRow {
                            title: root.label("PNG Compression Level", "Komprese PNG")
                            value: (root.draft.capture && root.draft.capture.pngCompression !== undefined) ? root.draft.capture.pngCompression : 4
                            minVal: 0; maxVal: 9; stepVal: 1; decimals: 0
                            onUpdated: (v) => root.setNested("capture", "pngCompression", v)
                        }
                        BoolSettingRow {
                            title: root.label("Copy Image to Clipboard After Save", "Kopírovat po uložení")
                            checked: !(root.draft.capture && root.draft.capture.copyAfterSave === false)
                            onToggled: (v) => root.setNested("capture", "copyAfterSave", v)
                        }
                        NumberSettingRow {
                            title: root.label("Magnifier Zoom Factor", "Přiblížení lupy")
                            value: (root.draft.ui && root.draft.ui.magnifierZoom !== undefined) ? root.draft.ui.magnifierZoom : 3.0
                            minVal: 1.5; maxVal: 10; stepVal: 0.5; decimals: 1
                            onUpdated: (v) => root.setNested("ui", "magnifierZoom", v)
                        }
                        NumberSettingRow {
                            title: root.label("Magnifier Size (px)", "Velikost lupy (px)")
                            value: (root.draft.ui && root.draft.ui.magnifierSize !== undefined) ? root.draft.ui.magnifierSize : 180
                            minVal: 100; maxVal: 320; stepVal: 10; decimals: 0
                            onUpdated: (v) => root.setNested("ui", "magnifierSize", v)
                        }
                        BoolSettingRow {
                            title: root.label("Show Bottom Keyboard Hints", "Zobrazit spodní nápovědu kláves")
                            checked: !(root.draft.ui && root.draft.ui.showHints === false)
                            onToggled: (v) => root.setNested("ui", "showHints", v)
                        }
                        TextSettingRow {
                            title: root.label("Post-Save Hook Command ({path})", "Příkaz po uložení ({path})")
                            value: root.draft.postSaveHook || ""
                            placeholder: "notify-send {path}"
                            onEdited: (t) => root.setNested(null, "postSaveHook", t)
                        }
                    }
                }
            }

            // Footer buttons
            Row {
                width: parent.width
                height: 34
                spacing: 8
                layoutDirection: Qt.RightToLeft

                Rectangle {
                    height: 32
                    width: saveBtnTxt.implicitWidth + 28
                    radius: 16
                    color: saveBtnMouse.containsMouse ? Theme.accentHover : Theme.accent
                    MouseArea {
                        id: saveBtnMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.applyAndSave()
                    }
                    Text {
                        id: saveBtnTxt
                        anchors.centerIn: parent
                        text: I18n.t("save")
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        font.weight: Font.DemiBold
                        color: Theme.accentText
                    }
                }

                Rectangle {
                    height: 32
                    width: cancelBtnTxt.implicitWidth + 24
                    radius: 16
                    color: cancelBtnMouse.containsMouse ? Theme.surfaceHover : Theme.surfaceSoft
                    border.color: Theme.barBorder
                    border.width: 1
                    MouseArea {
                        id: cancelBtnMouse
                        anchors.fill: parent
                        hoverEnabled: true
                        cursorShape: Qt.PointingHandCursor
                        onClicked: root.closeRequested()
                    }
                    Text {
                        id: cancelBtnTxt
                        anchors.centerIn: parent
                        text: I18n.t("close")
                        font.family: Theme.fontFamily
                        font.pixelSize: 12
                        color: Theme.text
                    }
                }
            }
        }
    }
}
