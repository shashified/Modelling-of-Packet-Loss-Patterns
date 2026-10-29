"""Saved runs: a small on-disk library of real captures and their headline results.

Each saved run is one folder under realworld/saved_runs/ (or $PL_LIBRARY_DIR):
    <id>/<label>_<YYYYmmdd-HHMMSS>.csv   the packets (copied from the capture)
    <id>/<label>_<YYYYmmdd-HHMMSS>.json  probe settings, plus saved_name / saved_note / saved_at
    <id>/summary.json                    headline numbers, so the list shows without re-running anything
"""
import json
import os
import re
import shutil
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def folder():
    return os.environ.get("PL_LIBRARY_DIR", os.path.join(ROOT, "realworld", "saved_runs"))


def slug(text):
    s = re.sub(r"[^A-Za-z0-9_-]+", "_", text.strip()).strip("_")
    return s[:40] or "run"


def save_run(csv_path, name, note, summary):
    """Copy a capture into the library with its summary. Returns the new run id."""
    lib = folder()
    os.makedirs(lib, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    run_id = f"{slug(name)}_{stamp}"
    i = 2
    while os.path.exists(os.path.join(lib, run_id)):
        run_id = f"{slug(name)}_{stamp}_{i}"
        i += 1
    d = os.path.join(lib, run_id)
    os.makedirs(d)
    base = os.path.basename(csv_path)[:-4]
    shutil.copyfile(csv_path, os.path.join(d, base + ".csv"))
    meta_src = csv_path[:-4] + ".json"
    meta = {}
    if os.path.exists(meta_src):
        with open(meta_src) as f:
            meta = json.load(f)
    meta.update(original_label=meta.get("label"), label=name.strip() or base, saved_name=name.strip() or base,
                saved_note=note.strip(), saved_at=datetime.now().isoformat(timespec="seconds"),
                original_file=os.path.basename(csv_path))
    with open(os.path.join(d, base + ".json"), "w") as f:
        json.dump(meta, f, indent=2)
    with open(os.path.join(d, "summary.json"), "w") as f:
        json.dump(dict(summary, id=run_id, name=meta["saved_name"], note=meta["saved_note"],
                       saved_at=meta["saved_at"]), f, indent=2, default=float)
    return run_id


def list_runs():
    """All saved runs, newest first, each with its summary and the path of its capture."""
    lib = folder()
    out = []
    if not os.path.isdir(lib):
        return out
    for run_id in os.listdir(lib):
        d = os.path.join(lib, run_id)
        sp = os.path.join(d, "summary.json")
        csvs = [f for f in os.listdir(d) if f.endswith(".csv")] if os.path.isdir(d) else []
        if not os.path.exists(sp) or not csvs:
            continue
        try:
            with open(sp) as f:
                s = json.load(f)
        except (OSError, ValueError):
            continue
        s["id"], s["csv"] = run_id, os.path.join(d, csvs[0])
        out.append(s)
    return sorted(out, key=lambda s: s.get("saved_at", ""), reverse=True)


def capture_paths():
    """CSV paths of every saved run (so they can be picked in the sidebar like any capture)."""
    return [s["csv"] for s in list_runs()]


def delete_run(run_id):
    d = os.path.join(folder(), os.path.basename(run_id))
    if os.path.isdir(d):
        shutil.rmtree(d)
