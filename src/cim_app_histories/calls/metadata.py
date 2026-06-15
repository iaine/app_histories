"""
Metadata workflow: one compact record per APK.

Collects app identity (name, package, versions), manifest surface
(permissions, activities), localisation coverage, and
A/B-testing SDK presence -- the per-version observables that the
app-histories method tracks across releases.

Pure data out: no printing, no file writing, no logger mutation, no
multiprocessing -- parallelism and serialisation belong to the CLI's
batch driver (one APK per task, JSONL out, SLURM-array friendly).
"""

from ..apk.apk import extractAPK
from ..dex.dex import analyseDEX


def extract_metadata(apkname):
    """Return the metadata record for one APK.

    :param apkname: path to the .apk file
    :returns: dict of metadata fields
    """
    a = extractAPK(apkname)

    results = {
        "applicationname": a.applicationname(),
        "pkg": a.packagename(),
        "version_code": a.android_version_code(),
        "android_name": a.android_version_name(),
        "permissions": a.permissions(),
        "activities": a.activities(),
        "localisation": a.get_locales(),
    }

    # A/B detection must scan every classes*.dex: most large apps are
    # multidex, and scanning only the first dex undercounts SDKs.
    ab = set()
    trackers = {}
    for buff in a.apk.get_all_dex():
        dex = analyseDEX(buff)
        ab.update(dex.find_ab_by_package())
        # keep one descriptor per matched tracker signature across dexes
        for t in dex.find_trackers():
            trackers[t["signature"]] = t
    results["ab"] = sorted(ab)
    results["trackers"] = sorted(trackers.values(),
                                 key=lambda t: t["signature"])

    return results


# Canonical CSV column order. One row per app; the categorical fields
# (permissions, locales, SDKs, activities) are flattened to
# counts plus a ;-joined list, which keeps the table readable while
# preserving the values. This ordering is the contract the metadata
# viewer's CSV export mirrors, so both produce identical columns.
CSV_COLUMNS = [
    "pkg", "applicationname", "android_name", "version_code",
    "permission_count", "sensitive_permission_count",
    "language_count", "ab_sdk_count", "tracker_count", "activity_count",
    "permissions", "sensitive_permissions", "languages", "ab_sdks",
    "trackers", "tracker_categories",
]

# Android runtime permissions worth counting separately in studies.
SENSITIVE_PERMISSIONS = {
    "RECORD_AUDIO", "CAMERA", "ACCESS_FINE_LOCATION",
    "ACCESS_COARSE_LOCATION", "ACCESS_BACKGROUND_LOCATION",
    "READ_CONTACTS", "READ_SMS", "READ_CALL_LOG", "BODY_SENSORS",
    "READ_EXTERNAL_STORAGE", "READ_MEDIA_AUDIO", "READ_MEDIA_IMAGES",
}


def _as_list(value):
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value:
        return value.split(";")
    return []


def metadata_to_row(record):
    """Flatten one metadata record (the dict from extract_metadata, or a
    full CLI output record wrapping it) into a flat dict keyed by
    CSV_COLUMNS. Pure; no I/O."""
    perms = [p.split(".")[-1] for p in _as_list(record.get("permissions"))]
    sensitive = [p for p in perms if p in SENSITIVE_PERMISSIONS]
    langs = sorted({loc[0] if isinstance(loc, (list, tuple)) else loc
                    for loc in record.get("localisation", []) if loc})
    ab = record.get("ab", [])
    acts = _as_list(record.get("activities"))

    # trackers may be a list of descriptor dicts (current records) or,
    # tolerantly, a list of bare signature strings.
    raw_trackers = record.get("trackers", []) or []
    tracker_names, tracker_cats = [], []
    for t in raw_trackers:
        if isinstance(t, dict):
            tracker_names.append(t.get("name") or t.get("signature", ""))
            if t.get("category"):
                tracker_cats.append(t["category"])
        else:
            tracker_names.append(str(t))

    return {
        "pkg": record.get("pkg", ""),
        "applicationname": record.get("applicationname", ""),
        "android_name": record.get("android_name", ""),
        "version_code": record.get("version_code", ""),
        "permission_count": len(perms),
        "sensitive_permission_count": len(sensitive),
        "language_count": len(langs),
        "ab_sdk_count": len(ab),
        "tracker_count": len(tracker_names),
        "activity_count": len(acts),
        "permissions": ";".join(perms),
        "sensitive_permissions": ";".join(sensitive),
        "languages": ";".join(langs),
        "ab_sdks": ";".join(ab),
        "trackers": ";".join(tracker_names),
        "tracker_categories": ";".join(sorted(set(tracker_cats))),
    }


def write_metadata_csv(records, path):
    """Write a list of metadata records to a CSV at ``path``, one row per
    app, using CSV_COLUMNS. Values are properly quoted by the csv module,
    so the ;-joined lists never break columns."""
    import csv as _csv

    with open(path, "w", newline="") as fh:
        writer = _csv.DictWriter(fh, fieldnames=CSV_COLUMNS,
                                 extrasaction="ignore")
        writer.writeheader()
        for record in records:
            writer.writerow(metadata_to_row(record))
