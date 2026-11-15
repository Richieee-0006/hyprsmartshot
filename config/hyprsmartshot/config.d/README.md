# HyprSmartShot Modular Config Drop-ins

HyprSmartShot loads configuration in layers (later layers deep-merge onto earlier ones):

1. Bundled defaults (`config/hyprsmartshot/config.json`)
2. User config (`~/.config/hyprsmartshot/config.json`, or `$SMARTSHOT_CONFIG`)
3. Optional per-module overrides in `~/.config/hyprsmartshot/`:
   - `theme.json`
   - `detection.json`
   - `rating.json`
   - `ai.json`
   - `ui.json`
   - `capture.json`
   - `presets.json`
   - `appRules.json`
4. Sorted drop-in fragments in `~/.config/hyprsmartshot/config.d/*.json`

Files ending in `.example` are ignored and can be copied and renamed to `.json` to activate.
