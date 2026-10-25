# HyprSmartShot

[![Target](https://img.shields.io/badge/target-Hyprland_Wayland-89b4fa?style=flat-square)](https://hyprland.org)
[![Toolkit](https://img.shields.io/badge/toolkit-QuickShell_Qt6-a6e3a1?style=flat-square)](https://quickshell.org)
[![Vision](https://img.shields.io/badge/vision-OpenCV-f9e2af?style=flat-square)](https://opencv.org)
[![Palette](https://img.shields.io/badge/palette-Pywal_Dynamic-cba6f7?style=flat-square)](https://github.com/dylanaraps/pywal)

Ultra-smart screenshotovací utilita pro **Hyprland** s automatickým rozpoznáváním herních rozhraní, inventářů a oken přes Computer Vision.

---

## Přehled úprav a funkcí

| Oblast | Popis |
| :--- | :--- |
| **Herní UI & Inventáře** | Automatická detekce pravoúhlých i stylizovaných panelů (batohy, sloty předmětů, chatboxy, skill bary, dialogy) přes optimalizovaný OpenCV contour engine (< 60 ms). |
| **Hierarchický zoom** | Procházení vrstev rozhraní kolečkem myši (`Scroll`) – od konkrétního slotu itemu přes grid batohu až po celou hru. |
| **Magnetické přichytávání** | Plynulé přitahování hran při volném tažení myší k nalezeným okrajům UI prvků. |
| **Potvrzovací režim** | Kliknutím se prvek uzamkne a zobrazí se plovoucí akční lišta (`Kopírovat`, `Uložit`, `OCR`, `Lupa`). |
| **Optické OCR** | Okamžitá extrakce textu dialogů a popisků předmětů do schránky přes `Tesseract`. |
| **Moderní vizuál** | Plovoucí skleněný panel (glassmorphism), fragment shader pro zaoblené výřezy a dynamické barvy z `pywal`. |

---

## Režimy snímání

| Režim | Volba | Popis |
| :--- | :--- | :--- |
| **Smart / Herní** | `universal` (výchozí) | Detekce herních panelů, slotů, plovoucích overlayů i oken + volný výběr tažením myší s magnetickým přichytáváním. |
| **Okno** | `window` | Nativní přichytávání k oknům Hyprlandu přes IPC (s prioritou pro plovoucí overlay okna). |
| **Obrazovka** | `screen` | Okamžité zachycení celého monitoru. |

---

## Ovládání a zkratky

| Vstup | Akce |
| :--- | :--- |
| **Pohyb myší** | Magnetické zvýraznění a přichycení k herním panelům, slotům nebo oknům |
| **Tažení myší** | Volný obdélníkový výběr s magnetickým přichytáváním k hranám |
| **Kolečko myši (Scroll)** | Změna úrovně hierarchie (např. slot předmětu $\leftrightarrow$ batoh $\leftrightarrow$ celá hra) |
| **Levé kliknutí** | **Potvrzovací režim**: Zamkne výběr a zobrazí potvrzovací lištu |
| **Enter / Dvojklik** | Zkopírování výběru do schránky (`wl-copy`) a ukončení |
| **Ctrl + S** | Uložení snímku do `~/Pictures/Screenshots/` a zkopírování |
| **O** | OCR rozpoznání textu z výběru (přes `tesseract`) a zkopírování do schránky |
| **Alt** | Zapnutí / vypnutí zvětšovací lupy s přesnými pixely |
| **Esc / Pravé tlačítko** | Odemknutí zamčeného výběru / zrušení a zavření overlaye |
| **1 / 2 / 3** | Přepínání režimů (Univerzální / Okno / Obrazovka) |

---

## Instalace

1. Naklonuj repozitář:
   ```bash
   git clone git@github.com:Richieee-0006/hyprsmartshot.git ~/.local/share/hyprsmartshot
   ```

2. Spusť instalační skript (připraví Python venv s OpenCV a vytvoří symlink do `~/.local/bin/hyprsmartshot`):
   ```bash
   cd ~/.local/share/hyprsmartshot
   ./install.sh
   ```

---

## Konfigurace

Přidej následující řádky do souboru `~/.config/hypr/hyprland.conf`:

```ini
# HyprSmartShot
bind = , Print, exec, hyprsmartshot universal
bind = SHIFT, Print, exec, hyprsmartshot full
bind = CTRL, Print, exec, hyprsmartshot window
```

### Anotační nástroj (Satty)

Pro estetické zobrazení anotačního editoru Satty v plovoucím okně doporučujeme přidat do pravidel oken Hyprlandu (`~/.config/hypr/hyprland.conf` nebo Lua modulů):

```ini
windowrulev2 = float, class:^(com\.gabm\.satty|satty)$
windowrulev2 = center, class:^(com\.gabm\.satty|satty)$
windowrulev2 = pin, class:^(com\.gabm\.satty|satty)$
windowrulev2 = dimaround, class:^(com\.gabm\.satty|satty)$
```

Kompletní Catppuccin konfigurace pro Satty v0.22+ je součástí repozitáře v `config/satty/config.toml` a automaticky se instaluje do `~/.config/satty/config.toml`.

