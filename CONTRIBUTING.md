# Contributing to HyprSmartShot

Thank you for your interest in contributing to **HyprSmartShot**! We welcome bug reports, feature requests, translation contributions, and code improvements.

---

## Development Setup

1. **Clone the repository**:
   ```bash
   git clone git@github.com:Richieee-0006/hyprsmartshot.git
   cd hyprsmartshot
   ```

2. **Prepare the Python virtual environment**:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install --upgrade pip
   pip install opencv-python-headless numpy
   ```

3. **Run the test suite**:
   ```bash
   # Test Computer Vision UI detector:
   python3 vision/test_detect_ui.py

   # Test Dynamic Localization (i18n):
   python3 tests/test_i18n.py
   ```

---

## Adding a New Language (Localization)

HyprSmartShot provides a dedicated helper script to generate and validate translation templates:

1. **Generate a translation template**:
   ```bash
   # Pre-populate with English reference text:
   scripts/localization_template.py <lang_code>

   # Or generate with blank values:
   scripts/localization_template.py <lang_code> --empty
   ```
   *(e.g., `scripts/localization_template.py de`, `scripts/localization_template.py ja`)*

2. **Translate the values**:
   Edit `localization/<lang_code>.json`. Keep all keys and format placeholders (such as `{path}`) intact.

3. **Verify your translation**:
   ```bash
   # Validate key parity and syntax:
   scripts/localization_template.py --check <lang_code>

   # Or run the full test suite:
   python3 -m unittest discover -s tests
   ```

4. **Submit a Pull Request**!

---

## Git & Commit Guidelines

- **Branching**: Create a dedicated feature branch for your changes:
  ```bash
  git checkout -b feature/your-feature-name
  # or
  git checkout -b fix/issue-description
  ```

- **Commit Messages**: Keep commit messages concise, clear, and conventional:
  - `feat: add german translation`
  - `fix: prevent magnifier clipping on screen edge`
  - `docs: update installation instructions`

---

## Pull Request Process

1. Ensure all tests pass (`vision/test_detect_ui.py` and `tests/test_i18n.py`).
2. Fill out the PR template checklist completely.
3. Keep pull requests focused on a single topic or feature.
