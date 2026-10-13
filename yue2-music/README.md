# yue2-music skill

This skill lets an AI agent make music with the YuE2 model. You tell the agent what you
want in usual words. The agent does the work and gives you the audio.

This package is a changed version of the upstream yue2-music skill. It adds support for
ComfyUI. Refer to [Changes from the upstream skill](#changes-from-the-upstream-skill).

## 1. What the skill can do

The agent can do these tasks:

- Make a song from a style description and lyrics.
- Make an instrumental piece without vocals.
- Make a cover of a recording. The agent keeps the melody and changes the style, the lyrics, or both.
- Change a score. For example, the agent can change the harmony, the tempo, or the instruments.
- Make a local web page. Use this page to listen to the results and compare them.

YuE2 does the work in two steps. First, it writes a score in ABC notation. ABC is a text
format for music. Then, YuE2 makes the audio from the score. The agent can change the
score between the two steps.

## 2. What you must have

You must have these items:

- An agent that can use skills and a terminal, for example Claude Code.
- Python 3.10 or a later version.
- One of the two backends below.

### 2.1 Backend A: ComfyUI

Use this backend if you already use ComfyUI. This package was tested with ComfyUI 0.39.2
on an NVIDIA GPU with 16 GB of memory.

You must have:

- A ComfyUI release that has the native YuE2 nodes. Examples of these nodes are
  `YuE2GenerateABC`, `YuE2GenerateMusic`, and `SheetSage2AudioToABC`.
- A YuE2 checkpoint in `ComfyUI/models/checkpoints`. The file name must contain `yue2`.
- For covers only: the SheetSage2 file in `ComfyUI/models/audio_encoders`. The file name
  must contain `sheetsage`.

Get the model files from [Comfy-Org/YuE2 on Hugging Face](https://huggingface.co/Comfy-Org/YuE2).
The ComfyUI templates "YuE2: Text to Music" and "YuE2: Music Cover" also show the links.

You do not have to install Python packages for this backend. The bridge script uses only
the Python standard library.

### 2.2 Backend B: the official yue2-infer runtime

This backend needs Linux and an NVIDIA GPU with 24 GB of memory and BF16 support. The
agent installs it. Refer to [references/models-and-setup.md](references/models-and-setup.md).

## 3. Install the skill

The skill is in the `yue2-music` folder of the repository
[p-and-c-podcast/skills](https://github.com/p-and-c-podcast/skills).
Use one of the three procedures below. Procedure 3.1 has the fewest steps.

Claude Code finds skills in these two locations:

| Location | Result |
| --- | --- |
| `~/.claude/skills/yue2-music` | The skill is available in all your projects. |
| `<your project>/.claude/skills/yue2-music` | The skill is available in that project only. |

NOTE: A skill gives instructions to your agent. Read the skill files before you install them.

### 3.1 Install with npx

You must have Node.js. The `npx` command is part of Node.js.

1. Open a terminal.
2. To install the skill for all your projects, use this command:

   ```bash
   npx skills add p-and-c-podcast/skills --skill yue2-music -a claude-code -g
   ```

3. To install the skill for one project only, go to the project folder. Then use the same command without `-g`.
4. Do the steps in [3.4](#34-make-sure-that-the-installation-is-correct).

For a different agent, change the value after `-a`. If you do not use `-a`, the CLI asks
which agents to use. To see the skills in the repository without an installation, use
`npx skills add p-and-c-podcast/skills --list`. For more data, refer to the
[skills CLI](https://github.com/vercel-labs/skills).

### 3.2 Install with git

You must have git.

1. Open a terminal.
2. Use these commands. They install the skill for all your projects.

   On Linux and macOS:

   ```bash
   git clone --depth 1 https://github.com/p-and-c-podcast/skills.git
   mkdir -p ~/.claude/skills
   cp -r skills/yue2-music ~/.claude/skills/
   ```

   On Windows (PowerShell):

   ```powershell
   git clone --depth 1 https://github.com/p-and-c-podcast/skills.git
   New-Item -ItemType Directory -Force "$HOME\.claude\skills" | Out-Null
   Copy-Item -Recurse skills\yue2-music "$HOME\.claude\skills\"
   ```

3. You can remove the `skills` folder that git made. The installed copy does not use it.
4. Do the steps in [3.4](#34-make-sure-that-the-installation-is-correct).

### 3.3 Install from the zip file

Use this procedure if you do not have Node.js or git.

1. Go to the [latest release](https://github.com/p-and-c-podcast/skills/releases/latest) of the repository.
2. Download the file `yue2-music-skill.zip`.
3. Unzip the file. You get a folder with the name `yue2-music`.
4. Put the `yue2-music` folder in one of the two locations in the table above.
5. Do the steps in [3.4](#34-make-sure-that-the-installation-is-correct).

Each release has its own zip file. The zip file of the latest release contains the latest version of the skill.

### 3.4 Make sure that the installation is correct

1. Make sure that the file `SKILL.md` is directly in the `yue2-music` folder. Do not put the folder one level deeper.
2. Start a new agent session.
3. Make sure that the agent shows `yue2-music` in its list of skills.

## 4. Use the skill

1. If you use Backend A, start ComfyUI. The skill does not start ComfyUI for you.
2. Tell the agent what music you want.
3. Answer the questions of the agent, if there are questions.
4. Listen to the result.

In Claude Code, you can also start the skill with the command `/yue2-music`.

These are examples of requests:

- "Make a warm piano pop song with these lyrics: ..."
- "Make a calm instrumental piece for solo piano."
- "Make a jazz cover of song.wav. Keep the melody."
- "Change the chords in the chorus. Do not change the melody."
- "Make the song in all three modes and compare them."

The agent gives you these items:

- The audio file (FLAC, 48 kHz).
- The full style prompt and the lyrics that YuE2 used.
- The score (`score.abc`), if the mode uses a score.
- The results of the score checks.
- A local web page (`index.html`) to listen to the results and compare them.

NOTE: A score check examines the score only. It does not examine the audio. Listen to
the audio to make sure that the result is correct.

## 5. The three generation modes

| Mode | What YuE2 does |
| --- | --- |
| `full` | YuE2 writes a score with melody and chords. Then it makes the audio from the score. |
| `melody` | YuE2 uses a melody score without chords. It makes its own accompaniment. Use this mode for covers. |
| `off` | YuE2 makes the audio directly from the text. There is no score that you can change. |

## 6. Use the scripts yourself (optional)

You can use the scripts without the agent. Go to the `yue2-music` folder before you use
these commands. The commands are for Backend A.

Make a song:

```bash
python scripts/comfy_yue2.py generate --request assets/prompt.json --output outputs/song
```

Make only the score:

```bash
python scripts/comfy_yue2.py plan --request assets/prompt.json --output outputs/plan
```

Make a song from a score that you changed:

```bash
python scripts/comfy_yue2.py generate --request assets/prompt.json --cot full --abc-file edits/new.abc --output outputs/new
```

Make a score from a recording:

```bash
python scripts/comfy_yue2.py transcribe song.wav --mode melody --output outputs/transcription
```

Compare two results on a web page:

```bash
python scripts/listen.py outputs/song outputs/new --output outputs/comparison
```

The request file is a JSON file. Refer to [assets/prompt.json](assets/prompt.json) for an
example. It has these fields:

| Field | Content |
| --- | --- |
| `id` | A short name for the song. |
| `style` | The genre, the instruments, the voice, the language, and the tempo. |
| `lyrics` | The section tags (for example `[Verse]`) and the words. |
| `cot` | The mode: `full`, `melody`, or `off`. |
| `seed` | A number. The same seed and the same request give the same result. |

Each output folder must be new. The scripts do not write over an old folder.

If ComfyUI is not at `http://127.0.0.1:8188`, use the `--server` option. You can also set
the `COMFYUI_URL` environment variable.

The scripts give these exit codes:

| Code | Meaning |
| --- | --- |
| 0 | The run is complete. |
| 1 | The run is complete, but you must examine the result. For example, the song can be cut off at the end. |
| 2 | An error occurred. Read the error message or the `failure.json` file. |

For all commands and all limits of Backend A, refer to
[references/comfyui-backend.md](references/comfyui-backend.md).

## 7. Limits of Backend A

- Backend A cannot decode old latents again. To make the same song again, use the same request and the same seed.
- Backend A does not have the legacy benchmark decoder.
- SheetSage2 in ComfyUI cannot select the vocal melody only. It also does not give MIDI files.
- Backend A uses the default sampling values of the ComfyUI nodes. The values are in the `config.json` file of each run.
- ComfyUI does one job at a time. If ComfyUI does a different job, the music job waits.

## 8. Licenses

This package contains files with three different licenses.

- This package as a whole uses the GNU General Public License version 3 (GPLv3). Refer to [COPYING](COPYING).
- The files that this package adds, and the changes to the upstream files, use GPLv3. The section [Changes from the upstream skill](#changes-from-the-upstream-skill) lists these files and changes.
- The upstream skill instructions, helpers, and templates use the Apache License 2.0. Copyright (c) 2026 the YuE2 authors. Refer to [LICENSE](LICENSE). These files keep the Apache License 2.0 terms.
- The helpers in the `instrumental` folder use the MIT License. Refer to [instrumental/LICENSE](instrumental/LICENSE).
- The model weights are not in this package. Their model cards give the CC BY-NC 4.0 license. This license permits noncommercial use only.

## Changes from the upstream skill

The upstream skill is at
<https://github.com/multimodal-art-projection/YuE/tree/main/skills/yue2-music>.
This package starts from commit `1647252` (2026-10-06).

These are the changes:

- Added `scripts/comfy_yue2.py`. This script connects the skill to a ComfyUI server.
- Added `references/comfyui-backend.md`. This file tells the agent how to use the ComfyUI backend.
- Added this `README.md` file.
- Added `.gitattributes`. This file keeps the same line endings on all operating systems.
- Added `COPYING`. This file contains the GPLv3 text.
- Changed `SKILL.md`. The description now includes ComfyUI. A new section tells the agent how to select the backend. Notes now tell the agent which steps to skip with ComfyUI. The line that recommends a different agent is removed.
- Changed `instrumental/SKILL.md`. A note now gives the ComfyUI steps. The line that recommends a different agent is removed.
- Changed `instrumental/bundle-manifest.json`. The hash of `instrumental/SKILL.md` is updated.
