"""
Functions to work on the DEX code
"""
from androguard.core.dex import DEX
import re
#from androguard.core.analysis import Analysis

class analyseDEX():

    def __init__(self):
        pass

    def extract(self, apk):
        '''
        Function to extract DEX code
        '''
        return DEX(apk)

    def strings(self, dexcode):
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
        return dex.get_methods()

    def cg(self, dex, classname):
        """
        Larger analyis
        See: class Analysis https://github.com/androguard/androguard/blob/master/androguard/core/analysis/analysis.py
        """
        a = Analysis(dex)
        a.find_methods(classname)