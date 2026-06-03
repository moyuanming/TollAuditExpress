import torch
import torch.nn as nn
from torchvision import transforms, models
from PIL import Image
import os

from apps.api.core.logging_config import get_logger

logger = get_logger(__name__)

class VehicleClassifier:
    def __init__(self, model_path, device=None):
        """
        初始化分类器
        :param model_path: 模型文件路径
        :param device: 指定计算设备 (可选)
        """
        self.device = device if device else self._auto_select_device()
        self.model = self._load_model(model_path)
        self.transform = self._create_transform()

    def _auto_select_device(self):
        """自动选择最佳计算设备"""
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")

    def _load_model(self, model_path):
        """加载预训练模型"""
        # 模型结构定义
        model = models.resnet18(weights=None)
        model.fc = nn.Sequential(nn.Dropout(0.5),
            nn.Linear(model.fc.in_features, 2))

        # 加载权重
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"Model file {model_path} not found")

        checkpoint = torch.load(model_path, map_location=self.device, weights_only=True)
        model.load_state_dict(checkpoint['model_state_dict'])
        return model.to(self.device).eval()

    def _create_transform(self):
        """创建标准图像预处理流程"""
        return transforms.Compose([
            transforms.Resize(256),
            transforms.CenterCrop(224),
            transforms.ToTensor(),
            transforms.Normalize([0.485, 0.456, 0.406],
                               [0.229, 0.224, 0.225])
        ])

    def classify(self, image_input):
        """
        核心分类函数
        :param image_input: 支持多种输入格式：
            - 单张图片路径 (str)
            - 图片路径列表 (list)
            - PIL.Image对象
            - 已经预处理的张量
        :return: 分类结果字典列表，空列表表示加载失败
        """
        # 统一输入格式处理，过滤 None
        inputs = self._preprocess_input(image_input)
        if not inputs:
            return []

        # 批量推理
        with torch.no_grad():
            outputs = self.model(torch.stack(inputs).to(self.device))
            probs = torch.nn.functional.softmax(outputs, dim=1)

        # 结果解析
        return self._parse_results(outputs, probs, image_input)

    def _preprocess_input(self, raw_input):
        """输入数据预处理"""
        if isinstance(raw_input, str):  # 单文件路径
            img = self._load_image(raw_input)
            return [img] if img is not None else []
        elif isinstance(raw_input, list):  # 文件路径列表
            images = [self._load_image(p) for p in raw_input]
            return [img for img in images if img is not None]
        elif isinstance(raw_input, Image.Image):  # PIL图像
            return [self.transform(raw_input)]
        elif torch.is_tensor(raw_input):  # 已处理张量
            return [raw_input]
        elif hasattr(raw_input, 'read'):  # 文件类对象 (BytesIO等)
            raw_input.seek(0)
            img = Image.open(raw_input).convert('RGB')
            return [self.transform(img)]
        else:
            raise ValueError("不支持的输入类型")

    def _load_image(self, path):
        """加载并预处理单张图片"""
        try:
            img = Image.open(path).convert('RGB')
            return self.transform(img)
        except Exception as e:
            logger.warning("Error loading %s: %s", path, e)
            return None

    def _parse_results(self, outputs, probs, original_input):
        """解析模型输出"""
        _, preds = torch.max(outputs, 1)
        results = []

        for i, (pred, prob) in enumerate(zip(preds, probs)):
            confidence = prob[pred].item()
            results.append({
                'class': 'truck' if pred.item() == 1 else 'car',
                'confidence': round(confidence, 4),
                'input_info': self._get_input_info(original_input, i)
            })
        return results

    def _get_input_info(self, original_input, index):
        """获取输入源信息"""
        if isinstance(original_input, (str, list)):
            return {'type': 'file_path',
                   'value': original_input[index]
                       if isinstance(original_input, list)
                       else original_input}
        elif isinstance(original_input, Image.Image):
            return {'type': 'pil_image'}
        else:
            return {'type': 'tensor'}
