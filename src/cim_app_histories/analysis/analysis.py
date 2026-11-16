"""
Larger analyis
See: class Analysis https://github.com/androguard/androguard/blob/master/androguard/core/analysis/analysis.py
"""

from androguard.core.analysis.analysis import Analysis, ExternalMethod

class Analyse:

    def create_analysis_object(self, dex):
        """
            Convert DEX object into analysis object
        """

        dx = Analysis()
        dex_objects = []

        dx.add(dex)
        dex_objects.append(dex)

        dx.create_xref()

        return dx

    #---------Callgraph ---------------

    def callgraph(self, dex, class_to_call, tracker_function=""):
        """
            Find the associated methods with the graph. 
            Args:
                dex: The DEX object to be analyzed.
                class_to_call: The class name for which to build the call graph.
                tracker_function: A function to filter tracker methods (optional).
            Returns:
                A call graph object representing the relationships between methods 
                in the specified class.
        """

        CFG = []

        for m in dex.find_methods(classname=class_to_call):
            orig_method = m.get_method()
 
            is_this_external = False
            if isinstance(orig_method, ExternalMethod):
                is_this_external = True
                
            CFG['nodes'].extend(orig_method, external=is_this_external, tracker=tracker_function)

            for _, callee, _ in m.get_xref_to():
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