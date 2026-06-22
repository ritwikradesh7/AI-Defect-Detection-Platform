#runs a pretrained CNN (MobileNetV3-Small)

import io
import json
import logging
import time
from pathlib import Path

from PIL import Image, ImageStat

from ..config import MODEL_STATE_DIR

logger = logging.getLogger(__name__)

try:
    import torch
    import torch.nn as nn
    import torchvision.models as tv_models
    import torchvision.transforms as T
    import numpy as np
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False


# --- tunables ---------------------------------------------------------
# These thresholds are starting points.
ANOMALY_THRESHOLD = 0.12       # cosine distance above this looks off
ANOMALY_SCALE = 0.06            # controls how sharp the cutoff is
MIN_REFERENCE_SAMPLES = 4       # need at least this many normal samples before judging anything
MAX_REFERENCE_POOL = 50         # cap how many embeddings we keep around
CLASSICAL_WEIGHT = 0.20         # how much the old brightness/variance signal still counts


class DefectDetectionModel:

    def __init__(self):
        self.backend = "heuristic" 
        self.feature_extractor = None
        self.transform = None

        self.reference_path = Path(MODEL_STATE_DIR) / "reference_profile.json"
        self.reference_embeddings = self._load_reference_pool()

        if TORCH_AVAILABLE:
            self._try_load_cnn()
        else:
            logger.warning(
                "torch/torchvision not installed — falling back to the "
                "brightness/variance heuristic. Run `pip install torch torchvision` "
                "to enable the real model."
            )

    def _try_load_cnn(self):
        """Attempt to load MobileNetV3-Small with pretrained ImageNet weights."""
        try:
            net = tv_models.mobilenet_v3_small(
                weights=tv_models.MobileNet_V3_Small_Weights.IMAGENET1K_V1
            )
            net.eval()

            self.feature_extractor = nn.Sequential(net.features, net.avgpool, nn.Flatten())

            self.transform = T.Compose([
                T.Resize(256),
                T.CenterCrop(224),
                T.ToTensor(),
                T.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225]),
            ])

            self.backend = "cnn"
            logger.info("Loaded MobileNetV3-Small (ImageNet pretrained) for feature extraction.")

        except Exception as e:
            
            logger.warning(
                f"Couldn't load the pretrained CNN ({e}). Falling back to the "
                f"brightness/variance heuristic — the app will keep working, "
                f"just with a much cruder signal."
            )
            self.backend = "heuristic"

    # --- reference pool persistence ------------------------------------

    def _load_reference_pool(self):
        if self.reference_path.exists():
            try:
                with open(self.reference_path) as f:
                    data = json.load(f)
                return data.get("embeddings", [])
            except (json.JSONDecodeError, OSError):
                logger.warning("Reference profile file was unreadable, starting fresh.")
        return []

    def _save_reference_pool(self):
        try:
            with open(self.reference_path, "w") as f:
                json.dump({"embeddings": self.reference_embeddings}, f)
        except OSError as e:
            logger.warning(f"Couldn't save reference profile: {e}")

    def _add_to_reference_pool(self, embedding):
        self.reference_embeddings.append(embedding)
        if len(self.reference_embeddings) > MAX_REFERENCE_POOL:
            self.reference_embeddings = self.reference_embeddings[-MAX_REFERENCE_POOL:]
        self._save_reference_pool()

    # --- the actual prediction ------------------------------------------

    def predict(self, image_path: str) -> dict:
        
        img = Image.open(image_path)
        img.verify()                       # raises if the file is corrupt
        img = Image.open(image_path)        # verify() consumes the file handle, reopen
        img = img.convert("RGB")

        classical_score = self._classical_anomaly_score(img)

        if self.backend == "cnn":
            return self._predict_cnn(img, classical_score)
        return self._predict_heuristic(classical_score)

    def _predict_cnn(self, img: Image.Image, classical_score: float) -> dict:
        embedding = self._embed(img)

        
        if len(self.reference_embeddings) < MIN_REFERENCE_SAMPLES:
            self._add_to_reference_pool(embedding.tolist())
            return {
                "is_defective": False,
                "confidence": 0.92,
                "model_version": "mobilenetv3-small-embed-v1 (calibrating)",
            }

        ref_mean = np.mean(np.array(self.reference_embeddings), axis=0)
        distance = self._cosine_distance(embedding, ref_mean)

        cnn_score = 1 / (1 + np.exp(-(distance - ANOMALY_THRESHOLD) / ANOMALY_SCALE))

        combined = (1 - CLASSICAL_WEIGHT) * cnn_score + CLASSICAL_WEIGHT * classical_score

        is_defective = combined > 0.5
        confidence = combined if is_defective else (1 - combined)

        if not is_defective:
            self._add_to_reference_pool(embedding.tolist())

        return {
            "is_defective": bool(is_defective),
            "confidence": float(round(confidence, 4)),
            "model_version": "mobilenetv3-small-embed-v1",
        }

    def _predict_heuristic(self, classical_score: float) -> dict:
        is_defective = classical_score > 0.5
        confidence = classical_score if is_defective else (1 - classical_score)
        return {
            "is_defective": bool(is_defective),
            "confidence": float(round(confidence, 4)),
            "model_version": "heuristic-fallback-v1",
        }

    def register_known_good(self, image_path: str):
 
        if self.backend != "cnn":
            return  # nothing to do in heuristic mode
        try:
            img = Image.open(image_path).convert("RGB")
            embedding = self._embed(img)
            self._add_to_reference_pool(embedding.tolist())
        except Exception as e:
            logger.warning(f"Couldn't register {image_path} as a known-good reference: {e}")

    # --- helpers ----------------------------------------------------------

    def _embed(self, img: Image.Image):
        x = self.transform(img).unsqueeze(0)
        with torch.no_grad():
            vec = self.feature_extractor(x)
        return vec.squeeze(0).numpy()

    @staticmethod
    def _cosine_distance(a, b):
        denom = (np.linalg.norm(a) * np.linalg.norm(b)) or 1e-8
        similarity = np.dot(a, b) / denom
        return 1 - similarity

    @staticmethod
    def _classical_anomaly_score(img: Image.Image) -> float:
     
        stat = ImageStat.Stat(img.convert("L"))  # grayscale for brightness stats
        brightness = stat.mean[0]
        variance = stat.var[0]

        darkness_penalty = max(0, (90 - brightness) / 90) * 0.5
        flatness_penalty = max(0, (300 - variance) / 300) * 0.5
        score = min(darkness_penalty + flatness_penalty, 1.0)
        return score

model = DefectDetectionModel()
