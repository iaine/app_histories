"""Automatic content recognition (ACR) detection.

Detects the Shazam-style capability of listening through the microphone,
computing an acoustic fingerprint, and matching it against a cloud
catalogue to identify music or other content.

ACR is a distinct research object from generic microphone use: an ACR app
records audio *in order to recognise what is playing*. The detector gathers
four independent signals and grades a confidence, because any single signal
has a benign explanation:

1. **SDK package** (strongest) -- a named ACR vendor shipped in the app.
2. **native library** (strong) -- a purpose-built fingerprinting ``.so``.
3. **endpoint** (strong) -- a recognition URL path.
4. **capture + egress** (corroborating) -- records audio *and* networks.

Plus a **CJK keyword** tier (corroboration only) for Chinese-market
"listen-to-identify" (听歌识曲) features.

Vendor knowledge lives in ``acr_sdks.csv`` / ``acr_signatures.csv`` -- edit
the data to extend coverage, no code change. Validated against real QQ
Music, NetEase Cloud Music, and a negative-control music player; see the
package README for the confidence semantics and known gaps.
"""

import csv
import os

_HERE = os.path.dirname(__file__)
_SDKS_CSV = os.path.join(_HERE, "acr_sdks.csv")
_SIGS_CSV = os.path.join(_HERE, "acr_signatures.csv")


def load_sdks(path=None):
    """ACR vendor SDK package signatures: [{signature, vendor, product,
    category, region, confidence}]."""
    with open(path or _SDKS_CSV, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def load_signatures(path=None):
    """Native-lib / endpoint-path / CJK-keyword signatures, split by kind:
    returns {"native": [...], "path": [...], "keyword": [...]}."""
    out = {"native": [], "path": [], "keyword": []}
    with open(path or _SIGS_CSV, encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            out.setdefault(row["kind"], []).append(row)
    return out


def find_acr_sdks(class_names, sdks=None):
    """Vendors whose SDK package is present. Anchored prefix match (same
    rule as trackers): ``com.acrcloud`` matches ``com.acrcloud.rec.Foo``
    but not ``com.acrcloudy.Bar``."""
    sdks = sdks if sdks is not None else load_sdks()
    classes = {c.strip("L;").replace("/", ".") for c in class_names}
    hits = []
    for row in sdks:
        sig = row["signature"]
        if any(c == sig or c.startswith(sig + ".") for c in classes):
            hits.append({"vendor": row["vendor"], "product": row["product"],
                         "category": row["category"],
                         "signature": sig, "confidence": row["confidence"]})
    return hits


def find_acr_native(lib_names, signatures=None):
    """ACR fingerprinting native libraries, matched on filename fragment
    (case-insensitive). Robust to obfuscation: a Flutter/stripped build
    still ships the ``.so`` under its real name."""
    signatures = signatures if signatures is not None else load_signatures()
    names = [n.rsplit("/", 1)[-1].lower() for n in lib_names]
    hits = []
    for row in signatures.get("native", []):
        pat = row["pattern"].lower()
        matched = sorted({n for n in names if pat in n})
        for n in matched:
            hits.append({"library": n, "pattern": row["pattern"],
                         "vendor": row.get("vendor", ""),
                         "confidence": row["confidence"]})
    return hits


def find_acr_endpoints(urls, signatures=None):
    """DEX URLs whose path/host matches an ACR recognition endpoint."""
    signatures = signatures if signatures is not None else load_signatures()
    hits = []
    seen = set()
    for url in urls:
        low = url.lower()
        for row in signatures.get("path", []):
            if row["pattern"].lower() in low and url not in seen:
                seen.add(url)
                hits.append({"url": url, "pattern": row["pattern"],
                             "vendor": row.get("vendor", ""),
                             "confidence": row["confidence"]})
                break
    return hits


def find_acr_keywords(strings, signatures=None):
    """CJK "listen-to-identify" feature strings in the DEX string pool.

    Corroboration only -- a feature label can outlive a removed feature or
    name a content chart (畅听音乐's 听歌识曲榜 is a *chart*, not the
    capability). Never raises confidence on its own. Only anchored 4+ char
    phrases are in the table, so innocent words (知识曲库 "knowledge song
    library") do not match.
    """
    signatures = signatures if signatures is not None else load_signatures()
    hits = []
    for row in signatures.get("keyword", []):
        pat = row["pattern"]
        if any(pat in s for s in strings):
            hits.append({"keyword": pat, "note": row.get("note", ""),
                         "confidence": row["confidence"]})
    return hits


def grade_confidence(sdk, native, endpoint, capture_egress, keyword):
    """Combine the signals into high / medium / low / none.

    A named SDK, or two strong signals, or several independent
    fingerprinting libraries, is ``high``. One strong signal plus capture
    is ``medium``. Capture and egress alone is ``low``. A keyword with no
    primary signal is inert -- ``none`` -- which is what keeps a music
    player that merely displays a 听歌识曲 chart from being flagged.
    """
    if sdk:
        return "high"
    # multiple independent fingerprint libraries, or impl-level CJK strings,
    # are strong in their own right (NetEase ships three fp libs + algorithm
    # strings but no named SDK -- clearly high, not medium)
    impl_keyword = any("算法" in k["keyword"] or "指纹" in k["keyword"]
                       for k in keyword)
    strong = (1 if native else 0) + (1 if endpoint else 0)
    if len(native) >= 2 or (native and impl_keyword):
        return "high"
    if strong >= 2:
        return "high"
    if strong == 1 and capture_egress:
        return "medium"
    if capture_egress:
        return "low"
    return "none"
