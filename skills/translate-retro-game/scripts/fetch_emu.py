"""Download an emulator release that matches this machine's OS and CPU into the repo's own tools/<name>/.

    python fetch_emu.py mesen|desmume|pcsx|ppsspp|gba-bios|psx-bios [--dest tools] [--force] [--dry-run] [--os windows|linux|macos] [--arch x64|arm64]

gba-bios / psx-bios fetch a console BIOS (github.com/Abdess/retrobios) to tools/mesen/Firmware/gba_bios.bin
and tools/bios/scph5500.bin (Japanese PS1), checked against the known SHA-1 of the dump.
Stdlib only. Asset names come from each project's release page (GitHub API; set GITHUB_TOKEN if rate-limited).
Windows on ARM falls back to the x64 build (Windows emulates it) except where an ARM64 build exists.
Exit 1 when no build exists for the OS/CPU or the archive can't be unpacked here, with the page to download from by hand.
"""
import argparse, hashlib, json, os, platform, re, shutil, subprocess, sys, tempfile, urllib.request, zipfile

GH = "https://api.github.com/repos/%s/releases/latest"
DISTRIB = "https://distrib.app"
# name -> (github repo | None, {(os, arch): asset regex}, manual page)
TARGETS = {
    "mesen": ("nesdev-org/MesenCE", {
        ("windows", "x64"): r"_Windows\.zip$", ("windows", "arm64"): r"_Windows\.zip$",
        ("linux", "x64"): r"_Linux_x64\.zip$", ("linux", "arm64"): r"_Linux_ARM64\.zip$",
        ("macos", "x64"): r"_macOS_x64_Intel\.zip$", ("macos", "arm64"): r"_macOS_ARM64_AppleSilicon\.zip$"},
     "github.com/nesdev-org/MesenCE/releases"),
    "desmume": ("minhnhattonthat/desmume", {("windows", "x64"): r"-win64\.zip$", ("windows", "arm64"): r"-win64\.zip$"},
                "github.com/minhnhattonthat/desmume/releases (the QA fork is Windows x64 only; elsewhere build `agent-qa`, see QA-FORK.md)"),
    "pcsx": (None, {("windows", "x64"): "dev-win-x64", ("windows", "arm64"): "dev-win-x64", ("linux", "x64"): "dev-linux-x64"},
             "github.com/grumpycoders/pcsx-redux (no macOS or ARM build is published)"),
    "ppsspp": ("hrydgard/ppsspp", {
        ("windows", "x64"): r"-Windows-x64\.zip$", ("windows", "arm64"): r"-Windows-ARM64\.zip$",
        ("linux", "x64"): r"-anylinux-x86_64\.AppImage$", ("linux", "arm64"): r"-anylinux-aarch64\.AppImage$",
        ("macos", "x64"): r"PPSSPPSDL-macOS-.*\.zip$", ("macos", "arm64"): r"PPSSPPSDL-macOS-.*\.zip$"},
     "ppsspp.org/downloads.html"),
}


RETROBIOS = "https://raw.githubusercontent.com/Abdess/retrobios/main/bios/"
# name -> (path in retrobios, destination under --dest, sha1)
BIOS = {"gba-bios": ("Nintendo/Game%20Boy%20Advance/gba_bios.bin", "mesen/Firmware/gba_bios.bin",
                     "300c20df6731a33952ded8c436f7f186d25d3492"),
        "psx-bios": ("Sony/PlayStation/scph5500.bin", "bios/scph5500.bin", "b05def971d8ec59f346f2d9ac21fb742e3eb6917")}


def fetch_bios(name, dest_root, force):
    src, rel, sha1 = BIOS[name]
    dest = os.path.join(dest_root, rel)
    if os.path.exists(dest) and not force:
        sys.exit(f"{dest} exists: pass --force to replace it")
    data = get(RETROBIOS + src)
    got = hashlib.sha1(data).hexdigest()
    if got != sha1:
        sys.exit(f"{name}: downloaded SHA-1 {got} is not the expected {sha1}; not saved")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    with open(dest, "wb") as f:
        f.write(data)
    print(f"{name}: saved {os.path.abspath(dest)} (SHA-1 verified)")


def host():
    os_ = {"Windows": "windows", "Linux": "linux", "Darwin": "macos"}.get(platform.system(), platform.system().lower())
    m = platform.machine().lower()
    return os_, "arm64" if m in ("arm64", "aarch64") else "x64" if m in ("amd64", "x86_64", "x64") else m


def get(url, as_json=False):
    req = urllib.request.Request(url, headers={"User-Agent": "translate-retro-game"})
    if os.environ.get("GITHUB_TOKEN") and "github.com" in url:
        req.add_header("Authorization", "Bearer " + os.environ["GITHUB_TOKEN"])
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r) if as_json else r.read()


def pick(name, os_, arch):
    repo, table, page = TARGETS[name]
    key = (os_, arch)
    if key not in table:
        sys.exit(f"no {name} build for {os_}/{arch}: download by hand from {page}")
    if repo is None:  # PCSX-Redux: distrib.app channel -> newest build's zip
        base = f"{DISTRIB}/storage/manifests/pcsx-redux/{table[key]}"
        bid = get(base + "/manifest.json", True)["builds"][0]["id"]
        path = get(f"{base}/manifest-{bid}.json", True)["path"]
        return os.path.basename(path), DISTRIB + path
    rel = get(GH % repo, True)
    hits = [a for a in rel["assets"] if re.search(table[key], a["name"])]
    if not hits:
        sys.exit(f"{name} {rel['tag_name']} has no asset matching {table[key]} for {os_}/{arch}: see {page}")
    return hits[0]["name"], hits[0]["browser_download_url"]


def unpack(archive, name, dest):
    low = name.lower()
    if low.endswith(".zip"):
        zipfile.ZipFile(archive).extractall(dest)
    elif low.endswith(".7z"):  # no stdlib reader: 7-Zip, or bsdtar (Windows 10+ tar.exe, macOS tar) which reads 7z
        for cmd in (["7z", "x", "-y", "-o" + dest, archive], ["7za", "x", "-y", "-o" + dest, archive], ["tar", "-xf", archive, "-C", dest]):
            if shutil.which(cmd[0]) and subprocess.run(cmd, capture_output=True).returncode == 0:
                return
        sys.exit(f"can't unpack {name}: install 7-Zip (7z on PATH) and rerun")
    elif low.endswith(".appimage"):
        shutil.copy(archive, os.path.join(dest, name))
        os.chmod(os.path.join(dest, name), 0o755)
    else:
        sys.exit(f"don't know how to unpack {name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("emulator", choices=[*TARGETS, *BIOS])
    ap.add_argument("--dest", default="tools", help="parent folder; the emulator goes in <dest>/<name>/")
    ap.add_argument("--force", action="store_true", help="unpack over a non-empty folder")
    ap.add_argument("--dry-run", action="store_true", help="print the chosen asset and stop")
    ap.add_argument("--os", dest="os_", choices=["windows", "linux", "macos"])
    ap.add_argument("--arch", choices=["x64", "arm64"])
    a = ap.parse_args()
    if a.emulator in BIOS:
        return fetch_bios(a.emulator, a.dest, a.force)
    h_os, h_arch = host()
    os_, arch = a.os_ or h_os, a.arch or h_arch
    name, url = pick(a.emulator, os_, arch)
    print(f"{a.emulator}: {os_}/{arch} -> {name}\n  {url}")
    if a.dry_run:
        return
    dest = os.path.join(a.dest, a.emulator)
    if os.path.isdir(dest) and os.listdir(dest) and not a.force:
        sys.exit(f"{dest} is not empty: pass --force to unpack over it (settings and saves there are kept)")
    os.makedirs(dest, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        archive = os.path.join(tmp, name)
        with open(archive, "wb") as f:
            f.write(get(url))
        unpack(archive, name, dest)
    print(f"unpacked to {os.path.abspath(dest)}")


if __name__ == "__main__":
    main()
