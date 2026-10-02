# Reproducible demos and screenshots

Use synthetic fixture mode for public demos. It reads no live host files and executes
no commands, even if an operation is confirmed. Never record private live host evidence.

```sh
dct --fixture tests/fixtures/healthy_rhel.json
```

Recommended terminal size: 100 × 32, minimum practical size 80 × 24. Show Home, Enter
Host Identity, Esc, / then type `Drives` and Enter, Esc, / then `Mount` and Enter. Select
`/dev/sdb1` and inspect the confirmation; Cancel is initially selected. `?` opens help,
Esc closes it, `h` returns Home, `q` exits. Fixture writes default to unavailable and
cannot affect the host. An incident export is an ordinary local file write.

For a screenshot, use Textual's `app.save_screenshot()` after collection inside
`app.run_test(size=(100, 32))`; see `scripts/screenshots.py`. Generated SVGs are under
`docs/screenshots/`. The script uses synthetic evidence exclusively.

For a terminal recording, optionally install asciinema through your platform's supported
channel, then run:

```sh
asciinema rec dct-demo.cast --command 'dct --fixture tests/fixtures/healthy_rhel.json'
```

The recording is optional and not a runtime dependency. Review output before publication.
Create an independent sample bundle with:

```sh
dct --fixture tests/fixtures/healthy_rhel.json --export /tmp/dct-sample
```

Services/GPU fixtures are reserved for future collectors; their presence does not claim
those menu features are implemented.
