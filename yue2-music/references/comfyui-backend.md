# ComfyUI backend

Use this backend when YuE2 runs as ComfyUI's native nodes instead of the `yue2-infer` package.
`scripts/comfy_yue2.py` replaces `run_yue2.py` and `transcribe.py`. It submits
API-format workflows to a running ComfyUI server and writes run directories that
`listen.py`, `abc_tools.py` and the instrumental helpers read unchanged. It needs
only the Python standard library; any Python 3.10+ works.

## Prerequisites

- ComfyUI running (default `http://127.0.0.1:8188`; override with `--server` or
  `COMFYUI_URL`). If it is not reachable, ask the user to start it. Do not start or
  restart it yourself.
- A YuE2 checkpoint visible to `CheckpointLoaderSimple` (auto-detected: the first name
  containing `yue2`; override with `--checkpoint`). Covers also need a SheetSage2 file
  visible to `AudioEncoderLoader` (auto-detected; `--audio-encoder`).
- Skip the venv, `pip install`, Hugging Face download and `setup_runtime.py` steps in
  [models-and-setup.md](models-and-setup.md). They apply only to `yue2-infer`.

## Command mapping

| Official helper | ComfyUI bridge |
| --- | --- |
| `run_yue2.py plan --request R --output O` | `comfy_yue2.py plan --request R --output O` |
| `run_yue2.py generate --request R [--cot M] [--abc-file A] --output O` | `comfy_yue2.py generate ...` (same flags) |
| `run_yue2.py all-modes --request R --output O` | `comfy_yue2.py all-modes ...` |
| `transcribe.py audio --task melody-full --output O` | `comfy_yue2.py transcribe audio --mode melody --output O` |
| `transcribe.py audio` (default full tasks) | `comfy_yue2.py transcribe audio --mode full --output O` |
| `run_yue2.py decode --source S` | Not available: ComfyUI does not save latents. Regenerate with the same seed instead. |
| `instrumental/scripts/instrumental.py run/cover` | Run its steps separately (below). |

The request JSON is the same (`id`, `style`/`tags`, `lyrics`, `cot`, `seed`, `abc` or
`abc_path`, `cfg_scale`). A missing seed is drawn at random and recorded in
`request.json`. `--seed` overrides the request. `generate` without ABC in `full` or
`melody` mode plans and renders in one ComfyUI run and saves the plan as `score.abc`.
To change the plan between those steps, run `plan` first, edit, then `generate --abc-file`.

The same seed drives the planner, the music token sampler and the KSampler, as in the
ComfyUI templates. ComfyUI caches identical node inputs, so rerunning an unchanged
request returns the same plan and audio almost instantly.

## Run directory

`input.json` (request as given), `request.json` (request with the ABC actually used),
`score.abc`, `audio.flac` (48 kHz), `abc_check.json`, `config.json` (checkpoint,
sampling, ComfyUI version, GPU), `result.json` (status, durations, truncation, SHA-256
of artifacts), `workflow_api.json` (the exact graph; drop it onto the ComfyUI canvas to
inspect or rerun it), `invocation.json` and `run.json`. A failure writes `failure.json`.

`result.json` status is `needs_review` when the ABC structure check fails or the song
reached `--max-duration` (360 s default). The node may also lower the cap for long
prompts, which the bridge cannot see. Compare `generated_seconds` with the score's
`nominal_duration_seconds` in `abc_check.json` before calling a song complete.

## Instrumental workflow through ComfyUI

`instrumental.py prepare`, `instrumentalize.py` and `listen.py` do not use the GPU and
run as-is. Paths are relative to this skill folder.

```bash
# 1. YuE2 writes the score (text request), or transcribe a reference for a cover.
python scripts/comfy_yue2.py plan --request work/request.json --output work/song/planning
# 2. Move every Vocal note to Ins (add --drop-chords for a cover without source harmony).
python instrumental/scripts/instrumentalize.py work/song/planning/score.abc --output work/song/conversion
# 3. Build the exact instrumental request (style suffixes, section-tag lyrics, cot).
python instrumental/scripts/instrumental.py prepare --abc work/song/conversion/score.abc \
  --source work/song/planning/score.abc --style "warm solo piano, gentle" --output work/song/prepared
# 4. Render and listen.
python scripts/comfy_yue2.py generate --request work/song/prepared/request.json --output work/song/generation
python scripts/listen.py work/song/generation --output work/song/listen
```

The instrumental planner request is the user's style with empty lyrics or section tags,
`cot` set to `full` or `melody` (`--plan-mode`).

## Differences from the official runtime

- Sampling defaults are ComfyUI's node defaults (planner: temperature 0.7, top-p 0.9,
  top-k 30; music: temperature 1.0, top-p 0.95, top-k 100, repetition penalty 1.2;
  32 `dpm_2`/`sgm_uniform` steps). They are recorded in `config.json`. Do not lower
  them silently.
- No semantic tokens, latents, prefix check or release validation are saved.
  `listen.py` shows the decoder as ComfyUI's VAE from the checkpoint and validation as
  not applicable. Reproduce a song by rerunning `workflow_api.json` or the same request.
- There is no `YuE2-Vae-legacy` benchmark decoder. Do not claim the benchmark protocol.
- SheetSage2 in ComfyUI offers `melody` (both melodies, no chords) and `full`. There
  is no vocal-only melody task, no warnings or diagnostics output, and no MIDI/LAB
  exports. Inspect `score.abc` with `abc_tools.py inspect` instead.
- One ComfyUI queue serves everything. Runs are sequential; a running image or video
  job delays the music job.
