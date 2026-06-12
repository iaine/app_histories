from multiprocessing import Pool
import os
import pandas as pd

from loguru import logger
logger.remove()  # removes all loguru handlers
logger.add(lambda msg: None, level="CRITICAL")


from localisation.localisation import Locales
from apk.apk import extractAPK
from dex.dex import analyseDEX

import re

def main(apkname):

    results = {}
    a = extractAPK(apkname)
    results['applicationname'] = a.applicationname()
    results['pkg'] = a.packagename()
    results['version_code'] = a.android_version_code()
    results['android_name'] = a.android_version_name()
    results['permissions'] = a.permissions()
    results['activities'] = a.activities()
    results['intents'] = a.intents()
    results['localisation'] = a.get_files()
    
    ed = analyseDEX(a)

    results['ab'] = ed.find_ab_by_package()
    l = Locales()

    return results
    
    

if __name__ == "__main__":
    r = []
    base = '/Users/iain/Desktop/scraper/apps/apk/'
    apks = [base + _apk for _apk in os.listdir(base) if _apk.endswith(".apk")]

    with Pool(6) as p:
        r.extend(p.map(main, apks))
    p.close()
    p.join() 
    texts = pd.DataFrame(r)
    texts.to_csv("", index=False)