from __future__ import annotations

from dataclasses import dataclass
from inspect import signature
from pathlib import Path
from typing import Any

from backend.app.core.config import get_settings

try:
    import torch
except Exception:  # pragma: no cover
    torch = None

try:
    from PIL import Image
except Exception:  # pragma: no cover
    Image = None

try:
    from paddleocr import PaddleOCR
except Exception:  # pragma: no cover
    PaddleOCR = None

try:
    import pytesseract
except Exception:  # pragma: no cover
    pytesseract = None

try:
    from transformers import DonutProcessor, VisionEncoderDecoderModel
except Exception:  # pragma: no cover
    DonutProcessor = None
    VisionEncoderDecoderModel = None

try:
    from transformers import LayoutLMv3ImageProcessor, LayoutLMv3Model, LayoutLMv3TokenizerFast
except Exception:  # pragma: no cover
    LayoutLMv3ImageProcessor = None
    LayoutLMv3Model = None
    LayoutLMv3TokenizerFast = None

try:
    from doclayout_yolo import YOLOv10
except Exception:  # pragma: no cover
    YOLOv10 = None

try:
    from huggingface_hub import hf_hub_download
except Exception:  # pragma: no cover
    hf_hub_download = None


@dataclass
class OCRResult:
    spans: list[dict[str, Any]]
    engine: str
    confidence: float


class DocumentEnsembleService:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.cuda_visible = bool(torch and torch.cuda.is_available())
        self.torch_cuda_usable = False
        self.gpu_unavailable_reason: str | None = None
        self.device_name: str | None = None
        self.device_capability: tuple[int, int] | None = None
        self.supported_arches: list[str] = []
        self.device = self._resolve_device()
        self._paddle = None
        self._donut_processor = None
        self._donut_model = None
        self._layout_processor = None
        self._layout_model = None
        self._layout_tokenizer = None
        self._doclayout_model = None
        self._doclayout_weights_path: Path | None = None

    def runtime_capabilities(self) -> dict[str, Any]:
        return {
            "runtime_mode": self.settings.document_runtime_mode,
            "gpu_preferred": self.settings.document_gpu_preferred,
            "gpu_available": self.torch_cuda_usable,
            "cuda_visible": self.cuda_visible,
            "torch_cuda_usable": self.torch_cuda_usable,
            "gpu_unavailable_reason": self.gpu_unavailable_reason,
            "device": self.device,
            "device_name": self.device_name,
            "device_capability": list(self.device_capability) if self.device_capability else None,
            "supported_arches": list(self.supported_arches),
            "layoutlmv3": self._status(LayoutLMv3Model),
            "doclayout_yolo": self._status(YOLOv10),
            "paddleocr": self._status(PaddleOCR),
            "tesseract": self._status(pytesseract),
            "donut": self._status(DonutProcessor and VisionEncoderDecoderModel),
        }

    def bootstrap_models(self) -> dict[str, Any]:
        report: dict[str, Any] = {
            "device": self.device,
            "gpu_available": self.torch_cuda_usable,
            "cuda_visible": self.cuda_visible,
            "torch_cuda_usable": self.torch_cuda_usable,
            "gpu_unavailable_reason": self.gpu_unavailable_reason,
            "device_name": self.device_name,
            "device_capability": list(self.device_capability) if self.device_capability else None,
            "supported_arches": list(self.supported_arches),
            "cache_dir": str(self.settings.document_worker_cache_dir),
            "engines": {},
        }
        report["engines"]["doclayout_yolo"] = self._bootstrap_doclayout()
        report["engines"]["paddleocr"] = self._bootstrap_paddle()
        report["engines"]["tesseract"] = self._bootstrap_tesseract()
        report["engines"]["layoutlmv3"] = self._bootstrap_layoutlmv3()
        report["engines"]["donut"] = self._bootstrap_donut()
        report["ready"] = all(item.get("ready") or item.get("status") == "optional_failed" for item in report["engines"].values())
        return report

    def extract_text_spans(self, image_paths: list[str]) -> tuple[list[dict[str, Any]], dict[str, str], float]:
        statuses = {
            "paddleocr": "not_run",
            "tesseract": "not_run",
            "donut": "not_run",
        }
        if image_paths:
            paddle = self._ocr_with_paddle(image_paths)
            if paddle.spans:
                statuses["paddleocr"] = "executed"
                statuses["tesseract"] = "standby"
                statuses["donut"] = "standby"
                return paddle.spans, statuses, paddle.confidence
            statuses["paddleocr"] = "failed_or_unavailable"

            tesseract = self._ocr_with_tesseract(image_paths)
            if tesseract.spans:
                statuses["tesseract"] = "executed"
                statuses["donut"] = "standby"
                return tesseract.spans, statuses, tesseract.confidence
            statuses["tesseract"] = "failed_or_unavailable"

            donut = self._ocr_with_donut(image_paths)
            if donut.spans:
                statuses["donut"] = "executed"
                return donut.spans, statuses, donut.confidence
            statuses["donut"] = "failed_or_unavailable"
        return [], statuses, 0.0

    def detect_layout(self, *, image_paths: list[str], text_spans: list[dict[str, Any]], raw_lines: list[str]) -> dict[str, Any]:
        engine_status = {
            "layoutlmv3": "not_run",
            "doclayout_yolo": "not_run",
        }
        regions: list[dict[str, Any]] = []
        semantic_scores: list[float] = []

        if image_paths:
            regions = self._detect_regions_doclayout(image_paths)
            engine_status["doclayout_yolo"] = "executed" if regions else "failed_or_unavailable"
            semantic_scores = self._layoutlmv3_semantic_scores(image_paths, text_spans)
            engine_status["layoutlmv3"] = "executed" if semantic_scores else "failed_or_unavailable"

        confidence = 0.62
        if regions:
            confidence += 0.12
        if semantic_scores:
            confidence += min(sum(semantic_scores) / max(len(semantic_scores), 1), 0.12)

        ambiguity_flags: list[str] = []
        if not regions:
            ambiguity_flags.append("layout_detector_unresolved")
        if not text_spans:
            ambiguity_flags.append("ocr_spans_missing")

        return {
            "regions": regions,
            "semantic_scores": semantic_scores[:20],
            "engine_status": engine_status,
            "confidence": min(confidence, 0.94),
            "ambiguity_flags": ambiguity_flags,
        }

    def _resolve_device(self) -> str:
        if not self.settings.document_gpu_preferred:
            self.gpu_unavailable_reason = "gpu execution disabled by configuration"
            return "cpu"
        if torch is None:
            self.gpu_unavailable_reason = "torch is not installed"
            return "cpu"
        if not self.cuda_visible:
            self.gpu_unavailable_reason = "cuda is not visible inside the container"
            return "cpu"
        try:
            device_index = torch.cuda.current_device()
            self.device_name = str(torch.cuda.get_device_name(device_index))
            self.device_capability = tuple(int(part) for part in torch.cuda.get_device_capability(device_index))
            self.supported_arches = [str(value) for value in (torch.cuda.get_arch_list() or [])]
            probe = torch.randn((8, 8), device="cuda")
            _ = (probe @ probe).sum().item()
            self.torch_cuda_usable = True
            return "cuda"
        except Exception as exc:
            self.gpu_unavailable_reason = f"{type(exc).__name__}: {exc}"
        return "cpu"

    def _status(self, dependency: Any) -> str:
        return "available" if dependency is not None else "unavailable"

    def _bootstrap_doclayout(self) -> dict[str, Any]:
        if YOLOv10 is None:
            return {"ready": False, "status": "unavailable", "detail": "doclayout_yolo package is not installed"}
        try:
            model = self._ensure_doclayout_model()
            return {
                "ready": model is not None,
                "status": "ready",
                "weights_path": str(self._doclayout_weights_path) if self._doclayout_weights_path else None,
            }
        except Exception as exc:
            return {"ready": False, "status": "failed", "detail": f"{type(exc).__name__}: {exc}"}

    def _bootstrap_paddle(self) -> dict[str, Any]:
        if PaddleOCR is None:
            return {"ready": False, "status": "unavailable", "detail": "PaddleOCR is not installed"}
        try:
            self._ensure_paddle()
            return {"ready": self._paddle is not None, "status": "ready", "device": self.device}
        except Exception as exc:
            return {"ready": False, "status": "failed", "detail": f"{type(exc).__name__}: {exc}"}

    def _bootstrap_tesseract(self) -> dict[str, Any]:
        if pytesseract is None:
            return {"ready": False, "status": "unavailable", "detail": "pytesseract is not installed"}
        try:
            version = str(pytesseract.get_tesseract_version())
            return {"ready": True, "status": "ready", "version": version}
        except Exception as exc:
            return {"ready": False, "status": "failed", "detail": f"{type(exc).__name__}: {exc}"}

    def _bootstrap_layoutlmv3(self) -> dict[str, Any]:
        if LayoutLMv3ImageProcessor is None or LayoutLMv3Model is None or LayoutLMv3TokenizerFast is None:
            return {"ready": False, "status": "unavailable", "detail": "LayoutLMv3 dependencies are not installed"}
        try:
            self._ensure_layoutlmv3()
            return {"ready": self._layout_model is not None, "status": "ready", "device": self.device}
        except Exception as exc:
            return {"ready": False, "status": "failed", "detail": f"{type(exc).__name__}: {exc}"}

    def _bootstrap_donut(self) -> dict[str, Any]:
        if DonutProcessor is None or VisionEncoderDecoderModel is None:
            return {"ready": False, "status": "unavailable", "detail": "Donut dependencies are not installed"}
        try:
            self._ensure_donut()
            return {"ready": self._donut_model is not None, "status": "ready", "device": self.device}
        except Exception as exc:
            return {"ready": False, "status": "failed", "detail": f"{type(exc).__name__}: {exc}"}

    def _ensure_paddle(self) -> None:
        if self._paddle is not None:
            return
        init_params = set(signature(PaddleOCR.__init__).parameters)
        candidates: list[dict[str, Any]] = []

        primary: dict[str, Any] = {"lang": "en"}
        if "device" in init_params:
            primary["device"] = "gpu" if self.device == "cuda" else "cpu"
        if "use_angle_cls" in init_params:
            primary["use_angle_cls"] = True
        if "show_log" in init_params:
            primary["show_log"] = False
        if "ocr_version" in init_params:
            primary["ocr_version"] = "PP-OCRv5"
        candidates.append(primary)

        if "device" in init_params:
            candidates.append({"lang": "en", "device": "cpu"})
        candidates.append({"lang": "en"})

        last_exc: Exception | None = None
        for kwargs in candidates:
            try:
                self._paddle = PaddleOCR(**kwargs)
                return
            except Exception as exc:
                last_exc = exc
        if last_exc is not None:
            raise last_exc

    def _ensure_donut(self) -> None:
        if self._donut_processor is None or self._donut_model is None:
            self._donut_processor = DonutProcessor.from_pretrained(self.settings.donut_model_name, cache_dir=str(self.settings.document_worker_cache_dir))
            self._donut_model = VisionEncoderDecoderModel.from_pretrained(self.settings.donut_model_name, cache_dir=str(self.settings.document_worker_cache_dir))
            if self.device == "cuda":
                self._donut_model = self._donut_model.to("cuda")

    def _ensure_layoutlmv3(self) -> None:
        if self._layout_processor is None or self._layout_model is None or self._layout_tokenizer is None:
            self._layout_processor = LayoutLMv3ImageProcessor(apply_ocr=False)
            self._layout_tokenizer = LayoutLMv3TokenizerFast.from_pretrained(self.settings.layoutlm_model_name, cache_dir=str(self.settings.document_worker_cache_dir))
            self._layout_model = LayoutLMv3Model.from_pretrained(self.settings.layoutlm_model_name, cache_dir=str(self.settings.document_worker_cache_dir))
            if self.device == "cuda":
                self._layout_model = self._layout_model.to("cuda")

    def _resolve_doclayout_weights(self) -> Path:
        if self._doclayout_weights_path and self._doclayout_weights_path.exists():
            return self._doclayout_weights_path
        local_path = self.settings.document_worker_cache_dir / self.settings.doclayout_model_filename
        if local_path.exists():
            self._doclayout_weights_path = local_path
            return local_path
        if hf_hub_download is None:
            raise RuntimeError("huggingface_hub is not available for DocLayout-YOLO weight download")
        downloaded = hf_hub_download(
            repo_id=self.settings.doclayout_model_repo_id,
            filename=self.settings.doclayout_model_filename,
            cache_dir=str(self.settings.document_worker_cache_dir),
        )
        self._doclayout_weights_path = Path(downloaded)
        return self._doclayout_weights_path

    def _ensure_doclayout_model(self):
        if self._doclayout_model is None:
            weights_path = self._resolve_doclayout_weights()
            self._doclayout_model = YOLOv10(str(weights_path))
        return self._doclayout_model

    def _ocr_with_paddle(self, image_paths: list[str]) -> OCRResult:
        if PaddleOCR is None:
            return OCRResult([], "paddleocr", 0.0)
        try:
            self._ensure_paddle()
            spans: list[dict[str, Any]] = []
            confidences: list[float] = []
            for page_index, image_path in enumerate(image_paths, start=1):
                try:
                    result = self._paddle.ocr(image_path, cls=True) or []
                except TypeError:
                    result = self._paddle.ocr(image_path) or []
                if result and hasattr(result[0], "res"):
                    result = [entry.res for entry in result]
                for line in result:
                    for item in line or []:
                        bbox = item[0]
                        text = str((item[1] or [""])[0]).strip()
                        confidence = float((item[1] or [None, 0.0])[1] or 0.0)
                        if not text:
                            continue
                        x_values = [point[0] for point in bbox]
                        y_values = [point[1] for point in bbox]
                        spans.append({
                            "page": page_index,
                            "text": text,
                            "bbox": [min(x_values), min(y_values), max(x_values), max(y_values)],
                            "confidence": confidence,
                            "engine": "paddleocr",
                        })
                        confidences.append(confidence)
            return OCRResult(spans, "paddleocr", round(sum(confidences) / max(len(confidences), 1), 4) if confidences else 0.0)
        except Exception:
            return OCRResult([], "paddleocr", 0.0)

    def _ocr_with_tesseract(self, image_paths: list[str]) -> OCRResult:
        if pytesseract is None or Image is None:
            return OCRResult([], "tesseract", 0.0)
        try:
            spans: list[dict[str, Any]] = []
            confidences: list[float] = []
            for page_index, image_path in enumerate(image_paths, start=1):
                data = pytesseract.image_to_data(Image.open(image_path), output_type=pytesseract.Output.DICT)
                count = len(data.get("text") or [])
                for idx in range(count):
                    text = str((data.get("text") or [""])[idx]).strip()
                    if not text:
                        continue
                    conf_raw = (data.get("conf") or ["0"])[idx]
                    try:
                        confidence = max(float(conf_raw), 0.0) / 100.0
                    except Exception:
                        confidence = 0.0
                    left = int((data.get("left") or [0])[idx])
                    top = int((data.get("top") or [0])[idx])
                    width = int((data.get("width") or [0])[idx])
                    height = int((data.get("height") or [0])[idx])
                    spans.append({
                        "page": page_index,
                        "text": text,
                        "bbox": [left, top, left + width, top + height],
                        "confidence": confidence,
                        "engine": "tesseract",
                    })
                    confidences.append(confidence)
            return OCRResult(spans, "tesseract", round(sum(confidences) / max(len(confidences), 1), 4) if confidences else 0.0)
        except Exception:
            return OCRResult([], "tesseract", 0.0)

    def _ocr_with_donut(self, image_paths: list[str]) -> OCRResult:
        if DonutProcessor is None or VisionEncoderDecoderModel is None or Image is None or not image_paths:
            return OCRResult([], "donut", 0.0)
        try:
            self._ensure_donut()
            image = Image.open(image_paths[0]).convert("RGB")
            pixel_values = self._donut_processor(image, return_tensors="pt").pixel_values
            if self.device == "cuda":
                pixel_values = pixel_values.to("cuda")
            outputs = self._donut_model.generate(pixel_values, max_length=512)
            decoded = self._donut_processor.batch_decode(outputs, skip_special_tokens=True)[0]
            lines = [line.strip() for line in decoded.splitlines() if line.strip()]
            spans = [
                {
                    "page": 1,
                    "text": line,
                    "bbox": [0, index * 12, 800, index * 12 + 10],
                    "confidence": 0.62,
                    "engine": "donut",
                }
                for index, line in enumerate(lines[:200], start=1)
            ]
            return OCRResult(spans, "donut", 0.62 if spans else 0.0)
        except Exception:
            return OCRResult([], "donut", 0.0)

    def _detect_regions_doclayout(self, image_paths: list[str]) -> list[dict[str, Any]]:
        if YOLOv10 is None or not image_paths:
            return []
        try:
            model = self._ensure_doclayout_model()
            regions: list[dict[str, Any]] = []
            for page_index, image_path in enumerate(image_paths, start=1):
                predictions = model.predict(source=image_path, imgsz=1024, verbose=False)
                for result in predictions or []:
                    boxes = getattr(result, "boxes", None)
                    names = getattr(result, "names", {}) or {}
                    if boxes is None:
                        continue
                    xyxy = boxes.xyxy.tolist() if hasattr(boxes, "xyxy") else []
                    cls_ids = boxes.cls.tolist() if hasattr(boxes, "cls") else []
                    confs = boxes.conf.tolist() if hasattr(boxes, "conf") else []
                    for coords, cls_id, conf in zip(xyxy, cls_ids, confs):
                        label = names.get(int(cls_id), str(int(cls_id)))
                        regions.append({
                            "page": page_index,
                            "label": label,
                            "bbox": [float(coords[0]), float(coords[1]), float(coords[2]), float(coords[3])],
                            "confidence": float(conf),
                            "engine": "doclayout_yolo",
                        })
            return regions
        except Exception:
            return []

    def _layoutlmv3_semantic_scores(self, image_paths: list[str], text_spans: list[dict[str, Any]]) -> list[float]:
        if LayoutLMv3ImageProcessor is None or LayoutLMv3Model is None or LayoutLMv3TokenizerFast is None or Image is None or not image_paths or not text_spans:
            return []
        try:
            self._ensure_layoutlmv3()
            first_page = Image.open(image_paths[0]).convert("RGB")
            words = [str(item.get("text") or "") for item in text_spans if int(item.get("page") or 1) == 1][:128]
            boxes = []
            for item in [span for span in text_spans if int(span.get("page") or 1) == 1][:128]:
                bbox = [int(float(value)) for value in (item.get("bbox") or [0, 0, 0, 0])]
                boxes.append([max(0, min(1000, bbox[0])), max(0, min(1000, bbox[1])), max(0, min(1000, bbox[2])), max(0, min(1000, bbox[3]))])
            if not words or not boxes:
                return []
            image = self._layout_processor(first_page, return_tensors="pt")
            tokens = self._layout_tokenizer(words, boxes=boxes, return_tensors="pt", truncation=True, padding="max_length", max_length=128)
            pixel_values = image["pixel_values"]
            if self.device == "cuda":
                pixel_values = pixel_values.to("cuda")
                tokens = {key: value.to("cuda") for key, value in tokens.items()}
            outputs = self._layout_model(pixel_values=pixel_values, input_ids=tokens["input_ids"], attention_mask=tokens["attention_mask"], bbox=tokens["bbox"])
            hidden = outputs.last_hidden_state.detach().float().cpu()
            norms = hidden.norm(dim=-1).squeeze(0).tolist()
            return [round(min(float(score) / 100.0, 1.0), 4) for score in norms[:20]]
        except Exception:
            return []
