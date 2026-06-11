"""
Functions to work on the DEX code
"""
from androguard.core.dex import DEX
import re
import os

from androguard.core.analysis import Analysis

class analyseDEX():

    def __init__(self):
        pass

    def extract(self, apk):
        '''
        Function to extract DEX code
        '''
        return DEX(apk)

    def find_methods(self, dexcode, classname):
        '''
        Get strings from DEX code

        Args:
            dex - the DEX file. 
        
        Return:
            list
        '''
        strs = []
        try:
            for string in dexcode.get_methods():
                strs.extend(re.findall(r'https?://\S+', string))
                
        except Exception:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)

        return strs

    def http_strings(self, dexcode):
        '''
        Get strings from DEX code

        Args:
            dex - the DEX file. 
        
        Return:
            list
        '''
        strs = []
        try:
            for string in dexcode.get_strings():
                strs.extend(re.findall(r'https?://\S+', string))
        except Exception:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)

        return strs

    def callgraph(self, dx, class_name):
        '''
        Find the network callgraph
        '''
        try:
            CFG = nx.DiGraph()

            for m in Analysis(dx).find_methods(classname=class_name):
                orig_method = m.get_method()

                is_this_external = False
                if isinstance(orig_method, ExternalMethod):
                    is_this_external = True

                CFG.add_node(orig_method, external=is_this_external)

                for _, callee,_ in m.get_xref_to():
                    is_external = False
                    if isinstance(callee, ExternalMethod):
                        is_external = True

                    if callee not in CFG.nodes:
                        CFG.add_node(callee, external=is_external)

                    if not CFG.has_edge(orig_method, callee):
                        CFG.add_edge(orig_method, callee)

            return CFG
        except Exception as e:
            exc_type, exc_obj, exc_tb = sys.exc_info()
            fname = os.path.split(exc_tb.tb_frame.f_code.co_filename)[1]
            print(exc_type, fname, exc_tb.tb_lineno)

    def methods(self, dex):
        return [method.get_name() for method in dex.get_methods()]

    def get_classes(self, dex, string_find):
        '''
        Function to find string in class name
        '''
        classes = []
        for cls in dex.get_classes():
            if string_find in cls.name:
                classes.extend([cls.name])
        return classes

    def cg(self, dex, classname):
        """
        Larger analyis
        See: class Analysis https://github.com/androguard/androguard/blob/master/androguard/core/analysis/analysis.py
        """
        for d in dex.find_methods(classname):
            pass

    def dynamic_detection(self, dex):
        '''
           Finding dynamic loading classes. 
           Loading apps?
        '''
        dynamic_methods = [
            "dalvik.system.DexClassLoader",
            "dalvik.system.PathClassLoader"
        ]

        dynamic = []

        for method in dex.get_methods():
            for dyn_method in dynamic_methods:
                if dyn_method in str(method.get_code()):
                    dynamic.extend(method.name)
        return dynamic