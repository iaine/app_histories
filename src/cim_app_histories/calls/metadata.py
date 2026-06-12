from multiprocessing import Pool
import os
import pandas as pd

from loguru import logger
logger.remove()  # removes all loguru handlers
logger.add(lambda msg: None, level="CRITICAL")

from androguard.core.analysis.analysis import Analysis
from androguard.decompiler.decompile import DvClass
from androguard.core.dex import DEX
from androguard.core.apk import APK
from androguard.core.analysis.analysis import ExternalMethod

from localisation.localisation import Locales
from dex.dex import analyseDEX

import re

def main(apkname):

    results = {}
    a = APK(apkname)
    results['pkg'] = a.get_package()
    results['version_code'] = a.get_androidversion_code()
    results['android_name'] = a.get_androidversion_name()
    results['permissions'] = a.get_permissions()
    results['activities'] = a.get_activities()
    results['intents'] = a.get_intent_filters()
    results['localisation'] = l.get_files(a)
    ed = analyseDEX()
    dx = DEX(a)
    results['ab'] = ed.find_ab_by_package(dx)
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