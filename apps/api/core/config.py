"""配置管理"""

import os

try:
    from dotenv import load_dotenv
    # config.py 在 apps/api/core/config.py
    # 要到 repo 根需剥 3 层：core → api → apps
    # 要到 apps/api 需剥 2 层：core → api
    _here = os.path.dirname(os.path.abspath(__file__))
    _root = os.path.join(_here, '..', '..', '..', '.env')
    if os.path.exists(_root):
        load_dotenv(_root)
    _api = os.path.join(_here, '..', '.env')
    if os.path.exists(_api):
        # override=True：api 专用配置覆盖根 .env 里的空占位
        load_dotenv(_api, override=True)
except ImportError:
    pass

# 数据库配置 — 源库(远程 Doris,只读原始通行流水)
DB_HOST = os.getenv('DB_HOST', 'localhost')
DB_PORT = int(os.getenv('DB_PORT', '9030'))
DB_USER = os.getenv('DB_USER', 'audit_user')
DB_PASSWORD = os.getenv('DB_PASSWORD', '')
DB_NAME = os.getenv('DB_NAME', 'dwd_tolldata')

# 数据库配置 — 审计目标库(承载 SQLite 派生表,迁移目的地)
# 默认与源库共用连接,需要时可通过 DB_AUDIT_HOST 等覆盖为独立实例
DB_AUDIT_HOST = os.getenv('DB_AUDIT_HOST', DB_HOST)
DB_AUDIT_PORT = int(os.getenv('DB_AUDIT_PORT', str(DB_PORT)))
DB_AUDIT_USER = os.getenv('DB_AUDIT_USER', DB_USER)
DB_AUDIT_PASSWORD = os.getenv('DB_AUDIT_PASSWORD', DB_PASSWORD)
DB_AUDIT_NAME = os.getenv('DB_AUDIT_NAME', 'ods_AI_DB')

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

# OAuth / JWT 统一登录平台配置
AUTH_ENABLED = os.getenv('AUTH_ENABLED', 'false').lower() == 'true'
AUTH_JWT_SERVICE_BASE_URL = os.getenv('AUTH_JWT_SERVICE_BASE_URL', '')
AUTH_JWT_CLIENT_ID = os.getenv('AUTH_JWT_CLIENT_ID', '')
AUTH_JWT_CLIENT_SECRET = os.getenv('AUTH_JWT_CLIENT_SECRET', '')
_raw_key = os.getenv('AUTH_JWT_PUBLIC_KEY', '')
AUTH_JWT_PUBLIC_KEY = _raw_key.replace('\\n', '\n') if _raw_key else ''
AUTH_LOGIN_URL = os.getenv('AUTH_LOGIN_URL', '')

# 日志
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
