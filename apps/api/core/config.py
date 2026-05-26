"""配置管理"""

import os

# 数据库配置
DB_HOST = os.getenv('DB_HOST', '10.11.1.36')
DB_PORT = int(os.getenv('DB_PORT', '9030'))
DB_USER = os.getenv('DB_USER', 'root')
DB_PASSWORD = os.getenv('DB_PASSWORD', 'AynyDskmXx@AynyDskmXx')
DB_NAME = os.getenv('DB_NAME', 'dwd_tolldata')

# ML 模型路径
MODEL_PATH = os.getenv('MODEL_PATH', '/Users/moyuanming/getmoveobu/best_model.pth')

# 图片下载配置
IMAGE_DOWNLOAD_TIMEOUT = int(os.getenv('IMAGE_DOWNLOAD_TIMEOUT', '15'))
IMAGE_DOWNLOAD_RETRIES = int(os.getenv('IMAGE_DOWNLOAD_RETRIES', '3'))

# 稽核配置
TRUCK_OBU_CONFIDENCE_THRESHOLD = float(os.getenv('TRUCK_OBU_CONFIDENCE_THRESHOLD', '0.8'))
FINGERPRINT_SIM_THRESHOLD = float(os.getenv('FINGERPRINT_SIM_THRESHOLD', '0.6'))
