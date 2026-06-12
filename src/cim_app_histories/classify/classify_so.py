"""
    Function to classify SO files
"""
import math
import re
from urllib.parse import urlparse

from androguard.core.analysis.analysis import Analysis
from androguard.core.dex import DEX
from androguard.core.apk import APK

from .safe_class import SafeMethod
from .classify_url import ClassifyURL

class ClassifySO():

    URL_REGEX = re.compile(r"https?://[a-zA-Z0-9\.\-_/:%?=&]+")

    MODEL_EXT = [".tflite", ".pb", ".onnx", ".model", ".bin", ".dat"]

    # ✅ Multilingual keywords
    MULTI_LANG_KEYWORDS = {
        "audio": ["audio", "sound", "voice", "mic",
                "音频", "声音", "语音", "麦克风",
                "音声", "マイク",
                "음성", "소리", "마이크"],

        "face": ["face", "facial", "landmark",
                "人脸", "面部",
                "顔", "顔検出",
                "얼굴"],

        "ml": ["model", "classify", "detect", "recognize",
            "模型", "分类", "检测", "识别",
            "モデル", "分類",
            "모델", "분류"]
    }

    # ✅ Vendors (including Chinese)
    AI_VENDORS = {
        "google": ["tensorflow", "mlkit"],
        "huawei": ["huawei", "hms"],
        "tencent": ["tencent", "youtu"],
        "baidu": ["baidu", "aip"],
        "alibaba": ["alibaba"],
        "megvii": ["megvii", "faceplusplus"],
        "sensetime": ["sensetime"]
    }

    # ✅ Keywords
    ML_KEYWORDS = ["classify", "detect", "recognize", "predict", "run", "process"]

    AUDIO_KEYWORDS = ["record", "capture", "speech", "stream"]

    AUDIO_INPUT_PATTERNS = ["audiorecord", "microphone", "audio"]

    ML_CATEGORIES = {
        "vision": ["image", "bitmap", "ocr", "detect", "识别"],
        "recommendation": ["recommend", "rank", "feed", "推荐"],
        "nlp": ["text", "language", "token", "文本"],
        "speech": ["speech", "asr", "语音"],
        "audio": AUDIO_KEYWORDS + AUDIO_INPUT_PATTERNS,
        "face": MULTI_LANG_KEYWORDS.get("face", [])
    }

    #re patterns
    PRINTABLE_RE = re.compile(rb"[ -~]{3,}")
    PRINTABLE_CACHE = {}

    #def safe_unpack_xref(item):
    #    if not isinstance(item, tuple):
    #        return None

    #    if len(item) == 3:
    #       cls, method, offset = item
    #    elif len(item) == 2:
    #        cls, method = item
    #        offset = None
    #    else:
    #        return None

    #    return cls, method, offset

    def to_safe_method(obj):
        if obj is None:
            return None

        # Already wrapped
        if isinstance(obj, SafeMethod):
            return obj

        # MethodAnalysis
        if hasattr(obj, "get_method"):
            return SafeMethod(obj)

        # EncodedMethod
        if hasattr(obj, "get_code"):
            class Dummy:
                def __init__(self, m):
                    self._m = m

                def get_method(self):
                    return self._m

            return SafeMethod(Dummy(obj))

        return None

    #def iter_safe_methods(dx):
    #    for m in dx.get_methods():
    #        sm = to_safe_method(m)
    #        if not sm:
    #            continue
    #        yield sm


    def get_all_strings(self, dx):
        if not hasattr(dx, "strings"):
            return []

        if isinstance(dx.strings, dict):
            return list(dx.strings.keys())

        if isinstance(dx.strings, list):
            return dx.strings

        return []

    def find_ai_models_with_inputs(
        self, 
        dx
    ):
        """
        AI model detection + input inference
        """

        strings = self.get_all_strings(dx)
        models = {}

        for i, s in enumerate(strings):

            if not isinstance(s, str):
                continue

            s = s.strip()

            if not self.is_real_model(s):
                continue

            if self.is_noise(s):
                continue

            if s in models:
                continue

            # ✅ local context only
            context = self.get_local_context(strings, i)

            categories = self.classify_categories(s + " " + context)
            inputs = self.infer_inputs(categories)

            all_strings = strings
            models[s] = {
                "model": s,
                "type": self.fingerprint_model(s),
                "vendor": self.detect_vendor(s, all_strings),
                "ml_categories": categories,
                "inputs": inputs
            }

        return list(models.values())

    def infer_inputs(self, categories):
        inputs = set()

        if "audio" in categories or "speech" in categories:
            inputs.add("audio")

        if "vision" in categories or "face" in categories:
            inputs.add("image")

        if "nlp" in categories:
            inputs.add("text")

        if "recommendation" in categories:
            inputs.add("user_data")

        if not inputs:
            inputs.add("unknown")

        return sorted(inputs)
        
    def classify_categories(self, text):
        """
                Classify if AI due to strings.
        """
        t = text.lower()
        cats = set()

        for cat, kws in self.ML_CATEGORIES.items():
            if any(k in t for k in kws):
                cats.add(cat)

        for cat, words in self.MULTI_LANG_KEYWORDS.items():
            if any(w.lower() in t for w in words):
                cats.add(cat)

        if any(k in t for k in self.ML_KEYWORDS):
            cats.add("ml")

        return sorted(cats)
        
    def is_noise(self, s):
        """
                Remove non-AI possibilities
        """
        s = s.lower()

        return any(k in s for k in [
                "viewmodel",
                "proto",
                "dto",
                "adapter",
                "button",
                "banner",
                "info",
                "config",
                "holder",
                "listener",
                "layout",
                "manager"
        ])


    def fingerprint_model(self, s):
        """
            Heuristic for determining model based on file extension
        """
        s = s.lower()

        if ".tflite" in s:
            return "tensorflow_lite"
        if ".onnx" in s:
            return "onnx"
        if ".pt" in s:
            return "pytorch"
        if ".nb" in s:
            return "huawei_model"

        return "generic_model"

    def detect_vendor_from_name(self, name):

        n = name.lower()

        if any(k in n for k in [
            "byte", "tt", "bytedance"
        ]):
            return "bytedance"

        if any(k in n for k in [
            "tenny", "tnn"
        ]):
            return "tencent"

        if "paddle" in n:
            return "baidu"

        if "hiai" in n:
            return "huawei"
            
        if "tflite" in n:
            return "google"

        if "onnx" in n:
            return "onnx"

        if "pytorch" in n or ".pt" in n:
            return "meta"

        if ".nb" in n:
            return "huawei"

        return None
        
    def detect_vendor_from_strings(self, strings):
        """Detect a vendor from extracted strings.

        Accepts a list of strings (preferred) or a single pre-joined
        string. Joining is only performed on lists: ``" ".join`` on a
        *string* would interleave every character with spaces and make
        every keyword check silently fail.
        """
        if isinstance(strings, str):
            text = strings.lower()
        else:
            text = " ".join(strings).lower()

        if any(k in text for k in [
            "bytedance", "ttnet", "toutiao"
        ]):
            return "bytedance"

        if any(k in text for k in [
            "tencent", "wechat", "tnn"
        ]):
            return "tencent"

        if any(k in text for k in [
            "huawei", "hiai"
        ]):
            return "huawei"

        if any(k in text for k in [
            "paddlepaddle"
        ]):
            return "baidu"
            
        if "tensorflow" in text or "tflite" in text:
            return "google"

        if "huawei" in text or "hiai" in text:
            return "huawei"

        if "pytorch" in text or "torch" in text:
            return "meta"

        if "onnx" in text:
            return "onnx"

        if "ncnn" in text:
            return "tencent"

        return None
        
    def detect_vendor(self, model_name, global_strings=None):
        """
            Detect vendor based on file extension
        """

        t = (model_name or "").lower()

        v = self.detect_vendor_from_name(t)
        if v:
            return v
            
        if global_strings:
            v = self.detect_vendor_from_strings(global_strings)
            if v:
                return v

        return "unknown"
        
    def is_real_model(self, s):
        s = s.lower()

        # ✅ strong signals only
        if any(ext in s for ext in self.MODEL_EXT):
            return True

        # ✅ ML-specific naming patterns
        if any(k in s for k in [
            "tflite", "onnx", "pytorch", "torch", "nn", "weights"
        ]):
            return True

        # ✅ file-like patterns
        if "/" in s or "." in s:
            if any(k in s for k in ["model", "weight", "param"]):
                return True

        return False

    def get_local_context(self, strings, index, window=5):
        start = max(0, index - window)
        end = min(len(strings), index + window)
        return " ".join(strings[start:end])

    def extract_vendors(self, models):
        vendors = set()

        for m in models:
            v = m.get("vendor")

            if not v or v == "unknown":
                continue

            vendors.add(v)

        return sorted(vendors)

    def remove_non_model_files(self, models):

        cleaned = []

        for m in models:
            name = (m.get("model") or "").lower()

            if name.endswith(".dex"):
                continue

            if "dex" in name and len(name) < 30:
                continue

            cleaned.append(m)

        return cleaned

    def is_noise_asset(self, s):
        s = s.lower()

        # too deep / path-like → usually not real models
        if s.count("/") > 3:
            return True

        # contains config-like words
        if any(k in s for k in [
            "config", "settings", "layout", "template",
            "description", "metadata", "resource"
        ]):
            return True

        return False

    def is_valid_asset_model(self, s):
        s = s.lower()

        if not s.startswith("assets/"):
            return False

        # ✅ REQUIRE strong indicators
        strong_indicators = [
            ".tflite", ".onnx", ".pt", ".nb",
            "model", "weight", "tensor"
        ]

        if not any(k in s for k in strong_indicators):
            return False

        # ❌ reject obvious non-model assets
        if any(s.endswith(ext) for ext in [
            ".json", ".xml", ".txt", ".html", ".js"
        ]):
            return False

        return True

    def remove_asset_noise(self, models):

        cleaned = []

        for m in models:
            name = (m.get("model") or "").lower()

            if name.startswith("assets/"):

                if not self.is_valid_asset_model(name):
                    continue

            cleaned.append(m)

        return cleaned


    def is_valid_model_name_provide_string(self, s):
        if not isinstance(s, str):
            return False

        s = s.strip()
        lower = s.lower()

        if lower.endswith(".dex") or "/.dex" in lower:
            return False

        
        if s.startswith("{") and s.endswith("}"):
            return False

        if len(s) > 200:
            return False
        
        if lower.startswith("assets/"):
            if self.is_noise_asset(lower):
                return False
            
            return self.is_valid_asset_model(lower)

        # ✅ strong signals
        if any(ext in lower for ext in [".tflite", ".onnx", ".pt", ".nb"]):
            return True

        # ✅ medium signals (important for TikTok)
        ML_HINTS = [
            "model",
            "weight",
            "tensor",
            "predict",
            "classifier",
            "embedding"
        ]

        if any(h in lower for h in ML_HINTS):
            return True

        return False

    def infer_inputs_from_path(self, name):

        n = name.lower()

        if "blinkcard" in n or "ocr" in n:
            return ["image"]

        if "audio" in n:
            return ["audio"]

        return ["other"]

    def detect_sdk_from_path(self, path):

        path = self.ensure_string(path).lower()

        SDK_MAP = {
            "microblink": "microblink",
            "blinkcard": "microblink",

            "mlkit": "google",
            "mediapipe": "google",

            "hiai": "huawei",
            "paddle": "baidu",

            "opencv": "opencv"
        }

        for key, vendor in SDK_MAP.items():
            if key in path:
                return vendor

        return None

    def looks_like_hashed_model(self, name):

        # Match Model_<long hex>
        return re.search(r'model_[a-f0-9]{16,}', name.lower()) is not None

    def is_proprietary_model_file(self, path):
        """
        Find proprietary models. 
        """

        path = self.ensure_string(path).lower()

        if any(path.endswith(ext) for ext in [
            ".dat", ".bin", ".pkg", ".model", ".rtttl"
        ]):
            return True

        return False


    def is_sdk_model_path(self, s):
        """
            Function to detect some SDKs
        """
        s = s.lower()

        return any(vendor in s for vendor in [
            "microblink",
            "blinkcard",
            "mlkit",
            "mediapipe",
            "vision",
            "ocr"
        ])

    def detect_sdk_model(self, path):
        """
            Detect SDKs and models in assets
        """

        path = self.ensure_string(path).lower()

        vendor = self.detect_sdk_from_path(path)

        if not path.startswith("assets/"):
            return None

        # ✅ strong signals
        if self.looks_like_hashed_model(path):
            return vendor or "sdk_unknown"

        if self.is_proprietary_model_file(path) and vendor:
            return vendor

        # ✅ fallback: vendor + model keyword
        if vendor and "model" in path:
            return vendor

        return None

    def is_known_non_model(self, s):
        """
            Function to remove some noise early. 
            Gets rid of code files. 
        """
        s = s.lower()

        if s.endswith(".dex"):
            return True

        if s.endswith(".xml"):
            return True

        if s.endswith(".json"):
            return True

        if s.endswith(".txt"):
            return True
        
        if s.endswith(".html") or s.endswith(".js"):
            return True

        return False

    def has_ml_runtime_patterns(self, strings):
        """
            Function to read if machine patterns in runtime
        """

        indicators = [
            # ✅ inference lifecycle
            "interpreter", "predict", "inference",
            "invoke", "execute", "run",

            # ✅ tensors
            "tensor", "input_tensor", "output_tensor",
            "shape", "dimension",

            # ✅ model handling
            "load_model", "load_param",
            "graph", "net",

            # ✅ memory ops (common in ML)
            "allocate", "buffer", "resize",

            # ✅ math ops
            "conv", "relu", "softmax", "matmul"
        ]

        hits = 0

        for s in strings:
            s = s.lower()
            for ind in indicators:
                if ind in s:
                    hits += 1

        return hits >= 4  # threshold

    def has_ml_function_signatures(self, strings):
        """
            Function to detect functin signatures
        """

        patterns = [
            "create_interpreter",
            "run_inference",
            "forward",
            "predict",
            "net_run",
            "model_execute"
        ]

        return any(p in s.lower() for s in strings for p in patterns)

    def detect_ml_math_patterns(self, strings):
        """
            Function to detect mathemetical terms
        """

        math_terms = [
            "conv", "relu", "batchnorm",
            "sigmoid", "tanh",
            "matmul", "gemm"
        ]

        count = 0

        for s in strings:
            s = s.lower()
            for m in math_terms:
                if m in s:
                    count += 1

        return count >= 3

    def detect_tensor_structure(self, strings):
        """
            Function to detect strings about tensors
        """

        indicators = [
            "stride",
            "shape",
            "ndim",
            "channel",
            "width",
            "height"
        ]

        return sum(
            1 for s in strings for i in indicators if i in s.lower()
        ) >= 3

    def detect_proprietary_ml_runtime(self, data):
        """
        Helper function to ML
        """

        strings = self.extract_strings(data)

        score = 0

        if self.has_ml_runtime_patterns(strings):
            score += 3

        if self.has_ml_function_signatures(strings):
            score += 2

        if self.detect_ml_math_patterns(strings):
            score += 2

        if self.detect_tensor_structure(strings):
            score += 2

        # threshold
        return score >= 2

    def is_valid_model_name(self, s):
        """
           checks if a model name is valid
        """
        if not isinstance(s, str):
            return False

        s = s.strip()
        lower = s.lower()
        
        if self.is_known_non_model(s):
            return False
        
        if lower.endswith((".dex", ".apk", ".jar", ".so")):
            return False
        
        if lower.startswith("classes") and lower.endswith(".dex"):
            return False
        
        # JSON fragments / configs
        if s.startswith("{") or s.endswith("}"):
            return False

        if "\"description\"" in lower:
            return False

        if ":" in s and len(s) > 80:
            return False

        if len(s) > 120:
            return False

        # looks like key-value text
        if re.search(r'".*":', s):
            return False

        # contains too many spaces (sentence-like)
        if len(s.split()) > 6:
            return False

        # ML file endings
        if any(ext in lower for ext in [".tflite", ".onnx", ".pt", ".nb"]):
            return True

        # Search for model function names
        if re.match(r'^[a-zA-Z0-9_\-\.]+$', s):
            if any(k in lower for k in [
                "model", "weight", "tensor", "net", "classifier", "embedding"
            ]):
                return True

        return False

    def normalize_inputs(self, inputs):
        if not inputs:
            return ["other"]

        valid = {"audio", "image", "text", "user_data"}

        cleaned = [i for i in inputs if i in valid]

        return cleaned if cleaned else ["other"]

    def convert_ai_models_for_ui(self, models, global_strings=None):

        vendors = self.detect_app_vendors(global_strings)

        if len(vendors) == 1:
            inferred_vendor = list(vendors)[0]
        else:
            #inferred_vendor = "multi"
            inferred_vendor = ",".join(sorted(vendors))
        converted = []

        for m in models:

            vendor = m.get("vendor")

            if not vendor or vendor == "unknown":
                vendor = self.detect_vendor(m.get("model"), global_strings)

            converted.append({
                "model": m.get("model"),
                "vendor": vendor,
                "inputs": self.normalize_inputs(m.get("inputs"))
            })

        return converted

    def detect_app_vendors(self, strings):
        if strings == None: return set()
        text = " ".join(strings).lower()

        vendors = set()

        if "tensorflow" in text:
            vendors.add("google")

        if "huawei" in text:
            vendors.add("huawei")

        if "pytorch" in text or "torch" in text:
            vendors.add("meta")

        if "onnx" in text:
            vendors.add("onnx")

        return vendors

    def fallback_vendor_from_model(self, model_name):
        m = model_name.lower()

        if "tflite" in m:
            return "google"

        if "onnx" in m:
            return "onnx"

        if "pytorch" in m or ".pt" in m:
            return "pytorch"

        if ".nb" in m:
            return "huawei"

        return "unknown"

    def has_valid_inputs(self, m):
        inputs = m.get("inputs", [])

        # reject models with ALL inputs (noise)
        if len(inputs) >= 4:
            return False

        return True

    def vendor_from_type(self, model_type):

        if model_type == "tflite":
            return "google"

        if model_type == "pytorch":
            return "meta"

        if model_type == "protobuf_model":
            return "generic"

        return "unknown"

    #testing files
    def sniff_binary_type(self, data):
        """
        Detect known media / structured binary types using signatures.
        Returns:
            "image", "audio", "video", "archive", or None
        """

        if not data or len(data) < 12:
            return None

        header = data[:32]

        # =========================
        # ✅ IMAGE DETECTION
        # =========================

        # JPEG
        if header.startswith(b"\xff\xd8\xff"):
            return "image"

        # PNG
        if header.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image"

        # WEBP
        if header.startswith(b"RIFF") and b"WEBP" in header:
            return "image"

        # =========================
        # ✅ AUDIO DETECTION
        # =========================

        # MP3 (ID3 tag)
        if header.startswith(b"ID3"):
            return "audio"

        # MP3 (frame sync)
        if header[:2] == b"\xff\xfb":
            return "audio"

        # WAV
        if header.startswith(b"RIFF") and b"WAVE" in header:
            return "audio"

        # OGG
        if header.startswith(b"OggS"):
            return "audio"

        # =========================
        # ✅ VIDEO DETECTION
        # =========================

        # MP4 / MOV
        if b"ftyp" in header:
            return "video"

        # Matroska / WebM
        if header.startswith(b"\x1A\x45\xDF\xA3"):
            return "video"

        # =========================
        # ✅ ARCHIVE / COMPRESSED
        # =========================

        # ZIP
        if header.startswith(b"PK\x03\x04"):
            return "archive"

        # GZIP
        if header.startswith(b"\x1f\x8b"):
            return "archive"

        # =========================
        # ✅ UNKNOWN
        # =========================

        return None

    def is_ml_runtime(self, category, score):
        return category == "ml_runtime" and score >= 3

    def entropy(self, data):
        prob = [float(data.count(c)) / len(data) for c in set(data)]
        return -sum(p * math.log2(p) for p in prob)

    def has_ml_symbols(self, strings):

        indicators = [
            "interpreter",
            "allocate_tensors",
            "invoke",
            "inference",
            "nnapi"
        ]

        return any(i in s.lower() for s in strings for i in indicators)


    def is_elf(self, data):
        return data.startswith(b"\x7fELF")

    def is_model_blob(self, data):

        if len(data) < 50000:
            return False
        
        if self.is_elf(data):
            return False
        
        detected_type = self.sniff_binary_type(data)

        if detected_type in ["image", "audio", "video"]:
            return False

        e = self.entropy(data)

        # ML weights tend to be high entropy
        if 6.5 < e < 8.0:
            return True

        return False

    def is_known_ml_runtime_name(self, filename):
        name = filename.lower()

        return any(x in name for x in [
            "tenny", "tnn", "mnn", "ncnn"
        ])


    def get_pattern(self, min_len):
        if min_len not in self.PRINTABLE_CACHE:
            self.PRINTABLE_CACHE[min_len] = re.compile(
                rb"[ -~]{" + str(min_len).encode() + rb",}"
            )
        return self.PRINTABLE_CACHE[min_len]


    def extract_strings(self, data, min_len=3):
        """
        Extract strings from a binary file across UTF-8 and UTF-16
        """

        ascii_strings = self.get_pattern(min_len).findall(data)

        results = [
            s.decode("ascii", errors="ignore")
            for s in ascii_strings
        ]

        try:
            utf16 = data.decode("utf-16le", errors="ignore")
            results.extend([
                s for s in utf16.split("\x00")
                if len(s) >= min_len and s.isprintable()
            ])
        except:
            pass

        return results

    def scan_so_for_ml_patterns(self, binary_data):

        text = binary_data.decode(errors="ignore").lower()

        hits = []

        for k in [
            "tflite",
            "tensorflow",
            "onnx",
            "pytorch",
            "ncnn",
            "snpe",
            "nnapi"
        ]:
            if k in text:
                hits.append(k)

        return hits

    def is_tflite(self, data):
        return b"TFL3" in data[:16]

    @staticmethod
    def _read_varint(data, pos):
        """Read a protobuf varint at ``pos``.

        Returns (value, new_pos), or (None, new_pos) if the bytes do not
        form a valid varint (runs past the end, or exceeds 10 bytes).
        """
        result = 0
        shift = 0
        start = pos
        while pos < len(data):
            if pos - start >= 10:          # varints are at most 10 bytes
                return None, pos
            b = data[pos]
            result |= (b & 0x7F) << shift
            pos += 1
            if not (b & 0x80):
                return result, pos
            shift += 7
        return None, pos                   # ran off the end mid-varint

    def is_protobuf(self, data, max_fields=16, min_fields=3):
        """Heuristic check that ``data`` is a protobuf-serialised message.

        Protobuf has no magic number, so the previous check
        (``b"\\x08" in data[:2]``) matched any file whose first two bytes
        happened to contain 0x08 -- roughly 1 in 128 of all binaries --
        and massively over-counted "protobuf models".

        This version walks the wire format instead: it parses successive
        (tag, value) fields and requires that

        * every field number is plausible (1..99999),
        * every wire type is valid (0 varint, 1 fixed64, 2
          length-delimited, 5 fixed32 -- the deprecated group types 3/4
          and undefined 6/7 are rejected),
        * every length-delimited payload fits inside the buffer, and
        * the walk either consumes the buffer exactly or survives
          ``max_fields`` consecutive fields, having seen at least
          ``min_fields`` fields including one length-delimited field
          (real model files -- TF GraphDef, ONNX -- always contain
          length-delimited submessages).

        Random or non-protobuf data almost always fails the bounds check
        on a length-delimited field within the first few fields.
        """
        if not data or len(data) < 8:
            return False

        limit = len(data)
        pos = 0
        fields = 0
        seen_length_delimited = False

        while pos < limit and fields < max_fields:
            tag, pos = self._read_varint(data, pos)
            if tag is None:
                return False

            wire_type = tag & 0x07
            field_no = tag >> 3

            if field_no == 0 or field_no > 99999:
                return False

            if wire_type == 0:                       # varint
                value, pos = self._read_varint(data, pos)
                if value is None:
                    return False
            elif wire_type == 1:                     # fixed64
                pos += 8
                if pos > limit:
                    return False
            elif wire_type == 2:                     # length-delimited
                length, pos = self._read_varint(data, pos)
                if length is None or pos + length > limit:
                    return False
                pos += length
                seen_length_delimited = True
            elif wire_type == 5:                     # fixed32
                pos += 4
                if pos > limit:
                    return False
            else:                                    # 3/4 deprecated, 6/7 invalid
                return False

            fields += 1

        if fields < min_fields or not seen_length_delimited:
            return False

        # Either we parsed the whole buffer cleanly, or we survived
        # max_fields consecutive well-formed fields.
        return pos == limit or fields >= max_fields

    def is_pytorch(self, data):
        return b"pytorch" in data or b"torch" in data.lower()

    def classify_binary(self, data):
        
        if self.is_tflite(data):
            return "tflite"

        if self.is_pytorch(data):
            return "pytorch"

        if self.is_protobuf(data):
            return "protobuf_model"

        return "unknown_binary"

    def detect_ml_binaries (self, apk):

        results = []

        for f in apk.get_files():
            data = apk.get_file(f)
            file_size = len(data)
            if file_size < 50000:
                continue

            if f.endswith(".so"):
                
                category, score = self.classify_so_pre(f, data)

                if category not in ["ml_runtime", "native"]:
                    continue
                
                if category == "ml_runtime":
                    results.append({
                        "file": f,
                        "type": "ml_runtime",
                        "confidence": "high" if score >= 4 else "medium"
                    })

                if self.detect_proprietary_ml_runtime(data):
                    results.append({            
                        "file": f,            
                        "type": "ml_runtime",            
                        "confidence": "high"        
                        })  

                    continue
                
                ml_hits = self.scan_so_for_ml_patterns(data)

                if ml_hits:                    
                    results.append({                        
                        "file": f,                        
                        "type": "native_ml_runtime",                        
                        "signals": ml_hits,                       
                        "confidence": "high"                    
                    })
                                
                continue
            
            model_type = self.classify_binary(data)

            is_blob = self.is_model_blob(data)

            if model_type != "unknown_binary" or is_blob:
                results.append({
                    "file": f,
                    "size": file_size,
                    "type": model_type,
                    "confidence": "high" if model_type != "unknown_binary" else "medium"
                })

        return results

    def classify_so_pre(self, file, data):
        """
            Function to filter out non-ML .so files. 
        """

        name = file.lower()
        strings = self.extract_strings(data)
        text = " ".join(strings).lower()

        # sensors
        if any(k in name for k in ["motion", "gyro", "sensor"]):
            return "sensor_processing", 1
        
        if "bdzstd" in name:
            return "standard", 0

        # =========================
        # ✅ 1. CERTIFICATE
        # =========================
        if name.endswith((".p12", ".pfx")):
            return "certificate", 0

        if data.startswith(b"\x30\x82"):
            return "certificate", 0

        # =========================
        # ✅ 2. JNI & Programming
        # =========================
        if name.endswith("jni.so") or "jni" in name:
            return "jni", 0

        if any(x in text for x in ["jnienv", "javavm", "-java", "wasm"]):
            return "jni", 0

        # =========================
        # ✅ 3. GRAPHICS / RENDERING
        # =========================
        if any(k in name for k in [
            "render", "draw", "canvas", "skia", "svg",
            "egl", "gles", "vulkan", "gpu"
        ]):
            return "graphics", 0

        if sum(1 for k in [
            "render", "shader", "texture", "surface"
        ] if k in text) >= 3:
            return "graphics", 0

        # =========================
        # ✅ 4. MEDIA CODEC
        # =========================
        if any(k in name for k in [
            "vc1", "h264", "h265", "hevc", "vp9", "av1"
        ]):
            return "media_codec", 1

        if sum(1 for k in [
            "decode", "encode", "frame", "bitstream"
        ] if k in text) >= 3:
            return "media_codec", 1

        # =========================
        # ✅ 5. SECURITY
        # =========================
        if any(k in name for k in [
            "guard", "protect", "shield", "secure"
        ]):
            return "security", 1

        if sum(1 for k in [
            "hook", "inject", "root", "detect"
        ] if k in text) >= 2:
            return "security", 1
        
        if any(k in name for k in ["encrypt", "decrypt", "cipher", "ssl"]):
            return "crypto", 1

        # =========================
        # ✅ 6. ANALYTICS
        # =========================
        if "applog" in name:
            return "analytics", 1

        if sum(1 for k in [
            "event", "track", "metrics", "report"
        ] if k in text) >= 3:
            return "analytics", 1

        # =========================
        # ✅ 7. PATCHING
        # =========================
        if any(k in name for k in ["bspatch", "bsdiff"]):
            return "patching", 1

        if sum(1 for k in [
            "patch", "diff", "merge"
        ] if k in text) >= 2:
            return "patching", 1

        # =========================
        # ✅ 8. TEXT / NLP (non-ML)
        # =========================
        text_indicators = [
            "dictionary", "locale", "unicode",
            "token", "stem", "normalize"
        ]

        if any(k in name for k in ["text", "word", "dict", "lang"]):
            if not any(k in text for k in ["tensor", "inference"]):
                return "text_processing", 1

        if sum(1 for k in text_indicators if k in text) >= 2:
            if not any(k in text for k in ["tensor", "inference"]):
                return "text_processing", 1

        # =========================
        # ✅ 9. SCRIPTING / AST
        # =========================
        if "ast" in name:
            return "scripting", 1

        if sum(1 for k in [
            "parse", "token", "grammar", "node"
        ] if k in text) >= 3:
            return "scripting", 1

        # =========================
        # ✅ 10. NETWORKING
        # =========================
        if sum(1 for k in [
            "http", "socket", "tcp", "dns"
        ] if k in text) >= 3:
            return "networking", 1

        # =========================
        # ✅ 11. STORAGE
        # =========================
        if any(k in text for k in ["sqlite", "database", "mmkv"]):
            return "storage", 1

        # =========================
        # ✅ 12. COMPRESSION
        # =========================
        if any(k in name for k in ["lz4", "gzip", "zlib", "snappy"]):
            return "compression", 1

        # =========================
        # ✅ 13. ML DETECTION
        # =========================
        ml_keywords = [
            "tensor", "inference", "predict",
            "interpreter", "nnapi", "model"
        ]

        ml_score = sum(1 for k in ml_keywords if k in text)

        if ml_score >= 3:
            return "ml_runtime", ml_score
        
        # =========================
        # ✅ MEDIA PROCESSING (FULL PIPELINE)
        # =========================

        # strong filename signals
        if any(k in name for k in [
            "vc1", "h264", "h265", "hevc", "vp9", "av1",
            "demux", "mux"
        ]):
            return "media_processing", 1

        # ByteDance / vendor media libs
        if name.startswith("libtt") and any(k in name for k in [
            "mux", "demux", "video", "audio", "media"
        ]):
            return "media_processing", 1
        
        # vendor media libs (pattern-based)
        if name.startswith("lib_") and (
            "jb" in name or "jh" in name
        ):
            # combine with weak string hints
            if sum(1 for k in ["frame", "decode", "media"] if k in text) >= 2:
                return "media_processing", 1

        if "alog" in name or "jazz" in name or "media" in name:
            return "media_processing", 1

        # string-based detection
        media_keywords = [
            "demux", "mux", "stream", "container",
            "packet", "timestamp", "frame",
            "decode", "encode", "bitstream"
        ]

        media_score = sum(1 for k in media_keywords if k in text)

        if media_score >= 3:
            return "media_processing", 1

        
            # ByteDance / vendor media libs
        if name.startswith("libtt") and any(k in name for k in [
            "mux", "demux", "video", "audio", "media"
        ]):
            return "media_processing", 1
        
        # vendor media libs (pattern-based)
        if name.startswith("lib_") and (
            "jb" in name or "jh" in name
        ):
            # combine with weak string hints
            #if sum(1 for k in ["frame", "decode", "media"] if k in text) >= 2:
            return "media_processing", 1


        # =========================
        # ✅ FINAL FALLBACK
        # =========================
        return "native", 0

    def convert_binary_models_for_ui(self, binary_models):
        """
        Convert binary model detection → same format as AI models
        """

        converted = []

        for b in binary_models:

            model_name = b.get("file", "unknown_model")
            model_type = b.get("type", "unknown")

            # =========================
            # ✅ Vendor mapping
            # =========================
            if model_type == "tflite":
                vendor = "google"
            elif model_type == "pytorch":
                vendor = "meta"
            elif model_type == "protobuf_model":
                vendor = "generic"
            else:
                vendor = "unknown"

            # =========================
            # ✅ Input inference (important)
            # =========================
            name_lower = model_name.lower()

            if "audio" in name_lower or "speech" in name_lower:
                inputs = ["audio"]

            elif "face" in name_lower or "image" in name_lower:
                inputs = ["image"]

            elif "text" in name_lower:
                inputs = ["text"]

            else:
                # fallback for unknown blobs
                inputs = ["other"]

            converted.append({
                "model": model_name,
                "vendor": vendor,
                "inputs": inputs
            })

        return converted

    def dedupe_models(self, models):
        seen = set()
        result = []

        for m in models:
            key = m.get("model")

            if key in seen:
                continue

            seen.add(key)
            result.append(m)

        return result

    def ensure_string(self, x):
        """Normalise path string"""
        if isinstance(x, str):
            return x

        if isinstance(x, list) and x:
            return str(x[0])

        return ""

    def create_analysis_object(self, dex):
        dx = Analysis()
        dex_objects = []

        dx.add(dex)
        dex_objects.append(dex)

        dx.create_xref()

        return dx