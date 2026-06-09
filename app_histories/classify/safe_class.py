class SafeMethod:
    def __init__(self, method_analysis):
        self.raw = method_analysis
        self.method = self._unwrap_method(method_analysis)

    def _unwrap_method(self, m):
        if hasattr(m, "get_method"):
            return m.get_method()
        return m

    @property
    def class_name(self):
        try:
            return self.method.get_class_name()
        except Exception:
            return ""

    @property
    def name(self):
        try:
            return self.method.get_name()
        except Exception:
            return ""

    @property
    def descriptor(self):
        try:
            return self.method.get_descriptor()
        except Exception:
            return ""

    @property
    def code(self):
        if hasattr(self.method, "get_code"):
            try:
                return self.method.get_code()
            except Exception:
                pass
        return None

    def has_code(self):
        return self.code is not None

    def get_xrefs(self):
        if hasattr(self.raw, "get_xref_to"):
            try:
                return self.raw.get_xref_to()
            except Exception:
                pass
        return []

    def __str__(self):
        return f"{self.class_name}->{self.name}"

