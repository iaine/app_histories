"""XAPK / APKS / APKM bundle ingestion.

Apps are increasingly distributed as a *bundle*: a zip holding a base APK
plus per-configuration split APKs (``config.<x>.apk``, where ``x`` is an
ABI, screen density, or language). The native libraries live in the
splits, so analysing the base alone yields near-empty results -- Live
Transcribe's base APK contains **zero** native libraries while all seven
sit in ``config.arm64_v8a.apk``.

This module is the packaged-bundle counterpart to the loose-split merging
in :mod:`cim_app_histories.analyse`. Both end up doing the same thing:
hand the workflow functions one merged set of files.

Formats handled (all are ordinary zips; they differ in manifest and
internal naming):

===========  ===========  ==================
Format       Extension    Manifest
===========  ===========  ==================
XAPK         ``.xapk``    ``manifest.json``
APKS         ``.apks``    ``toc.pb``
APKM         ``.apkm``    ``info.json``
===========  ===========  ==================

The manifest is a convenience, not a dependency: member filenames carry
enough information to proceed, so a missing or unreadable manifest falls
back to :func:`classify_split`.
"""

import json
import re
import zipfile
from pathlib import Path

BUNDLE_SUFFIXES = {".xapk", ".apks", ".apkm"}

# Native code lives in ABI splits; these are the values Android uses.
_ABIS = {"arm64_v8a", "armeabi_v7a", "armeabi", "x86", "x86_64", "mips",
         "mips64"}
_DENSITIES = {"ldpi", "mdpi", "hdpi", "xhdpi", "xxhdpi", "xxxhdpi", "tvdpi",
              "nodpi", "anydpi"}

# Split ids use underscores; Android's real ABI directory names mix
# hyphens and underscores, so map explicitly rather than guessing.
_ABI_NAMES = {
    "arm64_v8a": "arm64-v8a",
    "armeabi_v7a": "armeabi-v7a",
    "armeabi": "armeabi",
    "x86": "x86",
    "x86_64": "x86_64",
    "mips": "mips",
    "mips64": "mips64",
}

# Preference order when a bundle ships several architectures. Merging all
# of them would count the same library 2-4x (once per architecture) and
# inflate module and vendor tallies, so we take one: arm64 first, because
# that is what modern devices run and where the real libraries are.
ABI_PREFERENCE = ["arm64-v8a", "armeabi-v7a", "x86_64", "x86"]

_CONFIG_RE = re.compile(r"(?:split_)?config[._]([A-Za-z0-9_]+)\.apk$", re.I)
_BASE_DASH_RE = re.compile(r"base-([A-Za-z0-9_]+)\.apk$", re.I)


def is_bundle(path):
    """True when *path* is a packaged bundle rather than a plain APK.

    Sniffs content as well as extension: a ``.xapk`` that is really a
    single renamed APK, or a bundle with an unexpected suffix, should
    still be classified correctly.
    """
    p = Path(path)
    if p.suffix.lower() in BUNDLE_SUFFIXES:
        return True
    if p.suffix.lower() != ".apk":
        return False
    # An APK is itself a zip, so "is a zip" is not enough -- a bundle is a
    # zip whose *members* are APKs.
    try:
        with zipfile.ZipFile(p) as z:
            return any(n.lower().endswith(".apk") for n in z.namelist())
    except (zipfile.BadZipFile, OSError):
        return False


def classify_split(member_name):
    """Decode the ``x`` in ``config.x.apk`` into its kind.

    Returns ``{"kind": ..., "value": ...}`` where kind is one of
    ``base``, ``abi``, ``density``, ``language``, ``feature`` or
    ``unknown``. The kind drives both selection (which members to open)
    and provenance (the language list is a localisation signal, the ABI
    list is a target-hardware signal).
    """
    n = member_name.rsplit("/", 1)[-1]
    low = n.lower()
    if low in ("base.apk", "base-master.apk"):
        return {"kind": "base", "value": None}

    m = _CONFIG_RE.search(n) or _BASE_DASH_RE.search(n)
    if not m:
        if low.startswith("split_"):
            return {"kind": "feature", "value": n[len("split_"):-4]}
        return {"kind": "unknown", "value": n}

    x = m.group(1).lower()
    if x in _ABIS:
        # Android's own ABI names: arm ABIs use hyphens (arm64-v8a,
        # armeabi-v7a) but x86_64 keeps its underscore. A blanket
        # underscore->hyphen swap would produce "x86-64", which matches
        # no real lib path and would break ABI preference matching.
        return {"kind": "abi", "value": _ABI_NAMES.get(x, x.replace("_", "-"))}
    if x in _DENSITIES:
        return {"kind": "density", "value": x}
    # language splits are 2-3 letter codes, optionally with a region
    if re.fullmatch(r"[a-z]{2,3}", x):
        return {"kind": "language", "value": x}
    return {"kind": "feature", "value": x}


def select_members(members, abi_policy="preferred", keep_density=False):
    """Choose which bundle members to open.

    :param members: {member_name: classification} from
        :func:`classify_split`.
    :param abi_policy: ``"preferred"`` takes a single ABI (see
        :data:`ABI_PREFERENCE`); ``"all"`` takes every ABI and accepts the
        duplication, for a study explicitly comparing architectures.
    :param keep_density: density splits carry resources, not code, so they
        are skipped by default; ``metadata`` work may want them.

    Language and feature splits are always taken: they do not collide
    (different resources, different code), so there is nothing to
    de-duplicate.
    """
    chosen, abis = [], []
    for name, cls in members.items():
        kind = cls["kind"]
        if kind == "abi":
            abis.append((name, cls["value"]))
        elif kind == "density":
            if keep_density:
                chosen.append(name)
        else:
            # base, language, feature, unknown -- take them
            chosen.append(name)

    if abis:
        if abi_policy == "all":
            chosen.extend(n for n, _ in abis)
        else:
            available = {v: n for n, v in abis}
            pick = next((a for a in ABI_PREFERENCE if a in available), None)
            if pick is None:
                # none of the preferred ABIs present (e.g. only mips):
                # take what is there rather than returning nothing
                pick = abis[0][1]
                chosen.append(abis[0][0])
            else:
                chosen.append(available[pick])
    return chosen, [v for _, v in abis]


def read_manifest(zf):
    """Parse a bundle manifest when present. Best-effort: returns ``{}``
    for ``toc.pb`` (protobuf, not parsed here) or an unreadable file, and
    the caller falls back to filename inference."""
    for name in ("manifest.json", "info.json"):
        if name in zf.namelist():
            try:
                return json.loads(zf.read(name))
            except (ValueError, OSError):
                return {}
    return {}


def open_bundle(path, dest_dir, abi_policy="preferred", keep_density=False):
    """Extract the relevant members of a bundle to *dest_dir*.

    :returns: ``(member_paths, meta)`` where member_paths is a list of
        extracted APK paths with the base first (so base classes win on
        collision when merged), and meta is the provenance block.
    """
    path = Path(path)
    members, warnings = {}, []
    with zipfile.ZipFile(path) as z:
        manifest = read_manifest(z)
        for n in z.namelist():
            if not n.lower().endswith(".apk"):
                continue          # skip .obb asset packs, icons, manifests
            members[n] = classify_split(n)

        # A bundle whose members have no recognisable base (APKPure names
        # the base after the package) -- treat the largest, or the one not
        # classified as a config split, as base.
        if not any(c["kind"] == "base" for c in members.values()):
            for n, c in members.items():
                if c["kind"] == "unknown":
                    members[n] = {"kind": "base", "value": None}
                    break

        chosen, abis_available = select_members(
            members, abi_policy=abi_policy, keep_density=keep_density)

        dest = Path(dest_dir)
        dest.mkdir(parents=True, exist_ok=True)
        extracted = []
        for n in chosen:
            try:
                target = dest / Path(n).name
                with z.open(n) as src, open(target, "wb") as out:
                    out.write(src.read())
                extracted.append((n, target))
            except (KeyError, OSError, zipfile.BadZipFile) as exc:
                warnings.append(f"could not extract {n}: {exc}")

    # base first so its classes take precedence on merge
    extracted.sort(key=lambda t: members[t[0]]["kind"] != "base")
    member_paths = [p for _, p in extracted]

    abi_used = None
    for n, _ in extracted:
        if members[n]["kind"] == "abi":
            abi_used = members[n]["value"]
            break

    meta = {
        "format": path.suffix.lower().lstrip("."),
        "abi_used": abi_used,
        "abis_available": sorted(set(abis_available)),
        "languages": sorted({c["value"] for c in members.values()
                             if c["kind"] == "language"}),
        "feature_splits": sorted({c["value"] for c in members.values()
                                  if c["kind"] == "feature"}),
        "members_merged": [Path(n).name for n, _ in extracted],
    }
    if manifest.get("package_name"):
        meta["package_name"] = manifest["package_name"]
    if manifest.get("version_name"):
        meta["version_name"] = manifest["version_name"]
    if warnings:
        meta["warnings"] = warnings
    return member_paths, meta
