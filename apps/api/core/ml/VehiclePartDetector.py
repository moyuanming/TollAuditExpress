"""车辆部件检测器 - 使用YOLOv8检测车辆关键部件"""
import os
import torch
import numpy as np
from PIL import Image
from typing import Dict, List, Optional, Tuple
import json


class VehiclePartDetector:
    """车辆部件检测器 - 检测中网、大灯、前挡玻璃、前保险杠、Logo等部件"""

    PART_CLASSES = ['grille', 'headlight', 'windshield', 'bumper', 'logo']
    PART_COLORS = {
        'grille': '#FF6B6B', 'headlight': '#4ECDC4', 'windshield': '#45B7D1',
        'bumper': '#96CEB4', 'logo': '#FFEAA7',
    }

    def __init__(self, model_path: Optional[str] = None, device: Optional[str] = None):
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.model = None
        self.model_path = model_path
        self._load_model()

    def _load_model(self):
        try:
            from ultralytics import YOLO
            from apps.api.core.config import VEHICLE_PART_MODEL_PATH
            model_path = self.model_path or VEHICLE_PART_MODEL_PATH
            if model_path:
                self.model = YOLO(model_path)
                self.model.to(self.device)
            else:
                # Default YOLOv8n is COCO-pretrained and cannot detect vehicle parts.
                # Set VEHICLE_PART_MODEL_PATH in config to use a custom-trained model.
                self.model = None
        except ImportError:
            self.model = None

    def detect(self, image_path: Optional[str] = None,
               image_bytes: Optional[bytes] = None) -> Dict[str, Dict]:
        if image_path:
            img = Image.open(image_path).convert('RGB')
        elif image_bytes:
            from io import BytesIO
            img = Image.open(BytesIO(image_bytes)).convert('RGB')
        else:
            raise ValueError("需要提供 image_path 或 image_bytes")

        if self.model is None:
            return {}

        results = self.model(img)
        parts = {}
        for result in results:
            for box in result.boxes:
                cls_id = int(box.cls[0])
                conf = float(box.conf[0])
                if cls_id < len(self.PART_CLASSES):
                    part_name = self.PART_CLASSES[cls_id]
                    bbox = box.xyxy[0].cpu().numpy().tolist()
                    x1, y1, x2, y2 = bbox
                    center = ((x1 + x2) / 2, (y1 + y2) / 2)
                    if part_name not in parts or conf > parts[part_name]['confidence']:
                        parts[part_name] = {'bbox': bbox, 'confidence': conf, 'center': center, 'class_id': cls_id}
        return parts

    def crop_part(self, image_path: Optional[str] = None, image_bytes: Optional[bytes] = None,
                  bbox: List[float] = None, padding: float = 0.1) -> Optional[Image.Image]:
        if image_path:
            img = Image.open(image_path).convert('RGB')
        elif image_bytes:
            from io import BytesIO
            img = Image.open(BytesIO(image_bytes)).convert('RGB')
        else:
            return None
        if bbox is None:
            return None
        x1, y1, x2, y2 = bbox
        w, h = x2 - x1, y2 - y1
        x1 = max(0, int(x1 - w * padding)); y1 = max(0, int(y1 - h * padding))
        x2 = min(img.size[0], int(x2 + w * padding)); y2 = min(img.size[1], int(y2 + h * padding))
        return img.crop((x1, y1, x2, y2))

    def get_part_color(self, part_name: str) -> str:
        return self.PART_COLORS.get(part_name, '#FFFFFF')

    def get_all_parts_info(self) -> List[Dict]:
        return [
            {'name': 'grille', 'label': '中网', 'color': self.PART_COLORS['grille']},
            {'name': 'headlight', 'label': '大灯(左)', 'color': self.PART_COLORS['headlight']},
            {'name': 'headlight_right', 'label': '大灯(右)', 'color': self.PART_COLORS['headlight']},
            {'name': 'windshield', 'label': '前挡玻璃', 'color': self.PART_COLORS['windshield']},
            {'name': 'bumper', 'label': '前保险杠', 'color': self.PART_COLORS['bumper']},
            {'name': 'logo', 'label': 'Logo', 'color': self.PART_COLORS['logo']},
        ]


if __name__ == '__main__':
    detector = VehiclePartDetector()
    test_img = Image.new('RGB', (400, 300), color='white')
    test_path = '/tmp/test_car.jpg'
    test_img.save(test_path)
    parts = detector.detect(test_path)
    print("检测到的部件:", list(parts.keys()))
