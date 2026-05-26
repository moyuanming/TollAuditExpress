"""
出入口车辆比对服务
比对出入口车辆图片，判断是否为同一辆车
适配自 getmoveobu/audit/services/entry_exit_matcher.py
"""

import sys
import os
from typing import Dict, Optional

GETMOVEOBU_PATH = '/Users/moyuanming/getmoveobu'
if GETMOVEOBU_PATH not in sys.path:
    sys.path.insert(0, GETMOVEOBU_PATH)

try:
    import requests
    from io import BytesIO
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from apps.api.core.ml.vehicle_classifier import VehicleClassifier
from apps.api.core.ml.multi_part_fingerprint import MultiPartFingerprint


class EntryExitMatcher:
    """出入口车辆比对器"""

    def __init__(self, model_path: str = None):
        if model_path is None:
            model_path = os.path.join(GETMOVEOBU_PATH, 'best_model.pth')
        self.classifier = VehicleClassifier(model_path)
        self.fingerprint = MultiPartFingerprint()

    def download_image(self, url: str) -> Optional[BytesIO]:
        """下载图片"""
        if not HAS_REQUESTS:
            return None

        try:
            response = requests.get(url, timeout=15)
            if response.status_code == 200 and 'image' in response.headers.get('Content-Type', ''):
                return BytesIO(response.content)
        except Exception:
            pass
        return None

    def compare(self, entry_record: Dict, exit_record: Dict) -> Dict:
        """
        比对出入口车辆

        Args:
            entry_record: 入口记录
            exit_record: 出口记录

        Returns:
            比对结果:
                - is_suspicious: 是否可疑
                - fraud_type: 逃费类型
                - color_match: 颜色是否一致
                - type_match: 车型是否一致
                - fingerprint_sim: 车纹相似度
                - _comparison_success: 比对是否成功
        """
        result = {
            'is_suspicious': False,
            'fraud_type': None,
            'color_match': True,
            'type_match': True,
            'fingerprint_sim': 0.0,
            'entry_color': None,
            'exit_color': None,
            'entry_visual_type': None,
            'exit_visual_type': None,
            '_comparison_success': False
        }

        entry_url = entry_record.get('image_license')
        exit_url = exit_record.get('image_license')

        if not entry_url or not exit_url:
            result['fingerprint_sim'] = 0.0
            return result

        # 下载图片
        entry_io = self.download_image(entry_url)
        exit_io = self.download_image(exit_url)

        if not entry_io or not exit_io:
            result['fingerprint_sim'] = 0.0
            return result

        try:
            # 车型比对
            entry_result = self.classifier.classify(entry_io)
            exit_result = self.classifier.classify(exit_io)

            if entry_result and len(entry_result) > 0:
                result['entry_visual_type'] = entry_result[0]['class']

            if exit_result and len(exit_result) > 0:
                result['exit_visual_type'] = exit_result[0]['class']

            if entry_result and exit_result:
                if entry_result[0]['class'] != exit_result[0]['class']:
                    result['type_match'] = False
                    result['is_suspicious'] = True
                    result['fraud_type'] = 'ENTRY_EXIT_MISMATCH'

            # 车纹比对
            entry_io.seek(0)
            exit_io.seek(0)

            entry_features = self.fingerprint.extract_all_features(entry_io)
            exit_features = self.fingerprint.extract_all_features(exit_io)

            if entry_features and exit_features:
                import numpy as np
                entry_vec = entry_features['global_feature']
                exit_vec = exit_features['global_feature']

                sim = np.dot(entry_vec, exit_vec) / (np.linalg.norm(entry_vec) * np.linalg.norm(exit_vec))
                result['fingerprint_sim'] = float(sim)

                if sim < 0.6:
                    result['is_suspicious'] = True
                    result['fraud_type'] = 'ENTRY_EXIT_MISMATCH'

                # 颜色比对
                if entry_features.get('color') and exit_features.get('color'):
                    result['entry_color'] = entry_features['color']
                    result['exit_color'] = exit_features['color']
                    if entry_features['color'] != exit_features['color']:
                        result['color_match'] = False

            result['_comparison_success'] = True

        except Exception as e:
            print(f"EntryExitMatcher error: {e}")
            result['_comparison_success'] = False
            result['fingerprint_sim'] = 0.0

        return result


def compare_trip(entry_record: Dict, exit_record: Dict) -> Dict:
    """
    便捷函数：比对出入口记录
    """
    matcher = EntryExitMatcher()
    return matcher.compare(entry_record, exit_record)
