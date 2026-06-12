"""
Methods to work on the DEX code. 

Starts with extracting dex code from apk then moves onto 
methods to work with the dex code.
"""
import os
import re
import sys

from androguard.core.dex import DEX

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