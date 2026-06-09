"""
    Functions to read and classify the URLs
"""
import re
from urllib.parse import urlparse

class ClassifyURL:

    def __init__(self):
        pass

    def normalize_inputs(self, inputs):
        if not inputs:
            return ["other"]

        valid = {"audio", "image", "text", "user_data"}

        cleaned = [i for i in inputs if i in valid]

        return cleaned if cleaned else ["other"]
    
    def convert_urls_for_ui(self, urls):

        return [
            {
                "url": u.get("url"),
                "domain": u.get("domain", "unknown"),
                "inputs": self.normalize_inputs(u.get("inputs"))
            }
            for u in urls
        ]
    def infer_inputs(self, categories):
        inputs = set()

        if "audio" in categories:
            inputs.add("audio")

        if "image" in categories:
            inputs.add("image")

        if "text" in categories:
            inputs.add("text")

        if "recommendation" in categories:
            inputs.add("user_data")

        if not inputs:
            inputs.add("unknown")

        return sorted(inputs)

    # =========================
    # ✅ TEMPLATE GENERATION (CRITICAL)
    # =========================

    def generate_template(self, url):
        """
            Convert:
            https://api.example.com/v1/user/123/profile
            → /v1/user/{id}/profile
        """

        try:
            parsed = urlparse(url)
            path = parsed.path

            # replace numbers/ids with placeholders
            path = re.sub(r"/\d+", "/{id}", path)
            path = re.sub(r"[a-f0-9]{8,}", "{hash}", path)

            return path if path else "/"
        except Exception:
            return "/unknown"

    #=========================
    # ✅ DOMAIN EXTRACTION
    # =========================
    def get_domain_safe(self, url):
        try:
            d = urlparse(url).netloc
            return d if d else "unknown"
        except:
            return "unknown"

    def is_url(self, s):
        return isinstance(s, str) and (
            s.startswith("http://") or s.startswith("https://")
        ) 
    def find_urls_with_analysis(self, strings):
        """
        Extract + classify URLs from string list
        """

        results = []

        seen = set()

        for s in strings:

            if not self.is_url(s):
                continue

            if s in seen:
                continue

            seen.add(s)

            categories = self.classify_url(s)
            inputs = self.infer_inputs(categories)

            results.append({
                "url": s,
                "domain": self.get_domain_safe(s),
                "categories": categories,
                "inputs": inputs,
                "template": self.generate_template(s)
            })

        return results

    def is_valid_url(self, u):
        """
        Check this is a real URL, not a fragment
        """
        if not u or len(u) < 10:
            return False

        if u in ["http://", "https://"]:
            return False

        return True

    def classify_url(self, url):
        u = url.lower()
        cats = set()

        if any(k in u for k in ["upload", "post", "submit"]):
            cats.add("upload")

        if any(k in u for k in ["recommend", "feed", "rank"]):
            cats.add("recommendation")

        if any(k in u for k in ["track", "log", "event", "metrics"]):
            cats.add("tracking")

        if any(k in u for k in ["login", "auth", "token"]):
            cats.add("authentication")

        if any(k in u for k in ["image", "img", "photo"]):
            cats.add("image")

        if any(k in u for k in ["audio", "voice", "speech"]):
            cats.add("audio")

        if any(k in u for k in ["text", "comment", "caption"]):
            cats.add("text")

        if any(k in u for k in ["api", "v1", "v2"]):
            cats.add("api")

        if any(k in u for k in ["chat"]):
            cats.add("chat")

        return sorted(cats)

    def summarize_url_behaviour(self, apkname, urls):

        if not urls:
            return ["No network endpoints detected."]

        inputs = set()
        categories = set()
        domains = set()

        for u in urls:
            inputs.update(u["inputs"])
            categories.update(u["categories"])
            domains.add(u["domain"])

        summary = []

        # ✅ high-level
        high = []

        if "audio" in inputs:
            high.append("audio data transmission")

        if "image" in inputs:
            high.append("image data transmission")

        if "text" in inputs:
            high.append("text data transmission")

        if "tracking" in categories:
            high.append("user tracking")

        if "recommendation" in categories:
            high.append("recommendation API calls")

        if "chat" in categories:
            high.append("chat API calls")

        if high:
            summary.append(f"The {apkname} app performs " + ", ".join(sorted(high)) + ".")

        # ✅ domain summary
        summary.append("It communicates with: " + ", ".join(sorted(domains)) + ".")

        return " ".join(summary)