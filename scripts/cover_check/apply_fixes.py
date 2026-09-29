#!/usr/bin/env python3
"""
Apply cover-art replacements: images dropped into <workdir>/fixes/ are embedded
into the matching tracks on the VPS, then a Navidrome rescan is triggered.

Workflow (as simple as it gets):
  1. Spot a wrong cover somewhere (e.g. extracted to bad_covers/ by a review pass).
  2. Download the right artwork and name it exactly like the track file
     ("Artist - Title.jpg") — copy the stem from the review folder.
  3. Drop it into <workdir>/fixes/.
  4. If the watch mode is running (apply_fixes.py --watch <workdir>) it applies
     within seconds; otherwise run: python3 apply_fixes.py <workdir>

The script normalizes the image (max 2000 px, JPEG q92, NO cropping), uploads it,
embeds it into the track (the old cover is replaced), and triggers startScan.
Applied images are moved to fixes/applied/.

Cover file naming: exact "Artist - Title.jpg" (the track's filename stem) is the
primary form; "#N" or a bare number index also works with a manifest.
"""
import argparse, csv, glob, os, re, shlex, shutil, subprocess, sys, tempfile, time, unicodedata, urllib.parse

def nfc(s):
    return unicodedata.normalize("NFC", s)

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
SSH = ["ssh", "-i", os.path.expanduser("~/.ssh/id_ed25519_oracle")]
SCP = ["scp", "-q", "-i", os.path.expanduser("~/.ssh/id_ed25519_oracle")]
IMG_EXTS = (".jpg", ".jpeg", ".png")
MAX_SIDE = 2000      # longest side after normalization
JPEG_QUALITY = 92

def load_env():
    vals = {}
    with open(os.path.join(REPO, ".env")) as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            vals[k.strip()] = v.strip().strip("'\"")
    return vals

def load_manifest(wd):
    with open(os.path.join(wd, "manifest.csv"), newline="") as fh:
        return {r["index"]: r for r in csv.DictReader(fh)}

def resolve_track(fname, manifest, names):
    """Resolve the track base name from a cover file name.
    Priority: 1) stem matches a track filename stem in the library;
    2) leading #N or a bare number = manifest index; 3) otherwise the name
    as-is (the VPS side will answer NOT_FOUND)."""
    base = os.path.splitext(fname)[0]
    if nfc(base) in names:
        return base
    m = re.search(r"#(\d+)", fname) or re.match(r"^(\d+)\.", fname)
    if m:
        idx = str(int(m.group(1)))
        row = manifest.get(idx)
        if row and row.get("path"):
            return os.path.splitext(os.path.basename(row["path"]))[0]
        return None
    return base

def normalize_image(src):
    """Cap at MAX_SIDE px, JPEG q92. NO cropping: aspect ratios are kept,
    non-square covers are embedded as-is.
    Returns (normalized file path, temp dir)."""
    tmpdir = tempfile.mkdtemp(prefix="coverfix_")
    r = subprocess.run(["sips", "-g", "pixelWidth", "-g", "pixelHeight", src],
                       capture_output=True, text=True, check=True)
    w = h = 0
    for line in r.stdout.splitlines():
        if "pixelWidth" in line:
            w = int(line.split(":")[1])
        if "pixelHeight" in line:
            h = int(line.split(":")[1])
    cur = src
    if max(w, h) > MAX_SIDE:
        nxt = os.path.join(tmpdir, "resized.jpg")
        subprocess.run(["sips", "-Z", str(MAX_SIDE), cur, "--out", nxt],
                       check=True, capture_output=True)
        cur = nxt
    final = os.path.join(tmpdir, "final.jpg")
    subprocess.run(["sips", "-s", "format", "jpeg",
                    "-s", "formatOptions", str(JPEG_QUALITY),
                    cur, "--out", final], check=True, capture_output=True)
    return final, tmpdir

def trigger_scan(domain, user, password):
    p = urllib.parse.quote(password, safe="")
    u = urllib.parse.quote(user, safe="")
    url = (f"http://localhost:4533/rest/startScan?u={u}&p={p}"
           f"&v=1.16.1&c=coverfix&f=json")
    r = subprocess.run(SSH + [f"ubuntu@{domain}", f"curl -s '{url}'"],
                       capture_output=True, text=True, timeout=60)
    return (r.stdout or "").strip()[:200]

def process_fixes(domain, wd, manifest, names, cooldown):
    """Process every image in fixes/. Returns the number applied."""
    fixes = os.path.join(wd, "fixes")
    applied = os.path.join(fixes, "applied")
    os.makedirs(applied, exist_ok=True)
    imgs = sorted(f for f in os.listdir(fixes)
                  if os.path.splitext(f)[1].lower() in IMG_EXTS)
    if not imgs:
        return 0
    done = 0
    for fname in imgs:
        img = os.path.join(fixes, fname)
        base = resolve_track(fname, manifest, names)
        if base is None:
            print(f"NO TRACK with that manifest index: {fname} — left in fixes/")
            continue
        if base in cooldown and time.monotonic() - cooldown[base] < 300:
            continue  # NOT_FOUND recently — don't hammer the VPS every 5 seconds
        try:
            norm, tmpdir = normalize_image(img)
            subprocess.run(SCP + [norm, f"ubuntu@{domain}:/tmp/coverfix_img"], check=True)
            shutil.rmtree(tmpdir, ignore_errors=True)
            cmd = (f"python3 /tmp/coverfix_remote.py /tmp/coverfix_img {shlex.quote(base)}"
                   f"; rm -f /tmp/coverfix_img")
            r = subprocess.run(SSH + [f"ubuntu@{domain}", cmd],
                               capture_output=True, text=True, timeout=120)
        except Exception as e:
            print(f"ERROR (scp/ssh): {base}: {e} — retrying next cycle")
            continue
        out = (r.stdout or "") + (r.stderr or "")
        if "NOT_FOUND" in out:
            cooldown[base] = time.monotonic()
            print(f"NOT_FOUND on VPS: {base} (will retry in 5 min)")
        elif "EMBEDDED" in out:
            n = out.split("EMBEDDED")[1].strip().split()[0]
            print(f"OK ({n} file(s)): {base}")
            os.replace(img, os.path.join(applied, fname))
            cooldown.pop(base, None)
            done += 1
        else:
            print(f"ERROR: {base}: {out.strip()[:200]}")
    return done

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("workdir")
    ap.add_argument("--watch", action="store_true",
                    help="watch fixes/ and apply new images automatically")
    args = ap.parse_args()
    wd = args.workdir

    env = load_env()
    domain = env.get("DOMAIN")
    if not domain:
        print("DOMAIN not found in .env"); sys.exit(1)

    remote_script = os.path.join(REPO, "scripts", "cover_check", "apply_remote.py")
    subprocess.run(SCP + [remote_script, f"ubuntu@{domain}:/tmp/coverfix_remote.py"],
                   check=True)

    manifest = load_manifest(wd)
    names = {nfc(os.path.splitext(os.path.basename(r["path"]))[0])
             for r in manifest.values() if r.get("path")}
    if args.watch:
        print("watch mode: polling fixes/ every 5 seconds (Ctrl+C to stop).")
        print("Drop images named after their track — they are applied automatically.")
    last_scan = 0.0
    pending_scan = False
    cooldown = {}
    while True:
        try:
            done = process_fixes(domain, wd, manifest, names, cooldown)
        except Exception as e:
            import traceback
            print(f"CYCLE ERROR: {e}; keep watching")
            traceback.print_exc()
            time.sleep(5)
            continue
        now = time.monotonic()
        if done:
            print(f"applied {done}")
        if (done or pending_scan) and now - last_scan >= 60:
            # rescan at most once per minute — otherwise we burn the Navidrome auth rate limit
            scan = trigger_scan(domain, env.get("NAVIDROME_USER", ""),
                                env.get("NAVIDROME_PASSWORD", ""))
            print(f"startScan: {scan or 'started'}")
            last_scan = now
            pending_scan = False
        elif done:
            pending_scan = True
            print("rescan deferred (auth rate limit), catching up in a minute")
        if not args.watch:
            if done == 0:
                print("Nothing to do: drop images into fixes/ first")
            break
        time.sleep(5)

if __name__ == "__main__":
    main()
