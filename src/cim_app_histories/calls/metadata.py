"""
Metadata workflow: one compact record per APK.

Collects app identity (name, package, versions), manifest surface
(permissions, activities, intents), localisation coverage, and
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
        "intents": a.intents(),
        "localisation": a.get_files(),
    }

    # A/B detection must scan every classes*.dex: most large apps are
    # multidex, and scanning only the first dex undercounts SDKs.
    ab = set()
    for buff in a.apk.get_all_dex():
        ab.update(analyseDEX(buff).find_ab_by_package())
    results["ab"] = sorted(ab)

    return results
