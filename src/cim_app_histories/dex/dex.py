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

    # Builder/host fragments that signal a URL is being assembled rather
    # than stored as one literal. Java URL building rarely leaves a whole
    # https://host/path string in the constant pool; it is split across
    # const-string fragments fed into StringBuilder.append / Uri.Builder /
    # Retrofit / OkHttp, so http_strings (which only matches whole-URL
    # literals) misses them.
    _URL_BUILDER_HINTS = (
        "StringBuilder", "Uri$Builder", "Uri;->", "HttpUrl",
        "Request$Builder", "Retrofit", "okhttp3", "HttpURLConnection",
        ".append", "buildUpon",
    )
    # Framework capture APIs. The presence of an *invoke* instruction
    # targeting one of these class descriptors is direct evidence the app
    # records audio in Java/Kotlin -- which native-.so scanning cannot see
    # (e.g. Otter: no audio .so, records via AudioRecord in the DEX). These
    # are class-descriptor fragments as they appear in invoke operands
    # ("Landroid/media/AudioRecord;->startRecording..."). Framework class
    # names survive R8/ProGuard (only app classes are renamed), so this is
    # robust to the obfuscation that defeats app-symbol heuristics.
    _AUDIO_CAPTURE_APIS = (
        "Landroid/media/AudioRecord",
        "Landroid/media/MediaRecorder",
        "Landroid/media/projection/MediaProjection",
    )
    # A fragment that plausibly belongs to a URL: a host-ish token, a path
    # segment, a scheme, or a query piece.
    _URL_FRAGMENT_RE = re.compile(
        r"^(https?://|/|[A-Za-z0-9.-]+\.[A-Za-z]{2,}|[?&][\w%-]+=?)")
    _HOSTISH_RE = re.compile(r"^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")

    def _iter_method_string_consts(self):
        """Yield (method, [string constants in its body]) for every method
        that has bytecode. String literals are read from const-string
        instruction operands, in textual order, so adjacent fragments that
        are appended together stay adjacent."""
        for method in self.dex.get_methods():
            try:
                code = method.get_code()
                if code is None:
                    continue
            except Exception:
                continue
            consts, builderish = [], False
            try:
                for ins in method.get_instructions():
                    name = ins.get_name()
                    out = ins.get_output() or ""
                    if name.startswith("const-string"):
                        # operand text is rendered like: v3, 'fragment'
                        m = re.search(r"'(.*)'\s*$", out)
                        if m:
                            consts.append(m.group(1))
                    elif name.startswith("invoke"):
                        if any(h in out for h in self._URL_BUILDER_HINTS):
                            builderish = True
            except Exception:
                continue
            if consts:
                yield method, consts, builderish

    def find_built_urls(self):
        """Find URLs assembled at runtime from fragments (StringBuilder,
        Uri.Builder, Retrofit/OkHttp), which http_strings cannot see.

        Strategy (static, best-effort): within each method that invokes a
        URL-builder API, concatenate its string-constant fragments in
        order and also pair scheme/host fragments with following path
        fragments. Returns candidate URLs plus the looser host+path joins,
        de-duplicated.

        These are CANDIDATES: static fragment-stitching cannot know the
        real runtime concatenation order or values supplied by variables,
        so treat results as "this method assembles a URL towards this
        host/path", not as a verified endpoint.
        """
        candidates = set()
        for method, consts, builderish in self._iter_method_string_consts():
            # whole-literal URLs caught here too (cheap), but the value is
            # in the builder case
            joined = "".join(consts)
            for u in re.findall(r"https?://[^\s\"'<>]+", joined):
                candidates.add(u)

            if not builderish:
                continue

            # stitch a scheme/host fragment to subsequent path/query frags
            base = None
            for frag in consts:
                if frag.startswith("http://") or frag.startswith("https://"):
                    base = frag.rstrip("/")
                elif self._HOSTISH_RE.match(frag):
                    base = "https://" + frag.rstrip("/")
                elif base and self._URL_FRAGMENT_RE.match(frag):
                    sep = "" if frag.startswith(("/", "?", "&")) else "/"
                    candidates.add(base + sep + frag.lstrip())
                    # keep extending the same base for further path parts
                    if frag.startswith("/"):
                        base = base + frag.rstrip("/")
        return sorted(candidates)

    def all_urls(self):
        """Union of literal URLs (http_strings) and runtime-assembled URL
        candidates (find_built_urls). The practical entry point for URL
        extraction across both styles."""
        return sorted(set(self.http_strings()) | set(self.find_built_urls()))

    def audio_inputs(self):
        """Capture inputs evidenced by framework API calls in the DEX.

        Returns a dict ``{input_id: set(api names)}`` -- e.g.
        ``{"microphone": {"AudioRecord"}}`` -- where the evidence is an
        *invoke* instruction targeting a known capture class. This finds
        Java/Kotlin audio capture that native-.so string scanning misses
        (the Otter case: records via AudioRecord, ships no audio library).

        The check is on the invoke operand only, so the bare class name
        appearing as a string constant does NOT count -- a call, not a
        mention. Best-effort and static: presence of the call path, not
        proof it executes at runtime.

        Note: MediaRecorder can also record video-with-audio, so counting
        it toward microphone may occasionally over-claim; kept simple here
        (a later refinement can inspect the audio-source setter).
        """
        found = {}
        # Real DEX: get_methods() yields MethodIdItem (no code). The methods
        # that carry bytecode are the EncodedMethods; instructions come from
        # code.get_bc().get_instructions(). (A stub in tests may expose the
        # simpler get_instructions() directly, so support both.)
        try:
            methods = self.dex.get_encoded_methods()
        except AttributeError:
            methods = self.dex.get_methods()
        for method in methods:
            try:
                code = method.get_code()
                if code is None:
                    continue
                if hasattr(code, "get_bc"):
                    instructions = code.get_bc().get_instructions()
                else:
                    instructions = method.get_instructions()
                for ins in instructions:
                    if not ins.get_name().startswith("invoke"):
                        continue
                    out = ins.get_output() or ""
                    for api in self._AUDIO_CAPTURE_APIS:
                        if api in out:
                            found.setdefault("microphone", set()).add(
                                api.rsplit("/", 1)[-1])
            except Exception:
                continue
        return found

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

    #-------- Trackers ---------------

    @staticmethod
    def _load_trackers():
        '''
        Load the tracker signature table packaged alongside this module
        (trackers.csv: signature,name,category). Loaded once and cached
        on the class so repeated analyseDEX instances across a corpus do
        not re-read the file.
        '''
        import csv
        path = os.path.join(os.path.dirname(__file__), "trackers.csv")
        trackers = []
        with open(path, newline="") as fh:
            for row in csv.DictReader(fh):
                sig = (row.get("signature") or "").strip()
                if sig:
                    trackers.append({
                        "signature": sig,
                        "name": (row.get("name") or "").strip(),
                        "category": (row.get("category") or "").strip(),
                    })
        return trackers

    @classmethod
    def trackers(cls):
        '''Tracker signature table (loaded once, cached on the class).'''
        cached = cls.__dict__.get("_TRACKERS")
        if cached is None:
            cached = cls._load_trackers()
            cls._TRACKERS = cached
        return cached

    def find_trackers(self):
        '''
        Third-party tracker SDKs present in this dex.

        Uses the same anchored prefix matching as find_ab_by_package (a
        signature matches a class equal to it or in a subpackage of it),
        so a tracker is reported only when its package is actually shipped
        in the app. Returns the full tracker descriptor (signature, name,
        category) for each match, so callers can group by category
        (advertising, analytics, crash_reporting, ...).

        :return: list of {"signature", "name", "category"} for matches
        '''
        names = self.class_names()
        return [t for t in self.trackers()
                if any(x == t["signature"] or x.startswith(t["signature"] + ".")
                       for x in names)]
    
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