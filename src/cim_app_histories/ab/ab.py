"""
Methods for tracking AB testing

AB_CLASSES is further described on the App Histories site
"""

class AB():

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
    
    def __init__(self):
        pass

    def find_ab_by_package(self, classes):
        '''
            Files to Inspect: Look for experimentation frameworks, often indicated by the use of libraries like Firebase A/B Testing or flag-based components in the code.
        
            Also look at the tracker listing from Python. 

            :param classes - DEX classes from dex package. 
            :return list of common packages from AB testing
        '''

        common = []
        for tr in self.AB_CLASSES:
            if any(tr in x for x in classes):
                common.append(tr)

        return common
