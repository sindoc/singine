# Farsi Font Proofing In Emacs

This gives you a saved, replayable workflow for Persian and Arabic font experiments under the `singine` repo.

The generated artifacts go to:

`docs/target/farsi-proof/`

That directory is already ignored by git, so you keep the PDFs, TeX source, and manifests without polluting the repo history.

If you want to write elsewhere, set:

```elisp
(setq singine-fa-proof-artifacts-dir "/tmp/farsi-proof")
```

## What the Elisp does

The helper at [`elisp/singine-fa-proof.el`](/Users/skh/ws/git/github/sindoc/singine/elisp/singine-fa-proof.el) does four things:

1. Resolves each requested family to an exact font file with `fc-match`.
2. Writes a standalone `.tex` specimen file.
3. Compiles the specimen to PDF with `xelatex`.
4. Optionally renders a HarfBuzz preview with `hb-view`.

This matters because TeX font name lookup is often unreliable on macOS when you only give it a family name. Resolving the exact file first makes the experiment stable and reproducible.

## Load It In Emacs

```elisp
(load-file "~/ws/git/github/sindoc/singine/elisp/singine-fa-proof.el")
```

Useful starting variables:

```elisp
(setq singine-fa-proof-default-fonts
      '("Amiri"
        "Geeza Pro"
        "Al Bayan"
        "Damascus"
        "Baghdad"
        "Tahoma"))

(setq singine-fa-proof-default-title "Eid Prayer Font Proof")
```

## Main Commands

Build a default proof sheet from the built-in sample text:

```elisp
(singine-fa-proof-build-sample)
```

Build from the current buffer, or the active region if one is selected:

```elisp
(call-interactively #'singine-fa-proof-buffer-to-pdf)
```

See where the default families resolve on your machine:

```elisp
(singine-fa-proof-list-font-candidates)
```

Generate a HarfBuzz-only preview PDF for one family:

```elisp
(singine-fa-proof-preview-with-harfbuzz
 "Amiri"
 "اَللّهُمَّ اَهْلَ الْكِبْرِيَاءِ وَالْعَظَمَةِ")
```

For now, this is also the recommended path for local variable-font files such as the current Noto Arabic variable fonts. The TeX helper uses exact font files for reproducibility, and XeLaTeX is much less happy with filenames like `NotoNaskhArabic[wght].ttf` than `hb-view` is.

## Typical Workflow

1. Put your prayer text, poem, or test paragraph in a buffer.
2. Select the exact passage you want, if you do not want the whole buffer.
3. Run `M-x singine-fa-proof-buffer-to-pdf`.
4. Enter a comma-separated list of font families.
5. Open the generated PDF in `docs/target/farsi-proof/`.
6. Keep the `.tex` and `.json` files as your saved experiment record.

The `.json` file records the requested family, resolved family, style, and exact font path that was used.

## Suggested Farsi Stress Text

Use text that exercises:

- Persian `ی` and `ک`
- Arabic diacritics
- ZWNJ / نیم‌فاصله
- punctuation and brackets
- Persian and Latin digits

Example:

```text
اَللّهُمَّ اَهْلَ الْكِبْرِيَاءِ وَالْعَظَمَةِ وَأَهْلَ الْجُودِ وَالْجَبَرُوتِ.

می‌خواهم شکل‌گیری حروف، جای‌گیری اعراب، نیم‌فاصله، و خوانایی متن فارسی را دقیق ببینم.

فارسی امروز: کتاب‌ها، می‌روم، نمی‌خواهم، اندازه‌گیری، برنامه‌ریزی، پژوهش‌محور.

اعداد و نشانه‌ها: ۰۱۲۳۴۵۶۷۸۹ | 123456789 | () [] {} «»
```

## Saving The Interaction

If you want the exact experiment to be restorable later, keep these files together:

- the source text buffer or note
- the generated `.tex`
- the generated `.pdf`
- the generated `.json`

That is enough to reconstruct the comparison later without depending on chat history.

## Optional: Drive It From `emacsclient`

If you already run an Emacs daemon:

```bash
emacsclient --eval \
  '(progn
     (load-file "~/ws/git/github/sindoc/singine/elisp/singine-fa-proof.el")
     (prin1 (singine-fa-proof-build-sample)))'
```

That keeps the workflow compatible with the existing Emacs-oriented surfaces already present in `singine`.
