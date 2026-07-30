# Training real `help_en`/`socorro_pt` wake-word models

`server/listener/config.yaml`'s `keyword_spotting` list has two provisional
entries pointing at model files that don't exist yet:

```yaml
- event_name: help_en
  model_path: /app/models/openwakeword/help_en.tflite   # [PROVISIONAL] not trained yet
- event_name: socorro_pt
  model_path: /app/models/openwakeword/socorro_pt.tflite   # [PROVISIONAL] not trained yet
```

The listener logs a warning and skips them at startup (`main.py`), and
`mqtt_out.py` withholds their HA discovery entity, so nothing breaks or
fakes coverage in the meantime. This doc is the runbook for whoever picks up
actually training them.

## Why this wasn't done automatically

openWakeWord's own README is explicit: *"Currently, openWakeWord only
supports English"* — the pretrained TTS models it uses for synthetic
training data are English-only. Training real models needs real effort:

- **`help_en` (English)** — the well-supported path. openWakeWord's own
  training pipeline (`piper-sample-generator` + the
  `automatic_model_training.ipynb` notebook) is built for exactly this.
- **`socorro_pt` (Portuguese)** — unproven/DIY. Piper (the TTS engine used
  for synthetic sample generation) does have Portuguese voices — `pt_BR`
  includes a voice named "Faber" — but openWakeWord's own training/quality
  validation pipeline has never been tested against a non-English target
  phrase. This is genuinely exploratory, not a supported path.
- The official training notebook has been reported as bit-rotted against
  current Colab runtimes as of 2026 (see `dscripka/openWakeWord` issue #296)
  — budget time for patching it, not just running it.
- GPU strongly recommended, not required. Order of magnitude from
  community reports: ~10 min for clip generation on a free Colab T4, and a
  full training run anywhere from ~75 min (Colab Pro / L4) to several hours
  on weaker hardware.

## Steps (English: `help_en`)

1. Set up [`piper-sample-generator`](https://github.com/dscripka/piper-sample-generator)
   (the fork linked from openWakeWord's README) or the actively-maintained
   upstream [`rhasspy/piper-sample-generator`](https://github.com/rhasspy/piper-sample-generator).
2. Run the detailed notebook,
   [`automatic_model_training.ipynb`](https://github.com/dscripka/openWakeWord/blob/main/notebooks/automatic_model_training.ipynb)
   (Linux-only — Piper's TTS library requirement), or the
   [simple Colab](https://colab.research.google.com/drive/1q1oe2zOyZp7UsB3jJiQ1IFn8z5YfjwEb?usp=sharing)
   for a faster, lower-quality first pass.
3. Config keys that matter: `target_phrase: "help"` (or a natural phrase
   like "help me"), `n_samples` (thousands recommended — quality scales
   with dataset size), `background_paths` (negative/noise data — the
   notebook downloads AudioSet/FMA/room-impulse-response sets for this).
4. Output is a `.tflite` model. Drop it at
   `server/models/openwakeword/help_en.tflite` (or the equivalent path
   inside `addons/heyra/models/` for the Add-on build) — no
   code or config changes needed, `main.py` picks it up automatically once
   the file exists.

## Steps (Portuguese: `socorro_pt`) — exploratory

1. Same pipeline as above, but pass a Portuguese Piper voice to the
   upstream `rhasspy/piper-sample-generator`'s v3+ "Piper voices" mode
   (`--model voices/pt_BR-faber-medium.onnx`, from
   [`rhasspy/piper-voices`](https://huggingface.co/rhasspy/piper-voices/tree/main/pt))
   instead of the English-only multi-speaker generator.
2. Expect to iterate — this combination isn't validated by openWakeWord's
   own docs/tests. Evaluate false-accept/false-reject rates against real
   speech recordings (yours, your brother's) before trusting it, more so
   than for `help_en`.
3. Same drop-in path: `server/models/openwakeword/socorro_pt.tflite`.

## Verifying it worked

- `pytest server/listener/tests/` — `test_keyword_spotting_list_parses_provisional_entries`
  confirms the config still parses; once a model file exists, restart the
  listener and check its startup log for the absence of the "not found,
  skipping" warning for that event.
- The HA entity (`binary_sensor.heyra_<room>_help_en` /
  `_socorro_pt`) should appear after restart — `mqtt_out.py` only
  publishes discovery once the model file is present.
