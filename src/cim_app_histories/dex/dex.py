"""
Methods to work on the DEX code. 

Starts with extracting dex code from apk then moves onto 
methods to work with the dex code.
"""
import networkx as nx
import os
import re
import sys

from loguru import logger as log

##log.add(level="CRITICAL")

from androguard.core.dex import DEX
from androguard.core.analysis.analysis import ExternalMethod

from ..general.exception import CastException

class analyseDEX():

    def __init__(self, apk):
        try:
            self.dex = DEX(apk)
        except CastException as ce:
            log.critical("DEX cannot be created")

    def find_methods(self):
        '''
        Get strings from DEX code

        Args:
            dex - the DEX file. 
        
        Return:
            list
        '''
        strs = []
        try:
            for string in self.dex.get_methods():
                strs.extend(re.findall(r'https?://\S+', string))
                
        except Exception:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)

        return strs

    def http_strings(self):
        '''
        Get strings from DEX code

        Args:
            dex - the DEX file. 
        
        Return:
            list
        '''
        strs = []
        try:
            for string in self.dex.get_strings():
                strs.extend(re.findall(r'https?://\S+', string))
        except Exception:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)

        return strs

    def methods(self):
        return [method.get_name() for method in self.dex.get_methods()]

    def get_classes(self, string_find):
        '''
        Function to find string in class name
        '''
        classes = []
        for cls in self.dex.get_classes():
            if string_find in cls.name:
                classes.extend([cls.name])
        return classes

    def dynamic_detection(self):
        '''
           Finding dynamic loading classes. 
           Loading apps?
        '''
        dynamic_methods = [
            "dalvik.system.DexClassLoader",
            "dalvik.system.PathClassLoader"
        ]

        dynamic = []

        for method in self.dex.get_methods():
            for dyn_method in dynamic_methods:
                if dyn_method in str(method.get_code()):
                    dynamic.extend(method.name)
        return dynamic
    
    #-------- AB testing ---------------

    AB_CLASSES = ['com.playnomics.android.sdk.Playnomics', 'com.abtasty', 'io.adapty',
                  'com.adobe.marketing.mobile', 'com.amplitude',
                  'com.apphud.ApphudSDK-Android', 'com.applause', 
                  'com.apptimize.Apptimize', 'com.apptimize.ApptimizeTest',
                  'com.batch.android', 'com.leanplum', 'com.configcat',
                  'com.gameanalytics.sdk', 'com.gameofwhales.gow',
                  'com.gameofwhales.sdk', 'com.google.firebase',
                  'com.huawei.hwid', 'com.huawei.hms', 'com.huawei.agconnect',
                  'com.huawei.updatesdk', 'com.kameleoon', 'com.launchdarkly',
                  'com.mparticle', 'com.optimizely.ab', 'com.posthog',
                  'io.qonversion.android.sdk', 'com.sensorsdata.abtest.SensorsABTest',
                  'com.sensorsdata.abtest.SensorsABTestConfigOptions',
                  'com.sensorsdata.analytics.android', 'io.split.client',
                  'com.statsig.androidsdk', 'com.swrve.sdk.android', 'com.taplytics.sdk',
                  'com.umeng.commonsdk', 'com.umeng.analytics.game', 'com.uxcam.UXCam',
                  'com.uxcam.datamodel.UXConfig', 'com.vwo.mobile']

    def class_names(self):
        '''
        Class names in dotted form (com.abtasty.Foo). DEX stores them as
        type descriptors (Lcom/abtasty/Foo;), so comparing dotted
        signatures against raw names can never match.
        '''
        return [str(c.get_name())[1:-1].replace("/", ".")
                for c in self.dex.get_classes()]

    def find_ab_by_package(self):
        '''
        A/B-testing SDK signatures present in this dex.

        Anchored prefix matching: a signature matches a class equal to it
        or in a subpackage of it -- substring matching over-counted
        (io.split matched studio.splitties).

        :return: list of matched signatures from AB_CLASSES
        '''
        names = self.class_names()
        return [tr for tr in self.AB_CLASSES
                if any(x == tr or x.startswith(tr + ".") for x in names)]
    
    #---------Callgraph ---------------

    def callgraph(self, class_to_call):
        """
            Find the associated methods with the graph. 
        """

        CFG = nx.DiGraph()

        for m in self.dex.find_methods(classname=class_to_call):
            orig_method = m.get_method()
 
            is_this_external = False
            if isinstance(orig_method, ExternalMethod):
                is_this_external = True
                
            CFG.add_node(orig_method, external=is_this_external)

            for other_class, callee, offset in m.get_xref_to():
                is_external = False
                if isinstance(callee, ExternalMethod):
                    is_external = True


                if callee not in CFG.nodes:
                    CFG.add_node(callee, external=is_external)

                if not CFG.has_edge(orig_method, callee):
                    CFG.add_edge(orig_method, callee)

        internal = []
        external = []

        for n in CFG.node:
            if isinstance(n, ExternalMethod):
                external.append(n)
            else:
                internal.append(n)

        return CFG