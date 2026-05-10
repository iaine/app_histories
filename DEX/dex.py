"""
Functions to work on the DEX code
"""
from androguard.core.dex import DEX

class analyseDEX():

    def extract(self, apk):
        '''
        Function to extract DEX code
        '''
        return DEX(apk)

    def find_http_string(dex):
        strs = []
        try:
            #strs = [string for string in dex.get_strings() if  re.findall(r'https?://\S+', string)]
            for string in dex.get_strings():
                strs.extend(re.findall(r'https?://\S+', string))
        except Exception:
            print(Exception)
            pass

        return strs

    def callgraph(dx, class_name):
        '''
        Find the network callgraph
        '''
        try:
            CFG = nx.DiGraph()

            for m in dx.find_methods(classname=class_name):
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
            print(e)