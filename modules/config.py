#!/usr/bin/env python
# -*- coding: utf-8 -*-
#作者：忆痕
#仓库地址：https://github.com/a937750307/lan-printing

"""常量、全局状态与配置管理"""

import os
import sys
import json
import time
import logging
from logging.handlers import RotatingFileHandler

# ==================== Windows DeviceCapabilities 常量 ====================
DC_DUPLEX = 7
DC_COLORDEVICE = 32
DC_PAPERS = 2
DC_PAPERNAMES = 16
DC_ENUMRESOLUTIONS = 13
DC_ORIENTATION = 17
DC_COPIES = 18
DC_TRUETYPE = 28
DC_DRIVER = 11

# ==================== 控制台窗口相关全局变量 ====================
CONSOLE_WINDOW = None
CONSOLE_VISIBLE = True

# ==================== IP配置状态跟踪 ====================
IP_CONFIG_STATE = {'is_static': False, 'last_set_ip': None}

# ==================== 打印和扫描互斥状态管理 ====================
DEVICE_STATUS = {
    'is_printing': False,
    'is_scanning': False,
    'print_start_time': None,
    'scan_start_time': None,
    'print_client': '',
    'scan_client': ''
}

# ==================== 调试模式 ====================
# 调试模式：如果True，则显示虚拟打印机（用于无物理打印机的测试环境）
# 设置环境变量 PRINTING_DEBUG=1 或在此修改来启用
DEBUG_MODE = False

# ==================== Windows纸张大小常量 ====================
DMPAPER_LETTER = 1
DMPAPER_A4 = 9
DMPAPER_A3 = 8
DMPAPER_A5 = 11
DMPAPER_B4 = 12
DMPAPER_B5 = 13
DMPAPER_LEGAL = 5
DMPAPER_EXECUTIVE = 7
DMPAPER_TABLOID = 3

# ==================== 纸张名称映射 ====================
PAPER_NAMES = {
    1: "Letter (8.5 x 11 in)",
    3: "Tabloid (11 x 17 in)",
    5: "Legal (8.5 x 14 in)",
    7: "Executive (7.25 x 10.5 in)",
    8: "A3 (297 x 420 mm)",
    9: "A4 (210 x 297 mm)",
    11: "A5 (148 x 210 mm)",
    12: "B4 (250 x 354 mm)",
    13: "B5 (182 x 257 mm)",
}

# ==================== 虚拟打印机列表 ====================
VIRTUAL_PRINTERS = {
    '导出为WPS PDF', 'WPS PDF', 'Microsoft Print to PDF', 'Microsoft XPS Document Writer',
    'Fax', '传真', 'OneNote', 'OneNote (Desktop)', 'Send To OneNote 2016',
    'Adobe PDF', 'Foxit Reader PDF Printer', 'PDF Creator', 'CutePDF Writer',
    'novaPDF', 'PDFCreator', 'Bullzip PDF Printer', 'doPDF', 'PDF24',
    'Virtual PDF Printer', '虚拟PDF打印机', 'Send to Kindle', '发送到WPS高级打印'
}

# ==================== 允许的文件类型 ====================
ALLOWED_EXT = {'pdf', 'jpg', 'jpeg', 'png', 'txt', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx'}

# ==================== 路径和文件变量（在path_manager初始化后设置） ====================
CONFIG_FILE = None
UPLOAD_FOLDER = None
LOG_FILE = None

# ==================== 日志系统 ====================
logger = logging.getLogger('print_server')
logger.setLevel(logging.INFO)
_logger_initialized = False


def setup_logger(path_mgr):
    """初始化日志系统，使用RotatingFileHandler自动轮转"""
    global _logger_initialized
    if _logger_initialized:
        return
    log_path = path_mgr.get_log_path()
    if not log_path:
        return
    try:
        os.makedirs(os.path.dirname(log_path), exist_ok=True)
        handler = RotatingFileHandler(
            log_path, maxBytes=5 * 1024 * 1024, backupCount=3, encoding='utf-8'
        )
        handler.setFormatter(logging.Formatter(
            '%(asctime)s %(message)s', datefmt='%Y-%m-%d %H:%M:%S'
        ))
        logger.addHandler(handler)
        _logger_initialized = True
    except Exception as e:
        print(f"日志系统初始化失败: {e}")


def init_paths(path_mgr):
    """初始化路径相关的全局变量，需在path_manager创建后调用"""
    global CONFIG_FILE, UPLOAD_FOLDER, LOG_FILE
    CONFIG_FILE = path_mgr.get_config_path()
    UPLOAD_FOLDER = path_mgr.get_upload_dir()
    LOG_FILE = path_mgr.get_log_path()


# ==================== 配置管理函数 ====================

def load_config():
    """加载配置文件"""
    try:
        if CONFIG_FILE and os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                print(f" 配置文件加载成功: {CONFIG_FILE}")
                return config
        print("配置文件不存在，使用默认配置")
        return {}
    except Exception as e:
        print(f"配置文件加载失败: {e}，使用默认配置")
        return {}


def save_config(config):
    """保存配置文件"""
    try:
        if CONFIG_FILE:
            os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
            with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
                json.dump(config, f, ensure_ascii=False, indent=2)
            print(f"配置已保存到: {CONFIG_FILE}")
            return True
        return False
    except Exception as e:
        print(f"配置保存失败: {e}")
        return False


def get_config_port():
    """从配置文件获取端口号"""
    config = load_config()
    return config.get('port', 5000)  # 默认端口5000


def save_port_config(port):
    """保存端口配置"""
    config = load_config()
    config['port'] = port
    return save_config(config)
