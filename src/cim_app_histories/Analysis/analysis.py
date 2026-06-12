"""
Larger analyis
See: class Analysis https://github.com/androguard/androguard/blob/master/androguard/core/analysis/analysis.py
"""

from androguard.core.analysis.analysis import Analysis

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