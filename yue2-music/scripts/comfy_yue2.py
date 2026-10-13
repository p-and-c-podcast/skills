#!/usr/bin/env python3
"""Plan, generate, or transcribe with YuE2 through a running ComfyUI server.

Companion to run_yue2.py and transcribe.py for hosts where YuE2 runs as ComfyUI's
native nodes (YuE2GenerateABC, YuE2GenerateMusic, SheetSage2AudioToABC) instead of
the yue2-infer package. Standard library only. Each run directory uses the layout
listen.py reads: request.json, config.json, result.json, score.abc, audio.flac.

Usage:
  python scripts/comfy_yue2.py plan --request assets/prompt.json --output outputs/plan
  python scripts/comfy_yue2.py generate --request assets/prompt.json --output outputs/pop
  python scripts/comfy_yue2.py generate --request edits/jazz.json --cot full \
      --abc-file edits/jazz.abc --output outputs/jazz
  python scripts/comfy_yue2.py all-modes --request assets/prompt.json --output outputs/modes
  python scripts/comfy_yue2.py transcribe reference.wav --mode melody --output outputs/transcription

Exit 0: complete; 1: finished but needs review (truncation or ABC check); 2: error.

Added to the upstream yue2-music skill; licensed under Apache 2.0 like the rest of this skill.
"""

import argparse
import hashlib
import json
import mimetypes
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from abc_tools import parse_abc, report  # noqa: E402
from common import fresh_directory, read_json, sha256, write_json  # noqa: E402

FRAMES_PER_SECOND = 25  # YuE2 latent rate in ComfyUI: 48 kHz / 1920.
SEED_LIMIT = 2 ** 63
# Defaults copied from ComfyUI's YuE2 nodes and its YuE2 workflow templates.
ABC_SAMPLING = dict(max_abc_tokens=8192, temperature=0.7, top_p=0.9, top_k=30,
                    repetition_penalty=1.005, penalty_window=100)
MUSIC_SAMPLING = dict(temperature=1.0, top_p=0.95, top_k=100, repetition_penalty=1.2)
DIFFUSION = dict(steps=32, cfg=1.0, sampler_name="dpm_2", scheduler="sgm_uniform", denoise=1.0)


class ComfyError(RuntimeError):
    pass


class Comfy:
    def __init__(self, server, timeout):
        self.server = server.rstrip("/")
        self.timeout = timeout
        self.client_id = uuid.uuid4().hex

    def _open(self, path, data=None, headers=None):
        request = urllib.request.Request(self.server + path, data=data, headers=headers or {})
        try:
            with urllib.request.urlopen(request, timeout=60) as response:
                return response.read()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "replace")
            raise ComfyError(f"ComfyUI {path} returned HTTP {exc.code}: {body[:4000]}") from None
        except urllib.error.URLError as exc:
            raise ComfyError(f"Cannot reach ComfyUI at {self.server}: {exc.reason}") from None

    def get(self, path):
        return json.loads(self._open(path))

    def post(self, path, value):
        return json.loads(self._open(path, json.dumps(value).encode("utf-8"),
                                     {"Content-Type": "application/json"}) or b"{}")

    def options(self, node, field):
        info = self.get(f"/object_info/{node}")
        if node not in info:
            raise ComfyError(f"ComfyUI has no {node} node; update ComfyUI to a release with YuE2 support")
        spec = info[node]["input"]["required"][field]
        return spec[1].get("options", []) if spec[0] == "COMBO" else spec[0]

    def upload(self, path):
        boundary = uuid.uuid4().hex
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        parts = []
        for name, value in (("type", "input"), ("subfolder", "yue2_bridge")):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode())
        parts.append((f'--{boundary}\r\nContent-Disposition: form-data; name="image"; '
                      f'filename="{path.name}"\r\nContent-Type: {content_type}\r\n\r\n').encode())
        parts.append(path.read_bytes())
        parts.append(f"\r\n--{boundary}--\r\n".encode())
        reply = json.loads(self._open("/upload/image", b"".join(parts),
                                      {"Content-Type": f"multipart/form-data; boundary={boundary}"}))
        return f"{reply['subfolder']}/{reply['name']}" if reply.get("subfolder") else reply["name"]

    def run(self, graph):
        reply = self.post("/prompt", {"prompt": graph, "client_id": self.client_id})
        if reply.get("node_errors"):
            raise ComfyError(f"ComfyUI rejected the workflow: {json.dumps(reply['node_errors'])[:4000]}")
        prompt_id = reply["prompt_id"]
        start = time.monotonic()
        last_note = start
        try:
            while True:
                entry = self.get(f"/history/{prompt_id}").get(prompt_id)
                if entry and entry.get("status", {}).get("completed") is not None:
                    status = entry["status"]
                    if status.get("status_str") == "error" or not status.get("completed"):
                        errors = [m[1] for m in status.get("messages", []) if m[0] == "execution_error"]
                        detail = errors[0] if errors else status
                        if isinstance(detail, dict):
                            detail = f"{detail.get('node_type')}: {detail.get('exception_message', '').strip()}"
                        raise ComfyError(f"ComfyUI execution failed: {detail}")
                    return prompt_id, entry["outputs"], time.monotonic() - start
                now = time.monotonic()
                if now - start > self.timeout:
                    raise ComfyError(f"Timed out after {self.timeout:.0f} s waiting for prompt {prompt_id}")
                if now - last_note >= 30:
                    print(f"  ... ComfyUI working, {now - start:.0f} s elapsed", file=sys.stderr, flush=True)
                    last_note = now
                time.sleep(2)
        except KeyboardInterrupt:
            self.cancel(prompt_id)
            raise

    def cancel(self, prompt_id):
        try:
            self.post("/queue", {"delete": [prompt_id]})
            queue = self.get("/queue")
            if any(item[1] == prompt_id for item in queue.get("queue_running", [])):
                self.post("/interrupt", {"prompt_id": prompt_id})
            print(f"Cancelled ComfyUI prompt {prompt_id}", file=sys.stderr)
        except ComfyError:
            pass

    def download(self, item, destination):
        query = urllib.parse.urlencode({k: item.get(k, "") for k in ("filename", "subfolder", "type")})
        destination.write_bytes(self._open(f"/view?{query}"))


def pick(options, flag, wanted, words):
    if wanted:
        if wanted not in options:
            raise ValueError(f"{flag} {wanted!r} is not available in ComfyUI; options: {options}")
        return wanted
    found = sorted(o for o in options if all(w in o.lower() for w in words))
    if not found:
        raise ValueError(f"No {' '.join(words)} file in ComfyUI; install it or pass {flag}. Options: {options}")
    return found[0]


def flac_info(path):
    """Return (sample_rate, seconds) from a FLAC STREAMINFO block."""
    with path.open("rb") as stream:
        head = stream.read(42)
    if not head.startswith(b"fLaC") or head[4] & 0x7F != 0:
        raise ValueError(f"{path.name} is not a FLAC file with STREAMINFO")
    info = head[8:42]
    rate = (info[10] << 12) | (info[11] << 4) | (info[12] >> 4)
    samples = ((info[13] & 0x0F) << 32) | int.from_bytes(info[14:18], "big")
    return rate, (samples / rate if rate else None)


def text_output(outputs, node):
    values = outputs.get(node, {}).get("text")
    if not values:
        raise ComfyError(f"ComfyUI returned no text from node {node}")
    return values


def score_check(text, mode):
    if text is None:
        return {"status": "not_applicable"}
    try:
        score = parse_abc(text)
        if mode == "melody" and any(v.chords for v in score.voices.values()):
            raise ValueError("Melody-mode score contains chord symbols")
        return {"status": "passed", "scope": "native ABC structure only", "score": report(score)}
    except ValueError as exc:
        return {"status": "failed", "error": str(exc)}


def request_data(args):
    data = read_json(args.request)
    if not isinstance(data, dict):
        raise ValueError("Request must be a JSON object")
    allowed = {"style", "tags", "lyrics", "cot", "seed", "abc", "abc_path", "cfg_scale", "id"}
    if set(data) - allowed:
        raise ValueError(f"Unsupported request fields: {sorted(set(data) - allowed)}")
    if "tags" in data:
        tags = data.pop("tags")
        if "style" in data and data["style"] != tags:
            raise ValueError("style and tags disagree")
        data["style"] = tags
    if not isinstance(data.get("style"), str) or not isinstance(data.get("lyrics", ""), str):
        raise ValueError("style must be a string; lyrics must be a string")
    data.setdefault("lyrics", "")
    sources = sum(x is not None for x in (data.get("abc"), data.get("abc_path"), args.abc_file))
    if sources > 1:
        raise ValueError("Use only one of abc, abc_path or --abc-file")
    abc_path = data.pop("abc_path", None)
    if abc_path is not None:
        data["abc"] = (Path(args.request).parent / abc_path).read_bytes().decode("utf-8")
    if args.abc_file:
        data["abc"] = Path(args.abc_file).read_bytes().decode("utf-8")
    if data.get("abc") is not None and not data["abc"].strip():
        raise ValueError("ABC input is empty; omit it to plan a fresh score, or use --cot off")
    if args.cot:
        data["cot"] = args.cot
    data.setdefault("cot", "full")
    if data["cot"] not in ("full", "melody", "off"):
        raise ValueError("cot must be full, melody or off")
    data.setdefault("id", "song")
    if args.seed is not None:
        data["seed"] = args.seed
    if data.get("seed") is None:
        data["seed"] = random.randrange(SEED_LIMIT)
    if type(data["seed"]) is not int or not 0 <= data["seed"] < SEED_LIMIT:
        raise ValueError("seed must be an integer from 0 to 2**63-1")
    if args.action == "all-modes" and data.get("abc") is not None:
        raise ValueError("all-modes requires text-only input, since off cannot accept ABC")
    if args.action == "plan" and data["cot"] == "off":
        raise ValueError("off has no symbolic plan; use generate")
    if data.get("abc") is not None:
        if data["cot"] == "off":
            raise ValueError("off cannot accept ABC")
        if args.action == "plan":
            raise ValueError("plan writes a new score; pass the ABC to generate instead")
        score = parse_abc(data["abc"])
        if data["cot"] == "melody" and any(v.chords for v in score.voices.values()):
            raise ValueError("melody input still contains chords; use abc_tools.py strip-chords")
    return data


def planner_node(request, ckpt):
    return {"class_type": "YuE2GenerateABC", "inputs": dict(
        clip=[ckpt, 1], style=request["style"], lyrics=request["lyrics"], seed=request["seed"],
        mode=request["cot"], **ABC_SAMPLING)}


def plan_graph(request, checkpoint):
    return {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}},
            "2": planner_node(request, "1"),
            "3": {"class_type": "PreviewAny", "inputs": {"source": ["2", 0]}}}


def song_graph(request, checkpoint, max_duration, steps, prefix):
    graph = {"1": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": checkpoint}}}
    if request["cot"] == "off":
        abc = ""
    elif request.get("abc") is not None:
        abc = request["abc"]
    else:
        graph["2"] = planner_node(request, "1")
        graph["3"] = {"class_type": "PreviewAny", "inputs": {"source": ["2", 0]}}
        abc = ["2", 0]
    music = dict(clip=["1", 1], style=request["style"], lyrics=request["lyrics"], abc=abc,
                 seed=request["seed"], mode="full" if request["cot"] == "off" else request["cot"],
                 max_duration=max_duration, **MUSIC_SAMPLING)
    if request.get("cfg_scale") is not None:
        music["cfg_scale"] = request["cfg_scale"]
    graph.update({
        "4": {"class_type": "YuE2GenerateMusic", "inputs": music},
        "5": {"class_type": "ConditioningZeroOut", "inputs": {"conditioning": ["4", 0]}},
        "6": {"class_type": "EmptyYuE2LatentAudio", "inputs": {"seconds": ["4", 1], "batch_size": 1}},
        "7": {"class_type": "KSampler", "inputs": dict(
            model=["1", 0], seed=request["seed"], positive=["4", 0], negative=["5", 0],
            latent_image=["6", 0], **dict(DIFFUSION, steps=steps))},
        "8": {"class_type": "VAEDecodeAudio", "inputs": {"samples": ["7", 0], "vae": ["1", 2]}},
        "9": {"class_type": "SaveAudio", "inputs": {"audio": ["8", 0], "filename_prefix": prefix}},
        "10": {"class_type": "PreviewAny", "inputs": {"source": ["4", 1]}},
    })
    return graph


def artifact_hashes(directory, names):
    return {n: {"sha256": sha256(directory / n), "bytes": (directory / n).stat().st_size}
            for n in names if (directory / n).is_file()}


def identity(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def run_one(comfy, args, request, checkpoint, destination, system):
    write_json(destination / "input.json", request)
    planned = request["cot"] != "off" and request.get("abc") is None
    if args.action == "plan":
        graph = plan_graph(request, checkpoint)
    else:
        safe_id = re.sub(r"[^A-Za-z0-9_.-]+", "_", request["id"]).strip("._") or "song"
        prefix = f"yue2_bridge/{safe_id}_{request['cot']}"
        graph = song_graph(request, checkpoint, args.max_duration, args.steps, prefix)
    write_json(destination / "workflow_api.json", graph)
    config = {
        "backend": "ComfyUI native YuE2 nodes", "server": comfy.server,
        "comfyui_version": system.get("system", {}).get("comfyui_version"),
        "pytorch_version": system.get("system", {}).get("pytorch_version"),
        "device": (system.get("devices") or [{}])[0].get("name"),
        "checkpoint": checkpoint, "mode": request["cot"], "abc_source": (
            "none (off)" if request["cot"] == "off" else "planned by YuE2GenerateABC" if planned else "supplied"),
        "abc_sampling": ABC_SAMPLING if planned else None,
        "decoder_release": f"ComfyUI VAEDecodeAudio, VAE from {checkpoint}",
        "validation_status": "not_applicable: ComfyUI backend has no yue2-infer release validation",
    }
    if args.action != "plan":
        config.update(music_sampling=MUSIC_SAMPLING, diffusion=dict(DIFFUSION, steps=args.steps),
                      max_duration=args.max_duration,
                      cfg_scale=request.get("cfg_scale", "node default (1.01 for off, else 1.0)"))
    write_json(destination / "config.json", config)
    try:
        prompt_id, outputs, seconds = comfy.run(graph)
        abc = request.get("abc")
        if planned:
            abc = text_output(outputs, "3")[0]
        if abc is not None:
            (destination / "score.abc").write_text(abc, encoding="utf-8", newline="\n")
        saved = dict(request, abc=abc) if abc is not None else dict(request)
        write_json(destination / "request.json", saved)
        check = score_check(abc, request["cot"])
        write_json(destination / "abc_check.json", check)
        result = {"mode": request["cot"], "prompt_id": prompt_id, "elapsed_seconds": round(seconds, 2)}
        truncated = {"abc": None}
        if args.action != "plan":
            files = outputs.get("9", {}).get("audio") or []
            if not files:
                raise ComfyError("ComfyUI returned no saved audio")
            comfy.download(files[0], destination / "audio.flac")
            rate, audio_seconds = flac_info(destination / "audio.flac")
            generated = float(text_output(outputs, "10")[0])
            cap = args.max_duration - 1 / FRAMES_PER_SECOND - 1e-6
            truncated["semantic"] = generated >= cap
            result.update(audio_seconds=audio_seconds, sample_rate=rate,
                          generated_seconds=generated, comfy_audio=files[0])
        if check["status"] == "failed":
            result["warnings"] = [f"ABC structural check failed: {check['error']}"]
        if truncated.get("semantic"):
            result.setdefault("warnings", []).append(
                f"Generation reached max_duration {args.max_duration} s; the song may be cut off")
        result.update(
            status="needs_review" if check["status"] == "failed" or truncated.get("semantic") else "complete",
            truncated=truncated, weights={"checkpoint": checkpoint},
            identity=identity({"request": saved, "config": config}),
            artifacts=artifact_hashes(destination, ["audio.flac", "score.abc", "request.json"]))
        write_json(destination / "result.json", result)
    except Exception as exc:
        result = {"mode": request["cot"], "status": "failed", "error": str(exc), "type": type(exc).__name__}
        write_json(destination / "failure.json", result)
    print(json.dumps({k: result.get(k) for k in ("mode", "status", "audio_seconds", "warnings", "error")
                      if result.get(k) is not None}, ensure_ascii=False), flush=True)
    return result


def transcribe(comfy, args, output, system):
    source = Path(args.audio)
    if not source.is_file():
        raise ValueError(f"Audio file not found: {source}")
    encoder = pick(comfy.options("AudioEncoderLoader", "audio_encoder_name"), "--audio-encoder",
                   args.audio_encoder, ["sheetsage"])
    write_json(output / "invocation.json", {
        "action": "transcribe", "loader": {"server": comfy.server, "audio_encoder": encoder,
                                           "backend": "ComfyUI"},
        "source": {"path": str(source.resolve()), "sha256": sha256(source), "bytes": source.stat().st_size},
        "mode": args.mode, "comfyui_version": system.get("system", {}).get("comfyui_version")})
    try:
        uploaded = comfy.upload(source)
        graph = {"1": {"class_type": "LoadAudio", "inputs": {"audio": uploaded}},
                 "2": {"class_type": "AudioEncoderLoader", "inputs": {"audio_encoder_name": encoder}},
                 "3": {"class_type": "SheetSage2AudioToABC",
                       "inputs": {"audio_encoder": ["2", 0], "audio": ["1", 0], "mode": args.mode}},
                 "4": {"class_type": "PreviewAny", "inputs": {"source": ["3", 0]}}}
        write_json(output / "workflow_api.json", graph)
        prompt_id, outputs, seconds = comfy.run(graph)
        abc = text_output(outputs, "4")[0]
        (output / "score.abc").write_text(abc, encoding="utf-8", newline="\n")
        check = score_check(abc, args.mode)
        write_json(output / "abc_check.json", check)
        result = {"status": "complete" if check["status"] == "passed" else "needs_review",
                  "mode": args.mode, "chords_removed": args.mode == "melody", "prompt_id": prompt_id,
                  "elapsed_seconds": round(seconds, 2), "comfy_input": uploaded,
                  "artifacts": artifact_hashes(output, ["score.abc"])}
        write_json(output / "result.json", result)
    except Exception as exc:
        result = {"status": "failed", "error": str(exc), "type": type(exc).__name__}
        write_json(output / "failure.json", result)
    print(json.dumps({k: result.get(k) for k in ("status", "mode", "error") if result.get(k)}), flush=True)
    return 0 if result["status"] == "complete" else 1 if result["status"] == "needs_review" else 2


def run(args):
    comfy = Comfy(args.server, args.timeout)
    if args.action == "transcribe":
        system = comfy.get("/system_stats")
        return transcribe(comfy, args, fresh_directory(args.output), system)
    data = request_data(args)  # Cheap preflight before touching the server or output.
    system = comfy.get("/system_stats")
    checkpoint = pick(comfy.options("CheckpointLoaderSimple", "ckpt_name"), "--checkpoint",
                      args.checkpoint, ["yue2"])
    modes = ("full", "melody", "off") if args.action == "all-modes" else (data["cot"],)
    requests = [dict(data, cot=m, id=f"{data['id']}_{m}") if args.action == "all-modes" else data
                for m in modes]
    output = fresh_directory(args.output)
    write_json(output / "invocation.json", {
        "action": args.action, "backend": "ComfyUI",
        "loader": {"server": comfy.server, "checkpoint": checkpoint},
        "comfyui_version": system.get("system", {}).get("comfyui_version"), "requests": requests})
    results = []
    for request in requests:
        destination = fresh_directory(output / request["cot"]) if args.action == "all-modes" else output
        results.append(run_one(comfy, args, request, checkpoint, destination, system))
    write_json(output / "run.json", {"results": results})
    if any(r["status"] == "failed" for r in results):
        return 2
    return int(any(r["status"] != "complete" for r in results))


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("generate", "all-modes", "plan", "transcribe"):
        command = sub.add_parser(action)
        command.add_argument("--output", required=True, type=Path, help="Fresh destination; never overwritten")
        command.add_argument("--server", default=os.environ.get("COMFYUI_URL", "http://127.0.0.1:8188"))
        command.add_argument("--timeout", type=float, default=7200, help="Seconds to wait per ComfyUI run")
        if action == "transcribe":
            command.add_argument("audio", type=Path)
            command.add_argument("--mode", choices=("melody", "full"), default="melody",
                                 help="melody: both melodies, no chords (for covers); full: melody and chords")
            command.add_argument("--audio-encoder", help="SheetSage2 file as listed by ComfyUI")
            continue
        command.add_argument("--request", required=True, type=Path)
        command.add_argument("--cot", choices=("full", "melody", "off"))
        command.add_argument("--abc-file", type=Path)
        command.add_argument("--seed", type=int, help="Overrides the request seed")
        command.add_argument("--checkpoint", help="YuE2 checkpoint as listed by ComfyUI (auto-detected)")
        if action != "plan":
            command.add_argument("--max-duration", type=float, default=360.0, help="Seconds; node default 360")
            command.add_argument("--steps", type=int, default=DIFFUSION["steps"])
    args = parser.parse_args()
    try:
        return run(args)
    except (ValueError, OSError, ComfyError) as exc:
        print(f"{type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    sys.exit(main())
