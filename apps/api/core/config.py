"""配置管理"""

import os

# 数据库配置
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '9030'))
DB_USER = os.getenv('DB_USER', 'audit_user')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'dwd_tolldata')

# 外部工具路径
GETMOVEOBU_PATH = os.getenv('GETMOVEOBU_PATH', '')
MODEL_PATH = os.getenv('MODEL_PATH', os.path.join(GETMOVEOBU_PATH, 'best_model.pth') if GETMOVEOBU_PATH else '')

# 图片下载配置
IMAGE_DOWNLOAD_TIMEOUT = int(os.getenv('IMAGE_DOWNLOAD_TIMEOUT', '15'))
IMAGE_DOWNLOAD_RETRIES = int(os.getenv('IMAGE_DOWNLOAD_RETRIES', '3'))

# 稽核配置
TRUCK_OBU_CONFIDENCE_THRESHOLD = float(os.getenv('TRUCK_OBU_CONFIDENCE_THRESHOLD', '0.8'))
FINGERPRINT_SIM_THRESHOLD = float(os.getenv('FINGERPRINT_SIM_THRESHOLD', '0.6'))

# LLM API Keys
ZHIPU_API_KEY = os.getenv('ZHIPU_API_KEY', '')
DOUBAO_API_KEY = os.getenv('DOUBAO_API_KEY', '')
QWEN_API_KEY = os.getenv('QWEN_API_KEY', '')
MAAS_API_KEY = os.getenv('MAAS_API_KEY', '')
MAAS_MODEL = os.getenv('MAAS_MODEL', 'qwen2.5-vl-72b')
MAAS_API_URL = os.getenv('MAAS_API_URL', 'https://api.modelarts-maas.com/v1/chat/completions')
LLM_TIMEOUT = int(os.getenv('LLM_TIMEOUT', '60'))

# 车辆部件检测模型（需自定义训练模型，COCO预训练模型无法检测车辆部件）
VEHICLE_PART_MODEL_PATH = os.getenv('VEHICLE_PART_MODEL_PATH', '')

# CORS
CORS_ORIGINS = os.getenv('CORS_ORIGINS', 'http://localhost:3000').split(',')

# 鉴权
API_KEY = os.getenv('API_KEY', '')

# 日志
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
