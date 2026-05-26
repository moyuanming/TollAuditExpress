"""多部件特征提取器 - 提取车辆各部件的视觉特征"""
import torch
import torch.nn as nn
from torchvision import models, transforms
from PIL import Image
import numpy as np
from typing import Dict, Optional
import json

from VehiclePartDetector import VehiclePartDetector


class MultiPartFingerprint:
    """多部件特征提取器 - 同时提取全局特征和部件特征"""

    # 特征权重 (用于搜索融合)
    FEATURE_WEIGHTS = {
        'global': 0.3,
        'grille': 0.2,
        'headlight': 0.15,
        'windshield': 0.15,
        'bumper': 0.1,
        'logo': 0.1,
    }

    def __init__(self, device: Optional[str] = None):
        self.device = device or ('cuda' if torch.cuda.is_available() else 'cpu')
        self.backbone = self._load_backbone()
        self.transform = transforms.Compose([
            transforms.Resize((224, 224)),
            transforms.ToTensor(),
            transforms.Normalize(mean=[0.485, 0.456, 0.406], std=[0.229, 0.224, 0.225])
        ])
        self.part_detector = VehiclePartDetector()

    def _load_backbone(self) -> nn.Module:
        """加载ResNet50特征提取器"""
        model = models.resnet50(weights='IMAGENET1K_V1')
        # 移除最后全连接层,输出2048维特征
        model = torch.nn.Sequential(*list(model.children())[:-1])
        return model.to(self.device).eval()

    def extract_global_feature(self, image_path: Optional[str] = None,
                               image_bytes: Optional[bytes] = None) -> np.ndarray:
        """提取全局特征"""
        if image_path:
            img = Image.open(image_path).convert('RGB')
        elif image_bytes:
            from io import BytesIO
            img = Image.open(BytesIO(image_bytes)).convert('RGB')
        else:
            raise ValueError("需要提供 image_path 或 image_bytes")

        img_tensor = self.transform(img).unsqueeze(0).to(self.device)
        with torch.no_grad():
            feature = self.backbone(img_tensor)
        feature = feature.squeeze().cpu().numpy()
        feature = feature / np.linalg.norm(feature)
        return feature.astype(np.float32)

    def extract_part_features(self, image_path: Optional[str] = None,
                              image_bytes: Optional[bytes] = None) -> Dict[str, Dict]:
        """提取各部件特征"""
        if image_path:
            img = Image.open(image_path).convert('RGB')
        elif image_bytes:
            from io import BytesIO
            img = Image.open(BytesIO(image_bytes)).convert('RGB')
        else:
            raise ValueError("需要提供 image_path 或 image_bytes")

        # 检测部件
        parts = self.part_detector.detect(image_path=image_path, image_bytes=image_bytes)

        part_features = {}
        for part_name, part_info in parts.items():
            bbox = part_info['bbox']
            conf = part_info.get('confidence', 0.9)
            cropped = self.part_detector.crop_part(image_path=image_path, image_bytes=image_bytes, bbox=bbox)
            if cropped:
                img_tensor = self.transform(cropped).unsqueeze(0).to(self.device)
                with torch.no_grad():
                    feat = self.backbone(img_tensor)
                feat = feat.squeeze().cpu().numpy()
                feat = feat / np.linalg.norm(feat)
                part_features[part_name] = {
                    'feature': feat.astype(np.float32),
                    'bbox': bbox,
                    'confidence': conf
                }

        return part_features

    def extract_all_features(self, image_path: Optional[str] = None,
                            image_bytes: Optional[bytes] = None) -> Dict:
        """提取完整特征(全局 + 部件)"""
        global_feat = self.extract_global_feature(image_path=image_path, image_bytes=image_bytes)
        part_feats = self.extract_part_features(image_path=image_path, image_bytes=image_bytes)

        # 检测颜色
        color = self._detect_color(image_path=image_path, image_bytes=image_bytes)

        return {
            'global': global_feat,
            'parts': part_feats,
            'color': color,
        }

    def _detect_color(self, image_path: Optional[str] = None,
                      image_bytes: Optional[bytes] = None) -> str:
        """检测车辆颜色（基于HSV主色调分析）"""
        try:
            import cv2
            if image_path:
                img = cv2.imread(image_path)
            else:
                from io import BytesIO
                buf = BytesIO(image_bytes)
                img = cv2.imread(buf)
            if img is None:
                return 'unknown'

            hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)

            color_ranges = [
                ('白色', ([0, 0, 180], [180, 30, 255])),
                ('黑色', ([0, 0, 0], [180, 255, 50])),
                ('灰色', ([0, 0, 50], [180, 30, 180])),
                ('红色', ([0, 150, 50], [10, 255, 255])),
                ('蓝色', ([100, 100, 50], [130, 255, 255])),
                ('绿色', ([35, 50, 50], [85, 255, 255])),
                ('黄色', ([15, 100, 100], [35, 255, 255])),
                ('棕色', ([10, 50, 30], [30, 200, 150])),
                ('银色', ([0, 0, 80], [180, 20, 200])),
                ('橙色', ([10, 150, 150], [25, 255, 255])),
                ('紫色', ([125, 50, 50], [155, 255, 255])),
            ]

            max_pixels = 0
            dominant_color = '未知'
            total_pixels = img.shape[0] * img.shape[1]

            for color_name, (lower, upper) in color_ranges:
                lower = np.array(lower)
                upper = np.array(upper)
                mask = cv2.inRange(hsv, lower, upper)
                pixels = cv2.countNonZero(mask)
                if pixels > max_pixels:
                    max_pixels = pixels
                    dominant_color = color_name

            if max_pixels / total_pixels < 0.05:
                return '未知'
            return dominant_color
        except:
            return 'unknown'

    def features_to_dict(self, features: Dict) -> Dict:
        """将特征转为可序列化字典"""
        result = {
            'global': features['global'].tolist() if isinstance(features['global'], np.ndarray) else features['global'],
            'parts': {},
            'color': features.get('color', 'unknown'),
        }
        for name, feat in features['parts'].items():
            result['parts'][name] = feat.tolist() if isinstance(feat, np.ndarray) else feat
        return result

    def get_weights(self) -> Dict[str, float]:
        """获取特征权重"""
        return self.FEATURE_WEIGHTS.copy()


if __name__ == '__main__':
    mpf = MultiPartFingerprint()
    test_img = Image.new('RGB', (400, 300), color='white')
    test_path = '/tmp/test_car.jpg'
    test_img.save(test_path)
    
    features = mpf.extract_all_features(test_path)
    print("全局特征维度:", features['global'].shape)
    print("部件特征:", {k: v.shape for k, v in features['parts'].items()})
    print("颜色:", features['color'])
