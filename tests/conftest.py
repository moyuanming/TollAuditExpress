"""共享测试 fixtures"""
import os
import sys
import pytest
import tempfile
from unittest.mock import patch, MagicMock
from io import BytesIO

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
def temp_db(monkeypatch):
    """使用临时 SQLite 数据库，并在测试后清理"""
    fd, path = tempfile.mkstemp(suffix='.db')
    os.close(fd)

    import apps.api.database.connection as conn_module
    monkeypatch.setattr(conn_module, 'DB_PATH', path)

    from apps.api.database.connection import init_db
    init_db()

    yield path

    try:
        os.unlink(path)
    except OSError:
        pass


@pytest.fixture
def mock_ml_models():
    """Mock ML 模型，避免依赖 GPU 和模型文件"""
    import numpy as np

    mock_classifier = MagicMock()
    mock_classifier.classify.return_value = [{'class': 'truck', 'confidence': 0.95}]

    mock_fp = MagicMock()
    mock_fp.extract_all_features.return_value = {
        'global': np.array([0.1] * 512),
        'parts': {},
        'color': 'blue'
    }

    with patch(
        'apps.api.services.entry_exit_matcher.VehicleClassifier',
        return_value=mock_classifier
    ), patch(
        'apps.api.services.truck_obu_detector.VehicleClassifier',
        return_value=mock_classifier
    ), patch(
        'apps.api.services.entry_exit_matcher.MultiPartFingerprint',
        return_value=mock_fp
    ), patch(
        'apps.api.services.truck_obu_detector.TruckOBUDetector._verify_with_llm',
        return_value=1
    ):
        yield


@pytest.fixture
def mock_image_download():
    """Mock 图片下载 — 需 patch 所有已导入该函数的模块"""
    fake_bytes = BytesIO(b'fake-image-data')
    with patch(
        'apps.api.services.entry_exit_matcher.download_image',
        return_value=fake_bytes
    ), patch(
        'apps.api.services.truck_obu_detector.download_image',
        return_value=fake_bytes
    ), patch(
        'apps.api.services.image_utils.download_image',
        return_value=fake_bytes
    ):
        yield
