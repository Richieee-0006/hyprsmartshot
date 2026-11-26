#include "core/config.hpp"
#include "ipc/daemon.hpp"
#include "vision/ai_client.hpp"

#include <algorithm>
#include <gtk/gtk.h>
#include <string>
#include <vector>

namespace {

struct SettingsApp {
    nlohmann::json cfg;
    std::string explicit_config;
    std::string initial_tab = "theme";

    // Theme widgets
    GtkDropDown* theme_mode = nullptr;
    GtkEntry* pywal_path = nullptr;
    GtkSwitch* sync_satty = nullptr;
    GtkSwitch* sync_pin = nullptr;
    GtkScale* dim_opacity = nullptr;
    GtkSpinButton* border_radius = nullptr;
    GtkSpinButton* outline_thick = nullptr;
    GtkEntry* font_family = nullptr;

    // Detection & Rating widgets
    GtkSwitch* det_text = nullptr;
    GtkSwitch* det_panels = nullptr;
    GtkSwitch* det_grids = nullptr;
    GtkSwitch* det_win_content = nullptr;
    GtkSwitch* rate_enabled = nullptr;
    GtkSwitch* rate_adaptive = nullptr;
    GtkScale* rate_min_conf = nullptr;

    // AI Vision widgets
    GtkSwitch* ai_enabled = nullptr;
    GtkDropDown* ai_trigger = nullptr;
    GtkDropDown* ai_provider = nullptr;
    GtkEntry* ai_model = nullptr;
    GtkEntry* ai_base_url = nullptr;
    GtkEntry* ai_api_key = nullptr;
    GtkSpinButton* ai_timeout = nullptr;
    GtkSpinButton* ai_max_dim = nullptr;
    GtkLabel* ai_models_status = nullptr;

    // Capture & UI widgets
    GtkEntry* lang_entry = nullptr;
    GtkEntry* ocr_langs = nullptr;
    GtkEntry* save_dir = nullptr;
    GtkSpinButton* png_comp = nullptr;
    GtkSwitch* copy_after_save = nullptr;
    GtkSwitch* show_hints = nullptr;
    GtkSwitch* show_conf = nullptr;
    GtkSwitch* show_mag = nullptr;
    GtkSpinButton* mag_zoom = nullptr;
    GtkEntry* post_save_hook = nullptr;
    GtkEntry* post_copy_hook = nullptr;

    GtkLabel* status_label = nullptr;

    std::vector<std::string> provider_keys = {
        "openai_compatible", "local_llm", "copilot", "ollama",
        "gemini", "groq", "openrouter", "mistral", "ovhcloud", "kilo",
    };

    std::string current_provider_key() const {
        guint idx = gtk_drop_down_get_selected(ai_provider);
        if (idx < provider_keys.size()) return provider_keys[idx];
        return "openai_compatible";
    }

    void populate_provider_fields() {
        std::string key = current_provider_key();
        const auto& provs = cfg["ai"]["providers"];
        nlohmann::json p = (provs.is_object() && provs.contains(key)) ? provs[key] : nlohmann::json::object();
        gtk_editable_set_text(GTK_EDITABLE(ai_model), p.value("model", std::string()).c_str());
        gtk_editable_set_text(GTK_EDITABLE(ai_base_url), p.value("baseUrl", std::string()).c_str());
        gtk_editable_set_text(GTK_EDITABLE(ai_api_key), p.value("apiKey", std::string()).c_str());
    }

    void save_all() {
        const char* modes[] = {"pywal", "auto", "static"};
        guint mi = gtk_drop_down_get_selected(theme_mode);
        cfg["theme"]["mode"] = (mi < 3) ? modes[mi] : "pywal";
        cfg["theme"]["pywalPath"] = gtk_editable_get_text(GTK_EDITABLE(pywal_path));
        cfg["theme"]["syncSatty"] = static_cast<bool>(gtk_switch_get_active(sync_satty));
        cfg["theme"]["syncPinWindow"] = static_cast<bool>(gtk_switch_get_active(sync_pin));
        cfg["theme"]["dimOpacity"] = gtk_range_get_value(GTK_RANGE(dim_opacity));
        cfg["theme"]["borderRadius"] = gtk_spin_button_get_value_as_int(border_radius);
        cfg["theme"]["outlineThickness"] = gtk_spin_button_get_value_as_int(outline_thick);
        cfg["theme"]["fontFamily"] = gtk_editable_get_text(GTK_EDITABLE(font_family));

        cfg["detection"]["enableText"] = static_cast<bool>(gtk_switch_get_active(det_text));
        cfg["detection"]["enablePanels"] = static_cast<bool>(gtk_switch_get_active(det_panels));
        cfg["detection"]["enableGrids"] = static_cast<bool>(gtk_switch_get_active(det_grids));
        cfg["detection"]["enableWindowContent"] = static_cast<bool>(gtk_switch_get_active(det_win_content));
        cfg["rating"]["enabled"] = static_cast<bool>(gtk_switch_get_active(rate_enabled));
        cfg["rating"]["adaptiveLearning"] = static_cast<bool>(gtk_switch_get_active(rate_adaptive));
        cfg["rating"]["minConfidence"] = gtk_range_get_value(GTK_RANGE(rate_min_conf));

        cfg["ai"]["enabled"] = static_cast<bool>(gtk_switch_get_active(ai_enabled));
        const char* trgs[] = {"manual", "auto"};
        guint ti = gtk_drop_down_get_selected(ai_trigger);
        cfg["ai"]["trigger"] = (ti < 2) ? trgs[ti] : "manual";
        std::string pkey = current_provider_key();
        cfg["ai"]["provider"] = pkey;
        cfg["ai"]["providers"][pkey]["model"] = gtk_editable_get_text(GTK_EDITABLE(ai_model));
        cfg["ai"]["providers"][pkey]["baseUrl"] = gtk_editable_get_text(GTK_EDITABLE(ai_base_url));
        cfg["ai"]["providers"][pkey]["apiKey"] = gtk_editable_get_text(GTK_EDITABLE(ai_api_key));
        cfg["ai"]["timeoutMs"] = gtk_spin_button_get_value_as_int(ai_timeout);
        cfg["ai"]["maxImageDim"] = gtk_spin_button_get_value_as_int(ai_max_dim);

        cfg["language"] = gtk_editable_get_text(GTK_EDITABLE(lang_entry));
        cfg["ocrLanguages"] = gtk_editable_get_text(GTK_EDITABLE(ocr_langs));
        cfg["capture"]["defaultSaveDir"] = gtk_editable_get_text(GTK_EDITABLE(save_dir));
        cfg["capture"]["pngCompression"] = gtk_spin_button_get_value_as_int(png_comp);
        cfg["capture"]["copyAfterSave"] = static_cast<bool>(gtk_switch_get_active(copy_after_save));
        cfg["ui"]["showHints"] = static_cast<bool>(gtk_switch_get_active(show_hints));
        cfg["ui"]["showConfidenceBadge"] = static_cast<bool>(gtk_switch_get_active(show_conf));
        cfg["ui"]["showMagnifierByDefault"] = static_cast<bool>(gtk_switch_get_active(show_mag));
        cfg["ui"]["magnifierZoom"] = gtk_spin_button_get_value(mag_zoom);
        cfg["postSaveHook"] = gtk_editable_get_text(GTK_EDITABLE(post_save_hook));
        cfg["postCopyHook"] = gtk_editable_get_text(GTK_EDITABLE(post_copy_hook));

        hss::ConfigManager::save_user_config(cfg, explicit_config);
        if (cfg["theme"].value("syncSatty", false)) {
            hss::ConfigManager::export_satty_pywal_config(cfg);
        }
        bool reloaded = hss::Daemon::notify_reload_config();
        gtk_label_set_text(status_label, reloaded ? "Saved & synced with daemon." : "Saved to config.json.");
    }
};

GtkWidget* make_row(const char* label_txt, GtkWidget* control) {
    GtkWidget* box = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 12);
    gtk_widget_set_margin_top(box, 4);
    gtk_widget_set_margin_bottom(box, 4);
    GtkWidget* lbl = gtk_label_new(label_txt);
    gtk_label_set_xalign(GTK_LABEL(lbl), 0.0f);
    gtk_widget_set_hexpand(lbl, TRUE);
    gtk_box_append(GTK_BOX(box), lbl);
    gtk_box_append(GTK_BOX(box), control);
    return box;
}

GtkWidget* make_page_box() {
    GtkWidget* box = gtk_box_new(GTK_ORIENTATION_VERTICAL, 8);
    gtk_widget_set_margin_top(box, 16);
    gtk_widget_set_margin_bottom(box, 16);
    gtk_widget_set_margin_start(box, 16);
    gtk_widget_set_margin_end(box, 16);
    return box;
}

void on_activate(GtkApplication* app, gpointer user_data) {
    auto* sa = static_cast<SettingsApp*>(user_data);

    GtkWidget* win = gtk_application_window_new(app);
    gtk_window_set_title(GTK_WINDOW(win), "HyprSmartShot Settings");
    gtk_window_set_default_size(GTK_WINDOW(win), 620, 520);

    GtkWidget* root = gtk_box_new(GTK_ORIENTATION_VERTICAL, 0);
    gtk_window_set_child(GTK_WINDOW(win), root);

    GtkWidget* stack = gtk_stack_new();
    gtk_widget_set_vexpand(stack, TRUE);
    GtkWidget* switcher = gtk_stack_switcher_new();
    gtk_stack_switcher_set_stack(GTK_STACK_SWITCHER(switcher), GTK_STACK(stack));
    gtk_widget_set_halign(switcher, GTK_ALIGN_CENTER);
    gtk_widget_set_margin_top(switcher, 12);
    gtk_widget_set_margin_bottom(switcher, 8);
    gtk_box_append(GTK_BOX(root), switcher);
    gtk_box_append(GTK_BOX(root), stack);

    // Tab 1: Theme & Pywal
    {
        GtkWidget* page = make_page_box();
        const char* modes[] = {"pywal", "auto", "static", nullptr};
        sa->theme_mode = GTK_DROP_DOWN(gtk_drop_down_new_from_strings(modes));
        std::string cur_m = sa->cfg["theme"].value("mode", std::string("pywal"));
        gtk_drop_down_set_selected(sa->theme_mode, cur_m == "auto" ? 1 : (cur_m == "static" ? 2 : 0));
        gtk_box_append(GTK_BOX(page), make_row("Theme Mode", GTK_WIDGET(sa->theme_mode)));

        sa->pywal_path = GTK_ENTRY(gtk_entry_new());
        gtk_editable_set_text(GTK_EDITABLE(sa->pywal_path), sa->cfg["theme"].value("pywalPath", std::string("~/.cache/wal/colors.json")).c_str());
        gtk_widget_set_size_request(GTK_WIDGET(sa->pywal_path), 280, -1);
        gtk_box_append(GTK_BOX(page), make_row("Pywal colors.json Path", GTK_WIDGET(sa->pywal_path)));

        sa->font_family = GTK_ENTRY(gtk_entry_new());
        gtk_editable_set_text(GTK_EDITABLE(sa->font_family), sa->cfg["theme"].value("fontFamily", std::string("JetBrainsMono Nerd Font")).c_str());
        gtk_widget_set_size_request(GTK_WIDGET(sa->font_family), 280, -1);
        gtk_box_append(GTK_BOX(page), make_row("Font Family", GTK_WIDGET(sa->font_family)));

        sa->dim_opacity = GTK_SCALE(gtk_scale_new_with_range(GTK_ORIENTATION_HORIZONTAL, 0.1, 0.9, 0.05));
        gtk_range_set_value(GTK_RANGE(sa->dim_opacity), sa->cfg["theme"].value("dimOpacity", 0.65));
        gtk_widget_set_size_request(GTK_WIDGET(sa->dim_opacity), 200, -1);
        gtk_box_append(GTK_BOX(page), make_row("Dim Opacity", GTK_WIDGET(sa->dim_opacity)));

        sa->border_radius = GTK_SPIN_BUTTON(gtk_spin_button_new_with_range(0, 24, 1));
        gtk_spin_button_set_value(sa->border_radius, sa->cfg["theme"].value("borderRadius", 10));
        gtk_box_append(GTK_BOX(page), make_row("Border Radius (px)", GTK_WIDGET(sa->border_radius)));

        sa->outline_thick = GTK_SPIN_BUTTON(gtk_spin_button_new_with_range(1, 8, 1));
        gtk_spin_button_set_value(sa->outline_thick, sa->cfg["theme"].value("outlineThickness", 2));
        gtk_box_append(GTK_BOX(page), make_row("Outline Thickness (px)", GTK_WIDGET(sa->outline_thick)));

        sa->sync_satty = GTK_SWITCH(gtk_switch_new());
        gtk_switch_set_active(sa->sync_satty, sa->cfg["theme"].value("syncSatty", false));
        gtk_box_append(GTK_BOX(page), make_row("Sync Satty Palette", GTK_WIDGET(sa->sync_satty)));

        sa->sync_pin = GTK_SWITCH(gtk_switch_new());
        gtk_switch_set_active(sa->sync_pin, sa->cfg["theme"].value("syncPinWindow", true));
        gtk_box_append(GTK_BOX(page), make_row("Sync Pin Window Border", GTK_WIDGET(sa->sync_pin)));

        gtk_stack_add_titled(GTK_STACK(stack), page, "theme", "Theme & Pywal");
    }

    // Tab 2: CV & Rating
    {
        GtkWidget* page = make_page_box();
        sa->det_text = GTK_SWITCH(gtk_switch_new());
        gtk_switch_set_active(sa->det_text, sa->cfg["detection"].value("enableText", true));
        gtk_box_append(GTK_BOX(page), make_row("Detect Text & Paragraphs", GTK_WIDGET(sa->det_text)));

        sa->det_panels = GTK_SWITCH(gtk_switch_new());
        gtk_switch_set_active(sa->det_panels, sa->cfg["detection"].value("enablePanels", true));
        gtk_box_append(GTK_BOX(page), make_row("Detect Panels & Columns", GTK_WIDGET(sa->det_panels)));

        sa->det_grids = GTK_SWITCH(gtk_switch_new());
        gtk_switch_set_active(sa->det_grids, sa->cfg["detection"].value("enableGrids", true));
        gtk_box_append(GTK_BOX(page), make_row("Detect Slot Grids (Games)", GTK_WIDGET(sa->det_grids)));

        sa->det_win_content = GTK_SWITCH(gtk_switch_new());
        gtk_switch_set_active(sa->det_win_content, sa->cfg["detection"].value("enableWindowContent", true));
        gtk_box_append(GTK_BOX(page), make_row("Detect Browser / App Panes", GTK_WIDGET(sa->det_win_content)));

        sa->rate_enabled = GTK_SWITCH(gtk_switch_new());
        gtk_switch_set_active(sa->rate_enabled, sa->cfg["rating"].value("enabled", true));
        gtk_box_append(GTK_BOX(page), make_row("Enable Confidence Rating", GTK_WIDGET(sa->rate_enabled)));

        sa->rate_adaptive = GTK_SWITCH(gtk_switch_new());
        gtk_switch_set_active(sa->rate_adaptive, sa->cfg["rating"].value("adaptiveLearning", true));
        gtk_box_append(GTK_BOX(page), make_row("Adaptive Feedback Learning (+/-)", GTK_WIDGET(sa->rate_adaptive)));

        sa->rate_min_conf = GTK_SCALE(gtk_scale_new_with_range(GTK_ORIENTATION_HORIZONTAL, 0.0, 0.9, 0.05));
        gtk_range_set_value(GTK_RANGE(sa->rate_min_conf), sa->cfg["rating"].value("minConfidence", 0.30));
        gtk_widget_set_size_request(GTK_WIDGET(sa->rate_min_conf), 200, -1);
        gtk_box_append(GTK_BOX(page), make_row("Min Confidence Threshold", GTK_WIDGET(sa->rate_min_conf)));

        gtk_stack_add_titled(GTK_STACK(stack), page, "detection", "CV & Rating");
    }

    // Tab 3: AI Vision
    {
        GtkWidget* page = make_page_box();
        sa->ai_enabled = GTK_SWITCH(gtk_switch_new());
        gtk_switch_set_active(sa->ai_enabled, sa->cfg["ai"].value("enabled", false));
        gtk_box_append(GTK_BOX(page), make_row("Enable AI Vision", GTK_WIDGET(sa->ai_enabled)));

        const char* trgs[] = {"manual", "auto", nullptr};
        sa->ai_trigger = GTK_DROP_DOWN(gtk_drop_down_new_from_strings(trgs));
        gtk_drop_down_set_selected(sa->ai_trigger, sa->cfg["ai"].value("trigger", std::string("manual")) == "auto" ? 1 : 0);
        gtk_box_append(GTK_BOX(page), make_row("Trigger Mode", GTK_WIDGET(sa->ai_trigger)));

        std::vector<const char*> pstrs;
        for (const auto& k : sa->provider_keys) pstrs.push_back(k.c_str());
        pstrs.push_back(nullptr);
        sa->ai_provider = GTK_DROP_DOWN(gtk_drop_down_new_from_strings(pstrs.data()));
        std::string cur_p = sa->cfg["ai"].value("provider", std::string("openai_compatible"));
        for (size_t i = 0; i < sa->provider_keys.size(); ++i) {
            if (sa->provider_keys[i] == cur_p) {
                gtk_drop_down_set_selected(sa->ai_provider, static_cast<guint>(i));
                break;
            }
        }
        gtk_box_append(GTK_BOX(page), make_row("Provider", GTK_WIDGET(sa->ai_provider)));

        sa->ai_model = GTK_ENTRY(gtk_entry_new());
        gtk_widget_set_size_request(GTK_WIDGET(sa->ai_model), 280, -1);
        gtk_box_append(GTK_BOX(page), make_row("Model ID", GTK_WIDGET(sa->ai_model)));

        sa->ai_base_url = GTK_ENTRY(gtk_entry_new());
        gtk_widget_set_size_request(GTK_WIDGET(sa->ai_base_url), 280, -1);
        gtk_box_append(GTK_BOX(page), make_row("Base URL", GTK_WIDGET(sa->ai_base_url)));

        sa->ai_api_key = GTK_ENTRY(gtk_entry_new());
        gtk_entry_set_visibility(sa->ai_api_key, FALSE);
        gtk_widget_set_size_request(GTK_WIDGET(sa->ai_api_key), 280, -1);
        gtk_box_append(GTK_BOX(page), make_row("API Key (optional override)", GTK_WIDGET(sa->ai_api_key)));

        sa->ai_timeout = GTK_SPIN_BUTTON(gtk_spin_button_new_with_range(2000, 120000, 1000));
        gtk_spin_button_set_value(sa->ai_timeout, sa->cfg["ai"].value("timeoutMs", 35000));
        gtk_box_append(GTK_BOX(page), make_row("Timeout (ms)", GTK_WIDGET(sa->ai_timeout)));

        sa->ai_max_dim = GTK_SPIN_BUTTON(gtk_spin_button_new_with_range(384, 2048, 64));
        gtk_spin_button_set_value(sa->ai_max_dim, sa->cfg["ai"].value("maxImageDim", 960));
        gtk_box_append(GTK_BOX(page), make_row("Max Image Dim (px)", GTK_WIDGET(sa->ai_max_dim)));

        GtkWidget* refresh_btn = gtk_button_new_with_label("Refresh Models");
        sa->ai_models_status = GTK_LABEL(gtk_label_new(""));
        gtk_box_append(GTK_BOX(page), make_row("Model Discovery", refresh_btn));
        gtk_box_append(GTK_BOX(page), GTK_WIDGET(sa->ai_models_status));

        g_signal_connect(sa->ai_provider, "notify::selected", G_CALLBACK(+[](GObject*, GParamSpec*, gpointer d) {
            static_cast<SettingsApp*>(d)->populate_provider_fields();
        }), sa);

        g_signal_connect(refresh_btn, "clicked", G_CALLBACK(+[](GtkButton*, gpointer d) {
            auto* s = static_cast<SettingsApp*>(d);
            auto models = hss::AiClient::list_provider_models(s->cfg, s->current_provider_key(), true);
            std::string txt = "Found " + std::to_string(models.size()) + " models";
            if (!models.empty()) txt += " (first: " + models.front() + ")";
            gtk_label_set_text(s->ai_models_status, txt.c_str());
        }), sa);

        sa->populate_provider_fields();
        gtk_stack_add_titled(GTK_STACK(stack), page, "ai", "AI Vision");
    }

    // Tab 4: Capture & UI
    {
        GtkWidget* page = make_page_box();
        sa->lang_entry = GTK_ENTRY(gtk_entry_new());
        gtk_editable_set_text(GTK_EDITABLE(sa->lang_entry), sa->cfg.value("language", std::string("en")).c_str());
        gtk_box_append(GTK_BOX(page), make_row("Language (en, cs, ...)", GTK_WIDGET(sa->lang_entry)));

        sa->ocr_langs = GTK_ENTRY(gtk_entry_new());
        gtk_editable_set_text(GTK_EDITABLE(sa->ocr_langs), sa->cfg.value("ocrLanguages", std::string("eng")).c_str());
        gtk_box_append(GTK_BOX(page), make_row("OCR Languages", GTK_WIDGET(sa->ocr_langs)));

        sa->save_dir = GTK_ENTRY(gtk_entry_new());
        gtk_editable_set_text(GTK_EDITABLE(sa->save_dir), sa->cfg["capture"].value("defaultSaveDir", std::string()).c_str());
        gtk_widget_set_size_request(GTK_WIDGET(sa->save_dir), 260, -1);
        gtk_box_append(GTK_BOX(page), make_row("Default Save Dir", GTK_WIDGET(sa->save_dir)));

        sa->png_comp = GTK_SPIN_BUTTON(gtk_spin_button_new_with_range(0, 9, 1));
        gtk_spin_button_set_value(sa->png_comp, sa->cfg["capture"].value("pngCompression", 4));
        gtk_box_append(GTK_BOX(page), make_row("PNG Compression (0-9)", GTK_WIDGET(sa->png_comp)));

        sa->copy_after_save = GTK_SWITCH(gtk_switch_new());
        gtk_switch_set_active(sa->copy_after_save, sa->cfg["capture"].value("copyAfterSave", true));
        gtk_box_append(GTK_BOX(page), make_row("Copy to Clipboard on Save", GTK_WIDGET(sa->copy_after_save)));

        sa->show_hints = GTK_SWITCH(gtk_switch_new());
        gtk_switch_set_active(sa->show_hints, sa->cfg["ui"].value("showHints", true));
        gtk_box_append(GTK_BOX(page), make_row("Show Bottom Hints", GTK_WIDGET(sa->show_hints)));

        sa->show_conf = GTK_SWITCH(gtk_switch_new());
        gtk_switch_set_active(sa->show_conf, sa->cfg["ui"].value("showConfidenceBadge", true));
        gtk_box_append(GTK_BOX(page), make_row("Show Confidence %", GTK_WIDGET(sa->show_conf)));

        sa->show_mag = GTK_SWITCH(gtk_switch_new());
        gtk_switch_set_active(sa->show_mag, sa->cfg["ui"].value("showMagnifierByDefault", false));
        gtk_box_append(GTK_BOX(page), make_row("Magnifier On By Default", GTK_WIDGET(sa->show_mag)));

        sa->mag_zoom = GTK_SPIN_BUTTON(gtk_spin_button_new_with_range(1.5, 8.0, 0.5));
        gtk_spin_button_set_value(sa->mag_zoom, sa->cfg["ui"].value("magnifierZoom", 3.0));
        gtk_box_append(GTK_BOX(page), make_row("Magnifier Zoom", GTK_WIDGET(sa->mag_zoom)));

        sa->post_save_hook = GTK_ENTRY(gtk_entry_new());
        gtk_editable_set_text(GTK_EDITABLE(sa->post_save_hook), sa->cfg.value("postSaveHook", std::string()).c_str());
        gtk_widget_set_size_request(GTK_WIDGET(sa->post_save_hook), 260, -1);
        gtk_box_append(GTK_BOX(page), make_row("Post-Save Hook ({path})", GTK_WIDGET(sa->post_save_hook)));

        sa->post_copy_hook = GTK_ENTRY(gtk_entry_new());
        gtk_editable_set_text(GTK_EDITABLE(sa->post_copy_hook), sa->cfg.value("postCopyHook", std::string()).c_str());
        gtk_widget_set_size_request(GTK_WIDGET(sa->post_copy_hook), 260, -1);
        gtk_box_append(GTK_BOX(page), make_row("Post-Copy Hook ({path})", GTK_WIDGET(sa->post_copy_hook)));

        gtk_stack_add_titled(GTK_STACK(stack), page, "capture", "Capture & UI");
    }

    if (!sa->initial_tab.empty()) {
        gtk_stack_set_visible_child_name(GTK_STACK(stack), sa->initial_tab.c_str());
    }

    // Bottom Action Bar
    GtkWidget* footer = gtk_box_new(GTK_ORIENTATION_HORIZONTAL, 8);
    gtk_widget_set_margin_top(footer, 8);
    gtk_widget_set_margin_bottom(footer, 12);
    gtk_widget_set_margin_start(footer, 16);
    gtk_widget_set_margin_end(footer, 16);

    sa->status_label = GTK_LABEL(gtk_label_new(""));
    gtk_label_set_xalign(sa->status_label, 0.0f);
    gtk_widget_set_hexpand(GTK_WIDGET(sa->status_label), TRUE);
    gtk_box_append(GTK_BOX(footer), GTK_WIDGET(sa->status_label));

    GtkWidget* close_btn = gtk_button_new_with_label("Close");
    GtkWidget* save_btn = gtk_button_new_with_label("Save & Apply");
    gtk_widget_add_css_class(save_btn, "suggested-action");
    gtk_box_append(GTK_BOX(footer), close_btn);
    gtk_box_append(GTK_BOX(footer), save_btn);
    gtk_box_append(GTK_BOX(root), footer);

    g_signal_connect(save_btn, "clicked", G_CALLBACK(+[](GtkButton*, gpointer d) {
        static_cast<SettingsApp*>(d)->save_all();
    }), sa);
    g_signal_connect_swapped(close_btn, "clicked", G_CALLBACK(gtk_window_destroy), win);

    gtk_window_present(GTK_WINDOW(win));
}

}  // namespace

int main(int argc, char** argv) {
    SettingsApp sa;
    std::vector<char*> gtk_argv = {argv[0]};
    for (int i = 1; i < argc; ++i) {
        std::string a = argv[i];
        if (a == "--tab" && i + 1 < argc) {
            sa.initial_tab = argv[++i];
        } else if (a == "--config" && i + 1 < argc) {
            sa.explicit_config = argv[++i];
        } else {
            gtk_argv.push_back(argv[i]);
        }
    }
    sa.cfg = hss::ConfigManager::load_config(sa.explicit_config);

    GtkApplication* app = gtk_application_new("eu.rutterle.hyprsmartshot.settings", G_APPLICATION_DEFAULT_FLAGS);
    g_signal_connect(app, "activate", G_CALLBACK(on_activate), &sa);
    int rc = g_application_run(G_APPLICATION(app), static_cast<int>(gtk_argv.size()), gtk_argv.data());
    g_object_unref(app);
    return rc;
}
