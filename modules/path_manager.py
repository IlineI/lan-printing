#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""统一路径管理器"""

import os
import sys


class PathManager:
    """统一路径管理器，支持PyInstaller打包和开发环境"""
    
    def __init__(self):
        self._is_packaged = hasattr(sys, '_MEIPASS')
        if self._is_packaged:
            self._resource_dir = sys._MEIPASS
            self._app_dir = os.path.dirname(sys.executable)
            self._data_dir = self._app_dir
        else:
            modules_dir = os.path.dirname(os.path.abspath(__file__))
            script_dir = os.path.dirname(modules_dir)  # 项目根目录（modules的上一级）
            self._resource_dir = script_dir
            self._app_dir = script_dir
            self._data_dir = script_dir
    
    @property
    def is_packaged(self):
        return self._is_packaged
    
    @property
    def app_dir(self):
        return self._app_dir
    
    def get_resource_path(self, relative_path):
        return os.path.join(self._resource_dir, relative_path)
    
    def get_data_path(self, relative_path):
        return os.path.join(self._data_dir, relative_path)
    
    def get_config_path(self):
        return self.get_data_path('config.json')
    
    def get_log_path(self):
        return self.get_data_path('print_log.txt')
    
    def get_upload_dir(self):
        return self.get_data_path('uploads')
    
    def get_scan_dir(self):
        return self.get_data_path('scanned_files')
    
    def get_executable_name(self):
        return os.path.basename(sys.executable) if self._is_packaged else os.path.basename(sys.argv[0])
    
    def ensure_data_dirs(self):
        try:
            os.makedirs(self.get_upload_dir(), exist_ok=True)
            os.makedirs(self.get_scan_dir(), exist_ok=True)
            return True
        except Exception as e:
            print(f"创建数据目录失败: {e}")
            return False


def get_poppler_path(path_mgr):
    """确定用于 pdf2image 的 poppler 可执行文件路径。
    优先级：环境变量 `POPPLER_PATH` -> path_manager 中配置（若有）-> 打包内置目录 -> 项目相对 `third_party/poppler`。
    返回 None 表示使用系统 PATH 查找。
    """
    try:
        # 1. 环境变量覆盖
        env_path = os.environ.get('POPPLER_PATH')
        if env_path and os.path.isdir(env_path):
            return env_path

        # 2. path_manager 支持
        try:
            pm_path = getattr(path_mgr, 'get_poppler_path', None)
            if pm_path:
                p = pm_path()
                if p and os.path.isdir(p):
                    return p
        except Exception:
            pass

        # 3. PyInstaller 打包时资源会解压到 sys._MEIPASS
        base = None
        if getattr(sys, '_MEIPASS', None):
            base = sys._MEIPASS
        else:
            base = os.path.dirname(os.path.abspath(__file__))  # modules/
            base = os.path.dirname(base)  # 项目根目录

        candidates = [
            os.path.join(base, 'poppler_bin'),
            os.path.join(base, 'third_party', 'poppler', 'Library', 'bin'),
            os.path.join(base, 'third_party', 'poppler', 'bin'),
            os.path.join(base, 'poppler', 'Library', 'bin'),
            os.path.join(base, 'poppler', 'bin'),
            os.path.join(base, 'poppler'),
        ]

        for c in candidates:
            if os.path.isdir(c):
                return c

    except Exception:
        pass
    return None


def print_startup_diagnostics(path_mgr):
    """打印启动诊断信息"""
    # Poppler 路径检测
    try:
        _detected_poppler = get_poppler_path(path_mgr)
        if _detected_poppler:
            print(f"Poppler path detected: {_detected_poppler}")
        else:
            print("Poppler path not detected: will use system PATH or pdf2image default")
    except Exception as _e:
        print(f"检测 Poppler 路径时出错: {_e}")

    # 其他启动时诊断信息
    try:
        print(f"Python executable: {sys.executable}")
        print(f"Working directory: {os.getcwd()}")
        try:
            import pdf2image
            print("pdf2image available")
        except Exception as _e:
            print(f"pdf2image not available: {_e}")

        try:
            import win32print
            try:
                default_pr = win32print.GetDefaultPrinter()
                print(f"Default printer: {default_pr}")
            except Exception:
                print("Default printer: 未能检测到")
        except Exception:
            print("win32print not available, 跳过默认打印机检测")
    except Exception as _e:
        print(f"启动时环境诊断出错: {_e}")


# 全局单例，供其他模块直接导入使用
path_manager = PathManager()
