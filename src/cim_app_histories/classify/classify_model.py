"""
Classify model assets found inside an APK.

Complements ClassifySO (which classifies native *runtimes*) by
classifying the model *artefacts* they load: format (tflite, onnx,
ncnn, ...), modality (audio / vision / nlp), and vendor. Keyword
tables are internationalised: on-device models shipped by Chinese
vendors frequently carry Chinese-language names and metadata, so
English-only matching systematically under-detects them.
"""

from .classify_so import ClassifySO

# Model file extensions -> format. Extends magic-byte sniffing
# (ClassifySO.classify_binary) with the proprietary formats common in
# Chinese vendor stacks: MNN (Alibaba), ncnn (Tencent), Paddle-Lite
# (Baidu, .nb), bytenn (ByteDance), MindSpore/HiAI (Huawei, .ms/.om).
EXTENSION_FORMATS = {
    ".tflite": "tflite", ".lite": "tflite",
    ".onnx": "onnx",
    ".pt": "pytorch", ".ptl": "pytorch",
    ".pb": "tf_protobuf",
    ".mnn": "mnn",
    ".param": "ncnn", ".bin": "ncnn_weights",
    ".nb": "paddle_lite",
    ".ms": "mindspore", ".om": "huawei_om",
    ".bytenn": "bytenn", ".model": "generic_model", ".dat": "generic_blob",
}

# Modality keywords: English + Chinese (extendable per language).
MODALITY_KEYWORDS = {
    "audio": [
        "asr", "speech", "voice", "audio", "tts", "vad", "wakeword",
        "keyword_spot", "denoise", "aec",
        "\u8bed\u97f3",          # 语音 speech/voice
        "\u58f0\u5b66",          # 声学 acoustic
        "\u5524\u9192",          # 唤醒 wake(-word)
        "\u97f3\u9891",          # 音频 audio
        "\u964d\u566a",          # 降噪 denoise
    ],
    "vision": [
        "face", "image", "vision", "ocr", "detect", "segment", "beauty",
        "gesture", "pose", "landmark",
        "\u4eba\u8138",          # 人脸 face
        "\u56fe\u50cf",          # 图像 image
        "\u89c6\u89c9",          # 视觉 vision
        "\u624b\u52bf",          # 手势 gesture
        "\u7f8e\u989c",          # 美颜 beautification
    ],
    "nlp": [
        "nlp", "bert", "token", "translate", "sentiment", "segment_text",
        "intent", "ner",
        "\u6587\u672c",          # 文本 text
        "\u5206\u8bcd",          # 分词 word segmentation
        "\u7ffb\u8bd1",          # 翻译 translation
        "\u60c5\u611f",          # 情感 sentiment
    ],
}


class ClassifyModel:
    """Classify a single model asset by format, modality, and vendor."""

    def __init__(self, classify_so=None):
        self._so = classify_so or ClassifySO()

    def model_format(self, name, data):
        lower = name.lower()
        for ext, fmt in EXTENSION_FORMATS.items():
            if lower.endswith(ext):
                return fmt
        sniffed = self._so.classify_binary(data)
        return sniffed if sniffed != "unknown_binary" else "unknown"

    def modality(self, name, text=""):
        """Infer modality from the asset name plus any associated text
        (e.g. strings of the library that references it). ``text`` should
        include a tolerant UTF-8 decode so Chinese keywords can match."""
        haystack = name.lower() + " " + text
        scores = {
            m: sum(1 for k in kws if k in haystack)
            for m, kws in MODALITY_KEYWORDS.items()
        }
        best = max(scores, key=scores.get)
        return best if scores[best] > 0 else "unknown"

    def classify(self, name, data, context_text=""):
        return {
            "file": name,
            "kind": "model",
            "format": self.model_format(name, data),
            "modality": self.modality(name, context_text),
            "vendor": self._so.detect_vendor(name, None),
            "size": len(data),
        }
