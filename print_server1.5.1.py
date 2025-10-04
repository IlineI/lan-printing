#!/usr/bin/env python
# -*- coding: utf-8 -*-
#作者：忆痕
#仓库地址：https://github.com/a937750307/lan-printing
 
import os
from flask import Flask, request, render_template_string, send_from_directory, redirect, url_for, flash, jsonify
# 打印相关
import win32print
import win32api
import win32con
import subprocess
import time
from datetime import datetime
# 托盘相关
import threading
import sys
import pystray
from PIL import Image, ImageDraw
import socket
import winreg
import time
import json

# Windows DeviceCapabilities 常量
DC_DUPLEX = 7
DC_COLORDEVICE = 32
DC_PAPERS = 2
DC_PAPERNAMES = 16
DC_ENUMRESOLUTIONS = 13
DC_ORIENTATION = 17
DC_COPIES = 18
DC_TRUETYPE = 28
DC_DRIVER = 11

# 控制台窗口相关全局变量
CONSOLE_WINDOW = None
CONSOLE_VISIBLE = True

# Windows纸张大小常量
DMPAPER_LETTER = 1
DMPAPER_A4 = 9
DMPAPER_A3 = 8
DMPAPER_A5 = 11
DMPAPER_B4 = 12
DMPAPER_B5 = 13
DMPAPER_LEGAL = 5
DMPAPER_EXECUTIVE = 7
DMPAPER_TABLOID = 3

# 纸张名称映射
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

class PathManager:
    """统一路径管理器"""
    
    def __init__(self):
        self._is_packaged = hasattr(sys, '_MEIPASS')
        self._app_dir = None
        self._resource_dir = None
        self._data_dir = None
        self._init_paths()
    
    def _init_paths(self):
        """初始化路径配置"""
        if self._is_packaged:
            # PyInstaller打包后的路径配置
            self._resource_dir = sys._MEIPASS  # 打包内的资源目录
            self._app_dir = os.path.dirname(sys.executable)  # exe所在目录
            self._data_dir = self._app_dir  # 数据文件存储目录
        else:
            # 源码运行时的路径配置
            script_dir = os.path.dirname(os.path.abspath(__file__))
            self._resource_dir = script_dir  # 资源和源码在同一目录
            self._app_dir = script_dir  # 应用目录
            self._data_dir = script_dir  # 数据文件存储目录
    
    @property
    def is_packaged(self):
        """是否为打包后的exe文件"""
        return self._is_packaged
    
    @property
    def app_dir(self):
        """应用主目录（exe所在目录或脚本所在目录）"""
        return self._app_dir
    
    def get_resource_path(self, relative_path):
        """获取资源文件的完整路径（图标、模板等）"""
        return os.path.join(self._resource_dir, relative_path)
    
    def get_data_path(self, relative_path):
        """获取数据文件的完整路径（配置、日志、上传文件等）"""
        return os.path.join(self._data_dir, relative_path)
    
    def get_config_path(self):
        """获取配置文件路径"""
        return self.get_data_path('config.json')
    
    def get_log_path(self):
        """获取日志文件路径"""
        return self.get_data_path('print_log.txt')
    
    def get_upload_dir(self):
        """获取上传文件目录"""
        return self.get_data_path('uploads')
    
    def get_executable_name(self):
        """获取当前执行文件名（用于进程检测）"""
        if self._is_packaged:
            return os.path.basename(sys.executable)
        else:
            return os.path.basename(sys.argv[0])
    
    def ensure_data_dirs(self):
        """确保数据目录存在"""
        try:
            upload_dir = self.get_upload_dir()
            os.makedirs(upload_dir, exist_ok=True)
            return True
        except Exception as e:
            print(f"⚠️ 创建数据目录失败: {e}")
            return False

# 创建全局路径管理器实例
path_manager = PathManager()

# 全局服务状态管理
class ServiceManager:
    """服务管理器，用于管理Flask服务和程序重启"""
    def __init__(self):
        self.flask_thread = None
        self.cleaner_thread = None
        self.monitor_thread = None
        self.should_restart = False
        self.restart_port = None
        self.service_running = False
        self.last_health_check = time.time()
        self.health_check_interval = 600  # 10分钟检查一次，进一步减少频率
        self.health_fail_count = 0  # 健康检查失败计数
        self.start_time = None  # 服务启动时间
    
    def set_restart(self, port):
        """设置重启标志和新端口"""
        self.should_restart = True
        self.restart_port = port
    
    def is_restart_requested(self):
        """检查是否需要重启"""
        return self.should_restart
    
    def get_restart_port(self):
        """获取重启端口"""
        return self.restart_port
    
    def clear_restart(self):
        """清除重启标志"""
        self.should_restart = False
        self.restart_port = None
    
    def mark_service_running(self):
        """标记服务运行状态"""
        self.service_running = True
        self.last_health_check = time.time()
        if self.start_time is None:  # 只在第一次启动时设置
            self.start_time = time.time()
        self.health_fail_count = 0  # 重置失败计数
    
    def mark_service_stopped(self):
        """标记服务停止状态"""
        self.service_running = False
    
    def is_service_healthy(self):
        """检查服务健康状态"""
        if not self.service_running:
            return False
        # 检查Flask线程是否仍然活跃
        if self.flask_thread and not self.flask_thread.is_alive():
            return False
        return True
    
    def update_health_check(self):
        """更新健康检查时间"""
        self.last_health_check = time.time()
    
    def restart_flask_service(self):
        """重启Flask服务"""
        try:
            print("🔄 检测到服务异常，正在重启Flask服务...")
            
            # 停止旧服务
            if self.flask_thread and self.flask_thread.is_alive():
                # 由于Flask没有优雅关闭机制，我们标记为停止并创建新线程
                self.mark_service_stopped()
            
            # 启动新服务
            port = getattr(app, 'current_port', 5000)
            app.current_port = port
            
            if os.environ.get('USE_WSGI', '').lower() == 'true':
                self.flask_thread = threading.Thread(target=run_wsgi, daemon=True)
            else:
                self.flask_thread = threading.Thread(target=run_flask, daemon=True)
            
            self.flask_thread.start()
            self.mark_service_running()
            
            print("✅ Flask服务重启成功")
            return True
            
        except Exception as e:
            print(f"❌ Flask服务重启失败: {e}")
            return False

service_manager = ServiceManager()

def clean_old_files(folder=None, expire_seconds=3600):
    """定期清理指定目录下超过expire_seconds的文件，并启动日志清理"""
    if folder is None:
        folder = path_manager.get_upload_dir()
    
    # 启动日志清理线程（只启动一次）
    if not hasattr(clean_old_files, 'log_cleanup_started'):
        import threading
        log_cleanup_thread = threading.Thread(target=periodic_log_cleanup, daemon=True)
        log_cleanup_thread.start()
        clean_old_files.log_cleanup_started = True
        print("📋 日志自动清理功能已启动")
    
    while True:
        now = time.time()
        for fname in os.listdir(folder):
            fpath = os.path.join(folder, fname)
            if os.path.isfile(fpath):
                try:
                    if now - os.path.getmtime(fpath) > 600:  # 10分钟
                        os.remove(fpath)
                except Exception:
                    pass
        time.sleep(60)  # 每1分钟检查一次

def monitor_service_health():
    """监控服务健康状态，发现异常时自动重启"""
    
    # 尝试导入requests，如果失败则使用简化的监控
    try:
        import requests
        use_http_check = True
    except ImportError:
        print("⚠️ requests库未安装，使用简化监控模式")
        use_http_check = False
    
    startup_message_shown = False  # 控制启动消息只显示一次
    
    while True:
        try:
            time.sleep(service_manager.health_check_interval)
            
            # 检查Flask线程是否还活着
            if not service_manager.is_service_healthy():
                print("⚠️ 检测到Flask服务异常")
                service_manager.restart_flask_service()
                startup_message_shown = False  # 重启后需要重新显示启动消息
                continue
            
            # 如果服务刚启动，给它一些时间稳定
            if service_manager.start_time and (time.time() - service_manager.start_time) < 10:
                if not startup_message_shown:
                    print("🔄 服务启动中，健康检查暂停10秒...")
                    startup_message_shown = True
                continue
            
            # 如果有requests库，进行HTTP健康检查
            if use_http_check:
                try:
                    port = getattr(app, 'current_port', 5000)
                    # 增加重试机制，避免网络抖动
                    response = requests.get(f'http://127.0.0.1:{port}/health', timeout=3)
                    if response.status_code == 200:
                        # 健康检查成功
                        service_manager.update_health_check()
                        # 重置失败计数
                        if hasattr(service_manager, 'health_fail_count'):
                            service_manager.health_fail_count = 0
                        # print("✅ 服务健康检查通过")  # 减少日志输出
                    else:
                        raise Exception(f"健康检查返回状态码: {response.status_code}")
                except Exception as e:
                    # print(f"⚠️ 服务健康检查失败: {e}")  # 减少日志噪音
                    # 连续失败5次才重启服务，避免误判（从3次改为5次）
                    if hasattr(service_manager, 'health_fail_count'):
                        service_manager.health_fail_count += 1
                    else:
                        service_manager.health_fail_count = 1
                    
                    # 只在失败计数达到3次及以上时才输出警告
                    if service_manager.health_fail_count >= 3:
                        print(f"⚠️ 健康检查失败计数: {service_manager.health_fail_count}/5")
                    
                    if service_manager.health_fail_count >= 5:
                        print("❌ 连续健康检查失败，重启服务")
                        service_manager.restart_flask_service()
                        service_manager.health_fail_count = 0
            else:
                # 简化监控：只检查线程状态和简单的socket连接
                try:
                    import socket
                    port = getattr(app, 'current_port', 5000)
                    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    sock.settimeout(3)  # 减少超时时间
                    result = sock.connect_ex(('127.0.0.1', port))
                    sock.close()
                    
                    if result == 0:
                        # 简化健康检查通过
                        service_manager.update_health_check()
                        if hasattr(service_manager, 'health_fail_count'):
                            service_manager.health_fail_count = 0
                        # print("✅ 简化健康检查通过")  # 减少日志输出
                    else:
                        raise Exception(f"端口{port}连接失败，错误码: {result}")
                        
                except Exception as e:
                    # print(f"⚠️ 简化健康检查失败: {e}")  # 减少日志噪音
                    # 连续失败5次才重启服务，避免误判（从3次改为5次）
                    if hasattr(service_manager, 'health_fail_count'):
                        service_manager.health_fail_count += 1
                    else:
                        service_manager.health_fail_count = 1
                    
                    # 只在失败计数达到3次及以上时才输出警告
                    if service_manager.health_fail_count >= 3:
                        print(f"⚠️ 简化健康检查失败计数: {service_manager.health_fail_count}/5")
                    
                    if service_manager.health_fail_count >= 5:
                        print("❌ 连续健康检查失败，重启服务")
                        service_manager.restart_flask_service()
                        service_manager.health_fail_count = 0
        
        except Exception as e:
            print(f"⚠️ 服务监控异常: {e}")
            time.sleep(10)  # 发生异常时短暂等待

# 使用路径管理器获取配置文件路径
CONFIG_FILE = path_manager.get_config_path()

def load_config():
    """加载配置文件"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                config = json.load(f)
                print(f"✅ 配置文件加载成功: {CONFIG_FILE}")
                return config
        else:
            print("ℹ️ 配置文件不存在，使用默认配置")
            return {}
    except Exception as e:
        print(f"⚠️ 配置文件加载失败: {e}，使用默认配置")
        return {}

def save_config(config):
    """保存配置文件"""
    try:
        # 确保目录存在
        os.makedirs(os.path.dirname(CONFIG_FILE), exist_ok=True)
        
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        print(f"✅ 配置已保存到: {CONFIG_FILE}")
        return True
    except Exception as e:
        print(f"❌ 配置保存失败: {e}")
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

def detect_system_software():
    """检测系统中可用的打印相关软件 - 注册表+文件路径双重检测"""
    software_status = {
        'pdf_readers': [],
        'office_suites': [],
        'browsers': []
    }
    
    # 方法1: 注册表检测（最准确和快速）
    try:
        import winreg
        reg_paths = [
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"),
            (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"),
        ]
        
        found_names = set()  # 避免重复
        
        for hkey, reg_path in reg_paths:
            try:
                with winreg.OpenKey(hkey, reg_path) as key:
                    for i in range(min(200, winreg.QueryInfoKey(key)[0])):  # 限制搜索数量提高速度
                        try:
                            subkey_name = winreg.EnumKey(key, i)
                            with winreg.OpenKey(key, subkey_name) as subkey:
                                try:
                                    display_name = winreg.QueryValueEx(subkey, "DisplayName")[0]
                                    name_lower = display_name.lower()
                                    
                                    # PDF软件检测
                                    if 'adobe' in name_lower and ('reader' in name_lower or 'acrobat' in name_lower):
                                        if display_name not in found_names:
                                            software_status['pdf_readers'].append((display_name, "注册表检测"))
                                            found_names.add(display_name)
                                    
                                    # Office软件检测
                                    elif 'wps office' in name_lower or 'kingsoft' in name_lower:
                                        if display_name not in found_names:
                                            software_status['office_suites'].append((display_name, "注册表检测"))
                                            found_names.add(display_name)
                                    
                                    elif 'microsoft office' in name_lower:
                                        if display_name not in found_names:
                                            software_status['office_suites'].append((display_name, "注册表检测"))
                                            found_names.add(display_name)
                                            
                                except FileNotFoundError:
                                    pass
                        except Exception:
                            continue
            except Exception:
                continue
    except ImportError:
        pass
    
    # 方法2: 文件夹快速检测（作为补充，只检查主要路径）
    quick_checks = [
        # Adobe 检查
        (r"C:\Program Files\Adobe", "Adobe 产品套装", "pdf_readers"),
        (r"C:\Program Files (x86)\Adobe", "Adobe 产品套装", "pdf_readers"), 
        # Kingsoft/WPS 检查
        (r"C:\Program Files (x86)\Kingsoft", "WPS Office", "office_suites"),
        (r"C:\Program Files\Kingsoft", "WPS Office", "office_suites"),
        # Microsoft Office 检查  
        (r"C:\Program Files (x86)\Microsoft Office", "Microsoft Office", "office_suites"),
        (r"C:\Program Files\Microsoft Office", "Microsoft Office", "office_suites")
    ]
    
    for folder_path, software_name, category in quick_checks:
        try:
            if os.path.exists(folder_path):
                # 确保不重复添加
                exists = any(software_name in item[0] for item in software_status[category])
                if not exists:
                    software_status[category].append((software_name, f"文件夹检测: {folder_path}"))
        except Exception:
            continue
    
    # 方法3: 浏览器检测（用于PDF打印后备）
    browser_apps = [
        (r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe", "Microsoft Edge"),
        (r"C:\Program Files\Microsoft\Edge\Application\msedge.exe", "Microsoft Edge"),
        (r"C:\Program Files\Google\Chrome\Application\chrome.exe", "Google Chrome"),
        (r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe", "Google Chrome")
    ]
    
    found_browsers = set()
    for path, name in browser_apps:
        try:
            if os.path.exists(path) and name not in found_browsers:
                software_status['browsers'].append((name, path))
                found_browsers.add(name)
                break  # 找到一个即可
        except Exception:
            continue
    
    return software_status

 
# 获取本机局域网IP
def get_local_ip():
    """获取本机IP地址 - 支持内网穿透"""
    try:
        # 尝试连接外部服务器获取本机IP
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)  # 减少超时时间，快速失败
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        # 如果外网不通，尝试获取本地网络接口IP
        try:
            # 方案2：通过获取本机hostname对应的IP
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            if ip and ip != '127.0.0.1':
                return ip
        except Exception:
            pass
        
        try:
            # 方案3：遍历网络接口获取非回环地址
            import subprocess
            result = subprocess.run(['ipconfig'], capture_output=True, text=True, encoding='gbk', timeout=10)
            if result.returncode == 0:
                lines = result.stdout.split('\n')
                for line in lines:
                    if 'IPv4' in line and '地址' in line:
                        parts = line.split(':')
                        if len(parts) > 1:
                            ip = parts[1].strip()
                            if ip and not ip.startswith('127.') and not ip.startswith('169.254.'):
                                return ip
        except Exception:
            pass
        
        # 最后返回本地回环地址
        return '127.0.0.1'

def get_external_ip():
    """获取公网IP地址（用于内网穿透检测）"""
    try:
        import urllib.request
        # 尝试多个IP检测服务
        services = [
            'https://ipv4.icanhazip.com',
            'https://api.ipify.org',
            'https://checkip.amazonaws.com',
            'https://ipinfo.io/ip'
        ]
        
        for service in services:
            try:
                with urllib.request.urlopen(service, timeout=3) as response:
                    external_ip = response.read().decode('utf-8').strip()
                    if external_ip and '.' in external_ip and not external_ip.startswith('192.168.') and not external_ip.startswith('10.') and not external_ip.startswith('172.'):
                        return external_ip
            except Exception:
                continue
                
    except Exception:
        pass
    
    return None

def detect_network_mode():
    """检测网络模式：内网/公网/内网穿透"""
    local_ip = get_local_ip()
    external_ip = get_external_ip()
    
    # 判断是否为内网地址
    is_private = (local_ip.startswith('192.168.') or 
                  local_ip.startswith('10.') or 
                  local_ip.startswith('172.') or
                  local_ip == '127.0.0.1')
    
    # 更准确的内网穿透检测：
    # 1. 检查是否有端口转发或内网穿透工具的迹象
    # 2. 简单的方法：检测服务是否可从外网访问（但这需要实际测试，风险较大）
    # 3. 保守方案：仅在本机IP是公网IP时才判断为公网模式
    
    if not is_private:
        return "public"  # 本机直接使用公网IP
    elif local_ip == '127.0.0.1':
        return "private"  # 仅本机访问
    else:
        # 对于内网IP，默认返回private，不主动判断内网穿透
        # 因为普通家庭网络也会有公网IP，但不代表开启了内网穿透
        return "private"  # 纯内网模式

def get_current_ip_config():
    """获取当前IP配置状态"""
    try:
        # 使用更简单的方法获取IP信息
        current_ip = get_local_ip()
        if current_ip and current_ip != '127.0.0.1':
            # 尝试获取详细信息
            try:
                result = subprocess.run(['ipconfig', '/all'], 
                                      capture_output=True, text=True, 
                                      encoding='gbk', errors='ignore')
                
                # 简化解析，只获取基本信息
                config = {
                    'index': '1',
                    'description': '以太网适配器',
                    'ip': current_ip,
                    'subnet': '255.255.255.0',  # 默认子网掩码
                    'gateway': '',
                    'dhcp_enabled': True  # 默认假设DHCP
                }
                
                # 尝试从ipconfig输出中提取网关信息
                if 'Default Gateway' in result.stdout or '默认网关' in result.stdout:
                    lines = result.stdout.split('\n')
                    for line in lines:
                        if 'Default Gateway' in line or '默认网关' in line:
                            parts = line.split(':')
                            if len(parts) > 1:
                                gateway = parts[1].strip()
                                if gateway and gateway != '':
                                    config['gateway'] = gateway
                                    break
                
                return config
            except Exception:
                # 如果获取详细信息失败，返回基础信息
                return {
                    'index': '1',
                    'description': '网络适配器',
                    'ip': current_ip,
                    'subnet': '255.255.255.0',
                    'gateway': '',
                    'dhcp_enabled': True
                }
        else:
            return {}
    except Exception as e:
        print(f"获取IP配置失败: {e}")
        return {}

def set_static_ip(ip_address, subnet_mask='255.255.255.0', gateway=''):
    """设置静态IP地址"""
    try:
        # 获取当前网络适配器
        config = get_current_ip_config()
        if not config:
            return False, "未找到有效的网络适配器"
        
        adapter_index = config['index']
        
        # 如果没有指定网关，尝试自动推导
        if not gateway:
            ip_parts = ip_address.split('.')
            if len(ip_parts) == 4:
                gateway = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.1"
        
        # 设置静态IP
        cmd = [
            'netsh', 'interface', 'ip', 'set', 'address',
            f'name="本地连接"' if 'Ethernet' in config['description'] else f'name="以太网"',
            'static', ip_address, subnet_mask, gateway
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='gbk')
        
        if result.returncode == 0:
            return True, "IP地址设置成功"
        else:
            # 尝试使用WMI方式
            return set_static_ip_wmi(adapter_index, ip_address, subnet_mask, gateway)
    
    except Exception as e:
        return False, f"设置IP地址失败: {str(e)}"

def set_static_ip_wmi(adapter_index, ip_address, subnet_mask, gateway):
    """使用WMI设置静态IP地址"""
    try:
        cmd = [
            'wmic', 'path', 'win32_networkadapterconfiguration',
            'where', f'Index={adapter_index}',
            'call', 'EnableStatic',
            f'("{ip_address}")', f'("{subnet_mask}")'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            # 设置网关
            if gateway:
                gateway_cmd = [
                    'wmic', 'path', 'win32_networkadapterconfiguration',
                    'where', f'Index={adapter_index}',
                    'call', 'SetGateways',
                    f'("{gateway}")', '(1)'
                ]
                subprocess.run(gateway_cmd, capture_output=True, text=True)
            
            return True, "IP地址设置成功"
        else:
            return False, f"WMI设置失败: {result.stderr}"
    
    except Exception as e:
        return False, f"WMI设置异常: {str(e)}"

def set_dhcp():
    """启用DHCP动态获取IP"""
    try:
        config = get_current_ip_config()
        if not config:
            return False, "未找到有效的网络适配器"
        
        # 尝试使用netsh命令
        cmd = [
            'netsh', 'interface', 'ip', 'set', 'address',
            f'name="本地连接"' if 'Ethernet' in config['description'] else f'name="以太网"',
            'dhcp'
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, encoding='gbk')
        
        if result.returncode == 0:
            return True, "已启用DHCP动态获取IP"
        else:
            # 尝试WMI方式
            adapter_index = config['index']
            cmd = [
                'wmic', 'path', 'win32_networkadapterconfiguration',
                'where', f'Index={adapter_index}',
                'call', 'EnableDHCP'
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode == 0:
                return True, "已启用DHCP动态获取IP"
            else:
                return False, f"启用DHCP失败: {result.stderr}"
    
    except Exception as e:
        return False, f"启用DHCP异常: {str(e)}"

def suggest_static_ip():
    """建议一个可用的静态IP地址"""
    current_ip = get_local_ip()
    if current_ip and current_ip != '127.0.0.1':
        # 基于当前IP建议一个静态IP
        ip_parts = current_ip.split('.')
        if len(ip_parts) == 4:
            # 建议使用当前网段的.100地址
            suggested_ip = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.100"
            return suggested_ip
    
    # 默认建议
    return "192.168.1.100"
 
def detect_remote_desktop():
    """检测是否在远程桌面环境中运行"""
    try:
        # 方法1: 检查SESSIONNAME环境变量
        session_name = os.environ.get('SESSIONNAME', '')
        if session_name.startswith('RDP-Tcp'):
            return True
        
        # 方法2: 检查CLIENTNAME环境变量
        client_name = os.environ.get('CLIENTNAME', '')
        if client_name and client_name != os.environ.get('COMPUTERNAME', ''):
            return True
        
        # 方法3: 检查TS_SESSION_ID环境变量
        ts_session = os.environ.get('TS_SESSION_ID', '')
        if ts_session and ts_session != '0':
            return True
            
        # 方法4: 通过Windows API检查
        try:
            import ctypes
            from ctypes import wintypes
            
            # GetSystemMetrics(SM_REMOTESESSION)
            SM_REMOTESESSION = 0x1000
            user32 = ctypes.windll.user32
            is_remote = user32.GetSystemMetrics(SM_REMOTESESSION)
            if is_remote:
                return True
        except Exception:
            pass
            
        return False
    except Exception as e:
        print(f"检测远程桌面环境失败: {e}")
        return False

def get_print_queue_jobs(printer_name=None):
    """获取指定打印机的打印队列任务"""
    try:
        import win32print
        jobs = []
        
        if printer_name:
            # 获取指定打印机的任务
            try:
                printer_handle = win32print.OpenPrinter(printer_name)
                job_list = win32print.EnumJobs(printer_handle, 0, -1, 1)
                for job in job_list:
                    jobs.append({
                        'job_id': job['JobId'],
                        'printer': printer_name,
                        'document': job['pDocument'],
                        'user': job['pUserName'],
                        'status': job['Status'],
                        'pages': job['PagesPrinted'],
                        'size': job['Size']
                    })
                win32print.ClosePrinter(printer_handle)
            except Exception as e:
                print(f"获取打印机 {printer_name} 队列失败: {e}")
        else:
            # 获取所有打印机的任务
            for printer in PRINTERS:
                try:
                    printer_handle = win32print.OpenPrinter(printer)
                    job_list = win32print.EnumJobs(printer_handle, 0, -1, 1)
                    for job in job_list:
                        jobs.append({
                            'job_id': job['JobId'],
                            'printer': printer,
                            'document': job['pDocument'],
                            'user': job['pUserName'],
                            'status': job['Status'],
                            'pages': job['PagesPrinted'],
                            'size': job['Size']
                        })
                    win32print.ClosePrinter(printer_handle)
                except Exception as e:
                    print(f"获取打印机 {printer} 队列失败: {e}")
        
        return jobs
    except Exception as e:
        print(f"获取打印队列失败: {e}")
        return []

# Windows打印任务状态常量
JOB_STATUS_QUEUED = 0x0000
JOB_STATUS_PAUSED = 0x0001
JOB_STATUS_ERROR = 0x0002
JOB_STATUS_DELETING = 0x0004
JOB_STATUS_SPOOLING = 0x0008
JOB_STATUS_PRINTING = 0x0010
JOB_STATUS_OFFLINE = 0x0020
JOB_STATUS_PAPEROUT = 0x0040
JOB_STATUS_PRINTED = 0x0080
JOB_STATUS_DELETED = 0x0100
JOB_STATUS_BLOCKED_DEVQ = 0x0200
JOB_STATUS_USER_INTERVENTION = 0x0400
JOB_STATUS_RESTART = 0x0800
JOB_STATUS_COMPLETE = 0x1000

def get_job_status_description(status):
    """获取打印任务状态描述"""
    status_descriptions = []
    if status & JOB_STATUS_QUEUED:
        status_descriptions.append("排队中")
    if status & JOB_STATUS_PAUSED:
        status_descriptions.append("已暂停")
    if status & JOB_STATUS_ERROR:
        status_descriptions.append("错误")
    if status & JOB_STATUS_DELETING:
        status_descriptions.append("删除中")
    if status & JOB_STATUS_SPOOLING:
        status_descriptions.append("后台处理中")
    if status & JOB_STATUS_PRINTING:
        status_descriptions.append("正在打印")
    if status & JOB_STATUS_OFFLINE:
        status_descriptions.append("离线")
    if status & JOB_STATUS_PAPEROUT:
        status_descriptions.append("缺纸")
    if status & JOB_STATUS_PRINTED:
        status_descriptions.append("已打印")
    if status & JOB_STATUS_COMPLETE:
        status_descriptions.append("已完成")
    
    return ", ".join(status_descriptions) if status_descriptions else "未知状态"

def is_job_actively_printing(status):
    """检查任务是否正在打印"""
    return bool(status & (JOB_STATUS_PRINTING | JOB_STATUS_SPOOLING))

def is_job_cancellable(status):
    """检查任务是否可以取消"""
    # 不可取消的状态：已完成、已打印、正在删除
    uncancellable = (JOB_STATUS_PRINTED | JOB_STATUS_COMPLETE | JOB_STATUS_DELETED | JOB_STATUS_DELETING)
    return not bool(status & uncancellable)

def cancel_print_jobs_by_document(document_name, printer_name=None, cancel_active=False):
    """根据文档名取消打印任务
    
    Args:
        document_name: 文档名
        printer_name: 指定打印机名称，为None则搜索所有打印机
        cancel_active: 是否取消正在打印的任务（默认False）
    """
    try:
        import win32print
        cancelled_jobs = []
        skipped_jobs = []
        
        # 获取打印队列任务
        jobs = get_print_queue_jobs(printer_name)
        
        for job in jobs:
            # 检查文档名是否匹配（支持部分匹配）
            if document_name.lower() in job['document'].lower() or \
               os.path.splitext(document_name)[0].lower() in job['document'].lower():
                
                job_status = job['status']
                status_desc = get_job_status_description(job_status)
                is_printing = is_job_actively_printing(job_status)
                is_cancellable = is_job_cancellable(job_status)
                
                print(f"🔍 找到相关任务: {job['document']} (状态: {status_desc})")
                
                # 检查任务是否可取消
                if not is_cancellable:
                    print(f"⚠️ 跳过任务 {job['document']}: 任务已完成或正在删除")
                    skipped_jobs.append({
                        'job_id': job['job_id'],
                        'printer': job['printer'],
                        'document': job['document'],
                        'reason': '任务已完成或正在删除',
                        'status': status_desc
                    })
                    continue
                
                # 检查是否正在打印
                if is_printing and not cancel_active:
                    print(f"⚠️ 跳过正在打印的任务: {job['document']} (状态: {status_desc})")
                    print(f"    提示: 如需强制取消正在打印的任务，请使用带参数的API")
                    skipped_jobs.append({
                        'job_id': job['job_id'],
                        'printer': job['printer'],
                        'document': job['document'],
                        'reason': '正在打印，需要显式授权才能取消',
                        'status': status_desc
                    })
                    continue
                
                # 尝试取消任务
                try:
                    # 打开打印机句柄
                    printer_handle = win32print.OpenPrinter(job['printer'])
                    
                    # 取消打印任务
                    win32print.SetJob(printer_handle, job['job_id'], 0, None, win32print.JOB_CONTROL_CANCEL)
                    
                    cancelled_jobs.append({
                        'job_id': job['job_id'],
                        'printer': job['printer'],
                        'document': job['document'],
                        'status': status_desc,
                        'was_printing': is_printing
                    })
                    
                    action = "已强制取消" if is_printing else "已取消"
                    print(f"✅ {action}打印任务: {job['document']} (任务ID: {job['job_id']}, 状态: {status_desc})")
                    
                    win32print.ClosePrinter(printer_handle)
                    
                except Exception as e:
                    print(f"❌ 取消打印任务失败: {job['document']} - {e}")
                    skipped_jobs.append({
                        'job_id': job['job_id'],
                        'printer': job['printer'],
                        'document': job['document'],
                        'reason': f'取消失败: {e}',
                        'status': status_desc
                    })
        
        return {
            'cancelled': cancelled_jobs,
            'skipped': skipped_jobs,
            'total_found': len(cancelled_jobs) + len(skipped_jobs)
        }
        
    except Exception as e:
        print(f"取消打印任务失败: {e}")
        return {
            'cancelled': [],
            'skipped': [],
            'total_found': 0,
            'error': str(e)
        }

def clear_all_print_queues():
    """清空所有打印机的打印队列"""
    try:
        import win32print
        cleared_count = 0
        
        for printer in PRINTERS:
            try:
                printer_handle = win32print.OpenPrinter(printer)
                
                # 获取所有任务
                job_list = win32print.EnumJobs(printer_handle, 0, -1, 1)
                
                # 取消所有任务
                for job in job_list:
                    try:
                        win32print.SetJob(printer_handle, job['JobId'], 0, None, win32print.JOB_CONTROL_CANCEL)
                        cleared_count += 1
                        print(f"✅ 已取消: {printer} - {job['pDocument']} (任务ID: {job['JobId']})")
                    except Exception as e:
                        print(f"❌ 取消任务失败: {job['pDocument']} - {e}")
                
                win32print.ClosePrinter(printer_handle)
                
            except Exception as e:
                print(f"清理打印机 {printer} 队列失败: {e}")
        
        return cleared_count
        
    except Exception as e:
        print(f"清空打印队列失败: {e}")
        return 0

# 开机自启注册表操作
def set_autostart(enable=True):
    exe_path = sys.executable
    key = r'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
    name = 'PrintServerApp'
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_ALL_ACCESS) as regkey:
        if enable:
            winreg.SetValueEx(regkey, name, 0, winreg.REG_SZ, exe_path)
        else:
            try:
                winreg.DeleteValue(regkey, name)
            except FileNotFoundError:
                pass
 
def get_autostart():
    key = r'Software\\Microsoft\\Windows\\CurrentVersion\\Run'
    name = 'PrintServerApp'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ) as regkey:
            val, _ = winreg.QueryValueEx(regkey, name)
            return True if val else False
    except FileNotFoundError:
        return False
 
app = Flask(__name__)
app.secret_key = 'print_server_secret_key'

# Flask配置优化，防止长期运行问题
app.config.update(
    # 限制上传文件大小
    MAX_CONTENT_LENGTH=100 * 1024 * 1024,  # 100MB
    # 会话配置
    PERMANENT_SESSION_LIFETIME=3600,  # 1小时
    # 模板自动重载
    TEMPLATES_AUTO_RELOAD=False,
    # JSON配置
    JSON_AS_ASCII=False,
    JSONIFY_PRETTYPRINT_REGULAR=False,
    # 其他优化
    SEND_FILE_MAX_AGE_DEFAULT=300,  # 5分钟缓存
)

# 兼容PyInstaller打包的路径处理
# 使用路径管理器配置文件夹和文件路径
UPLOAD_FOLDER = path_manager.get_upload_dir()
LOG_FILE = path_manager.get_log_path()
path_manager.ensure_data_dirs()

# 添加请求后钩子，进行资源清理
@app.after_request
def after_request(response):
    """请求处理后的清理工作"""
    try:
        # 强制垃圾回收（适度使用）
        if hasattr(app, 'request_count'):
            app.request_count += 1
        else:
            app.request_count = 1
            
        # 每100个请求进行一次垃圾回收
        if app.request_count % 100 == 0:
            import gc
            gc.collect()
            
        # 设置响应头，防止缓存问题
        response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
        response.headers['Pragma'] = 'no-cache'
        response.headers['Expires'] = '0'
        
        # 确保连接正确关闭
        response.headers['Connection'] = 'close'
        
    except Exception as e:
        print(f"⚠️ 请求后清理异常: {e}")
        
    return response

# 添加错误处理器
@app.errorhandler(500)
def internal_error(error):
    """内部服务器错误处理"""
    print(f"⚠️ 内部服务器错误: {error}")
    return jsonify({
        'error': '服务器内部错误',
        'message': '请稍后重试，如果问题持续请重启服务'
    }), 500

@app.errorhandler(413)
def too_large(error):
    """请求实体过大错误处理"""
    return jsonify({
        'error': '文件过大',
        'message': '上传文件大小不能超过100MB'
    }), 413

# 虚拟打印机名称列表（这些不是真正的物理打印机）
VIRTUAL_PRINTERS = {
    '导出为WPS PDF', 'WPS PDF', 'Microsoft Print to PDF', 'Microsoft XPS Document Writer',
    'Fax', '传真', 'OneNote', 'OneNote (Desktop)', 'Send To OneNote 2016',
    'Adobe PDF', 'Foxit Reader PDF Printer', 'PDF Creator', 'CutePDF Writer',
    'novaPDF', 'PDFCreator', 'Bullzip PDF Printer', 'doPDF', 'PDF24',
    'Virtual PDF Printer', '虚拟PDF打印机', 'Send to Kindle', '发送到WPS高级打印'
}

# 获取所有本地和网络连接打印机，过滤掉虚拟打印机
ALL_PRINTERS = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
PRINTERS = [p for p in ALL_PRINTERS if p not in VIRTUAL_PRINTERS]

def get_default_printer():
    """获取系统默认打印机"""
    try:
        default_printer = win32print.GetDefaultPrinter()
        # 检查默认打印机是否在物理打印机列表中
        if default_printer in PRINTERS:
            return default_printer
        # 如果默认打印机是虚拟打印机，返回第一台物理打印机
        elif PRINTERS:
            return PRINTERS[0]
        else:
            return None
    except Exception as e:
        print(f"获取默认打印机失败: {e}")
        # 如果获取失败，返回第一台可用的物理打印机
        return PRINTERS[0] if PRINTERS else None

def refresh_printer_list():
    """刷新打印机列表"""
    global ALL_PRINTERS, PRINTERS
    try:
        ALL_PRINTERS = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
        PRINTERS = [p for p in ALL_PRINTERS if p not in VIRTUAL_PRINTERS]
        print(f"打印机列表已刷新，检测到 {len(PRINTERS)} 台物理打印机")
        return True
    except Exception as e:
        print(f"刷新打印机列表失败: {e}")
        return False

HTML = '''
{% with messages = get_flashed_messages(with_categories=true) %}
    {% if messages %}
        <div class="container mt-3">
            {% for category, msg in messages %}
                <div class="alert alert-{{category}} alert-dismissible fade show" role="alert">
                    {{msg}}
                    <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
                </div>
            {% endfor %}
        </div>
    {% endif %}
{% endwith %}
<!doctype html>
<html lang="zh-cn" spellcheck="false">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <title>内网打印服务</title>
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/css/bootstrap.min.css" rel="stylesheet" onerror="this.remove()">
    <!-- 离线CSS备用方案 -->
    <style>
        /* Bootstrap核心样式备用 */
        body { font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,"Helvetica Neue",Arial,sans-serif; margin: 0; padding: 0; }
        .container { max-width: 800px; margin: 0 auto; padding: 20px; }
        
        /* 禁用所有拼写检查波浪线 */
        *, *::before, *::after {
            -webkit-text-decoration-skip: none;
            text-decoration-skip: none;
        }
        select, input, textarea {
            -webkit-text-decoration-line: none !important;
            text-decoration-line: none !important;
            -webkit-text-decoration: none !important;
            text-decoration: none !important;
        }
        .btn { display: inline-block; padding: 6px 12px; margin-bottom: 0; font-size: 14px; font-weight: 400; line-height: 1.42857143; text-align: center; white-space: nowrap; vertical-align: middle; cursor: pointer; border: 1px solid transparent; border-radius: 4px; text-decoration: none; }
        .btn-primary { color: #fff; background-color: #007bff; border-color: #007bff; }
        .btn-outline-secondary { color: #6c757d; border-color: #6c757d; background-color: transparent; }
        .btn-warning { color: #212529; background-color: #ffc107; border-color: #ffc107; }
        .form-control { display: block; width: 100%; padding: 6px 12px; font-size: 14px; line-height: 1.42857143; color: #555; background-color: #fff; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; outline: none; transition: border-color 0.15s ease-in-out, box-shadow 0.15s ease-in-out; }
        .form-control:focus { border-color: #007bff; box-shadow: 0 0 0 0.2rem rgba(0, 123, 255, 0.25); }
        .form-select { background-image: url("data:image/svg+xml,%3csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 16 16'%3e%3cpath fill='none' stroke='%23343a40' stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='m1 6 7 7 7-7'/%3e%3c/svg%3e"); }
        .alert { padding: 15px; margin-bottom: 20px; border: 1px solid transparent; border-radius: 4px; }
        .alert-success { color: #155724; background-color: #d4edda; border-color: #c3e6cb; }
        .alert-danger { color: #721c24; background-color: #f8d7da; border-color: #f5c6cb; }
        .alert-warning { color: #856404; background-color: #fff3cd; border-color: #ffeaa7; }
        .alert-info { color: #0c5460; background-color: #d1ecf1; border-color: #bee5eb; }
        .table { width: 100%; margin-bottom: 20px; border-collapse: collapse; }
        .table th, .table td { padding: 8px; text-align: left; border-top: 1px solid #ddd; }
        .table-light th { background-color: #f8f9fa; }
        .nav { display: flex; flex-wrap: wrap; padding-left: 0; margin-bottom: 0; list-style: none; }
        .nav-pills .nav-link { border-radius: 0.25rem; }
        .nav-pills .nav-link.active { color: #fff; background-color: #007bff; }
        .nav-item { margin-right: 10px; }
        .nav-link { display: block; padding: 8px 16px; text-decoration: none; color: #007bff; cursor: pointer; border: 1px solid transparent; }
        .tab-content { margin-top: 20px; }
        .tab-pane { display: none; }
        .tab-pane.show.active { display: block; }
        .row { display: flex; flex-wrap: wrap; margin-right: -15px; margin-left: -15px; }
        .col-md-3, .col-md-4, .col-md-6, .col-md-8, .col-12 { position: relative; width: 100%; padding-right: 15px; padding-left: 15px; }
        @media (min-width: 768px) {
            .col-md-3 { flex: 0 0 25%; max-width: 25%; }
            .col-md-4 { flex: 0 0 33.333333%; max-width: 33.333333%; }
            .col-md-6 { flex: 0 0 50%; max-width: 50%; }
            .col-md-8 { flex: 0 0 66.666667%; max-width: 66.666667%; }
        }
        .card { position: relative; display: flex; flex-direction: column; background-color: #fff; border: 1px solid rgba(0,0,0,.125); border-radius: 0.25rem; }
        .card-header { padding: 0.75rem 1.25rem; background-color: rgba(0,0,0,.03); border-bottom: 1px solid rgba(0,0,0,.125); }
        .card-body { flex: 1 1 auto; padding: 1.25rem; }
        .form-text { margin-top: 0.25rem; font-size: 0.875em; color: #6c757d; }
        .badge { display: inline-block; padding: 0.25em 0.4em; font-size: 75%; font-weight: 700; line-height: 1; text-align: center; white-space: nowrap; vertical-align: baseline; border-radius: 0.25rem; }
        .bg-success { background-color: #28a745 !important; color: #fff; }
        .bg-primary { background-color: #007bff !important; color: #fff; }
        .list-group { display: flex; flex-direction: column; padding-left: 0; margin-bottom: 0; }
        .list-group-item { position: relative; display: block; padding: 0.75rem 1.25rem; background-color: #fff; border: 1px solid rgba(0,0,0,.125); }
        .g-3 > * { margin-bottom: 1rem; }
        .mb-3, .mb-4 { margin-bottom: 1.5rem; }
        .mt-4 { margin-top: 1.5rem; }
        .text-end { text-align: right; }
        .text-center { text-align: center; }
        .px-4 { padding-left: 1.5rem; padding-right: 1.5rem; }
        .justify-content-center { justify-content: center; }
        /* 原有的自定义样式 */
        body { background: #f8f9fa; }
        .container { max-width: 800px; margin-top: 40px; background: #fff; border-radius: 12px; box-shadow: 0 2px 12px #0001; padding: 32px; }
        h1 { font-size: 2rem; margin-bottom: 1.5rem; }
        .author-info { font-size: 1.2rem; color: #6c757d; font-weight: normal; }
        .form-label { font-weight: 500; }
        .table { background: #fff; }
        .log-list { max-height: 200px; overflow-y: auto; font-size: 0.95em; }
        .nav-pills .nav-link.active { background-color: #0d6efd; }
        .tab-content { margin-top: 20px; }
        .ip-status { padding: 15px; background: #f8f9fa; border-radius: 8px; margin-bottom: 20px; }
        .ip-status .badge { font-size: 0.9em; }
        
        /* 拖拽文件区域样式 */
        .file-drop-area {
            border: 2px dashed #ccc;
            border-radius: 8px;
            padding: 40px;
            text-align: center;
            background-color: #f9f9f9;
            transition: all 0.3s ease;
            margin-bottom: 20px;
            cursor: pointer;
        }
        
        .file-drop-area:hover {
            border-color: #007bff;
            background-color: #e3f2fd;
        }
        
        .file-drop-area.drag-over {
            border-color: #007bff;
            background-color: #e3f2fd;
            transform: scale(1.02);
        }
        
        .file-drop-area .drop-icon {
            font-size: 48px;
            color: #6c757d;
            margin-bottom: 15px;
        }
        
        .file-drop-area.drag-over .drop-icon {
            color: #007bff;
        }
        
        .file-list {
            max-height: 200px;
            overflow-y: auto;
            border: 1px solid #dee2e6;
            border-radius: 4px;
            padding: 10px;
            margin-top: 15px;
            background-color: #fff;
        }
        
        .file-item {
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 8px 12px;
            border-bottom: 1px solid #eee;
            background-color: #f8f9fa;
            border-radius: 4px;
            margin-bottom: 5px;
        }
        
        .file-item:last-child {
            margin-bottom: 0;
        }
        
        .file-item .file-name {
            font-weight: 500;
            color: #495057;
            flex-grow: 1;
            margin-right: 10px;
        }
        
        .file-item .file-size {
            color: #6c757d;
            font-size: 0.9em;
            margin-right: 10px;
        }
        
        .file-item .remove-btn {
            background: none;
            border: none;
            color: #dc3545;
            cursor: pointer;
            font-size: 16px;
            padding: 2px 6px;
            border-radius: 3px;
        }
        
        .file-item .remove-btn:hover {
            background-color: #dc3545;
            color: white;
        }
        
        /* 队列表格样式 */
        .queue-table {
            background-color: #fff;
            border-radius: 8px;
            overflow: hidden;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        
        .queue-table .file-name {
            font-weight: 500;
            color: #495057;
        }
        
        .queue-table .btn-group-sm .btn {
            padding: 0.25rem 0.5rem;
            font-size: 0.875rem;
        }
        
        /* 删除按钮样式 */
        .btn-outline-danger:hover {
            transform: scale(1.05);
            transition: transform 0.2s ease-in-out;
        }
        
        /* 空队列提示样式 */
        .empty-queue {
            padding: 2rem;
            text-align: center;
            color: #6c757d;
            background-color: #f8f9fa;
            border-radius: 8px;
            border: 2px dashed #dee2e6;
        }
        
        /* 文件类型徽章样式 */
        .file-type-badge {
            display: inline-block;
            padding: 0.25em 0.5em;
            font-size: 0.75em;
            font-weight: 500;
            line-height: 1;
            text-align: center;
            white-space: nowrap;
            vertical-align: baseline;
            border-radius: 0.25rem;
            text-transform: uppercase;
        }
        
        .file-type-pdf { background-color: #dc3545; color: white; }
        .file-type-doc, .file-type-docx { background-color: #2b579a; color: white; }
        .file-type-xls, .file-type-xlsx { background-color: #217346; color: white; }
        .file-type-ppt, .file-type-pptx { background-color: #d24726; color: white; }
        .file-type-txt { background-color: #6f42c1; color: white; }
        .file-type-jpg, .file-type-jpeg, .file-type-png { background-color: #fd7e14; color: white; }
        .file-type-unknown { background-color: #6c757d; color: white; }
    </style>
</head>
<body>
<div class="container">
    <h1 class="mb-4 text-center">内网打印服务</br><span class="author-info">（yckj666@52PJ，作者：忆痕）【<a href="https://github.com/a937750307/lan-printing" target="_blank" style="color: #007bff; text-decoration: none;">Github</a>】</span></h1>
    
    <!-- 导航标签 - 仅保留打印管理 -->
    <div class="text-center mb-4">
        <p class="text-muted">可右键托盘栏图标进行网络配置和其他设置</p>
    </div>

    <!-- 打印管理内容 -->
    <div class="main-content">
            <form method="post" enctype="multipart/form-data" class="row g-3 mb-4" id="printForm">
                <input type="hidden" name="action" value="print">
                <input type="hidden" name="device_name" id="deviceNameField" value="">
                <div class="col-md-6">
                    <label class="form-label">选择打印机 
                        <button type="button" class="btn btn-sm btn-outline-secondary ms-2" onclick="refreshPrinterList()" title="刷新打印机列表">
                            🔄 刷新
                        </button>
                    </label>
                    <select name="printer" class="form-select" id="printerSelect" spellcheck="false">
                        {% if printers %}
                            {% for p in printers %}
                                <option value="{{p}}" {% if p == default_printer %}selected{% endif %}>{{p}}{% if p == default_printer %} (默认){% endif %}</option>
                            {% endfor %}
                        {% else %}
                            <option value="">未检测到可用打印机</option>
                        {% endif %}
                    </select>
                    <div class="form-text text-muted">
                        {% if printers %}
                            <strong>⚠️ 重要提醒:</strong> 请仔细选择打印机！程序会严格按照您的选择发送到指定打印机，不会回退到默认打印机。
                            <br>已过滤虚拟打印机，自动选择默认打印机，可手动刷新列表
                        {% else %}
                            <span class="text-warning">⚠️ 未检测到物理打印机，请检查打印机连接后点击刷新</span>
                        {% endif %}
                    </div>
                </div>
                <div class="col-md-3">
                    <label class="form-label">打印份数</label>
                    <select name="copies" class="form-select" spellcheck="false">
                        <option value="1" selected>1</option>
                        <option value="2">2</option>
                        <option value="3">3</option>
                        <option value="4">4</option>
                        <option value="5">5</option>
                        <option value="6">6</option>
                        <option value="7">7</option>
                        <option value="8">8</option>
                        <option value="9">9</option>
                        <option value="10">10</option>
                    </select>
                </div>
                <div class="col-md-3">
                    <label class="form-label">单双面
                        {% if printer_caps and printer_caps.get('duplex_support') %}
                        <span class="badge bg-success ms-1">支持</span>
                        {% endif %}
                    </label>
                    <select name="duplex" class="form-select" id="duplexSelect" spellcheck="false">
                        <option value="1">📄 单面打印</option>
                        {% if printer_caps and printer_caps.get('duplex_support') %}
                        <option value="2">📖 长边翻转 (书本式)</option>
                        <option value="3">📋 短边翻转 (翻页式)</option>
                        {% endif %}
                    </select>
                    {% if printer_caps %}
                        {% if printer_caps.get('duplex_support') %}
                        <div class="form-text text-success">
                            <small>✅ 支持双面打印
                            {% if printer_caps.get('duplex_modes') %}
                            - {{ printer_caps.get('duplex_modes')|join(', ') }}
                            {% endif %}
                            </small>
                        </div>
                        {% else %}
                        <div class="form-text text-warning">
                            <small>⚠️ 打印机不支持双面打印，将使用单面模式</small>
                        </div>
                        {% endif %}
                    {% endif %}
                </div>
                <div class="col-md-4">
                    <label class="form-label">纸张大小</label>
                    <select name="papersize" class="form-select" id="paperSelect" spellcheck="false">
                        {% if printer_caps and printer_caps.get('papers') %}
                            {% for p in printer_caps.papers %}
                            <option value="{{p.id}}" {% if p.id == 9 %}selected{% endif %}>{{p.name}}</option>
                            {% endfor %}
                        {% else %}
                            <option value="9" selected>A4</option>
                        {% endif %}
                    </select>
                </div>
                <div class="col-md-4">
                    <label class="form-label">打印分辨率</label>
                    <select name="quality" class="form-select" id="qualitySelect" spellcheck="false">
                        {% if printer_caps and printer_caps.get('resolutions') %}
                            {% for r in printer_caps.resolutions %}
                            <option value="{{r}}">{{r}}</option>
                            {% endfor %}
                        {% else %}
                            <option value="600x600">600x600</option>
                        {% endif %}
                    </select>
                </div>
                <div class="col-md-8">
                    <label class="form-label">选择文件（支持PDF/JPG/PNG/DOC/DOCX/PPT/PPTX/XLS/XLSX/TXT，支持多选和拖拽）</label>
                    
                    <!-- 拖拽上传区域 -->
                    <div class="file-drop-area" id="fileDropArea">
                        <div class="drop-icon">📁</div>
                        <h5>拖拽文件到此处</h5>
                        <p>或者 <strong>点击选择文件</strong></p>
                        <p class="text-muted small">支持多个文件同时上传</p>
                        <input type="file" name="file" multiple class="form-control" id="fileInput" style="display: none;" spellcheck="false">
                    </div>
                    
                    <!-- 选中的文件列表 -->
                    <div class="file-list" id="fileList" style="display: none;">
                        <h6>已选择的文件：</h6>
                        <div id="selectedFiles"></div>
                    </div>
                </div>
                <div class="col-12 text-end">
                    {% if printers %}
                        <button type="submit" class="btn btn-primary px-4" id="printButton">上传并打印</button>
                    {% else %}
                        <button type="button" class="btn btn-secondary px-4" disabled title="无可用打印机">无法打印 - 请检查打印机</button>
                    {% endif %}
                </div>
            </form>

            <!-- 打印设置说明 -->
            <div class="alert alert-info">
                <h6><i class="bi bi-info-circle"></i> 静默打印说明</h6>
                <ul class="mb-0 small">
                    <li><strong>🔇 静默打印:</strong> 无需手动确认，文件会自动发送到选择的打印机</li>
                    <li><strong>📄 PDF文件:</strong> 优先使用WPS、Office或Adobe Reader进行静默打印，自动选择最佳方案</li>
                    <li><strong>🖼️ 图片文件:</strong> 支持JPG、PNG格式，使用Windows图片查看器静默打印</li>
                    <li><strong>📝 Office文档:</strong> 支持DOC/DOCX、XLS/XLSX、PPT/PPTX，使用Office应用程序或COM对象</li>
                    <li><strong>📃 文本文件:</strong> 支持TXT格式，直接发送到打印机</li>
                    <li><strong>⚙️ 打印参数:</strong> 直接应用您设置的打印参数（双面、纸张、质量）到实际打印任务</li>
                    <li><strong>✅ 成功标识:</strong> 看到绿色✅表示打印任务已成功发送</li>
                    <li><strong>🔄 备用方案:</strong> 如果主要方法失败，系统会自动尝试备用打印方案</li>
                </ul>
            </div>

            <!-- 环境状态提示 -->
            {% if env_status %}
            <div class="alert alert-{{env_status.type}}">
                <h6><i class="bi bi-{{env_status.icon}}"></i> {{env_status.title}}</h6>
                <div class="small">{{env_status.message|safe}}</div>
            </div>
            {% endif %}
            <div class="alert alert-info">
                <h6><i class="bi bi-lightbulb"></i> 队列管理功能</h6>
                <ul class="mb-0 small">
                    <li><strong>🗑️ 取消打印:</strong> 如果文件还未实际打印，点击删除按钮可取消打印</li>
                    <li><strong>⏰ 自动清理:</strong> 上传的文件会在10分钟后自动清理，也可以点击删除按钮手动删除</li>
                    <li><strong>📁 清空队列:</strong> 可以一键清空所有待打印文件，节省时间</li>
                    <li><strong>👁️ 文件预览:</strong> 打印前可以预览文件内容，确保正确性</li>
                    <li><strong>📊 文件信息:</strong> 显示文件大小、类型和上传时间，便于管理</li>
                    <li><strong>💡 使用建议:</strong> 打印前检查队列，删除不需要的文件可以节省纸张</li>
                </ul>
            </div>
            
            <div class="alert alert-warning">
                <h6><i class="bi bi-info-circle"></i> 高级打印功能提示</h6>
                <div class="small">
                    如需使用<strong>横版打印</strong>或<strong>自定义页码范围</strong>或<strong>布局调整</strong>等高级功能，请先使用 
                    <strong>Microsoft Office</strong> 或 <strong>WPS Office</strong> 等办公软件在本地进行编辑后，再发送到此服务进行打印。
                    这样可以获得最佳的打印效果！📝✨
                </div>
            </div>
            
            <!-- 系统软件状态显示 -->
            {% if software_status %}
            <div class="alert alert-info">
                <h6><i class="bi bi-gear"></i> 系统软件状态（可能无法检测全，以下只要有一个能用就行）</h6>
                <div class="row small">
                    <div class="col-md-4">
                        <strong>PDF阅读器:</strong><br>
                        {% if software_status.pdf_readers %}
                            {% for reader in software_status.pdf_readers %}
                            <span class="badge bg-success me-1">✓ {{ reader[0] }}</span><br>
                            {% endfor %}
                        {% else %}
                            <span class="badge bg-warning">⚠️ 未安装</span>
                            <div class="mt-1 text-muted">建议安装: Adobe Reader 或 WPS Office</div>
                        {% endif %}
                    </div>
                    <div class="col-md-4">
                        <strong>Office套件:</strong><br>
                        {% if software_status.office_suites %}
                            {% for office in software_status.office_suites %}
                            <span class="badge bg-success me-1">✓ {{ office[0] }}</span><br>
                            {% endfor %}
                        {% else %}
                            <span class="badge bg-warning">⚠️ 未安装</span>
                            <div class="mt-1 text-muted">建议安装: Microsoft Office 或 WPS Office</div>
                        {% endif %}
                    </div>
                    <div class="col-md-4">
                        <strong>浏览器:</strong><br>
                        {% if software_status.browsers %}
                            {% for browser in software_status.browsers %}
                            <span class="badge bg-success me-1">✓ {{ browser[0] }}</span><br>
                            {% endfor %}
                        {% else %}
                            <span class="badge bg-secondary">无可用浏览器</span>
                        {% endif %}
                    </div>
                </div>
                {% if not software_status.pdf_readers or not software_status.office_suites %}
                <div class="mt-2 p-2 bg-light rounded">
                    <small><strong>提示:</strong> 缺少必要的软件可能导致PDF、PPT、PPTX文件无法打印。请安装相应软件后重试。</small>
                </div>
                {% endif %}
            </div>
            {% endif %}

            <div class="d-flex justify-content-between align-items-center mt-4">
                <h4 class="mb-0">打印队列</h4>
                {% if files %}
                <button type="button" class="btn btn-outline-danger btn-sm" onclick="deleteAllFiles()" title="清空所有待打印文件">
                    🗑️ 清空队列
                </button>
                {% endif %}
            </div>
            <table class="table table-sm table-hover align-middle mt-2 queue-table">
                <thead class="table-light"><tr><th>文件名</th><th>大小</th><th>上传时间</th><th>操作</th></tr></thead>
                <tbody>
                {% for f in files %}
                    <tr>
                        <td>
                            <div class="d-flex align-items-center">
                                <span class="file-type-badge file-type-{{f.extension}} me-2">{{f.extension}}</span>
                                <div>
                                    <div class="file-name">{{f.name}}</div>
                                    {% if f.extension in ['pdf', 'doc', 'docx', 'xls', 'xlsx', 'ppt', 'pptx'] %}
                                        <small class="text-muted">办公文档</small>
                                    {% elif f.extension in ['jpg', 'jpeg', 'png', 'gif', 'bmp'] %}
                                        <small class="text-muted">图片文件</small>
                                    {% elif f.extension == 'txt' %}
                                        <small class="text-muted">文本文件</small>
                                    {% else %}
                                        <small class="text-muted">其他文件</small>
                                    {% endif %}
                                </div>
                            </div>
                        </td>
                        <td>
                            <span class="badge bg-light text-dark">{{f.size_str}}</span>
                        </td>
                        <td>
                            <small class="text-muted">{{f.upload_time}}</small>
                        </td>
                        <td>
                            <div class="btn-group btn-group-sm" role="group">
                                <a href="/preview/{{f.name}}" target="_blank" class="btn btn-outline-primary btn-sm" title="预览文件">
                                    👁️ 预览
                                </a>
                                <button type="button" class="btn btn-outline-danger btn-sm" 
                                        onclick="deleteFile('{{f.name}}')" title="从队列中删除">
                                    🗑️ 删除
                                </button>
                            </div>
                        </td>
                    </tr>
                {% else %}
                    <tr>
                        <td colspan="4">
                            <div class="empty-queue">
                                <div class="mb-3">📁</div>
                                <h6 class="mb-2">队列为空</h6>
                                <p class="mb-0">还没有待打印的文件，请先上传文件</p>
                            </div>
                        </td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>
            
            {% if files %}
            <div class="alert alert-info">
                <small>
                    📋 当前队列中有 <strong>{{files|length}}</strong> 个文件 | 
                    🗑️ 点击删除按钮可以从队列中移除文件 | 
                    ⏰ 文件会在10分钟后自动清理
                </small>
            </div>
            {% endif %}

            <h4 class="mt-4">打印日志</h4>
            <ul class="list-group log-list mb-0">
                {% for l in logs %}
                    <li class="list-group-item">{{l}}</li>
                {% endfor %}
            </ul>
        </div>
    </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js" onerror="console.log('Bootstrap JS 加载失败，使用备用方案')"></script>
<!-- 离线JavaScript备用方案 -->
<script>
// 获取设备名并设置到请求头
function getDeviceName() {
    let deviceName = '';
    
    // 尝试多种方法获取设备名
    try {
        // 方法1: 尝试获取网络信息中的主机名 (某些浏览器支持)
        if (navigator.connection && navigator.connection.effectiveType) {
            // 现代浏览器可能提供网络信息
        }
        
        // 方法2: 从User Agent解析设备信息
        const ua = navigator.userAgent;
        
        // Android设备
        if (/Android/i.test(ua)) {
            const match = ua.match(/Android.*?;\s*([^)]+)/);
            if (match) {
                deviceName = match[1].trim();
            } else {
                deviceName = 'Android设备';
            }
        }
        // iOS设备
        else if (/iPhone/i.test(ua)) {
            deviceName = 'iPhone';
        }
        else if (/iPad/i.test(ua)) {
            deviceName = 'iPad';
        }
        // Windows设备
        else if (/Windows/i.test(ua)) {
            const winMatch = ua.match(/Windows NT ([\d.]+)/);
            if (winMatch) {
                const version = winMatch[1];
                const versionNames = {
                    '10.0': 'Win10/11电脑',
                    '6.3': 'Win8.1电脑',
                    '6.2': 'Win8电脑',
                    '6.1': 'Win7电脑'
                };
                deviceName = versionNames[version] || `Windows NT ${version}电脑`;
            } else {
                deviceName = 'Windows电脑';
            }
        }
        // Mac设备
        else if (/Mac|Macintosh/i.test(ua)) {
            const macMatch = ua.match(/Mac OS X ([\d_]+)/);
            if (macMatch) {
                const version = macMatch[1].replace(/_/g, '.');
                deviceName = `macOS ${version}`;
            } else {
                deviceName = 'Mac电脑';
            }
        }
        // Linux设备
        else if (/Linux/i.test(ua)) {
            deviceName = 'Linux电脑';
        }
        else {
            deviceName = '未知设备';
        }
    } catch (e) {
        deviceName = '设备信息获取失败';
    }
    
    return deviceName;
}

// 为AJAX请求添加设备名 (用于删除操作等)
function addDeviceNameToRequests() {
    const deviceName = encodeURIComponent(getDeviceName());
    
    // 拦截fetch请求
    const originalFetch = window.fetch;
    window.fetch = function(url, options = {}) {
        options.headers = options.headers || {};
        options.headers['X-Device-Name'] = deviceName;
        return originalFetch(url, options);
    };
}

// 简化的警告消息处理
document.addEventListener('DOMContentLoaded', function() {
    // 初始化AJAX请求拦截
    addDeviceNameToRequests();
    
    // 设置设备名到隐藏字段
    const deviceNameField = document.getElementById('deviceNameField');
    if (deviceNameField) {
        deviceNameField.value = getDeviceName();
    }
    
    // 为表单提交添加设备名
    const printForm = document.getElementById('printForm');
    if (printForm) {
        printForm.addEventListener('submit', function() {
            const deviceNameField = document.getElementById('deviceNameField');
            if (deviceNameField) {
                deviceNameField.value = getDeviceName();
            }
        });
    }
    
    // 警告消息自动关闭功能
    const alerts = document.querySelectorAll('.alert');
    alerts.forEach(alert => {
        const closeBtn = alert.querySelector('.btn-close');
        if (closeBtn) {
            closeBtn.addEventListener('click', function() {
                alert.style.display = 'none';
            });
        }
        
        // 5秒后自动关闭成功消息
        if (alert.classList.contains('alert-success')) {
            setTimeout(() => {
                alert.style.display = 'none';
            }, 5000);
        }
    });
});

// 根据所选打印机实时获取并填充分辨率与纸张列表
function refreshPrinterInfo() {
    const printerSelect = document.getElementById('printerSelect');
    const paperSelect = document.getElementById('paperSelect');
    const qualitySelect = document.getElementById('qualitySelect');
    if (!printerSelect) return;
    const selectedPrinter = printerSelect.value;
    if (!selectedPrinter) return;

    fetch('/api/printer_info?printer=' + encodeURIComponent(selectedPrinter))
        .then(r => r.json())
        .then(data => {
            if (!data.success) return;
            const caps = data.capabilities || {};
            // 填充纸张
            if (paperSelect) {
                const prev = paperSelect.value;
                paperSelect.innerHTML = '';
                if (caps.papers && caps.papers.length) {
                    let a4Index = -1;
                    caps.papers.forEach((p, idx) => {
                        const opt = document.createElement('option');
                        opt.value = p.id;
                        opt.textContent = p.name;
                        paperSelect.appendChild(opt);
                        if (p.id === 9 || (typeof p.name === 'string' && p.name.toUpperCase().includes('A4'))) {
                            a4Index = idx;
                        }
                    });
                    // 优先恢复之前选择；否则默认选A4；否则选第一项
                    if (prev && Array.from(paperSelect.options).some(o => String(o.value) === String(prev))) {
                        paperSelect.value = prev;
                    } else if (a4Index >= 0) {
                        paperSelect.selectedIndex = a4Index;
                    } else {
                        paperSelect.selectedIndex = 0;
                    }
                } else {
                    const opt = document.createElement('option');
                    opt.value = '9'; // A4 ID
                    opt.textContent = 'A4';
                    paperSelect.appendChild(opt);
                }
            }
            // 填充分辨率
            if (qualitySelect) {
                qualitySelect.innerHTML = '';
                if (caps.resolutions && caps.resolutions.length) {
                    caps.resolutions.forEach(r => {
                        const opt = document.createElement('option');
                        opt.value = r;
                        opt.textContent = r;
                        qualitySelect.appendChild(opt);
                    });
                } else {
                    const opt = document.createElement('option');
                    opt.value = '600x600';
                    opt.textContent = '600x600';
                    qualitySelect.appendChild(opt);
                }
            }
        })
        .catch(() => {});
}



// 添加表单提交验证
document.addEventListener('DOMContentLoaded', function() {
    const uploadForm = document.querySelector('form[enctype="multipart/form-data"]');
    const printButton = document.getElementById('printButton');
    
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            const printerSelect = document.getElementById('printerSelect');
            const selectedPrinter = printerSelect ? printerSelect.value : '';
            
            // 检查是否选择了有效的打印机
            if (!selectedPrinter || selectedPrinter === '' || selectedPrinter === '未检测到可用打印机') {
                e.preventDefault();
                alert('请先选择一个有效的打印机！\\n\\n如果没有看到打印机，请检查：\\n1. 打印机是否正确连接\\n2. 打印机驱动是否安装\\n3. 打印机是否处于联机状态');
                return false;
            }
            
            // 检查是否选择了文件
            const fileInput = document.querySelector('input[type="file"]');
            if (fileInput && fileInput.files.length === 0) {
                e.preventDefault();
                alert('请选择要打印的文件！\\n\\n您可以：\\n1. 点击拖拽区域选择文件\\n2. 直接拖拽文件到上传区域');
                return false;
            }
            
            // 显示加载状态
            if (printButton) {
                printButton.disabled = true;
                printButton.innerHTML = '🔄 处理中...';
                
                // 5秒后恢复按钮状态（防止页面未刷新）
                setTimeout(() => {
                    printButton.disabled = false;
                    printButton.innerHTML = '上传并打印';
                }, 5000);
            }
            
            return true;
        });
    }
});

// 刷新打印机列表的函数
function refreshPrinterList() {
    const refreshButton = document.querySelector('button[onclick="refreshPrinterList()"]');
    const printerSelect = document.getElementById('printerSelect');
    
    if (refreshButton) {
        refreshButton.disabled = true;
        refreshButton.innerHTML = '🔄 刷新中...';
    }
    
    // 发送刷新请求
    fetch('/api/refresh_printers')
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 清空当前选项
                printerSelect.innerHTML = '';
                
                if (data.printers && data.printers.length > 0) {
                    // 添加新的打印机选项
                    data.printers.forEach(printer => {
                        const option = document.createElement('option');
                        option.value = printer;
                        option.textContent = printer;
                        
                        // 如果是默认打印机，添加标记并选中
                        if (printer === data.default_printer) {
                            option.textContent += ' (默认)';
                            option.selected = true;
                        }
                        
                        printerSelect.appendChild(option);
                    });
                    
                    // 显示成功消息
                    alert(data.message);

                    // 刷新当前选中打印机的能力（纸张/分辨率）
                    refreshPrinterInfo();
                } else {
                    // 没有找到打印机
                    const option = document.createElement('option');
                    option.value = '';
                    option.textContent = '未检测到可用打印机';
                    printerSelect.appendChild(option);
                    
                    alert('未检测到可用的物理打印机');
                }
            } else {
                alert('刷新失败: ' + data.error);
            }
        })
        .catch(error => {
            console.error('刷新打印机列表失败:', error);
            alert('刷新失败，请检查网络连接');
        })
        .finally(() => {
            // 恢复按钮状态
            if (refreshButton) {
                refreshButton.disabled = false;
                refreshButton.innerHTML = '🔄 刷新';
            }
        });
}

// 页面加载完成后的初始化
document.addEventListener('DOMContentLoaded', function() {
    const printerSelect = document.getElementById('printerSelect');
    if (printerSelect && printerSelect.value) {
        refreshPrinterInfo();
        printerSelect.addEventListener('change', refreshPrinterInfo);
    }
    
    // 初始化拖拽文件功能
    initFileDragDrop();
});

// 拖拽文件功能
function initFileDragDrop() {
    const dropArea = document.getElementById('fileDropArea');
    const fileInput = document.getElementById('fileInput');
    const fileList = document.getElementById('fileList');
    const selectedFiles = document.getElementById('selectedFiles');
    
    if (!dropArea || !fileInput) return;
    
    let currentFiles = [];
    
    // 支持的文件类型
    const allowedTypes = ['pdf', 'jpg', 'jpeg', 'png', 'txt', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx'];
    
    // 点击区域触发文件选择
    dropArea.addEventListener('click', function(e) {
        // 只阻止链接跳转，不阻止点击事件
        if (e.target.tagName === 'A') {
            e.preventDefault();
        }
        fileInput.click();
    });
    
    // 文件输入框变化
    fileInput.addEventListener('change', function(e) {
        const files = Array.from(e.target.files);
        addFiles(files);
    });
    
    // 阻止默认的拖拽行为
    ['dragenter', 'dragover', 'dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, preventDefaults, false);
    });
    
    // 只在document上阻止拖拽，不影响点击
    ['dragenter', 'dragover'].forEach(eventName => {
        document.body.addEventListener(eventName, function(e) {
            if (e.target !== dropArea && !dropArea.contains(e.target)) {
                e.preventDefault();
                e.stopPropagation();
            }
        }, false);
    });
    
    // 高亮拖拽区域
    ['dragenter', 'dragover'].forEach(eventName => {
        dropArea.addEventListener(eventName, highlight, false);
    });
    
    ['dragleave', 'drop'].forEach(eventName => {
        dropArea.addEventListener(eventName, unhighlight, false);
    });
    
    // 处理拖拽文件
    dropArea.addEventListener('drop', handleDrop, false);
    
    function preventDefaults(e) {
        e.preventDefault();
        e.stopPropagation();
    }
    
    function highlight() {
        dropArea.classList.add('drag-over');
        dropArea.querySelector('.drop-icon').textContent = '📤';
    }
    
    function unhighlight() {
        dropArea.classList.remove('drag-over');
        dropArea.querySelector('.drop-icon').textContent = '📁';
    }
    
    function handleDrop(e) {
        const dt = e.dataTransfer;
        const files = Array.from(dt.files);
        addFiles(files);
    }
    
    function addFiles(newFiles) {
        // 过滤允许的文件类型
        const validFiles = newFiles.filter(file => {
            const extension = file.name.split('.').pop().toLowerCase();
            return allowedTypes.includes(extension);
        });
        
        if (validFiles.length !== newFiles.length) {
            const invalidCount = newFiles.length - validFiles.length;
            alert(`有 ${invalidCount} 个文件格式不支持，已忽略。\\n支持的格式: ${allowedTypes.join(', ')}`);
        }
        
        // 添加有效文件到列表（避免重复）
        validFiles.forEach(file => {
            const exists = currentFiles.some(f => f.name === file.name && f.size === file.size);
            if (!exists) {
                currentFiles.push(file);
            }
        });
        
        updateFileList();
        updateFileInput();
    }
    
    function removeFile(index) {
        currentFiles.splice(index, 1);
        updateFileList();
        updateFileInput();
    }
    
    function updateFileList() {
        if (currentFiles.length === 0) {
            fileList.style.display = 'none';
            return;
        }
        
        fileList.style.display = 'block';
        selectedFiles.innerHTML = '';
        
        currentFiles.forEach((file, index) => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';
            fileItem.innerHTML = `
                <span class="file-name">${file.name}</span>
                <span class="file-size">${formatFileSize(file.size)}</span>
                <button type="button" class="remove-btn" onclick="removeFileFromList(${index})" title="移除文件">×</button>
            `;
            selectedFiles.appendChild(fileItem);
        });
    }
    
    function updateFileInput() {
        // 创建新的文件列表
        const dt = new DataTransfer();
        currentFiles.forEach(file => {
            dt.items.add(file);
        });
        fileInput.files = dt.files;
    }
    
    function formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    // 全局函数，供HTML调用
    window.removeFileFromList = function(index) {
        currentFiles.splice(index, 1);
        updateFileList();
        updateFileInput();
    };
}

// 删除队列中的文件
function deleteFile(filename) {
    if (confirm(`确定要从队列中删除文件 "${filename}" 吗？\\n\\n删除后无法恢复，如果需要打印需要重新上传。`)) {
        // 显示删除中状态
        const deleteButtons = document.querySelectorAll(`button[onclick="deleteFile('${filename}')"]`);
        deleteButtons.forEach(btn => {
            btn.disabled = true;
            btn.innerHTML = '🔄 删除中...';
        });
        
        // 发送删除请求
        fetch('/api/delete_file', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({
                filename: filename
            })
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                // 删除成功，刷新页面或移除表格行
                const row = document.querySelector(`button[onclick="deleteFile('${filename}')"]`).closest('tr');
                if (row) {
                    row.style.backgroundColor = '#f8f9fa';
                    row.style.opacity = '0.5';
                    setTimeout(() => {
                        location.reload(); // 刷新页面以更新队列
                    }, 500);
                }
                
                // 显示成功消息
                showAlert('success', `✅ 文件 "${filename}" 已从队列中删除`);
            } else {
                showAlert('danger', `❌ 删除失败: ${data.error}`);
                // 恢复按钮状态
                deleteButtons.forEach(btn => {
                    btn.disabled = false;
                    btn.innerHTML = '🗑️ 删除';
                });
            }
        })
        .catch(error => {
            console.error('删除文件时发生错误:', error);
            showAlert('danger', `❌ 删除文件时发生网络错误: ${error.message || error}`);
            // 恢复按钮状态
            deleteButtons.forEach(btn => {
                btn.disabled = false;
                btn.innerHTML = '🗑️ 删除';
            });
        });
    }
}

// 显示提示消息
function showAlert(type, message) {
    // 创建提示框
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type} alert-dismissible fade show`;
    alertDiv.style.position = 'fixed';
    alertDiv.style.top = '20px';
    alertDiv.style.right = '20px';
    alertDiv.style.zIndex = '9999';
    alertDiv.style.minWidth = '300px';
    alertDiv.innerHTML = `
        ${message}
        <button type="button" class="btn-close" onclick="this.parentElement.remove()" aria-label="Close"></button>
    `;
    
    document.body.appendChild(alertDiv);
    
    // 3秒后自动消失
    setTimeout(() => {
        if (alertDiv.parentElement) {
            alertDiv.remove();
        }
    }, 3000);
}

// 批量删除功能
function deleteAllFiles() {
    const fileRows = document.querySelectorAll('table tbody tr');
    const fileCount = fileRows.length;
    
    // 排除空队列的情况
    const emptyRow = document.querySelector('table tbody tr td[colspan]');
    if (emptyRow) {
        showAlert('info', 'ℹ️ 队列为空，没有文件需要删除');
        return;
    }
    
    if (confirm(`确定要删除队列中的所有 ${fileCount} 个文件吗？\\n\\n删除后无法恢复！`)) {
        fetch('/api/delete_all_files', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            }
        })
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                showAlert('success', `✅ 已删除 ${data.count} 个文件`);
                setTimeout(() => {
                    location.reload();
                }, 1000);
            } else {
                showAlert('danger', `❌ 批量删除失败: ${data.error}`);
            }
        })
        .catch(error => {
            console.error('批量删除时发生错误:', error);
            showAlert('danger', `❌ 批量删除时发生网络错误: ${error.message || error}`);
        });
    }
}
</script>
</body>
</html>
'''
 
# 允许的文件类型
ALLOWED_EXT = {'pdf', 'jpg', 'jpeg', 'png', 'txt', 'doc', 'docx', 'ppt', 'pptx', 'xls', 'xlsx'}
 
def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT

def is_physical_printer(printer_name):
    """检查是否为真正的物理打印机"""
    if printer_name in VIRTUAL_PRINTERS:
        return False
    
    # 检查打印机名称中是否包含虚拟打印机的关键词
    virtual_keywords = ['pdf', 'fax', '传真', 'xps', 'onenote', 'virtual', '虚拟', 'send to', 'export', '导出']
    printer_lower = printer_name.lower()
    
    for keyword in virtual_keywords:
        if keyword in printer_lower:
            return False
    
    return True
 
def get_client_info():
    """获取客户端设备信息"""
    try:
        # 获取客户端IP
        client_ip = request.remote_addr or '未知IP'
        
        # 尝试通过各种方式获取计算机名/设备名
        device_name = None
        
        # 方法0: 优先检查表单中的设备名 (最准确的方法)
        try:
            form_device = request.form.get('device_name') if hasattr(request, 'form') and request.form else None
            if form_device:
                device_name = form_device.strip()
        except Exception:
            # 如果无法访问表单数据（比如JSON请求），跳过
            pass
        
        # 方法0.5: 检查是否有自定义的设备名请求头 (客户端可以主动发送)
        if not device_name:
            custom_device = request.headers.get('X-Device-Name') or request.headers.get('Device-Name')
            if custom_device:
                try:
                    # 解码URL编码的设备名
                    import urllib.parse
                    device_name = urllib.parse.unquote(custom_device.strip())
                except Exception:
                    device_name = custom_device.strip()
        
        # 方法1: 检查HTTP请求头中的计算机名信息
        user_agent = request.headers.get('User-Agent', '')
        
        # 方法2: 尝试通过IP地址反向解析获取计算机名
        try:
            import socket
            if client_ip and client_ip != '127.0.0.1' and client_ip != 'localhost':
                hostname = socket.gethostbyaddr(client_ip)[0]
                if hostname and hostname != client_ip:
                    device_name = hostname
        except:
            pass
        
        # 方法3: 从User-Agent中提取更详细的设备信息
        if user_agent:
            import re
            
            # Android设备 - 提取具体型号
            if 'android' in user_agent.lower():
                # 尝试多种Android设备型号模式
                patterns = [
                    r'Android.*?;\s*([^)]+?)\s*Build/',  # 标准Android模式
                    r'Android.*?;\s*(.*?)\)',  # 备用模式
                    r'\(([^;]+);\s*wv\)',  # WebView模式
                ]
                for pattern in patterns:
                    match = re.search(pattern, user_agent)
                    if match:
                        model = match.group(1).strip()
                        # 清理一些常见的无用信息
                        model = re.sub(r'^\w+\s*', '', model)  # 移除开头的语言代码
                        if model and len(model) > 2 and model not in ['Mobile', 'Mobile Safari', 'Safari']:
                            device_name = model
                            break
            
            # iPhone设备 - 提取型号
            elif 'iphone' in user_agent.lower():
                iphone_match = re.search(r'iPhone\s*OS\s*[\d_]+.*?\)', user_agent)
                if iphone_match:
                    # 尝试提取更具体的iPhone型号信息
                    cpu_match = re.search(r'iPhone(\d+,\d+)', user_agent)
                    if cpu_match:
                        device_name = f"iPhone({cpu_match.group(1)})"
                    else:
                        device_name = "iPhone"
                else:
                    device_name = "iPhone"
            
            # iPad设备
            elif 'ipad' in user_agent.lower():
                ipad_match = re.search(r'iPad(\d+,\d+)', user_agent)
                if ipad_match:
                    device_name = f"iPad({ipad_match.group(1)})"
                else:
                    device_name = "iPad"
            
            # Windows设备 - 尝试提取Windows版本
            elif 'windows' in user_agent.lower():
                win_match = re.search(r'Windows NT ([\d.]+)', user_agent)
                if win_match:
                    version = win_match.group(1)
                    version_names = {
                        '10.0': 'Win10/11',
                        '6.3': 'Win8.1',
                        '6.2': 'Win8',
                        '6.1': 'Win7'
                    }
                    win_version = version_names.get(version, f'Windows NT {version}')
                    if not device_name:  # 如果没有通过DNS获取到计算机名
                        device_name = f"{win_version}电脑"
                else:
                    if not device_name:
                        device_name = "Windows电脑"
            
            # Mac设备
            elif 'mac' in user_agent.lower() or 'macintosh' in user_agent.lower():
                mac_match = re.search(r'Mac OS X ([\d_]+)', user_agent)
                if mac_match:
                    mac_version = mac_match.group(1).replace('_', '.')
                    if not device_name:
                        device_name = f"macOS {mac_version}"
                else:
                    if not device_name:
                        device_name = "Mac电脑"
            
            # Linux设备
            elif 'linux' in user_agent.lower():
                if not device_name:
                    device_name = "Linux电脑"
        
        # 如果所有方法都失败，使用默认值
        if not device_name:
            device_name = "未知设备"
        
        return f"{client_ip}({device_name})"
    except Exception as e:
        return f"未知客户端(获取信息失败: {e})"

def log_print(filename, printer, copies, duplex, papersize, quality, client_info=None):
    # 改进双面打印日志显示
    duplex_text = {
        1: "单面",
        2: "双面(长边翻转)",
        3: "双面(短边翻转)"
    }.get(int(duplex), f"未知({duplex})")
    
    # 如果没有提供客户端信息，尝试获取
    if client_info is None:
        try:
            client_info = get_client_info()
        except:
            client_info = "未知客户端"
    
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{datetime.now()} 客户端: {client_info} 打印: {filename} 打印机: {printer} 份数: {copies} 模式: {duplex_text} 纸张: {papersize} 质量: {quality}\n")

def print_file_with_settings(filepath, printer_name, copies=1, duplex=1, papersize='A4', quality='normal'):
    """使用获取到的真实打印设置进行打印"""
    try:
        print(f"开始打印文件: {filepath}")
        print(f"目标打印机: {printer_name}")
        print(f"打印份数: {copies}")
        print(f"双面设置: {duplex}")
        print(f"纸张大小: {papersize}")
        print(f"打印质量: {quality}")
        
        # 获取文件扩展名
        file_ext = os.path.splitext(filepath)[1].lower()
        
        # 根据文件类型选择打印方案，并传递完整参数
        if file_ext == '.pdf':
            return print_pdf_with_settings(filepath, printer_name, copies, duplex, papersize, quality)
        elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif']:
            return print_image_silent(filepath, printer_name, copies)
        elif file_ext in ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
            return print_office_silent(filepath, printer_name, copies)
        elif file_ext == '.txt':
            # 使用简化的TXT静默打印
            return print_text_file_simple(filepath, printer_name, copies)
        # HTML/HTM 不再支持
        else:
            # 对于其他文件类型，尝试使用系统默认方式
            print(f"未知文件类型 {file_ext}，尝试使用系统默认打印方式")
            return print_with_shell_execute(filepath, printer_name, copies)
            
    except Exception as e:
        print(f"打印操作失败: {e}")
        return print_file_silent_fallback(filepath, printer_name, copies)

def validate_duplex_setting(printer_name, duplex_value):
    """验证双面打印设置是否被打印机支持"""
    try:
        # 获取打印机能力
        caps = get_printer_capabilities(printer_name)
        
        # 如果要求双面打印但打印机不支持
        if duplex_value > 1 and not caps.get('duplex_support', False):
            print(f"⚠️ 打印机 '{printer_name}' 不支持双面打印，将改为单面打印")
            return 1  # 强制改为单面
        
        # 验证具体的双面模式
        duplex_modes = caps.get('duplex_modes', [])
        if duplex_value == 2 and 'long_edge' not in duplex_modes:
            print(f"⚠️ 打印机不支持长边翻转，尝试使用其他双面模式")
            if 'short_edge' in duplex_modes:
                return 3  # 改为短边翻转
            else:
                return 1  # 改为单面
        
        if duplex_value == 3 and 'short_edge' not in duplex_modes:
            print(f"⚠️ 打印机不支持短边翻转，尝试使用其他双面模式") 
            if 'long_edge' in duplex_modes:
                return 2  # 改为长边翻转
            else:
                return 1  # 改为单面
        
        return duplex_value  # 设置有效，保持原值
        
    except Exception as e:
        print(f"验证双面设置时出错: {e}，使用原设置")
        return duplex_value

def apply_printer_settings(printer_name, copies, duplex, papersize, quality):
    """应用打印机设置，返回设备模式"""
    try:
        # 检查打印机名称
        if not printer_name or printer_name.strip() == "":
            print("错误: 打印机名称为空")
            return None
            
        if printer_name == "未检测到可用打印机":
            print("错误: 无可用打印机")
            return None
        
        # 验证并修正双面打印设置
        original_duplex = duplex
        duplex = validate_duplex_setting(printer_name, duplex)
        if duplex != original_duplex:
            print(f"双面设置已从 {original_duplex} 调整为 {duplex}")
        
        print(f"验证后的双面设置: {duplex}")
        
        # 获取打印机的默认设备模式
        printer_handle = win32print.OpenPrinter(printer_name)
        try:
            # 获取设备模式
            devmode = win32print.GetPrinter(printer_handle, 2)['pDevMode']
            if devmode is None:
                print("无法获取设备模式，使用默认设置")
                return None
            
            # 设置打印份数
            if copies > 1:
                devmode.Copies = copies
                print(f"设置打印份数: {copies}")
            
            # 设置双面打印（完整的双面打印逻辑）
            try:
                if duplex == 1:
                    # 单面打印
                    devmode.Duplex = win32con.DMDUP_SIMPLEX
                    print("设置打印模式: 单面打印")
                elif duplex == 2:
                    # 长边翻转双面打印（默认的双面模式）
                    devmode.Duplex = win32con.DMDUP_VERTICAL
                    print("设置打印模式: 双面打印 - 长边翻转")
                elif duplex == 3:
                    # 短边翻转双面打印
                    devmode.Duplex = win32con.DMDUP_HORIZONTAL
                    print("设置打印模式: 双面打印 - 短边翻转")
                else:
                    # 默认为单面打印
                    devmode.Duplex = win32con.DMDUP_SIMPLEX
                    print(f"未知双面设置值 {duplex}，默认使用单面打印")
                    
                # 确保设置生效
                devmode.Fields |= win32con.DM_DUPLEX
                
            except Exception as e:
                print(f"设置双面打印失败: {e}")
                # 失败时默认单面打印
                try:
                    devmode.Duplex = win32con.DMDUP_SIMPLEX
                    devmode.Fields |= win32con.DM_DUPLEX
                    print("双面设置失败，回退到单面打印")
                except:
                    print("双面打印设置完全失败，将使用打印机默认设置")
            
            # 设置纸张大小：支持直接传入DMPAPER数值ID
            try:
                if isinstance(papersize, int) or (isinstance(papersize, str) and papersize.isdigit()):
                    devmode.PaperSize = int(papersize)
                    print(f"设置纸张大小ID: {devmode.PaperSize}")
                else:
                    # 兼容老的名称映射（尽量少用）
                    paper_size_map = {
                        'A4': win32con.DMPAPER_A4,
                        'A3': win32con.DMPAPER_A3,
                        'Letter': win32con.DMPAPER_LETTER,
                        'Legal': win32con.DMPAPER_LEGAL
                    }
                    if papersize in paper_size_map:
                        devmode.PaperSize = paper_size_map[papersize]
                        print(f"设置纸张大小: {papersize}")
            except Exception as e:
                print(f"设置纸张大小失败: {e}")
            
            # 设置打印质量：支持 "600x600" 或 "600 x 600"
            try:
                if isinstance(quality, str) and ('x' in quality or 'X' in quality):
                    parts = quality.lower().replace(' ', '').split('x')
                    if len(parts) >= 2 and parts[0].isdigit() and parts[1].isdigit():
                        devmode.PrintQuality = int(parts[0])
                        devmode.YResolution = int(parts[1])
                        print(f"设置打印分辨率: {devmode.PrintQuality}x{devmode.YResolution}")
                elif isinstance(quality, int) or (isinstance(quality, str) and quality.isdigit()):
                    devmode.PrintQuality = int(quality)
                    print(f"设置打印质量(单值): {devmode.PrintQuality}")
                else:
                    # 兼容旧的关键字
                    if quality == 'high':
                        devmode.PrintQuality = win32con.DMRES_HIGH
                        print("设置打印质量: 高质量")
                    else:
                        devmode.PrintQuality = win32con.DMRES_MEDIUM
                        print("设置打印质量: 普通")
            except Exception as e:
                print(f"设置打印质量失败: {e}")
            
            return devmode
        finally:
            win32print.ClosePrinter(printer_handle)
    except Exception as e:
        print(f"设置打印参数失败: {e}")
        return None

def print_pdf_with_settings(filepath, printer_name, copies, duplex, papersize, quality):
    """使用设置参数打印PDF文件，优先使用WPS和Office"""
    try:
        print(f"打印PDF文件: {filepath}")
        
        # 优先尝试使用WPS PDF阅读器
        wps_paths = [
            r"C:\\Program Files (x86)\\Kingsoft\\WPS Office\\ksopdfreader.exe",
            r"C:\\Program Files\\Kingsoft\\WPS Office\\ksopdfreader.exe",
            r"C:\\Users\\{}\\AppData\\Local\\Kingsoft\\WPS Office\\ksopdfreader.exe".format(os.environ.get('USERNAME', '')),
            r"C:\\Program Files (x86)\\Kingsoft\\WPS Office\\office6\\wpsoffice.exe",
            r"C:\\Program Files\\Kingsoft\\WPS Office\\office6\\wpsoffice.exe"
        ]
        
        print("🥇 优先尝试WPS PDF阅读器...")
        for wps_path in wps_paths:
            if os.path.exists(wps_path):
                try:
                    # 应用打印设置
                    _ = apply_printer_settings(printer_name, copies, duplex, papersize, quality)
                    
                    # WPS静默打印命令
                    cmd = f'"{wps_path}" /p "{filepath}"'
                    print(f"使用WPS打印: {cmd}")
                    
                    result = os.system(cmd)
                    if result == 0:
                        print("✅ WPS PDF打印命令执行成功")
                        return True, "WPS PDF打印成功"
                except Exception as e:
                    print(f"❌ WPS打印失败: {e}")
                    continue
        
        # 尝试使用Microsoft Edge PDF查看器（改进版）
        print("🥈 尝试使用Microsoft Edge PDF查看器...")
        try:
            edge_paths = [
                r"C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe",
                r"C:\\Program Files\\Microsoft\\Edge\\Application\\msedge.exe"
            ]
            
            for edge_path in edge_paths:
                if os.path.exists(edge_path):
                    _ = apply_printer_settings(printer_name, copies, duplex, papersize, quality)
                    
                    # 尝试多种Edge打印方法
                    success_count = 0
                    for i in range(copies):
                        try:
                            # 方法1: 尝试使用printto
                            result = win32api.ShellExecute(
                                0, 'printto', filepath, f'"{printer_name}"', None, win32con.SW_HIDE
                            )
                            
                            if result > 32:
                                success_count += 1
                                print(f"✅ Edge printto 第{i+1}份成功")
                            else:
                                # 方法2: 尝试默认打印
                                result2 = win32api.ShellExecute(
                                    0, 'print', filepath, '', '.', win32con.SW_HIDE
                                )
                                if result2 > 32:
                                    success_count += 1
                                    print(f"✅ 默认打印 第{i+1}份成功")
                                else:
                                    print(f"⚠️ 打印失败 第{i+1}份 - 错误代码: {result}, {result2}")
                                    
                            time.sleep(2)
                            
                        except Exception as e:
                            print(f"❌ 第{i+1}份打印异常: {e}")
                    
                    if success_count > 0:
                        return True, f"系统默认PDF打印成功 ({success_count}/{copies}份)"
                    break
                    
        except Exception as e:
            print(f"❌ Edge打印失败: {e}")
        
        # 尝试使用Adobe Reader（备用方案）
        print("🥉 备用方案：尝试Adobe Reader...")
        adobe_paths = [
            r"C:\\Program Files\\Adobe\\Acrobat DC\\Acrobat\\Acrobat.exe",
            r"C:\\Program Files (x86)\\Adobe\\Acrobat Reader DC\\Reader\\AcroRd32.exe",
            r"C:\\Program Files\\Adobe\\Acrobat Reader DC\\Reader\\AcroRd32.exe"
        ]
        
        for adobe_path in adobe_paths:
            if os.path.exists(adobe_path):
                try:
                    _ = apply_printer_settings(printer_name, copies, duplex, papersize, quality)
                    
                    # Adobe Reader静默打印
                    cmd = f'"{adobe_path}" /p /h "{filepath}"'
                    print(f"使用Adobe Reader打印: {cmd}")
                    
                    result = os.system(cmd)
                    if result == 0:
                        print("✅ Adobe Reader打印命令执行成功")
                        return True, "Adobe Reader打印成功"
                except Exception as e:
                    print(f"❌ Adobe Reader打印失败: {e}")
                    continue
        
        # 最后回退到系统默认打印
        print("🔄 所有专用阅读器均不可用，使用系统默认方式...")
        fallback_result = print_pdf_silent(filepath, printer_name, copies)
        if fallback_result and fallback_result[0]:
            return fallback_result
        
        # 如果所有方法都失败，返回有用的错误信息
        error_msg = """PDF打印失败：系统中未检测到可用的PDF阅读器。

解决方案：
1. 安装 Adobe Acrobat Reader DC（推荐）
2. 安装 WPS Office（免费，包含PDF阅读器）
3. 右键PDF文件 → 打开方式 → Microsoft Edge，然后手动打印
4. 手动双击打开PDF文件，然后按Ctrl+P打印

或联系管理员安装PDF阅读软件。"""
        
        return False, error_msg
        
    except Exception as e:
        print(f"PDF打印失败: {e}")
        return False, f"PDF打印异常: {str(e)}"

def print_with_shell_execute(filepath, printer_name, copies):
    """使用ShellExecute进行应用程序调用打印，确保使用指定打印机"""
    try:
        print(f"🚀 使用ShellExecute打印: {filepath} -> {printer_name}")
        success_count = 0
        for i in range(copies):
            try:
                # 使用printto指定打印机
                result = win32api.ShellExecute(
                    0,  # hwnd
                    'printto',  # operation - 使用printto指定打印机
                    filepath,  # file
                    f'"{printer_name}"',  # parameters - 打印机名称
                    None,  # directory
                    0  # show command (SW_HIDE)
                )
                
                if result > 32:  # ShellExecute成功
                    success_count += 1
                    print(f"✅ 第{i+1}份打印任务已发送")
                    time.sleep(2)  # 给应用程序更多时间处理
                else:
                    print(f"❌ printto到{printer_name}失败，错误代码: {result}")
                    
            except Exception as e:
                print(f"❌ 打印第{i+1}份时出错: {e}")
                
        if success_count > 0:
            return True, f"通过关联应用程序打印已发送到 {printer_name} ({success_count}/{copies}份)"
        else:
            return False, f"无法打印到指定打印机 {printer_name}，请检查打印机状态和文件关联程序"            
    except Exception as e:
        return False, f"指定打印机打印失败: {str(e)}"

def print_file_silent_fallback(filepath, printer_name, copies=1):
    """备用的静默打印方案，确保使用指定打印机"""
    try:
        # 方案1: 使用ShellExecute的printto静默打印
        success_count = 0
        for i in range(copies):
            result = win32api.ShellExecute(
                0, 
                'printto', 
                filepath, 
                f'"{printer_name}"',  # 直接指定打印机名称
                '.', 
                win32con.SW_HIDE  # 隐藏窗口
            )
            if result > 32:
                success_count += 1
                time.sleep(1)
            else:
                print(f"printto失败，错误代码: {result}")
        
        if success_count > 0:
            return True, f"静默打印任务已发送到 {printer_name} ({success_count}/{copies}份)"
        else:
            # 如果printto全部失败，尝试其他方法而不是回退到默认打印机
            raise Exception("printto方法失败")
        
    except Exception as e1:
        try:
            # 方案2: 使用批处理文件指定打印机
            import tempfile
            
            # 创建批处理文件进行打印机指定打印
            bat_content = f'''@echo off
for /L %%i in (1,1,{copies}) do (
    rundll32.exe printui.dll,PrintUIEntry /o /n "{printer_name}" /f "{filepath}"
    timeout /t 2 /nobreak >nul
)
'''
            with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False, encoding='gbk') as bat_file:
                bat_file.write(bat_content)
                bat_file_path = bat_file.name
            
            # 静默执行批处理文件
            result = subprocess.run([bat_file_path], 
                         capture_output=True,
                         creationflags=subprocess.CREATE_NO_WINDOW,
                         shell=True, timeout=60)
            
            # 清理临时文件
            try:
                os.unlink(bat_file_path)
            except:
                pass
                
            if result.returncode == 0:
                return True, f"批处理打印任务已发送到 {printer_name} ({copies}份)"
            else:
                print(f"批处理打印失败: {result.stderr}")
                raise Exception("批处理方法失败")
            
        except Exception as e2:
            try:
                # 方案3: 使用WIN32 API直接打印（适用于文本文件）
                file_ext = os.path.splitext(filepath)[1].lower()
                if file_ext == '.txt':
                    return print_text_direct_to_printer(filepath, printer_name, copies)
                else:
                    # 最后尝试一次系统默认打印
                    print(f"🔄 最后尝试系统默认打印: {filepath}")
                    try:
                        result = win32api.ShellExecute(
                            0, 'print', filepath, '', '.', win32con.SW_HIDE
                        )
                        if result > 32:
                            return True, f"系统默认打印成功（可能会弹出打印对话框）"
                        else:
                            print(f"系统默认打印失败，错误代码: {result}")
                    except Exception as default_print_error:
                        print(f"系统默认打印异常: {default_print_error}")
                    
                    # 细化的错误信息
                    filename = os.path.basename(filepath)
                    if file_ext in ['.pdf']:
                        error_msg = f"PDF文件 '{filename}' 打印失败。请安装PDF阅读器（如Adobe Reader、WPS Office）后重试。"
                    elif file_ext in ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
                        error_msg = f"Office文档 '{filename}' 打印失败。请安装Office软件（如Microsoft Office、WPS Office、LibreOffice）后重试。"
                    else:
                        error_msg = f"文件 '{filename}' 打印失败。系统中没有适合的应用程序来打印此文件类型。"
                    
                    return False, error_msg
            except Exception as e3:
                return False, f"所有静默打印方案都失败: {str(e3)}"

def print_text_direct_to_printer(filepath, printer_name, copies=1):
    """使用WIN32 API直接将文本文件发送到指定打印机，支持多种编码"""
    try:
        import win32print
        import chardet
        
        print(f"🔧 使用API直接打印: {filepath}")
        
        # 智能检测文件编码
        content = read_text_with_encoding_detection(filepath)
        if not content:
            return False, "无法读取文本文件内容"
        
        print(f"文件内容长度: {len(content)} 字符")
        
        # 打开指定的打印机
        printer_handle = win32print.OpenPrinter(printer_name)
        
        try:
            success_count = 0
            for i in range(copies):
                # 开始打印作业
                job_id = win32print.StartDocPrinter(printer_handle, 1, ("Text Document", None, "RAW"))
                
                try:
                    win32print.StartPagePrinter(printer_handle)
                    
                    # 智能编码处理：尝试不同的编码方式发送到打印机
                    print_data = None
                    
                    # 尝试多种编码方式
                    encoding_attempts = ['utf-8', 'gbk', 'cp1252', 'latin1']
                    
                    for encoding in encoding_attempts:
                        try:
                            print_data = content.encode(encoding)
                            break
                        except UnicodeEncodeError:
                            continue
                    
                    # 如果所有编码都失败，使用错误替换模式
                    if print_data is None:
                        print_data = content.encode('utf-8', errors='replace')
                        print("⚠️ 使用UTF-8错误替换模式编码")
                    
                    # 发送文本内容到打印机
                    win32print.WritePrinter(printer_handle, print_data)
                    
                    win32print.EndPagePrinter(printer_handle)
                    win32print.EndDocPrinter(printer_handle)
                    success_count += 1
                    print(f"✅ 打印作业 {i+1} 成功")
                    
                except Exception as e:
                    print(f"打印作业 {i+1} 失败: {e}")
                    win32print.AbortPrinter(printer_handle)
                
            return True, f"直接打印到 {printer_name} 成功 ({success_count}/{copies}份)"
            
        finally:
            win32print.ClosePrinter(printer_handle)
            
    except Exception as e:
        return False, f"直接打印失败: {str(e)}"

def print_pdf_silent(filepath, printer_name, copies=1):
    """专门用于PDF文件的静默打印，优先使用Adobe Reader"""
    try:
        # 方案1: 优先使用PowerShell和Adobe COM对象实现完全静默打印
        print("🥇 优先尝试Adobe COM静默打印...")
        adobe_com_result = print_pdf_adobe_com(filepath, printer_name, copies)
        if adobe_com_result and adobe_com_result[0]:
            return adobe_com_result
            
        # 方案2: 尝试Adobe Reader命令行（可能有界面闪烁）
        print("🥈 尝试Adobe Reader命令行...")
        adobe_paths = [
            r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
            r"C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
            r"C:\Program Files\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
            r"C:\Program Files (x86)\Adobe\Reader 11.0\Reader\AcroRd32.exe",
            r"C:\Program Files\Adobe\Reader 11.0\Reader\AcroRd32.exe",
            r"C:\Program Files (x86)\Adobe\Reader 10.0\Reader\AcroRd32.exe"
        ]
        
        for adobe_path in adobe_paths:
            if os.path.exists(adobe_path):
                try:
                    print(f"✅ 找到Adobe Reader: {adobe_path}")
                    # 使用START /MIN隐藏窗口
                    for i in range(copies):
                        cmd = f'START /MIN "" "{adobe_path}" /t "{filepath}" "{printer_name}"'
                        result = subprocess.run(cmd, shell=True, 
                                              capture_output=True,
                                              creationflags=subprocess.CREATE_NO_WINDOW,
                                              timeout=30)
                        
                        if result.returncode == 0:
                            print(f"✅ 第{i+1}份 Adobe PDF打印已发送")
                        time.sleep(2)
                    
                    return True, f"Adobe Reader PDF打印已发送到 {printer_name} ({copies}份)"
                    
                except Exception as e:
                    print(f"❌ Adobe Reader打印失败: {e}")
                    continue
                    
        print("⚠️ 未找到可用的Adobe Reader，尝试其他方案...")
        
        # 方案2: 使用系统默认方式（如果Adobe Reader不可用）
        print("🥈 使用系统默认方式打印PDF...")
        try:
            success_count = 0
            for i in range(copies):
                # 使用printto指定打印机
                result = win32api.ShellExecute(0, 'printto', filepath, f'"{printer_name}"', None, 0)
                if result > 32:
                    success_count += 1
                    print(f"✅ 第{i+1}份系统默认PDF打印已发送")
                    time.sleep(3)  # 给应用程序更多时间
                else:
                    print(f"❌ printto失败，错误代码: {result}")
                    
            if success_count > 0:
                return True, f"系统默认PDF打印已发送到 {printer_name} ({success_count}/{copies}份)"
            else:
                print(f"❌ 系统默认PDF打印失败")
                
        except Exception as e:
            print(f"❌ 系统默认PDF打印异常: {e}")
        
        # 方案4: 使用系统printto指定打印机
        print("🔄 尝试系统默认PDF处理程序...")
        try:
            for i in range(copies):
                # 使用printto指定打印机
                result = win32api.ShellExecute(0, 'printto', filepath, f'"{printer_name}"', None, 0)
                if result <= 32:
                    print(f"printto失败，错误代码: {result}")
                    raise Exception(f"无法打印到指定打印机 {printer_name}")
                time.sleep(3)  # 给应用程序更多时间
            return True, f"系统PDF打印已发送到指定打印机 {printer_name} ({copies}份)"
        except Exception as e:
            print(f"系统打印失败: {e}")
        
        # 方案5: 使用PowerShell和COM对象，设置正确的打印机
        try:
            ps_script = f'''
try {{
    Add-Type -AssemblyName System.Drawing
    Add-Type -AssemblyName System.Windows.Forms
    
    # 设置指定的打印机
    $filepath = "{filepath.replace(chr(92), chr(92)+chr(92))}"
    $printer = "{printer_name}"
    
    # 尝试使用.NET PrintDocument设置打印机
    Add-Type -AssemblyName System.Drawing
    $printDoc = New-Object System.Drawing.Printing.PrintDocument
    $printDoc.PrinterSettings.PrinterName = $printer
    
    # 验证打印机是否可用
    if (-not $printDoc.PrinterSettings.IsValid) {{
        Write-Error "指定的打印机不可用: $printer"
        exit 1
    }}
    
    # 直接使用printto命令
    for ($i = 1; $i -le {copies}; $i++) {{
        $proc = Start-Process -FilePath "powershell" -ArgumentList "-Command", "Start-Process -FilePath '$filepath' -Verb PrintTo -ArgumentList '$printer'" -WindowStyle Hidden -PassThru
        $proc.WaitForExit(30000)  # 等待30秒
        Start-Sleep -Seconds 2
    }}
    
    Write-Output "PDF PowerShell打印完成，发送到: $printer"
}} catch {{
    Write-Error "PDF PowerShell打印失败: $_"
    exit 1
}}
'''
            result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script],
                                  capture_output=True, text=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW,
                                  timeout=60)
            
            if result.returncode == 0:
                return True, f"PDF PowerShell打印已发送到 {printer_name} ({copies}份)"
            else:
                print(f"PowerShell打印失败: {result.stderr}")
        
        except Exception as e:
            print(f"PowerShell PDF打印异常: {e}")
        
        # 最终备用方案
        print("🔄 使用通用备用方案...")
        return print_file_silent_fallback(filepath, printer_name, copies)
        
    except Exception as e:
        print(f"❌ PDF打印完全失败: {e}")
        return print_file_silent_fallback(filepath, printer_name, copies)

def print_pdf_adobe_com(filepath, printer_name, copies=1):
    """强化PDF COM打印 - 支持Adobe Acrobat、Reader、WPS PDF"""
    try:
        abs_filepath = os.path.abspath(filepath)
        print(f"🔧 强化PDF COM打印: {abs_filepath}")
        
        # 方案1: Adobe Acrobat Professional (最强功能)
        print("🔸 尝试Adobe Acrobat Professional...")
        ps_script_acrobat = f'''
try {{
    $ErrorActionPreference = "Stop"
    
    # 尝试创建Adobe Acrobat COM对象
    try {{
        $acrobat = New-Object -ComObject AcroExch.App
        $avDoc = New-Object -ComObject AcroExch.AVDoc
        Write-Host "成功创建Adobe COM对象"
    }} catch {{
        Write-Host "无法创建Adobe COM对象： $_"
        exit 1
    }}
    
    # 打开PDF文档
    $opened = $avDoc.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}", "")
    if (-not $opened) {{
        Write-Host "无法打开PDF文件"
        exit 1
    }}
    
    Write-Host "PDF文档打开成功"
    
    # 获取PDDoc对象
    $pdDoc = $avDoc.GetPDDoc()
    if (-not $pdDoc) {{
        Write-Host "无法获取PDDoc对象"
        $avDoc.Close([ref]$true)
        exit 1
    }}
    
    # 执行静默打印
    Write-Host "开始静默打印 {copies} 份到打印机: {printer_name}"
    for ($i = 1; $i -le {copies}; $i++) {{
        try {{
            # 使用JSObject执行JavaScript打印命令
            $jsObj = $pdDoc.GetJSObject()
            $printParams = @{{
                bUI = $false
                bSilent = $true
                bShrinkToFit = $true
                printerName = "{printer_name}"
            }}
            
            # 调用JavaScript print方法
            $jsObj.print($printParams)
            Write-Host "第${{i}}份打印命令已发送"
            Start-Sleep -Seconds 1
        }} catch {{
            Write-Host "第${{i}}份打印失败： $_"
        }}
    }}
    
    # 清理资源
    $avDoc.Close([ref]$true)
    $acrobat.Exit()
    
    # 释放COM对象
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($pdDoc) | Out-Null
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($avDoc) | Out-Null
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($acrobat) | Out-Null
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
    
    Write-Output "Adobe COM静默打印完成"
}} catch {{
    Write-Host "Adobe COM打印失败： $_"
    exit 1
}}
'''
        
        
        # 执行Adobe Acrobat COM
        try:
            result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_acrobat],
                                  capture_output=True, text=True, timeout=45,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                print("✅ Adobe Acrobat COM打印成功")
                return True, f"Adobe Acrobat COM打印完成 ({copies}份)"
        except Exception as e:
            print(f"Adobe Acrobat COM异常: {e}")
        
        # 方案2: Adobe Reader COM (有限支持)
        print("🔸 尝试Adobe Reader COM...")
        ps_script_reader = f'''
try {{
    $ErrorActionPreference = "Stop"
    
    # 创建Adobe Reader COM对象
    $reader = New-Object -ComObject AcroRd32.App
    $reader.Hide()
    
    # 打开PDF文档
    $avDoc = New-Object -ComObject AcroRd32.AVDoc
    $opened = $avDoc.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}", "")
    if (-not $opened) {{
        Write-Host "Reader无法打开PDF"
        exit 1
    }}
    
    # Reader的打印方法（通过菜单执行）
    for ($i = 1; $i -le {copies}; $i++) {{
        try {{
            # 使用Reader的打印接口
            $avDoc.GetAVPageView().DoGoToPage(0)
            Start-Sleep -Milliseconds 300
            
            # 执行打印菜单命令
            $avDoc.GetAVPageView().GetAVDoc().GetAVWindow().SetTitle("Printing...")
            
            # 尝试调用打印对话框并自动确认
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.SendKeys]::SendWait("^p")
            Start-Sleep -Seconds 1
            [System.Windows.Forms.SendKeys]::SendWait("{{TAB}}{{TAB}}{{ENTER}}")
            Start-Sleep -Seconds 2
            
            Write-Host "Reader打印第${{i}}份已发送"
        }} catch {{
            Write-Host "Reader打印第${{i}}份失败: $_"
        }}
    }}
    
    $avDoc.Close([ref]$true)
    $reader.Exit()
    Write-Output "Adobe Reader打印完成"
}} catch {{
    Write-Host "Adobe Reader COM失败: $_"
    exit 1
}}
'''
        
        try:
            result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_reader],
                                  capture_output=True, text=True, timeout=60,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                print("✅ Adobe Reader COM打印成功")
                return True, f"Adobe Reader COM打印完成 ({copies}份)"
        except Exception as e:
            print(f"Adobe Reader COM异常: {e}")
        
        # 方案3: WPS PDF COM对象
        print("🔸 尝试WPS PDF COM...")
        ps_script_wps = f'''
try {{
    $ErrorActionPreference = "Stop"
    
    # 尝试创建WPS COM对象
    $wps = New-Object -ComObject kwps.application
    $wps.Visible = $false
    Write-Host "WPS COM对象创建成功"
    
    # 打开PDF文档
    $doc = $wps.Documents.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}")
    Write-Host "WPS打开PDF成功"
    
    # 设置打印机
    try {{
        $wps.ActivePrinter = "{printer_name}"
        Write-Host "WPS设置打印机成功"
    }} catch {{
        Write-Host "WPS无法设置指定打印机，使用默认"
    }}
    
    # 执行打印
    for ($i = 1; $i -le {copies}; $i++) {{
        try {{
            $doc.PrintOut()
            Write-Host "WPS PDF打印第${{i}}份完成"
            Start-Sleep -Seconds 2
        }} catch {{
            Write-Host "WPS PDF打印第${{i}}份失败: $_"
        }}
    }}
    
    $doc.Close([ref]$false)
    $wps.Quit()
    Write-Output "WPS PDF打印成功"
}} catch {{
    Write-Host "WPS PDF COM失败: $_"
    exit 1
}}
'''
        
        try:
            result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_wps],
                                  capture_output=True, text=True, timeout=45,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                print("✅ WPS PDF COM打印成功")
                return True, f"WPS PDF COM打印完成 ({copies}份)"
        except Exception as e:
            print(f"WPS PDF COM异常: {e}")
        
        print("❌ 所有PDF COM方案均失败")
        return False, "PDF COM对象均不可用"
        
    except Exception as e:
        print(f"❌ PDF COM打印整体异常: {e}")
        return False, f"PDF COM异常: {str(e)}"

def print_text_file_simple(filepath, printer_name, copies=1):
    """改进的TXT文件打印：支持各种记事本软件创建的文件"""
    try:
        print(f"📝 开始打印文本文件: {filepath}")
        
        # 检测是否为远程桌面环境
        is_remote_desktop = detect_remote_desktop()
        
        # 方案1: 优先使用直接API打印 (无页码，纯文本)
        print("🥇 尝试使用直接API打印...")
        try:
            api_success = print_text_direct_to_printer(filepath, printer_name, copies)
            if api_success[0]:
                return api_success
        except Exception as e:
            print(f"直接API打印失败: {e}")
        
        # 方案2: 使用ShellExecute printto (远程桌面环境下优先使用)
        if is_remote_desktop:
            print("🌐 远程桌面环境，优先使用printto...")
        else:
            print("� 尝试使用默认程序printto...")
        sent = 0
        for i in range(copies):
            r = win32api.ShellExecute(0, 'printto', filepath, f'"{printer_name}"', None, 0)
            if r > 32:
                sent += 1
                time.sleep(2)  # 给更多时间处理
            else:
                print(f"printto到{printer_name}失败，错误代码: {r}")
                
        if sent > 0:
            return True, f"默认程序打印已发送到 {printer_name} ({sent}/{copies}份)"
        
        # 方案3: 尝试WordPad打印 (支持更多编码，但可能有格式)
        if not is_remote_desktop:  # 远程桌面环境下跳过GUI应用
            print("🥉 尝试使用WordPad打印...")
            wordpad_success = try_wordpad_print(filepath, printer_name, copies)
            if wordpad_success[0]:
                return wordpad_success
        
        # 方案4: 最后使用记事本打印 (会产生页码)
        if not is_remote_desktop:  # 远程桌面环境下跳过GUI应用
            print("🔄 尝试使用Windows记事本打印(可能有页码)...")
            notepad_success = try_notepad_print(filepath, printer_name, copies)
            if notepad_success[0]:
                return notepad_success
        
        # 所有方案都失败
        return False, f"所有TXT打印方案都失败，无法发送到指定打印机 {printer_name}"
        
    except Exception as e:
        return False, f"TXT文件打印失败: {e}"

def try_notepad_print(filepath, printer_name, copies=1):
    """使用Windows自带记事本进行打印"""
    try:
        import subprocess
        notepad_path = r"C:\Windows\System32\notepad.exe"
        
        if not os.path.exists(notepad_path):
            return False, "Windows记事本未找到"
        
        success_count = 0
        for i in range(copies):
            try:
                # 使用记事本的打印功能
                # 注意：记事本没有直接的命令行打印参数，所以我们使用printto
                cmd = [notepad_path, '/p', filepath]
                result = subprocess.run(cmd, 
                                      creationflags=subprocess.CREATE_NO_WINDOW,
                                      timeout=30)
                
                # 由于notepad /p 会显示打印对话框，我们改用ShellExecute方式
                # 让系统调用notepad进行printto操作
                
                # 创建临时批处理文件来实现记事本静默打印
                temp_bat = create_notepad_print_batch(filepath, printer_name)
                if temp_bat:
                    bat_result = subprocess.run([temp_bat], 
                                              creationflags=subprocess.CREATE_NO_WINDOW,
                                              timeout=30)
                    if bat_result.returncode == 0:
                        success_count += 1
                    
                    # 清理临时文件
                    try:
                        os.remove(temp_bat)
                    except:
                        pass
                else:
                    # 如果批处理创建失败，使用备用方法
                    r = win32api.ShellExecute(0, 'open', notepad_path, f'/pt "{filepath}" "{printer_name}"', None, 0)
                    if r > 32:
                        success_count += 1
                
                time.sleep(1)
                
            except Exception as e:
                print(f"记事本打印第{i+1}份时出错: {e}")
                continue
        
        if success_count > 0:
            return True, f"Windows记事本打印成功 ({success_count}/{copies}份)"
        else:
            return False, "Windows记事本打印失败"
            
    except Exception as e:
        return False, f"记事本打印异常: {e}"

def try_wordpad_print(filepath, printer_name, copies=1):
    """使用WordPad进行打印（更好的编码支持）"""
    try:
        import subprocess
        wordpad_path = r"C:\Program Files\Windows NT\Accessories\wordpad.exe"
        
        # 64位系统的备用路径
        if not os.path.exists(wordpad_path):
            wordpad_path = r"C:\Program Files (x86)\Windows NT\Accessories\wordpad.exe"
        
        if not os.path.exists(wordpad_path):
            return False, "WordPad未找到"
        
        success_count = 0
        for i in range(copies):
            try:
                # WordPad支持 /pt 参数进行静默打印
                cmd = [wordpad_path, '/pt', filepath, printer_name]
                result = subprocess.run(cmd, 
                                      creationflags=subprocess.CREATE_NO_WINDOW,
                                      timeout=30)
                
                if result.returncode == 0:
                    success_count += 1
                    time.sleep(2)
                else:
                    print(f"WordPad打印返回代码: {result.returncode}")
                    
            except Exception as e:
                print(f"WordPad打印第{i+1}份时出错: {e}")
                continue
        
        if success_count > 0:
            return True, f"WordPad打印成功 ({success_count}/{copies}份)"
        else:
            return False, "WordPad打印失败"
            
    except Exception as e:
        return False, f"WordPad打印异常: {e}"

def read_text_with_encoding_detection(filepath):
    """智能检测文件编码并读取内容，兼容各种记事本软件"""
    try:
        # 常见的编码顺序，按优先级排序
        encodings_to_try = [
            'utf-8-sig',  # UTF-8 with BOM (Notepad3 常用)
            'utf-8',      # UTF-8 无BOM
            'gbk',        # 中文GBK
            'gb2312',     # 中文GB2312
            'cp1252',     # Windows-1252
            'latin1',     # ISO-8859-1
            'utf-16',     # UTF-16
            'utf-16le',   # UTF-16 LE
            'utf-16be'    # UTF-16 BE
        ]
        
        # 方法1: 尝试使用chardet检测编码
        try:
            with open(filepath, 'rb') as f:
                raw_data = f.read()
            
            # 使用chardet检测编码（如果可用）
            try:
                import chardet
                detected = chardet.detect(raw_data)
                if detected and detected['encoding'] and detected['confidence'] > 0.7:
                    detected_encoding = detected['encoding']
                    print(f"检测到编码: {detected_encoding} (置信度: {detected['confidence']:.2f})")
                    
                    # 将检测到的编码放在首位尝试
                    if detected_encoding not in encodings_to_try:
                        encodings_to_try.insert(0, detected_encoding)
                    else:
                        # 将检测到的编码移到首位
                        encodings_to_try.remove(detected_encoding)
                        encodings_to_try.insert(0, detected_encoding)
            except ImportError:
                print("chardet库未安装，使用默认编码顺序")
            
            # 尝试各种编码
            for encoding in encodings_to_try:
                try:
                    content = raw_data.decode(encoding)
                    print(f"✅ 成功使用编码 {encoding} 读取文件")
                    
                    # 验证内容是否合理（不包含太多替换字符）
                    replacement_ratio = content.count('�') / len(content) if len(content) > 0 else 0
                    if replacement_ratio < 0.1:  # 替换字符少于10%
                        return content
                    else:
                        print(f"编码 {encoding} 包含过多替换字符，尝试其他编码")
                        continue
                        
                except (UnicodeDecodeError, UnicodeError) as e:
                    print(f"编码 {encoding} 失败: {e}")
                    continue
            
            # 如果所有编码都失败，使用错误处理模式
            print("⚠️ 所有编码尝试失败，使用错误替换模式")
            return raw_data.decode('utf-8', errors='replace')
            
        except Exception as e:
            print(f"文件读取异常: {e}")
            return None
            
    except Exception as e:
        print(f"编码检测过程异常: {e}")
        return None

def create_notepad_print_batch(filepath, printer_name):
    """创建临时批处理文件实现记事本静默打印"""
    try:
        import tempfile
        
        # 创建临时批处理文件
        temp_dir = tempfile.gettempdir()
        bat_file = os.path.join(temp_dir, f"print_text_{int(time.time())}.bat")
        
        # 批处理内容：使用type命令直接发送到打印机
        bat_content = f'''@echo off
echo 正在打印文件到 {printer_name}...
type "{filepath}" > "\\\\localhost\\{printer_name}"
if errorlevel 1 (
    echo 打印失败
    exit /b 1
) else (
    echo 打印成功
    exit /b 0
)
'''
        
        with open(bat_file, 'w', encoding='gbk') as f:
            f.write(bat_content)
        
        return bat_file
        
    except Exception as e:
        print(f"创建批处理文件失败: {e}")
        return None

def print_image_silent(filepath, printer_name, copies=1):
    """专门用于图片文件的静默打印，确保使用指定打印机"""
    try:
        success_total = 0
        # 方法1：使用系统画图(MSPaint)的 /pt 参数
        for i in range(copies):
            try:
                cmd = ['mspaint.exe', '/pt', filepath, printer_name]
                result = subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW, timeout=30)
                if result.returncode == 0:
                    success_total += 1
                    time.sleep(1)
                    continue
            except Exception:
                pass
            # 方法2：ShellExecute 'printto'
            try:
                r = win32api.ShellExecute(0, 'printto', filepath, f'"{printer_name}"', None, 0)
                if r > 32:
                    success_total += 1
                    time.sleep(2)
                    continue
                else:
                    print(f"printto图片到{printer_name}失败，错误代码: {r}")
            except Exception as e:
                print(f"printto图片异常: {e}")
            
            # 方法3：不再回退到默认打印机，而是记录失败
            print(f"第{i+1}份图片打印失败，无法发送到指定打印机 {printer_name}")
                
        if success_total > 0:
            return True, f"图片静默打印已发送到 {printer_name} ({success_total}/{copies}份)"
        else:
            return False, f"图片打印失败，无法发送到指定打印机 {printer_name}"
    except Exception as e:
        return False, f"图片静默打印异常: {e}"
def print_office_silent(filepath, printer_name, copies=1):
    """专门用于Office文档的静默打印，优先使用Office程序/COM直接打印"""
    try:
        file_ext = os.path.splitext(filepath)[1].lower()
        print(f"📊 开始Office文档打印: {filepath} ({file_ext})")
        
        # PowerPoint特殊处理：使用独立的直接打印方案
        if file_ext in ['.ppt', '.pptx']:
            print("🎯 PowerPoint文档：使用独立直接打印方案...")
            ppt_result = print_powerpoint_direct(filepath, printer_name, copies)
            if ppt_result and ppt_result[0]:
                return ppt_result
            else:
                print(f"⚠️ PowerPoint独立打印失败: {ppt_result[1] if ppt_result else '未知错误'}")
                # PowerPoint失败后继续尝试通用方案
        
        # 方案1: 优先使用强化COM对象直接打印
        print("🥇 优先尝试强化COM对象打印...")
        com_result = print_office_com(filepath, printer_name, copies, file_ext)
        if com_result and com_result[0]:
            return com_result
        else:
            # 强化COM失败，记录详细信息但继续尝试其他方案
            print(f"⚠️ 强化COM打印失败: {com_result[1] if com_result else '未知错误'}")
        
        # 方案2: 使用Office程序命令行打印
        print("🥈 尝试Office程序命令行打印...")
        
        # 根据文件类型选择相应的Office应用程序
        if file_ext in ['.doc', '.docx']:
            office_paths = [
                r"C:\Program Files\Microsoft Office\root\Office16\WINWORD.EXE",
                r"C:\Program Files (x86)\Microsoft Office\root\Office16\WINWORD.EXE",
                r"C:\Program Files\Microsoft Office\Office16\WINWORD.EXE",
                r"C:\Program Files (x86)\Microsoft Office\Office16\WINWORD.EXE",
                r"C:\Program Files\Microsoft Office\Office15\WINWORD.EXE",
                r"C:\Program Files (x86)\Microsoft Office\Office15\WINWORD.EXE"
            ]
            app_name = "Word"
        elif file_ext in ['.xls', '.xlsx']:
            office_paths = [
                r"C:\Program Files\Microsoft Office\root\Office16\EXCEL.EXE",
                r"C:\Program Files (x86)\Microsoft Office\root\Office16\EXCEL.EXE",
                r"C:\Program Files\Microsoft Office\Office16\EXCEL.EXE",
                r"C:\Program Files (x86)\Microsoft Office\Office16\EXCEL.EXE",
                r"C:\Program Files\Microsoft Office\Office15\EXCEL.EXE",
                r"C:\Program Files (x86)\Microsoft Office\Office15\EXCEL.EXE"
            ]
            app_name = "Excel"
        elif file_ext in ['.ppt', '.pptx']:
            # PowerPoint文档
            office_paths = [
                r"C:\Program Files\Microsoft Office\root\Office16\POWERPNT.EXE",
                r"C:\Program Files (x86)\Microsoft Office\root\Office16\POWERPNT.EXE",
                r"C:\Program Files\Microsoft Office\Office16\POWERPNT.EXE",
                r"C:\Program Files (x86)\Microsoft Office\Office16\POWERPNT.EXE",
                r"C:\Program Files\Microsoft Office\Office15\POWERPNT.EXE",
                r"C:\Program Files (x86)\Microsoft Office\Office15\POWERPNT.EXE"
            ]
            app_name = "PowerPoint"
        else:
            return print_file_silent_fallback(filepath, printer_name, copies)
        
        # 查找可用的Office应用程序
        office_app = None
        for path in office_paths:
            if os.path.exists(path):
                office_app = path
                break
        
        if office_app:
            # 使用Office应用程序静默打印
            try:
                for i in range(copies):
                    # 修改命令参数以确保正确的静默打印
                    if app_name == "Word":
                        cmd = [office_app, '/q', '/n', '/mFilePrint', '/mFileExit', filepath]
                    elif app_name == "Excel":
                        cmd = [office_app, '/e', filepath, '/p']
                    elif app_name == "PowerPoint":
                        cmd = [office_app, '/p', filepath]
                    else:
                        cmd = [office_app, '/q', '/n', '/mFilePrintDefault', '/mFileExit', filepath]
                    
                    process = subprocess.Popen(cmd, 
                                             creationflags=subprocess.CREATE_NO_WINDOW,
                                             stdout=subprocess.PIPE, 
                                             stderr=subprocess.PIPE)
                    # 给Office应用程序足够的时间处理
                    time.sleep(6 + i)  # 递增等待时间避免冲突
                    
                    # 检查进程状态并清理
                    if process.poll() is None:
                        try:
                            process.terminate()
                            process.wait(timeout=3)
                        except:
                            process.kill()
                            
                return True, f"{app_name}文档静默打印已发送到 {printer_name} ({copies}份)"
            except Exception as e:
                print(f"Office应用程序打印失败: {e}")
                # 尝试COM方式
                return print_office_com(filepath, printer_name, copies, file_ext)
        else:
            # 如果找不到Office应用程序，但强化COM已经尝试过所有方案
            print("💻 未找到Office应用程序路径，但强化COM已包含完整检测...")
            
            # 最后尝试系统默认方式
            print("🔄 尝试系统默认文件关联打印...")
            try:
                success_count = 0
                for i in range(copies):
                    # 尝试使用printto指定打印机
                    result = win32api.ShellExecute(
                        0, 'printto', filepath, f'"{printer_name}"', None, win32con.SW_HIDE
                    )
                    
                    if result > 32:
                        success_count += 1
                        print(f"✅ 第{i+1}份系统默认打印成功")
                    else:
                        # 尝试默认打印
                        result2 = win32api.ShellExecute(
                            0, 'print', filepath, '', '.', win32con.SW_HIDE
                        )
                        if result2 > 32:
                            success_count += 1
                            print(f"✅ 默认关联打印 第{i+1}份成功")
                        else:
                            print(f"⚠️ 系统打印失败 第{i+1}份 - 错误代码: {result}, {result2}")
                    
                    time.sleep(3)  # Office文档需要更长时间
                
                if success_count > 0:
                    return True, f"系统默认Office打印成功 ({success_count}/{copies}份)"
            
            except Exception as e:
                print(f"❌ 系统默认打印失败: {e}")
            
            # 所有方法都失败，返回实际的错误信息（不再误导说"未检测到Office"）
            file_type_names = {
                '.doc': 'Word文档', '.docx': 'Word文档',
                '.xls': 'Excel表格', '.xlsx': 'Excel表格', 
                '.ppt': 'PowerPoint演示', '.pptx': 'PowerPoint演示'
            }
            
            file_type_name = file_type_names.get(file_ext, 'Office文档')
            
            error_msg = f"""{file_type_name}打印失败：尝试了多种打印方案均无法成功。

已尝试的方案：
1. ✓ Microsoft Office COM对象
2. ✓ WPS Office COM对象  
3. ✓ Office应用程序命令行打印
4. ✓ 系统文件关联打印

可能的解决方案：
1. 检查打印机是否正常工作
2. 尝试手动打开文档并打印测试
3. 重启打印服务和Office应用程序
4. 将文档转换为PDF格式后再打印
"""
            
            return False, error_msg
        
    except Exception as e:
        # 如果Office专用方法失败，使用通用方法
        print(f"❌ Office打印异常: {e}")
        return print_file_silent_fallback(filepath, printer_name, copies)

def print_powerpoint_direct(filepath, printer_name, copies=1):
    """PowerPoint直接打印 - 绕过COM权限问题的独立方案"""
    import tempfile
    try:
        abs_filepath = os.path.abspath(filepath)
        print(f"🎯 PowerPoint直接打印: {abs_filepath}")
        
        # 方案1: 使用PowerShell + 系统打印队列
        print("🔸 尝试PowerShell系统打印...")
        ps_script_direct = f'''
try {{
    $ErrorActionPreference = "Stop"
    
    # 直接使用系统的PrintTo功能
    Write-Host "开始PowerPoint系统打印 {copies} 份..."
    
    for ($i = 1; $i -le {copies}; $i++) {{
        try {{
            # 方法1: 使用COM Automation但不依赖PowerPoint应用程序
            $shell = New-Object -ComObject Shell.Application
            $folder = $shell.Namespace((Get-Item "{abs_filepath.replace(chr(92), chr(92)+chr(92))}").DirectoryName)
            $item = $folder.ParseName((Get-Item "{abs_filepath.replace(chr(92), chr(92)+chr(92))}").Name)
            
            # 获取打印动词
            $verbs = $item.Verbs()
            $printVerb = $verbs | Where-Object {{ $_.Name -match "打印|Print" }}
            
            if ($printVerb) {{
                $printVerb.DoIt()
                Write-Host "PowerPoint系统打印第${{i}}份已发送"
                Start-Sleep -Seconds 3
            }} else {{
                # 备用方法：使用Start-Process PrintTo
                Start-Process -FilePath "{abs_filepath.replace(chr(92), chr(92)+chr(92))}" -Verb PrintTo -ArgumentList "{printer_name}" -WindowStyle Hidden -Wait
                Write-Host "PowerPoint PrintTo第${{i}}份完成"
                Start-Sleep -Seconds 2
            }}
        }} catch {{
            Write-Host "PowerPoint系统打印第${{i}}份失败: $_"
            
            # 最后备用：直接文件关联打印
            try {{
                cmd /c 'print /d:"{printer_name}" "{abs_filepath.replace(chr(92), chr(92)+chr(92))}"'
                Write-Host "PowerPoint命令行打印第${{i}}份完成"
            }} catch {{
                Write-Host "PowerPoint所有打印方法都失败了"
            }}
        }}
    }}
    
    Write-Output "PowerPoint直接打印完成"
}} catch {{
    Write-Host "PowerPoint直接打印失败: $_"
    exit 1
}}
'''
        
        # 尝试PowerShell直接打印
        try:
            result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_direct],
                                  capture_output=True, text=True, timeout=120,
                                  creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                print("✅ PowerPoint直接打印成功")
                return True, f"PowerPoint直接打印完成 ({copies}份)"
            else:
                print(f"PowerPoint直接打印stderr: {result.stderr}")
        except Exception as e:
            print(f"PowerPoint直接打印异常: {e}")
        
        # 方案2: 使用win32api直接打印
        print("🔸 尝试Win32API直接打印...")
        try:
            for i in range(copies):
                # 使用Windows API直接打印
                result = win32api.ShellExecute(0, 'printto', abs_filepath, f'"{printer_name}"', None, 0)
                if result > 32:  # ShellExecute成功返回值 > 32
                    print(f"✅ PowerPoint Win32API打印第{i+1}份成功")
                    time.sleep(3)
                else:
                    print(f"❌ PowerPoint Win32API打印第{i+1}份失败，返回码: {result}")
            
            return True, f"PowerPoint Win32API打印完成 ({copies}份)"
        except Exception as e:
            print(f"PowerPoint Win32API打印异常: {e}")
        
        # 方案3: 临时转PDF打印（最可靠的备用方案）
        print("🔸 尝试临时PDF转换打印...")
        try:
            # 先尝试用LibreOffice转换（如果有的话）
            libreoffice_paths = [
                r"C:\Program Files\LibreOffice\program\soffice.exe",
                r"C:\Program Files (x86)\LibreOffice\program\soffice.exe"
            ]
            
            for lo_path in libreoffice_paths:
                if os.path.exists(lo_path):
                    print(f"✅ 找到LibreOffice: {lo_path}")
                    temp_dir = tempfile.gettempdir()
                    
                    for i in range(copies):
                        temp_pdf = os.path.join(temp_dir, f"ppt_temp_{i}_{int(time.time())}.pdf")
                        
                        # LibreOffice转换PDF
                        convert_cmd = [lo_path, '--headless', '--convert-to', 'pdf', '--outdir', temp_dir, abs_filepath]
                        convert_result = subprocess.run(convert_cmd, capture_output=True, 
                                                     creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)
                        
                        if convert_result.returncode == 0:
                            # 查找生成的PDF文件
                            base_name = os.path.splitext(os.path.basename(abs_filepath))[0]
                            generated_pdf = os.path.join(temp_dir, f"{base_name}.pdf")
                            
                            if os.path.exists(generated_pdf):
                                # 重命名为我们的临时文件名
                                os.rename(generated_pdf, temp_pdf)
                                
                                # 打印PDF
                                print_result = win32api.ShellExecute(0, 'printto', temp_pdf, f'"{printer_name}"', None, 0)
                                
                                # 清理临时文件
                                time.sleep(2)
                                try:
                                    os.remove(temp_pdf)
                                except:
                                    pass
                                
                                if print_result > 32:
                                    print(f"✅ PowerPoint PDF转换打印第{i+1}份成功")
                                else:
                                    print(f"❌ PowerPoint PDF转换打印第{i+1}份失败")
                        
                        time.sleep(1)
                    
                    return True, f"PowerPoint PDF转换打印完成 ({copies}份)"
            
            print("⚠️ 未找到LibreOffice，无法进行PDF转换")
            
        except Exception as e:
            print(f"PowerPoint PDF转换打印异常: {e}")
        
        print("❌ PowerPoint所有直接打印方法都失败")
        return False, "PowerPoint直接打印失败：所有方法都无法成功"
        
    except Exception as e:
        print(f"PowerPoint直接打印函数异常: {e}")
        return False, f"PowerPoint直接打印异常: {str(e)}"


def print_office_com(filepath, printer_name, copies, file_ext):
    """强化Office COM打印 - 支持Microsoft Office和WPS Office"""
    try:
        abs_filepath = os.path.abspath(filepath)
        print(f"🔧 强化Office COM打印: {abs_filepath}")
        
        if file_ext in ['.doc', '.docx']:
            # Word文档 - 优先Microsoft Word，回退WPS Writer
            print("📝 强化Word COM打印...")
            
            # 方案1: Microsoft Word
            print("🔸 尝试Microsoft Word...")
            ps_script_word = f'''
try {{
    $ErrorActionPreference = "Stop"
    
    # 创建Microsoft Word COM对象
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = $false
    Write-Host "Microsoft Word COM创建成功"
    
    # 打开文档
    $doc = $word.Documents.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}")
    Write-Host "Word文档打开成功"
    
    # 设置打印机
    try {{
        $word.ActivePrinter = "{printer_name}"
        Write-Host "Word打印机设置成功: {printer_name}"
    }} catch {{
        Write-Host "Word无法设置指定打印机，使用默认"
    }}
    
    # 执行打印 - 使用更可靠的参数
    Write-Host "开始Word打印 {copies} 份..."
    for ($i = 1; $i -le {copies}; $i++) {{
        try {{
            # PrintOut(Background, Append, Range, OutputFileName, From, To, Item, Copies, Pages, PageType, PrintToFile, Collate, ActivePrinterMacGX, ManualDuplexPrint, PrintZoomColumn, PrintZoomRow, PrintZoomPaperWidth, PrintZoomPaperHeight)
            $doc.PrintOut([ref]$false, [ref]$false, [ref]0, [ref]"", [ref]1, [ref]($doc.Range().End), [ref]7, [ref]1)
            Write-Host "Word打印第${{i}}份完成"
            Start-Sleep -Seconds 2
        }} catch {{
            Write-Host "Word打印第${{i}}份失败: $_"
        }}
    }}
    
    $doc.Close([ref]$false)
    $word.Quit()
    
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($doc) | Out-Null
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
    
    Write-Output "Microsoft Word打印成功"
}} catch {{
    Write-Host "Microsoft Word打印失败: $_"
    if ($word) {{
        try {{ $word.Quit() }} catch {{}}
    }}
    exit 1
}}
'''
            
            # 尝试Microsoft Word
            try:
                result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_word],
                                      capture_output=True, text=True, timeout=60,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode == 0:
                    print("✅ Microsoft Word COM打印成功")
                    return True, f"Microsoft Word COM打印完成 ({copies}份)"
            except Exception as e:
                print(f"Microsoft Word COM异常: {e}")
            
            # 方案2: WPS Writer
            print("🔸 尝试WPS Writer...")
            ps_script_wps_writer = f'''
try {{
    $ErrorActionPreference = "Stop"
    
    # 创建WPS Writer COM对象
    $wps = New-Object -ComObject wps.application
    $wps.Visible = $false
    Write-Host "WPS Writer COM创建成功"
    
    # 打开文档
    $doc = $wps.Documents.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}")
    Write-Host "WPS Writer文档打开成功"
    
    # 设置打印机
    try {{
        $wps.ActivePrinter = "{printer_name}"
        Write-Host "WPS Writer打印机设置成功"
    }} catch {{
        Write-Host "WPS Writer无法设置指定打印机，使用默认"
    }}
    
    # 执行打印
    for ($i = 1; $i -le {copies}; $i++) {{
        try {{
            $doc.PrintOut()
            Write-Host "WPS Writer打印第${{i}}份完成"
            Start-Sleep -Seconds 2
        }} catch {{
            Write-Host "WPS Writer打印第${{i}}份失败: $_"
        }}
    }}
    
    $doc.Close([ref]$false)
    $wps.Quit()
    Write-Output "WPS Writer打印成功"
}} catch {{
    Write-Host "WPS Writer打印失败: $_"
    if ($wps) {{
        try {{ $wps.Quit() }} catch {{}}
    }}
    exit 1
}}
'''
            
            try:
                result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_wps_writer],
                                      capture_output=True, text=True, timeout=45,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode == 0:
                    print("✅ WPS Writer COM打印成功")
                    return True, f"WPS Writer COM打印完成 ({copies}份)"
            except Exception as e:
                print(f"WPS Writer COM异常: {e}")
            
            print("❌ Word文档COM打印失败")
            return False, "Word COM对象均不可用"
        elif file_ext in ['.xls', '.xlsx']:
            # Excel文档 - 优先Microsoft Excel，回退WPS Spreadsheets
            print("📊 强化Excel COM打印...")
            
            # 方案1: Microsoft Excel
            print("🔸 尝试Microsoft Excel...")
            ps_script_excel = f'''
try {{
    $ErrorActionPreference = "Stop"
    
    # 创建Microsoft Excel COM对象
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    Write-Host "Microsoft Excel COM创建成功"
    
    # 打开工作簿
    $workbook = $excel.Workbooks.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}")
    Write-Host "Excel工作簿打开成功"
    
    # 设置打印机
    try {{
        $excel.ActivePrinter = "{printer_name}"
        Write-Host "Excel打印机设置成功: {printer_name}"
    }} catch {{
        Write-Host "Excel无法设置指定打印机，使用默认"
    }}
    
    # 执行打印 - 使用更精确的参数
    Write-Host "开始Excel打印 {copies} 份..."
    for ($i = 1; $i -le {copies}; $i++) {{
        try {{
            # PrintOut(From, To, Copies, Preview, ActivePrinter, PrintToFile, Collate, PrToFileName)
            $workbook.PrintOut([Type]::Missing, [Type]::Missing, 1, [Type]::Missing, [Type]::Missing, [Type]::Missing, [Type]::Missing, [Type]::Missing)
            Write-Host "Excel打印第${{i}}份完成"
            Start-Sleep -Seconds 2
        }} catch {{
            Write-Host "Excel打印第${{i}}份失败: $_"
        }}
    }}
    
    $workbook.Close([ref]$false)
    $excel.Quit()
    
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($workbook) | Out-Null
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
    [System.GC]::Collect()
    [System.GC]::WaitForPendingFinalizers()
    
    Write-Output "Microsoft Excel打印成功"
}} catch {{
    Write-Host "Microsoft Excel打印失败: $_"
    if ($excel) {{
        try {{ $excel.Quit() }} catch {{}}
    }}
    exit 1
}}
'''
            
            # 尝试Microsoft Excel
            try:
                result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_excel],
                                      capture_output=True, text=True, timeout=60,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode == 0:
                    print("✅ Microsoft Excel COM打印成功")
                    return True, f"Microsoft Excel COM打印完成 ({copies}份)"
            except Exception as e:
                print(f"Microsoft Excel COM异常: {e}")
            
            # 方案2: WPS Spreadsheets
            print("🔸 尝试WPS Spreadsheets...")
            ps_script_wps_excel = f'''
try {{
    $ErrorActionPreference = "Stop"
    
    # 创建WPS Spreadsheets COM对象
    $et = New-Object -ComObject et.application
    $et.Visible = $false
    Write-Host "WPS Spreadsheets COM创建成功"
    
    # 打开工作簿
    $workbook = $et.Workbooks.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}")
    Write-Host "WPS Spreadsheets工作簿打开成功"
    
    # 设置打印机
    try {{
        $et.ActivePrinter = "{printer_name}"
        Write-Host "WPS Spreadsheets打印机设置成功"
    }} catch {{
        Write-Host "WPS Spreadsheets无法设置指定打印机，使用默认"
    }}
    
    # 执行打印
    for ($i = 1; $i -le {copies}; $i++) {{
        try {{
            $workbook.PrintOut()
            Write-Host "WPS Spreadsheets打印第${{i}}份完成"
            Start-Sleep -Seconds 2
        }} catch {{
            Write-Host "WPS Spreadsheets打印第${{i}}份失败: $_"
        }}
    }}
    
    $workbook.Close([ref]$false)
    $et.Quit()
    Write-Output "WPS Spreadsheets打印成功"
}} catch {{
    Write-Host "WPS Spreadsheets打印失败: $_"
    if ($et) {{
        try {{ $et.Quit() }} catch {{}}
    }}
    exit 1
}}
'''
            
            try:
                result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_wps_excel],
                                      capture_output=True, text=True, timeout=45,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode == 0:
                    print("✅ WPS Spreadsheets COM打印成功")
                    return True, f"WPS Spreadsheets COM打印完成 ({copies}份)"
            except Exception as e:
                print(f"WPS Spreadsheets COM异常: {e}")
            
            print("❌ Excel文档COM打印失败")
            return False, "Excel COM对象均不可用"
        elif file_ext in ['.ppt', '.pptx']:
            # PowerPoint文档 - 优先Microsoft PowerPoint，回退WPS Presentation
            print("📽️ 强化PowerPoint COM打印...")
            
            # 方案1: Microsoft PowerPoint - 修复权限版本
            print("🔸 尝试Microsoft PowerPoint...")
            ps_script_ppt = f'''
try {{
    $ErrorActionPreference = "Stop"
    
    # 创建Microsoft PowerPoint COM对象，增加权限处理
    $ppt = New-Object -ComObject PowerPoint.Application
    $ppt.Visible = $false
    $ppt.DisplayAlerts = 0  # 禁用所有警告
    Start-Sleep -Seconds 1
    Write-Host "Microsoft PowerPoint COM创建成功"
    
    # 打开演示文稿 - 简化参数
    $presentation = $ppt.Presentations.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}")
    Write-Host "PowerPoint演示文稿打开成功"
    
    # 设置打印机
    try {{
        $ppt.ActivePrinter = "{printer_name}"
        Write-Host "PowerPoint打印机设置成功: {printer_name}"
    }} catch {{
        Write-Host "PowerPoint无法设置指定打印机，使用默认"
    }}
    
    # 执行打印 - 先尝试PDF转换方案（更可靠）
    Write-Host "开始PowerPoint打印 {copies} 份..."
    for ($i = 1; $i -le {copies}; $i++) {{
        $success = $false
        
        # 优先使用PDF转换方案（更稳定）
        try {{
            Write-Host "尝试PowerPoint PDF转换打印第${{i}}份..."
            $tempPdf = "$env:TEMP\\ppt_print_${{i}}.pdf"
            # 导出为PDF
            $presentation.SaveAs($tempPdf, 32)  # 32 = ppSaveAsPDF
            Write-Host "PDF导出成功: $tempPdf"
            
            # 打印PDF
            # 使用正确的PrintTo动词指定打印机
            Start-Process -FilePath $tempPdf -Verb PrintTo -ArgumentList "{printer_name}" -WindowStyle Hidden -Wait
            Start-Sleep -Seconds 2
            
            # 清理临时文件
            if (Test-Path $tempPdf) {{
                Remove-Item $tempPdf -Force -ErrorAction SilentlyContinue
            }}
            
            Write-Host "PowerPoint第${{i}}份PDF转换打印成功"
            $success = $true
        }} catch {{
            Write-Host "PowerPoint PDF转换第${{i}}份失败: $_"
        }}
        
        # 如果PDF方案失败，尝试直接打印
        if (-not $success) {{
            try {{
                Write-Host "尝试PowerPoint直接打印第${{i}}份..."
                $presentation.PrintOut()
                Write-Host "PowerPoint直接打印第${{i}}份成功"
                Start-Sleep -Seconds 3
            }} catch {{
                Write-Host "PowerPoint直接打印第${{i}}份也失败: $_"
                throw "所有PowerPoint打印方法都失败了"
            }}
        }}
    }}
    
    $presentation.Close()
    $ppt.Quit()
    
    # 清理COM对象
    try {{
        [System.Runtime.Interopservices.Marshal]::ReleaseComObject($presentation) | Out-Null
        [System.Runtime.Interopservices.Marshal]::ReleaseComObject($ppt) | Out-Null
        [System.GC]::Collect()
        [System.GC]::WaitForPendingFinalizers()
    }} catch {{
        # 忽略清理错误
    }}
    
    Write-Output "Microsoft PowerPoint打印成功"
}} catch {{
    Write-Host "Microsoft PowerPoint打印失败: $_"
    if ($ppt) {{
        try {{
            if ($presentation) {{ $presentation.Close() }}
            $ppt.Quit()
        }} catch {{}}
    }}
    exit 1
}}
'''
            
            # 尝试Microsoft PowerPoint
            try:
                result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_ppt],
                                      capture_output=True, text=True, timeout=90,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode == 0:
                    print("✅ Microsoft PowerPoint COM打印成功")
                    return True, f"Microsoft PowerPoint COM打印完成 ({copies}份)"
            except Exception as e:
                print(f"Microsoft PowerPoint COM异常: {e}")
            
            # 方案2: WPS Presentation
            print("🔸 尝试WPS Presentation...")
            ps_script_wps_ppt = f'''
try {{
    $ErrorActionPreference = "Stop"
    
    # 创建WPS Presentation COM对象
    $wpp = New-Object -ComObject wpp.application
    $wpp.Visible = $false
    Write-Host "WPS Presentation COM创建成功"
    
    # 打开演示文稿
    $presentation = $wpp.Presentations.Open("{abs_filepath.replace(chr(92), chr(92)+chr(92))}")
    Write-Host "WPS Presentation文档打开成功"
    
    # 设置打印机
    try {{
        $wpp.ActivePrinter = "{printer_name}"
        Write-Host "WPS Presentation打印机设置成功"
    }} catch {{
        Write-Host "WPS Presentation无法设置指定打印机，使用默认"
    }}
    
    # 执行打印
    for ($i = 1; $i -le {copies}; $i++) {{
        try {{
            $presentation.PrintOut()
            Write-Host "WPS Presentation打印第${{i}}份完成"
            Start-Sleep -Seconds 3
        }} catch {{
            Write-Host "WPS Presentation直接打印第${{i}}份失败，尝试PDF转换: $_"
            try {{
                $tempPdf = "$env:TEMP\\wps_ppt_temp_${{i}}.pdf"
                $presentation.ExportAsFixedFormat($tempPdf, 2)  # 2=PDF格式
                # 使用正确的PrintTo动词指定打印机
                Start-Process -FilePath $tempPdf -Verb PrintTo -ArgumentList "{printer_name}" -WindowStyle Hidden -Wait
                Start-Sleep -Seconds 2
                Remove-Item $tempPdf -Force -ErrorAction SilentlyContinue
                Write-Host "WPS Presentation第${{i}}份PDF转换打印成功"
            }} catch {{
                Write-Host "WPS Presentation第${{i}}份PDF转换失败: $_"
            }}
        }}
    }}
    
    $presentation.Close()
    $wpp.Quit()
    Write-Output "WPS Presentation打印成功"
}} catch {{
    Write-Host "WPS Presentation打印失败: $_"
    if ($wpp) {{
        try {{ $wpp.Quit() }} catch {{}}
    }}
    exit 1
}}
'''
            
            try:
                result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script_wps_ppt],
                                      capture_output=True, text=True, timeout=75,
                                      creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode == 0:
                    print("✅ WPS Presentation COM打印成功")
                    return True, f"WPS Presentation COM打印完成 ({copies}份)"
            except Exception as e:
                print(f"WPS Presentation COM异常: {e}")
            
            print("❌ PowerPoint文档COM打印失败")
            return False, f"""PowerPoint COM打印失败详情：

已尝试的COM方案：
1. Microsoft PowerPoint COM (包含PDF转换备用)
2. WPS Presentation COM (包含PDF转换备用)

可能原因：
- PowerPoint/WPS未正确安装或注册
- COM对象权限不足
- 文档格式损坏或不兼容
- 打印机驱动问题

建议解决方案：
1. 手动打开 {os.path.basename(filepath)} 测试是否正常
2. 尝试"打印到PDF"测试COM功能
3. 重新注册Office COM: regsvr32 /i pptcore.dll
4. 以管理员权限运行打印服务"""
        else:
            print("❌ 不支持的Office文档类型")
            return print_file_silent_fallback(filepath, printer_name, copies)
        
    except Exception as e:
        print(f"❌ Office COM打印整体异常: {e}")
        return False, f"Office COM异常: {str(e)}"

def print_html_silent(filepath, printer_name, copies=1):
    """专门用于HTML文件的静默打印"""
    try:
        # 方案1: 使用Internet Explorer的静默打印
        for i in range(copies):
            cmd = [
                'rundll32.exe', 
                'mshtml.dll,PrintHTML', 
                filepath
            ]
            subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
        return True, f"HTML静默打印已发送到 {printer_name} ({copies}份)"
        
    except Exception as e1:
        try:
            # 方案2: 使用PowerShell和Internet Explorer COM对象
            ps_script = f'''
try {{
    $ie = New-Object -ComObject InternetExplorer.Application
    $ie.Visible = $false
    $ie.Navigate("file:///{filepath.replace(chr(92), '/')}")
    while ($ie.Busy) {{ Start-Sleep -Milliseconds 100 }}
    for ($i = 1; $i -le {copies}; $i++) {{
        $ie.ExecWB(6, 2)  # 静默打印
    }}
    $ie.Quit()
    Write-Host "HTML打印完成"
}} catch {{
    Write-Host "HTML打印失败： $_"
}}
'''
            subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script],
                          creationflags=subprocess.CREATE_NO_WINDOW)
            return True, f"HTML PowerShell静默打印已执行 ({copies}份)"
            
        except Exception as e2:
            # 备用方案
            return print_file_silent_fallback(filepath, printer_name, copies)

def get_printer_capabilities(printer_name):
    """获取指定打印机的功能参数（原始返回）
    返回结构:
    {
        'duplex_support': bool,
        'color_support': bool,
        'papers': [{'id': int, 'name': str}],
        'resolutions': ['600x600', ...],
        'printer_status': str,
        'driver_name': str,
        'port_name': str
    }
    """
    try:
        print(f"正在获取打印机 '{printer_name}' 的实际参数...")
        
        # 检查打印机名称是否有效
        if not printer_name or printer_name.strip() == "" or printer_name == "未检测到可用打印机":
            print("打印机名称无效")
            return {
                'duplex_support': False,
                'color_support': False,
                'paper_sizes': ['A4'],
                'quality_levels': ['normal'],
                'printer_status': '离线或不可用',
                'driver_name': '未知'
            }
        
        # 尝试打开打印机并获取其属性
        printer_handle = win32print.OpenPrinter(printer_name)
        
        try:
            # 获取打印机信息
            printer_info = win32print.GetPrinter(printer_handle, 2)
            driver_name = printer_info.get('pDriverName', '未知')
            port_name = printer_info.get('pPortName', '未知')
            status = printer_info.get('Status', 0)
            
            print(f"打印机驱动: {driver_name}")
            print(f"打印机端口: {port_name}")
            print(f"打印机状态码: {status}")
            
            # 解析打印机状态
            printer_status = '在线'
            if status != 0:
                status_descriptions = {
                    0x00000001: '暂停',
                    0x00000002: '错误',
                    0x00000004: '正在删除',
                    0x00000008: '缺纸',
                    0x00000010: '缺纸',
                    0x00000020: '手动送纸',
                    0x00000040: '纸张故障',
                    0x00000080: '离线',
                    0x00000100: 'I/O 活动',
                    0x00000200: '忙',
                    0x00000400: '正在打印',
                    0x00000800: '输出槽满',
                    0x00001000: '不可用',
                    0x00002000: '等待',
                    0x00004000: '正在处理',
                    0x00008000: '正在初始化',
                    0x00010000: '正在预热',
                    0x00020000: '碳粉不足',
                    0x00040000: '没有碳粉',
                    0x00080000: '页面错误',
                    0x00100000: '用户干预',
                    0x00200000: '内存不足',
                    0x00400000: '门打开'
                }
                # 找到最符合的状态描述
                for status_bit, description in status_descriptions.items():
                    if status & status_bit:
                        printer_status = description
                        break
                else:
                    printer_status = f'未知状态 ({status})'
            
            # 获取设备功能，使用自定义的常量
            duplex_support = False
            color_support = False
            papers = []  # [{'id': int, 'name': str}]
            resolutions_list = []  # ['600x600']
            
            try:
                # 检查双面打印支持
                try:
                    duplex_caps = win32print.DeviceCapabilities(printer_name, port_name, DC_DUPLEX, None)
                    # 修复：双面打印支持应该检查 > 0，不只是 == 1
                    # duplex_caps 的含义：
                    # 0 = 不支持双面打印
                    # 1 = 支持双面打印 (仅长边翻转)
                    # 2 = 支持双面打印 (仅短边翻转) 
                    # 3 = 支持双面打印 (长边和短边都支持)
                    duplex_support = duplex_caps > 0
                    duplex_modes = []
                    if duplex_caps >= 1:
                        duplex_modes.append("long_edge")  # 长边翻转
                    if duplex_caps >= 2:
                        duplex_modes.append("short_edge")  # 短边翻转
                    
                    print(f"双面打印支持: {duplex_support} (DeviceCapabilities返回: {duplex_caps})")
                    if duplex_modes:
                        print(f"支持的双面模式: {', '.join(duplex_modes)}")
                except Exception as e:
                    print(f"检查双面打印支持失败: {e}")
                    duplex_support = False
                    duplex_modes = []
                
                # 检查颜色支持
                try:
                    color_caps = win32print.DeviceCapabilities(printer_name, port_name, DC_COLORDEVICE, None)
                    color_support = color_caps == 1
                    print(f"颜色打印支持: {color_support} (DeviceCapabilities返回: {color_caps})")
                except Exception as e:
                    print(f"检查颜色支持失败: {e}")
                    color_support = False
                
                # 获取支持的纸张（ID+名称）
                try:
                    paper_ids = win32print.DeviceCapabilities(printer_name, port_name, DC_PAPERS, None)
                    paper_names = win32print.DeviceCapabilities(printer_name, port_name, DC_PAPERNAMES, None)
                    if paper_ids and paper_names:
                        # DC_PAPERNAMES 通常返回每个名称固定长度的字节/字符串数组
                        # pywin32 会解码为字符串元组，名称末尾可能含有\x00
                        count = min(len(paper_ids), len(paper_names))
                        for i in range(count):
                            pid = paper_ids[i]
                            pname = paper_names[i]
                            if isinstance(pname, bytes):
                                try:
                                    pname = pname.decode('mbcs', errors='ignore')
                                except Exception:
                                    pname = str(pname)
                            pname = pname.replace('\x00', '').strip()
                            if pname:
                                papers.append({'id': int(pid), 'name': pname})
                        print(f"纸张(原始): {papers[:8]}{' ...' if len(papers)>8 else ''}")
                    else:
                        print("未获取到纸张列表")
                except Exception as e:
                    print(f"获取纸张列表失败: {e}")
                
                # 获取打印分辨率（原始DPI列表）
                try:
                    resolutions = win32print.DeviceCapabilities(printer_name, port_name, DC_ENUMRESOLUTIONS, None)
                    if resolutions:
                        for res in resolutions:
                            # pywin32 分辨率项通常为 dict 或 tuple，包含 xdpi/ydpi
                            if isinstance(res, dict):
                                xdpi = res.get('xdpi') or res.get('X') or 0
                                ydpi = res.get('ydpi') or res.get('Y') or 0
                            elif isinstance(res, (tuple, list)) and len(res) >= 2:
                                xdpi, ydpi = res[0], res[1]
                            else:
                                continue
                            if xdpi and ydpi:
                                resolutions_list.append(f"{xdpi}x{ydpi}")
                        print(f"分辨率(原始): {resolutions_list}")
                    else:
                        print("未获取到分辨率列表")
                except Exception as e:
                    print(f"获取分辨率失败: {e}")
                
            except Exception as e:
                print(f"获取设备功能时出错: {e}")
            
            capabilities = {
                'duplex_support': duplex_support,
                'duplex_modes': duplex_modes if 'duplex_modes' in locals() else [],
                'color_support': color_support,
                'papers': papers,
                'resolutions': resolutions_list,
                'printer_status': printer_status,
                'driver_name': driver_name,
                'port_name': port_name
            }
            
            print(f"最终获取的打印机参数: {capabilities}")
            return capabilities
            
        finally:
            win32print.ClosePrinter(printer_handle)
            
    except Exception as e:
        print(f"无法访问打印机 '{printer_name}': {e}")
        # 返回默认功能，表示打印机不可用
        return {
            'duplex_support': False,
            'duplex_modes': [],
            'color_support': False,
            'papers': [],
            'resolutions': [],
            'printer_status': '离线或不可用',
            'driver_name': '未知',
            'port_name': ''
        }
 
def get_logs():
    if not os.path.exists(LOG_FILE):
        return []
    with open(LOG_FILE, 'r', encoding='utf-8') as f:
        return f.readlines()[-10:][::-1]

def clean_old_logs():
    """清理旧的打印日志，保留最近的记录"""
    try:
        if not os.path.exists(LOG_FILE):
            return
            
        # 检查日志文件大小
        file_size = os.path.getsize(LOG_FILE)
        max_size = 5 * 1024 * 1024  # 5MB限制
        
        if file_size > max_size:
            print(f"📋 日志文件过大({file_size/1024/1024:.1f}MB)，开始清理...")
            
            # 读取所有日志
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            # 保留最近1000条记录
            keep_lines = 1000
            if len(lines) > keep_lines:
                # 保留最新的记录
                new_lines = lines[-keep_lines:]
                
                # 写回文件
                with open(LOG_FILE, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                
                removed_count = len(lines) - keep_lines
                print(f"✅ 日志清理完成，删除了 {removed_count} 条旧记录，保留最新 {keep_lines} 条")
    
    except Exception as e:
        print(f"⚠️ 日志清理失败: {e}")

def clean_old_logs_by_date():
    """按日期清理日志，删除7天前的记录"""
    try:
        if not os.path.exists(LOG_FILE):
            return
            
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=7)  # 7天前
        
        # 读取日志并过滤
        new_lines = []
        removed_count = 0
        
        with open(LOG_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    # 尝试解析日志中的时间戳
                    if line.strip():
                        # 假设日志格式：2025-10-03 18:42:32 客户端: ...
                        date_str = line[:19]  # 提取前19个字符的日期时间
                        log_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                        
                        if log_date >= cutoff_date:
                            new_lines.append(line)
                        else:
                            removed_count += 1
                except:
                    # 如果解析失败，保留这行（可能是格式异常的日志）
                    new_lines.append(line)
        
        if removed_count > 0:
            # 写回文件
            with open(LOG_FILE, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            
            print(f"📋 按日期清理日志完成，删除了 {removed_count} 条7天前的记录")
    
    except Exception as e:
        print(f"⚠️ 按日期清理日志失败: {e}")

def periodic_log_cleanup():
    """定期日志清理任务"""
    import time
    while True:
        try:
            # 每天检查一次日志大小
            time.sleep(86400)  # 24小时
            
            from datetime import datetime
            current_hour = datetime.now().hour
            
                 # 下午3点执行清理任务
            if current_hour == 15:
                print("🕒 执行定时日志清理...")
                # 先按大小清理
                clean_old_logs()
                # 再按日期清理
                clean_old_logs_by_date()
            else:
                # 如果不是下午3点，等到下午3点再执行
                import datetime as dt
                now = dt.datetime.now()
                target_time = now.replace(hour=15, minute=0, second=0, microsecond=0)
                if now.hour >= 15:
                    target_time += dt.timedelta(days=1)  # 明天下午3点
                
                sleep_seconds = (target_time - now).total_seconds()
                print(f"📋 日志清理将在 {target_time.strftime('%Y-%m-%d %H:%M')} 执行")
                time.sleep(sleep_seconds)
           
        except Exception as e:
            print(f"⚠️ 定期日志清理异常: {e}")
            time.sleep(3600)  # 出错后1小时再试

@app.route('/health')
def health_check():
    """健康检查端点"""
    try:
        # 更新服务管理器的健康检查状态
        service_manager.update_health_check()
        
        # 计算正确的运行时间
        uptime = 0
        if hasattr(service_manager, 'start_time') and service_manager.start_time:
            uptime = time.time() - service_manager.start_time
        
        # 返回基本的服务状态信息
        return jsonify({
            'status': 'healthy',
            'timestamp': time.time(),
            'service_running': service_manager.service_running,
            'uptime': uptime
        }), 200
        
    except Exception as e:
        return jsonify({
            'status': 'unhealthy',
            'error': str(e),
            'timestamp': time.time()
        }), 500

@app.route('/api/printer_info')
def get_printer_info_api():
    """API端点：获取指定打印机的信息"""
    try:
        printer_name = request.args.get('printer')
        if not printer_name:
            return jsonify({'success': False, 'error': '未指定打印机名称'})
        
        capabilities = get_printer_capabilities(printer_name)
        return jsonify({
            'success': True,
            'capabilities': capabilities
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/delete_file', methods=['POST'])
def delete_file_api():
    """API端点：删除队列中的单个文件"""
    try:
        print(f"🔍 收到删除文件请求")
        print(f"   Content-Type: {request.content_type}")
        print(f"   Headers: {dict(request.headers)}")
        print(f"   Method: {request.method}")
        
        # 尝试解析JSON数据
        try:
            data = request.get_json()
            print(f"   解析的JSON数据: {data}")
        except Exception as json_error:
            print(f"❌ JSON解析错误: {json_error}")
            return jsonify({'success': False, 'error': f'JSON解析错误: {str(json_error)}'})
        
        if not data or 'filename' not in data:
            print(f"❌ 请求数据无效: {data}")
            return jsonify({'success': False, 'error': '未提供文件名'})
        
        filename = data['filename']
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        print(f"准备删除文件: {filepath}")
        
        # 检查文件是否存在
        if not os.path.exists(filepath):
            print(f"文件不存在: {filepath}")
            return jsonify({'success': False, 'error': '文件不存在或已被删除'})
        
        # 尝试取消相关的打印任务（在删除文件之前）
        cancel_result = {'cancelled': [], 'skipped': [], 'total_found': 0}
        try:
            print(f"🔍 检查是否有相关的打印任务需要取消...")
            
            # 默认不取消正在打印的任务，除非用户显式要求
            force_cancel = request.get_json().get('force_cancel_active', False) if request.get_json() else False
            
            cancel_result = cancel_print_jobs_by_document(filename, cancel_active=force_cancel)
            
            cancelled_count = len(cancel_result['cancelled'])
            skipped_count = len(cancel_result['skipped'])
            
            if cancelled_count > 0:
                print(f"✅ 已取消 {cancelled_count} 个打印任务")
            if skipped_count > 0:
                print(f"⚠️ 跳过 {skipped_count} 个任务（正在打印或已完成）")
            if cancel_result['total_found'] == 0:
                print(f"📝 未找到相关的打印任务")
                
        except Exception as cancel_error:
            print(f"⚠️ 取消打印任务失败: {cancel_error}")
        
        # 删除文件
        os.remove(filepath)
        print(f"文件删除成功: {filepath}")
        
        # 记录删除日志
        try:
            client_ip = request.remote_addr or '未知IP'
            cancelled_count = len(cancel_result['cancelled'])
            cancelled_info = f", 取消了 {cancelled_count} 个打印任务" if cancelled_count > 0 else ""
            log_message = f"{datetime.now()} 客户端: {client_ip} 删除文件: {filename}{cancelled_info}"
            with open(LOG_FILE, 'a', encoding='utf-8') as f:
                f.write(log_message + "\n")
            print(f"日志记录成功: {log_message}")
        except Exception as log_error:
            print(f"日志记录失败: {log_error}")
            # 即使日志记录失败，也继续返回成功
        
        # 返回结果，包含详细的打印任务信息
        response_message = f'文件 {filename} 已删除'
        
        cancelled_count = len(cancel_result['cancelled'])
        skipped_count = len(cancel_result['skipped'])
        
        if cancelled_count > 0:
            response_message += f'，取消了 {cancelled_count} 个打印任务'
        if skipped_count > 0:
            response_message += f'，跳过了 {skipped_count} 个任务（正在执行或已完成）'
        
        return jsonify({
            'success': True,
            'message': response_message,
            'print_queue_result': {
                'cancelled_jobs': cancelled_count,
                'skipped_jobs': skipped_count,
                'total_found': cancel_result['total_found'],
                'cancelled_details': cancel_result['cancelled'],
                'skipped_details': cancel_result['skipped']
            }
        })
        
    except Exception as e:
        print(f"删除文件API发生异常: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({
            'success': False,
            'error': f'服务器错误: {str(e)}'
        })

@app.route('/api/delete_all_files', methods=['POST'])
def delete_all_files_api():
    """API端点：清空队列中的所有文件"""
    try:
        files = os.listdir(UPLOAD_FOLDER)
        deleted_count = 0
        
        # 首先尝试清空所有打印机队列
        cleared_jobs = 0
        try:
            print(f"🗑️ 正在清空所有打印机队列...")
            cleared_jobs = clear_all_print_queues()
            if cleared_jobs > 0:
                print(f"✅ 已清空 {cleared_jobs} 个打印任务")
            else:
                print(f"📝 打印队列为空或无法访问")
        except Exception as clear_error:
            print(f"⚠️ 清空打印队列失败: {clear_error}")
        
        # 然后删除所有文件
        for filename in files:
            try:
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)
                    deleted_count += 1
            except Exception as e:
                print(f"删除文件 {filename} 时出错: {e}")
        
        # 记录删除日志
        client_ip = request.remote_addr or '未知IP'
        queue_info = f", 清空了 {cleared_jobs} 个打印任务" if cleared_jobs > 0 else ""
        log_message = f"{datetime.now()} 客户端: {client_ip} 清空队列: 删除了 {deleted_count} 个文件{queue_info}"
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_message + "\n")
        
        # 构建响应消息
        response_message = f'已删除 {deleted_count} 个文件'
        if cleared_jobs > 0:
            response_message += f'，清空了 {cleared_jobs} 个打印任务'
        
        return jsonify({
            'success': True,
            'count': deleted_count,
            'cleared_jobs': cleared_jobs,
            'message': response_message
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/refresh_printers')
def refresh_printers_api():
    """API端点：刷新打印机列表"""
    try:
        # 刷新打印机列表
        success = refresh_printer_list()
        if success:
            default_printer = get_default_printer()
            return jsonify({
                'success': True,
                'printers': PRINTERS,
                'default_printer': default_printer,
                'message': f'已刷新，检测到 {len(PRINTERS)} 台物理打印机'
            })
        else:
            return jsonify({
                'success': False,
                'error': '刷新打印机列表失败'
            })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/print_queue', methods=['GET'])
def get_print_queue_api():
    """API端点：获取打印队列状态"""
    try:
        printer_name = request.args.get('printer')
        jobs = get_print_queue_jobs(printer_name)
        
        return jsonify({
            'success': True,
            'jobs': jobs,
            'count': len(jobs)
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/clear_print_queue', methods=['POST'])
def clear_print_queue_api():
    """API端点：清空打印队列"""
    try:
        data = request.get_json() or {}
        printer_name = data.get('printer')
        
        if printer_name:
            # 清空指定打印机的队列
            jobs = get_print_queue_jobs(printer_name)
            cleared_count = 0
            for job in jobs:
                try:
                    import win32print
                    printer_handle = win32print.OpenPrinter(printer_name)
                    win32print.SetJob(printer_handle, job['job_id'], 0, None, win32print.JOB_CONTROL_CANCEL)
                    win32print.ClosePrinter(printer_handle)
                    cleared_count += 1
                except Exception as e:
                    print(f"取消任务失败: {e}")
            
            message = f'已清空打印机 {printer_name} 的 {cleared_count} 个任务'
        else:
            # 清空所有打印机的队列
            cleared_count = clear_all_print_queues()
            message = f'已清空所有打印机的 {cleared_count} 个任务'
        
        # 记录日志
        client_ip = request.remote_addr or '未知IP'
        log_message = f"{datetime.now()} 客户端: {client_ip} 清空打印队列: {message}"
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_message + "\n")
        
        return jsonify({
            'success': True,
            'cleared_count': cleared_count,
            'message': message
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

# 系统修复工具API已移除，功能整合到托盘菜单中
 
def get_file_list():
    """获取上传文件夹中的文件列表（包含详细信息）"""
    file_list = []
    try:
        for filename in os.listdir(UPLOAD_FOLDER):
            filepath = os.path.join(UPLOAD_FOLDER, filename)
            if os.path.isfile(filepath):
                try:
                    # 获取文件信息
                    stat = os.stat(filepath)
                    file_size = stat.st_size
                    upload_time = datetime.fromtimestamp(stat.st_mtime)
                    
                    # 格式化文件大小
                    if file_size < 1024:
                        size_str = f"{file_size} B"
                    elif file_size < 1024 * 1024:
                        size_str = f"{file_size / 1024:.1f} KB"
                    else:
                        size_str = f"{file_size / (1024 * 1024):.1f} MB"
                    
                    # 获取文件扩展名
                    extension = os.path.splitext(filename)[1].lower().lstrip('.')
                    
                    file_info = {
                        'name': filename,
                        'size': file_size,
                        'size_str': size_str,
                        'upload_time': upload_time.strftime('%m-%d %H:%M'),
                        'extension': extension or 'unknown'
                    }
                    
                    file_list.append(file_info)
                except Exception as e:
                    print(f"获取文件 {filename} 信息时出错: {e}")
                    # 如果无法获取详细信息，至少保留文件名
                    file_list.append({
                        'name': filename,
                        'size': 0,
                        'size_str': 'Unknown',
                        'upload_time': 'Unknown',
                        'extension': 'unknown'
                    })
        
        # 按上传时间排序（最新的在前）
        file_list.sort(key=lambda x: x['upload_time'], reverse=True)
    except Exception as e:
        print(f"获取文件列表时出错: {e}")
    
    return file_list

@app.route('/', methods=['GET', 'POST'])
def upload_file():
    files = get_file_list()  # 使用新的文件列表函数
    logs = get_logs()
    
    # 环境状态检测已取消
    env_status = None
    
    # 获取第一个打印机的功能信息（用于前端显示）
    printer_caps = {}
    if PRINTERS:
        printer_caps = get_printer_capabilities(PRINTERS[0])
    else:
        # 如果没有打印机，提供默认功能信息
        printer_caps = {
            'duplex_support': False,
            'color_support': False,
            'paper_sizes': ['A4', 'A3', 'Letter'],
            'quality_levels': ['normal'],
            'printer_status': '无可用打印机',
            'driver_name': '未知'
        }
    
    if request.method == 'POST':
        # 处理打印请求
        try:
            # 获取客户端信息
            client_info = get_client_info()
            
            # 获取表单参数
            printer = request.form.get('printer')
            copies = int(request.form.get('copies', 1))
            duplex = int(request.form.get('duplex', 1))
            papersize = request.form.get('papersize', '9')  # 默认A4 ID
            quality = request.form.get('quality', '600x600')
            uploaded_files = request.files.getlist('file')
            
            print(f"📝 收到打印请求: 打印机={printer}, 份数={copies}, 文件数={len(uploaded_files)}")
            
            # 检查是否选择了文件
            if not uploaded_files or all(not f.filename for f in uploaded_files):
                flash("❌ 错误: 请选择要打印的文件！", "danger")
                return redirect(url_for('upload_file'))
            
            # 检查是否有可用的打印机
            if not printer or printer == "" or printer == "未检测到可用打印机":
                flash("❌ 错误: 未选择有效的打印机，请检查打印机连接后重试！", "danger")
                return redirect(url_for('upload_file'))
            
            # 检查是否选择了虚拟打印机
            if not is_physical_printer(printer):
                flash(f"⚠️ 警告: '{printer}' 是虚拟打印机，不会进行实际打印，只会生成文件!", "warning")
            
            # 处理上传的文件
            success_count = 0
            total_files = 0
            
            for f in uploaded_files:
                if f and f.filename and allowed_file(f.filename):
                    total_files += 1
                    
                    # 确保文件名唯一，避免覆盖
                    filename = f.filename
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    counter = 1
                    max_attempts = 100
                    
                    # 生成唯一文件名
                    original_filename = filename
                    while os.path.exists(filepath) and counter <= max_attempts:
                        name, ext = os.path.splitext(original_filename)
                        filename = f"{name}_{counter}{ext}"
                        filepath = os.path.join(UPLOAD_FOLDER, filename)
                        counter += 1
                        
                    if counter > max_attempts:
                        flash(f"❌ 文件 {original_filename} 名称冲突，请重命名后再上传！", "danger")
                        continue
                    
                    try:
                        # 保存文件到uploads文件夹
                        f.save(filepath)
                        
                        # 验证文件是否成功保存
                        if not os.path.exists(filepath) or os.path.getsize(filepath) == 0:
                            flash(f"❌ 文件 {filename} 保存失败，请重试！", "danger")
                            continue
                            
                        print(f"✅ 文件已保存: {filepath} (大小: {os.path.getsize(filepath)} 字节)")
                        
                        # 根据文件类型选择最佳的静默打印方案
                        file_ext = os.path.splitext(filepath)[1].lower()
                        
                        print(f"🔄 开始打印文件: {filename} -> {printer}")
                        
                        # 根据文件类型选择打印方法
                        success = False
                        message = "未知错误"
                        
                        if file_ext == '.pdf':
                            # PDF文件使用专门的静默打印方法
                            print(f"📄 使用PDF打印方法")
                            result = print_pdf_silent(filepath, printer, copies)
                        elif file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.gif']:
                            # 图片文件使用专门的静默打印方法
                            print(f"🖼️ 使用图片打印方法")
                            result = print_image_silent(filepath, printer, copies)
                        elif file_ext in ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
                            # Office文档使用专门的静默打印方法
                            print(f"📈 使用Office打印方法")
                            result = print_office_silent(filepath, printer, copies)
                        elif file_ext == '.txt':
                            # 文本文件使用专门的打印方法
                            print(f"📝 使用文本打印方法")
                            result = print_text_file_simple(filepath, printer, copies)
                        else:
                            # 其他文件使用通用静默打印方法
                            print(f"📁 使用通用打印方法")
                            result = print_file_with_settings(filepath, printer, copies, duplex, papersize, quality)
                        
                        # 统一处理返回结果
                        if result and len(result) >= 2:
                            success, message = result[0], result[1]
                        elif result and isinstance(result, tuple) and len(result) == 1:
                            success, message = result[0], "打印任务已发送"
                        elif result is True:
                            success, message = True, "打印任务已发送"
                        elif result is False:
                            success, message = False, "打印失败"
                        else:
                            success, message = False, f"未知错误: {result}"
                        
                        # 记录结果
                        if success:
                            success_count += 1
                            print(f"✅ 打印成功: {filename} -> {message}")
                            flash(f"✅ {filename} {message}", "success")
                            log_print(filename, printer, copies, duplex, papersize, quality, client_info)
                        else:
                            print(f"❌ 打印失败: {filename} -> {message}")
                            flash(f"❌ {filename} 打印失败: {message}", "danger")
                            log_print(f"{filename} 失败: {message}", printer, copies, duplex, papersize, quality, client_info)
                            
                    except Exception as e:
                        print(f"⚠️ 打印异常: {filename} -> {str(e)}")
                        error_msg = f"打印异常: {str(e)}"
                        flash(f"⚠️ {filename} {error_msg}", "danger")
                        log_print(f"{filename} {error_msg}", printer, copies, duplex, papersize, quality, client_info)
                        import traceback
                        traceback.print_exc()
                        
                elif f and f.filename:
                    flash(f"⚠️ 文件 {f.filename} 的格式不支持，已跳过", "warning")
            
            # 显示最终统计
            if total_files > 0:
                if success_count == total_files:
                    flash(f"🎉 所有文件({success_count}/{total_files})都已成功发送到打印机！", "success")
                elif success_count > 0:
                    flash(f"⚠️ 部分文件打印成功({success_count}/{total_files})，请检查失败的文件", "warning")
                else:
                    flash(f"❌ 所有文件打印都失败，请检查打印机状态和文件格式！", "danger")
            else:
                flash("❌ 未找到有效的文件，请检查文件格式是否支持！", "danger")
                
        except Exception as e:
            print(f"❌ POST请求处理异常: {str(e)}")
            flash(f"❌ 请求处理异常: {str(e)}", "danger")
            import traceback
            traceback.print_exc()
        
        return redirect(url_for('upload_file'))
    
    # 获取默认打印机
    default_printer = get_default_printer()
    
    # 获取端口配置信息
    current_port = getattr(app, 'current_port', 5000)
    config_port = get_config_port()
    port_from_config = (current_port == config_port)
    
    # 检测系统软件状态
    software_status = detect_system_software()
    
    return render_template_string(HTML, printers=PRINTERS, files=files, logs=logs, 
                                printer_caps=printer_caps, default_printer=default_printer,
                                env_status=env_status, current_port=current_port,
                                port_from_config=port_from_config, software_status=software_status)
 
@app.route('/preview/<filename>')
def preview_file(filename):
    fpath = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(fpath):
        return f'<div class="container mt-4"><div class="alert alert-danger"><h4>文件未找到</h4><p>文件 "{filename}" 不存在或已被删除！</p><p><a href="/" class="btn btn-primary">返回首页</a></p></div></div>', 404
    
    try:
        ext = filename.rsplit('.', 1)[1].lower() if '.' in filename else ''
        
        if ext in {'jpg', 'jpeg', 'png'}:
            return send_from_directory(UPLOAD_FOLDER, filename, mimetype=f'image/{ext}')
        elif ext == 'pdf':
            return send_from_directory(UPLOAD_FOLDER, filename, mimetype='application/pdf')
        elif ext == 'txt':
            try:
                with open(fpath, 'r', encoding='utf-8') as f:
                    content = f.read()
                return f'''
                <div class="container mt-4">
                    <div class="d-flex justify-content-between align-items-center mb-3">
                        <h4>文件预览: {filename}</h4>
                        <a href="/" class="btn btn-secondary">返回首页</a>
                    </div>
                    <div class="card">
                        <div class="card-body">
                            <pre style="white-space: pre-wrap; font-family: monospace;">{content}</pre>
                        </div>
                    </div>
                </div>
                '''
            except UnicodeDecodeError:
                try:
                    with open(fpath, 'r', encoding='gbk') as f:
                        content = f.read()
                    return f'''
                    <div class="container mt-4">
                        <div class="d-flex justify-content-between align-items-center mb-3">
                            <h4>文件预览: {filename}</h4>
                            <a href="/" class="btn btn-secondary">返回首页</a>
                        </div>
                        <div class="card">
                            <div class="card-body">
                                <pre style="white-space: pre-wrap; font-family: monospace;">{content}</pre>
                            </div>
                        </div>
                    </div>
                    '''
                except Exception as e:
                    return f'''
                    <div class="container mt-4">
                        <div class="alert alert-warning">
                            <h4>无法预览文件</h4>
                            <p>文件 "{filename}" 无法以文本格式预览，编码错误: {str(e)}</p>
                            <p><a href="/" class="btn btn-primary">返回首页</a></p>
                        </div>
                    </div>
                    '''
        else:
            # 对于其他文件类型，提供下载链接和基本信息
            file_size = os.path.getsize(fpath)
            if file_size < 1024:
                size_str = f"{file_size} B"
            elif file_size < 1024 * 1024:
                size_str = f"{file_size / 1024:.1f} KB"
            else:
                size_str = f"{file_size / (1024 * 1024):.1f} MB"
            
            return f'''
            <div class="container mt-4">
                <div class="d-flex justify-content-between align-items-center mb-3">
                    <h4>文件信息: {filename}</h4>
                    <a href="/" class="btn btn-secondary">返回首页</a>
                </div>
                <div class="card">
                    <div class="card-body">
                        <h5 class="card-title">📄 {filename}</h5>
                        <p class="card-text">
                            <strong>文件类型:</strong> {ext.upper() if ext else 'Unknown'}<br>
                            <strong>文件大小:</strong> {size_str}<br>
                            <strong>说明:</strong> 此文件类型不支持在线预览
                        </p>
                        <div class="btn-group">
                            <a href="/uploads/{filename}" class="btn btn-primary" download>下载文件</a>
                            <button onclick="history.back()" class="btn btn-outline-secondary">返回</button>
                        </div>
                    </div>
                </div>
            </div>
            '''
    except Exception as e:
        return f'''
        <div class="container mt-4">
            <div class="alert alert-danger">
                <h4>预览错误</h4>
                <p>预览文件 "{filename}" 时发生错误: {str(e)}</p>
                <p><a href="/" class="btn btn-primary">返回首页</a></p>
            </div>
        </div>
        ''', 500

# 添加直接下载路由
@app.route('/uploads/<filename>')
def download_file(filename):
    """提供文件下载"""
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)
 
 
def run_flask():
    # 开发环境使用 Flask 内置服务器
    port = getattr(app, 'current_port', 5000)
    try:
        print(f"🚀 正在启动Flask服务 (端口:{port})...")
        service_manager.mark_service_running()
        
        # 添加请求超时和连接管理
        app.run(
            host='0.0.0.0', 
            port=port, 
            use_reloader=False, 
            threaded=True,
            debug=False,
            request_handler=None
        )
    except OSError as e:
        service_manager.mark_service_stopped()
        if "Address already in use" in str(e):
            print(f"⚠️ 端口 {port} 已被占用，Flask服务启动失败")
        else:
            print(f"⚠️ Flask服务启动失败: {e}")
    except Exception as e:
        service_manager.mark_service_stopped()
        print(f"⚠️ Flask服务异常停止: {e}")
        # 记录异常后尝试重启
        time.sleep(5)
        if service_manager.service_running:  # 如果应该运行但异常停止，尝试重启
            print("🔄 尝试自动重启Flask服务...")
            run_flask()

def run_wsgi():
    # 生产环境推荐使用 waitress
    try:
        from waitress import serve
        port = getattr(app, 'current_port', 5000)
        print(f"🚀 正在启动WSGI服务 (端口:{port})...")
        service_manager.mark_service_running()
        
        # 使用waitress，更稳定的WSGI服务器
        serve(
            app, 
            host='0.0.0.0', 
            port=port, 
            threads=6,
            connection_limit=100,
            cleanup_interval=30,
            channel_timeout=120
        )
    except ImportError:
        print("Waitress未安装，使用Flask内置服务器")
        run_flask()
    except OSError as e:
        service_manager.mark_service_stopped()
        if "Address already in use" in str(e):
            print(f"⚠️ 端口 {port} 已被占用，WSGI服务启动失败")
        else:
            print(f"⚠️ WSGI服务启动失败: {e}")
    except Exception as e:
        service_manager.mark_service_stopped()
        print(f"⚠️ WSGI服务异常停止: {e}")
        # 记录异常后尝试重启
        time.sleep(5)
        if service_manager.service_running:  # 如果应该运行但异常停止，尝试重启
            print("🔄 尝试自动重启WSGI服务...")
            run_wsgi()
 
 
def on_quit(icon, item):
    print("🔄 正在退出程序...")
    
    try:
        # 1. 标记服务停止状态
        service_manager.mark_service_stopped()
        
        # 2. 清除任何重启标志
        service_manager.clear_restart()
        
        # 3. 尝试关闭Flask服务器
        print("📡 正在关闭Web服务...")
        try:
            if hasattr(app, 'shutdown'):
                app.shutdown()
        except Exception as e:
            print(f"关闭Flask服务时出错: {e}")
        
        # 4. 等待服务线程结束
        print("🧵 正在等待服务线程结束...")
        threads_to_wait = []
        
        if service_manager.flask_thread and service_manager.flask_thread.is_alive():
            threads_to_wait.append(("Flask服务", service_manager.flask_thread))
        
        if service_manager.cleaner_thread and service_manager.cleaner_thread.is_alive():
            threads_to_wait.append(("文件清理", service_manager.cleaner_thread))
            
        if service_manager.monitor_thread and service_manager.monitor_thread.is_alive():
            threads_to_wait.append(("服务监控", service_manager.monitor_thread))
        
        # 给重要线程更多时间优雅退出
        for thread_name, thread in threads_to_wait:
            try:
                print(f"  等待 {thread_name} 线程结束...")
                thread.join(timeout=2)  # 给每个线程2秒时间
                if thread.is_alive():
                    print(f"  ⚠️ {thread_name} 线程未能在2秒内退出")
                else:
                    print(f"  ✅ {thread_name} 线程已结束")
            except Exception as e:
                print(f"  ❌ 等待 {thread_name} 线程时出错: {e}")
        
        # 5. 检查剩余的活跃线程
        remaining_threads = [t for t in threading.enumerate() 
                           if t is not threading.current_thread() and not t.daemon]
        
        if remaining_threads:
            print(f"⚠️ 还有 {len(remaining_threads)} 个非守护线程仍在运行")
            for t in remaining_threads:
                thread_name = getattr(t, 'name', 'Unknown')
                print(f"  - {thread_name}")
        
        # 6. 停止托盘图标
        print("🖥️ 正在停止托盘图标...")
        icon.stop()
        
        # 7. 清理临时文件（可选）
        try:
            import tempfile
            temp_dir = tempfile.gettempdir()
            print(f"🧹 清理完成")
        except Exception as e:
            print(f"清理临时文件时出错: {e}")
            
        print("✅ 程序退出准备完成")
        
    except Exception as e:
        print(f"❌ 退出过程中出现错误: {e}")
    
    finally:
        # 8. 强制退出进程 
        print("🔚 强制退出程序")
        try:
            # 使用os._exit确保立即退出
            import os
            os._exit(0)
        except Exception:
            # 最后的备用方案
            import sys
            sys.exit(0)

def toggle_console_window(icon, item):
    """切换控制台窗口显示/隐藏"""
    global CONSOLE_WINDOW, CONSOLE_VISIBLE
    
    try:
        import ctypes
        
        if not CONSOLE_WINDOW:
            kernel32 = ctypes.windll.kernel32
            CONSOLE_WINDOW = kernel32.GetConsoleWindow()
        
        if CONSOLE_WINDOW:
            user32 = ctypes.windll.user32
            
            if CONSOLE_VISIBLE:
                # 隐藏控制台
                user32.ShowWindow(CONSOLE_WINDOW, 0)  # SW_HIDE
                CONSOLE_VISIBLE = False
                print("✅ 控制台窗口已隐藏")
            else:
                # 显示控制台
                user32.ShowWindow(CONSOLE_WINDOW, 1)  # SW_SHOWNORMAL
                user32.SetForegroundWindow(CONSOLE_WINDOW)  # 带到前台
                CONSOLE_VISIBLE = True
                print("✅ 控制台窗口已显示")
            
            # 刷新托盘菜单
            icon.menu = build_menu(icon)
        else:
            print("⚠️ 未找到控制台窗口")
            
    except Exception as e:
        print(f"❌ 控制台窗口操作失败: {e}")
 
def on_toggle_autostart(icon, item):
    current = get_autostart()
    set_autostart(not current)
    # 刷新菜单
    icon.menu = build_menu(icon)

def on_show_ip_config(icon, item):
    """通过浏览器打开主页，网络配置功能已集成在托盘菜单"""
    import webbrowser
    ip = get_local_ip()
    port = getattr(app, 'current_port', 5000)
    url = f"http://{ip}:{port}/"
    webbrowser.open(url)

def on_set_static_ip(icon, item):
    """快速设置建议的静态IP"""
    try:
        suggested_ip = suggest_static_ip()
        success, message = set_static_ip(suggested_ip)
        
        if success:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()  # 隐藏主窗口
            messagebox.showinfo("IP设置成功", f"已将IP设置为: {suggested_ip}\n{message}")
            root.destroy()
        else:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("IP设置失败", message)
            root.destroy()
    except Exception as e:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("错误", f"设置IP时发生错误: {str(e)}")
        root.destroy()

def on_enable_dhcp(icon, item):
    """启用DHCP"""
    try:
        success, message = set_dhcp()
        
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        
        if success:
            messagebox.showinfo("DHCP设置成功", message)
        else:
            messagebox.showerror("DHCP设置失败", message)
        
        root.destroy()
    except Exception as e:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("错误", f"启用DHCP时发生错误: {str(e)}")
        root.destroy()

def on_open_github(icon, item):
    """打开GitHub仓库页面"""
    import webbrowser
    webbrowser.open("https://github.com/a937750307/lan-printing")

def on_view_config(icon, item):
    """查看当前配置"""
    try:
        config = load_config()
        config_info = f"""当前配置信息：

端口设置: {config.get('port', 5000)} {'✅' if config.get('port') else '(默认)'}
配置文件: {CONFIG_FILE}

配置文件内容：
{json.dumps(config, ensure_ascii=False, indent=2) if config else '{}'}

说明：
• 端口设置保存后需要手动重新运行程序才能生效
• 配置文件保存在用户桌面目录  
• 可通过托盘菜单修改端口设置"""
        
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showinfo("配置信息", config_info)
        root.destroy()
    except Exception as e:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("错误", f"查看配置时发生错误: {str(e)}")
        root.destroy()

def on_reset_config(icon, item):
    """重置配置到默认值"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        root = tk.Tk()
        root.withdraw()
        
        result = messagebox.askyesno(
            "重置配置确认",
            "确定要重置所有配置到默认值吗？\n\n"
            "这将：\n"
            "• 将端口重置为 5000\n"
            "• 删除当前配置文件\n"
            "• 需要重启程序生效"
        )
        
        if result:
            try:
                if os.path.exists(CONFIG_FILE):
                    os.remove(CONFIG_FILE)
                    messagebox.showinfo("重置成功", "配置已重置，程序将重启以应用默认设置")
                    
                    # 重启程序
                    import subprocess
                    import sys
                    root.destroy()
                    icon.stop()
                    subprocess.Popen([sys.executable] + sys.argv)
                    sys.exit(0)
                else:
                    messagebox.showinfo("提示", "配置文件不存在，当前已是默认配置")
            except Exception as e:
                messagebox.showerror("错误", f"重置配置失败: {str(e)}")
        
        root.destroy()
    except Exception as e:
        pass

def on_change_port(icon, item):
    """更改服务端口"""
    import tkinter as tk
    from tkinter import messagebox, simpledialog
    
    try:
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        
        # 获取当前端口
        current_port = getattr(app, 'current_port', 5000)
        
        # 弹出输入对话框
        new_port = simpledialog.askinteger(
            "更改端口",
            f"当前端口: {current_port}\n请输入新的端口号 (1024-65535):",
            minvalue=1024,
            maxvalue=65535,
            initialvalue=current_port
        )
        
        if new_port and new_port != current_port:
            # 验证端口是否被占用
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            try:
                sock.bind(('localhost', new_port))
                sock.close()
                
                # 端口可用，提示用户重启服务
                result = messagebox.askyesno(
                    "端口更改确认",
                    f"将端口从 {current_port} 更改为 {new_port}\n\n"
                    f"⚠️ 注意：更改端口后需要手动重新运行程序才能生效\n"
                    f"程序将在保存配置后自动退出\n\n"
                    f"是否继续更改端口？"
                )
                
                if result:
                    # 保存新端口到配置文件
                    if save_port_config(new_port):
                        messagebox.showinfo(
                            "端口更改成功", 
                            f"端口已更改为: {new_port}\n"
                            f"新的访问地址: http://{get_local_ip()}:{new_port}\n"
                            f"配置已保存！\n\n"
                            f"⚠️ 请手动重新运行程序以应用新端口设置"
                        )
                    else:
                        messagebox.showwarning(
                            "端口更改", 
                            f"端口已更改为: {new_port}，但配置保存失败\n"
                            f"下次启动可能恢复默认端口\n\n"
                            f"⚠️ 请手动重新运行程序以应用新端口设置"
                        )
                    
                    # 不再尝试自动重启，直接退出程序
                    root.destroy()
                    
                    # 停止托盘图标，退出程序
                    icon.stop()
                    
            except socket.error:
                messagebox.showerror("端口错误", f"端口 {new_port} 已被占用，请选择其他端口")
                sock.close()
        
        root.destroy()
        
    except Exception as e:
        try:
            messagebox.showerror("错误", f"更改端口时发生错误: {str(e)}")
            root.destroy()
        except:
            pass

def on_clean_logs(icon, item):
    """手动清理日志"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        
        root = tk.Tk()
        root.withdraw()
        
        result = messagebox.askyesnocancel(
            "清理日志确认",
            "选择日志清理方式：\n\n"
            "是(Y) - 按大小清理（保留最新1000条）\n"
            "否(N) - 按日期清理（删除7天前的记录）\n"
            "取消 - 不清理"
        )
        
        if result is True:
            # 按大小清理
            clean_old_logs()
            messagebox.showinfo("清理完成", "已按大小清理日志，保留最新1000条记录")
        elif result is False:
            # 按日期清理
            clean_old_logs_by_date()
            messagebox.showinfo("清理完成", "已删除7天前的日志记录")
        
        root.destroy()
    except Exception as e:
        print(f"手动清理日志失败: {e}")

def on_view_log_info(icon, item):
    """查看日志信息"""
    try:
        if os.path.exists(LOG_FILE):
            file_size = os.path.getsize(LOG_FILE)
            with open(LOG_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            size_mb = file_size / (1024 * 1024)
            
            # 获取最早和最新的日志时间
            first_date = "未知"
            last_date = "未知"
            
            try:
                if lines:
                    # 第一条记录
                    first_line = lines[0].strip()
                    if len(first_line) >= 19:
                        first_date = first_line[:19]
                    
                    # 最后一条记录
                    last_line = lines[-1].strip()
                    if len(last_line) >= 19:
                        last_date = last_line[:19]
            except:
                pass
            
            info = f"""📋 打印日志信息

📊 文件大小: {size_mb:.2f} MB
📝 记录总数: {len(lines)} 条
📅 最早记录: {first_date}
📅 最新记录: {last_date}
📁 文件路径: {LOG_FILE}

🔧 自动清理规则:
• 文件超过5MB时保留最新1000条
• 每天下午3点清理7天前的记录
• 每天检查一次文件大小"""
            
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("日志信息", info)
            root.destroy()
        else:
            import tkinter as tk
            from tkinter import messagebox
            root = tk.Tk()
            root.withdraw()
            messagebox.showinfo("日志信息", "📋 日志文件不存在")
            root.destroy()
    except Exception as e:
        print(f"查看日志信息失败: {e}")

def build_menu(icon):
    autostart = get_autostart()
    ip = get_local_ip()
    port = getattr(app, 'current_port', 5000)  # 获取当前端口
    ip_config = get_current_ip_config()
    
    # 构建IP状态显示文本
    ip_status = f"当前IP: {ip}"
    if ip_config:
        if ip_config['dhcp_enabled']:
            ip_status += " (DHCP)"
        else:
            ip_status += " (静态)"
    
    # 检查端口是否来自配置文件
    config_port = get_config_port()
    port_status = f"当前端口: {port}"
    if port == config_port:
        port_status += " ✅"
    else:
        port_status += " (临时)"
    
    return pystray.Menu(
        pystray.MenuItem(f'服务地址: {ip}:{port}', on_show_ip_config),
        pystray.MenuItem(ip_status, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('网络配置', pystray.Menu(
            pystray.MenuItem('打开配置页面', on_show_ip_config),
            pystray.MenuItem('设置建议静态IP', on_set_static_ip),
            pystray.MenuItem('启用DHCP', on_enable_dhcp),
        )),
        pystray.MenuItem('服务设置', pystray.Menu(
            pystray.MenuItem(port_status, None, enabled=False),
            pystray.MenuItem('更改端口', on_change_port),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem('查看配置', on_view_config),
            pystray.MenuItem('重置配置', on_reset_config),
        )),
        pystray.MenuItem('日志管理', pystray.Menu(
            pystray.MenuItem('查看日志信息', on_view_log_info),
            pystray.MenuItem('清理日志', on_clean_logs),
        )),
        pystray.MenuItem('开机自启：' + ('已开启' if autostart else '未开启'), on_toggle_autostart),
        pystray.Menu.SEPARATOR,
        # 控制台控制选项（所有模式下都可用）
        pystray.MenuItem(
            '控制台：' + ('已显示' if CONSOLE_VISIBLE else '已隐藏'), 
            toggle_console_window
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('GitHub仓库', on_open_github),
        pystray.MenuItem('退出', on_quit)
    )
 
def setup_tray():
    # 只使用logo.ico文件作为托盘图标
    try:
        # 加载logo.ico文件 - 改进路径查找逻辑
        logo_path = None
        
        # 候选路径列表，按优先级排序
        candidate_paths = []
        
        if hasattr(sys, '_MEIPASS'):
            # PyInstaller打包后的路径
            candidate_paths.extend([
                path_manager.get_resource_path('logo.ico'),  # 打包内的资源
                os.path.join(os.path.dirname(sys.executable), 'logo.ico'),  # exe同级目录
            ])
        else:
            # 源码运行时的路径
            candidate_paths.extend([
                path_manager.get_resource_path('logo.ico'),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.ico'),
                os.path.join(os.getcwd(), 'logo.ico'),
            ])
        
        # 通用备选路径
        candidate_paths.extend([
            'logo.ico',  # 当前工作目录
            path_manager.get_data_path('logo.ico'),  # 程序目录
        ])
        
        # 查找第一个存在的图标文件
        for path in candidate_paths:
            if os.path.exists(path):
                logo_path = path
                print(f"找到图标文件: {logo_path}")
                break
        
        if logo_path:
            try:
                image = Image.open(logo_path)
                print(f"成功加载图标文件，尺寸: {image.size}")
            except Exception as e:
                print(f"加载图标失败: {e}，使用默认图标")
                logo_path = None
        
        if not logo_path:
            print("未找到logo.ico文件，创建默认图标")
            # 创建默认图标
            image = Image.new('RGB', (32, 32), color='blue')
            draw = ImageDraw.Draw(image)
            draw.text((8, 8), "P", fill='white')
        
        # 创建系统托盘图标
        icon = pystray.Icon('print_server', image, '内网打印服务 - by 忆痕')
        icon.menu = build_menu(icon)
        print("系统托盘启动成功")
        
        try:
            icon.run()
        except Exception as e:
            print(f"系统托盘运行时出错: {e}")
            # 如果托盘运行失败，显示友好提示
            show_error_dialog(
                "系统托盘启动失败",
                f"系统托盘功能启动失败，但程序核心功能正常。\n\n"
                f"错误信息: {str(e)}\n\n"
                f"您仍可以通过以下方式使用程序：\n"
                f"• 直接访问: http://{get_local_ip()}:{getattr(app, 'current_port', 5000)}\n"
                f"• 程序会继续在后台运行\n"
                f"• 使用 Ctrl+C 可以停止程序",
                is_critical=False
            )
            
            # 保持程序运行
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("程序被用户中断")
                sys.exit(0)
        
    except Exception as e:
        print(f"系统托盘初始化失败: {e}")
        
        # 显示详细错误信息
        show_error_dialog(
            "系统托盘初始化失败",
            f"无法初始化系统托盘，可能的原因：\n\n"
            f"1. 缺少图标文件 logo.ico\n"
            f"2. 系统不支持托盘功能\n"
            f"3. 相关库文件缺失\n\n"
            f"程序核心功能正常，您可以直接访问：\n"
            f"http://{get_local_ip()}:{getattr(app, 'current_port', 5000)}\n\n"
            f"错误详情: {str(e)}",
            is_critical=False
        )
        
        # 如果系统托盘失败，至少保持程序运行
        print("程序将继续运行，但没有系统托盘图标")
        print(f"您可以通过浏览器访问: http://{get_local_ip()}:{getattr(app, 'current_port', 5000)}")
        
        # 保持主线程不退出
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("程序被用户中断")
            sys.exit(0)

# 环境检测功能已取消 - 简化启动流程

def show_error_dialog(title, message, is_critical=True):
    """显示友好的错误对话框"""
    try:
        import tkinter as tk
        from tkinter import messagebox
        
        root = tk.Tk()
        root.withdraw()  # 隐藏主窗口
        
        if is_critical:
            messagebox.showerror(title, message)
        else:
            messagebox.showwarning(title, message)
        
        root.destroy()
        return True
    except Exception:
        # 如果tkinter不可用，回退到控制台输出
        print(f"\n{'='*50}")
        print(f"错误: {title}")
        print(f"{'='*50}")
        print(message)
        print(f"{'='*50}\n")
        return False

def check_windows_features():
    """检查Windows特性和服务"""
    issues = []
    suggestions = []
    
    try:
        # 检查打印服务是否运行
        result = subprocess.run(['sc', 'query', 'Spooler'], 
                              capture_output=True, text=True, timeout=5)
        if 'RUNNING' not in result.stdout:
            issues.append("Windows打印服务未运行")
            suggestions.append("启动打印服务：sc start Spooler")
    except Exception:
        pass
    
    try:
        # 检查Windows防火墙状态
        result = subprocess.run(['netsh', 'advfirewall', 'show', 'allprofiles', 'state'], 
                              capture_output=True, text=True, timeout=5)
        if 'ON' in result.stdout:
            suggestions.append("如果无法访问服务，可能需要在防火墙中允许Python或此程序")
    except Exception:
        pass
    
    return issues, suggestions

if __name__ == '__main__':
    try:
        # 特殊检查：如果是exe文件运行
        if hasattr(sys, '_MEIPASS'):
            print("🔍 检测到exe文件运行模式")
            print("📦 内网打印服务 by 忆痕")
            
            # 询问是否隐藏控制台窗口
            try:
                import ctypes
                from ctypes import wintypes
                
                # 获取控制台窗口句柄
                kernel32 = ctypes.windll.kernel32
                user32 = ctypes.windll.user32
                
                # 获取当前控制台窗口
                CONSOLE_WINDOW = kernel32.GetConsoleWindow()
                
                if CONSOLE_WINDOW:
                    # 给用户5秒时间看到启动信息
                    print("⏰ 5秒后将自动隐藏控制台窗口...")
                    print("💡 程序将在系统托盘中运行")
                    print("💡 如需查看详细信息，右键托盘图标选择'控制台'")
                    time.sleep(5)
                    
                    # 隐藏控制台窗口
                    user32.ShowWindow(CONSOLE_WINDOW, 0)  # SW_HIDE = 0
                    CONSOLE_VISIBLE = False
                    print("✅ 控制台窗口已隐藏")  # 这个不会显示，但会记录在内存中
            except Exception as e:
                print(f"⚠️ 控制台窗口处理失败: {e}")
            

        
        # 检查命令行参数中的端口设置，并加载配置文件
        import sys
        port = get_config_port()  # 首先从配置文件获取端口
        
        # 命令行参数可以覆盖配置文件设置（用于临时更改）
        for arg in sys.argv:
            if arg.startswith('--port='):
                try:
                    cmdline_port = int(arg.split('=')[1])
                    port = cmdline_port
                    print(f"ℹ️ 使用命令行指定端口: {port}")
                except ValueError:
                    print(f"警告: 无效的端口参数 {arg}，使用配置文件端口 {port}")
        
        # 保存当前端口到应用对象
        app.current_port = port
        
        print("=" * 60)
        print("              内网打印服务")
        print("              作者：忆痕")
        print("    GitHub: https://github.com/a937750307/lan-printing")
        print("=" * 60)
        
        # 显示路径信息（便于调试）
        print(f" 程序目录: {path_manager.app_dir}")
        print(f" 上传目录: {UPLOAD_FOLDER}")
        print(f" 配置文件: {CONFIG_FILE}")
        print(f" 日志文件: {LOG_FILE}")
        if hasattr(sys, '_MEIPASS'):
            print(f" 运行模式: PyInstaller打包 (资源目录: {sys._MEIPASS})")
        else:
            print(f" 运行模式: 源码运行")
        
        # 显示端口信息
        config_port = get_config_port()
        if port == config_port:
            print(f" 使用配置端口: {port}")
        else:
            print(f" 使用临时端口: {port} (配置端口: {config_port})")
        


        
        # 检测网络状态
        local_ip = get_local_ip()
        if local_ip == '127.0.0.1':
            print("     网络状态: 离线模式")
            print("   - 程序仍可正常工作")
            print("   - 使用默认打印机配置")
            print("   - 界面样式可能简化")
            
            # 显示友好提示
            show_error_dialog(
                "网络连接提示",
                "检测到网络连接异常，程序将在离线模式下运行。\n\n"
                "离线模式功能：\n"
                "• 本地打印功能正常\n"
                "• 使用 http://127.0.0.1:5000 访问\n"
                "• 部分网络功能可能受限\n\n"
                "如需完整功能，请检查网络连接。",
                is_critical=False
            )
        else:
            print(f"【OK】网络状态: 在线 (IP: {local_ip})")
            print("     - 完整功能可用")
            print("     - 可获取实时打印机参数")
        
        print(f"🖨️  检测到 {len(PRINTERS)} 台物理打印机")
        if PRINTERS:
            for i, printer in enumerate(PRINTERS[:3], 1):  # 只显示前3台
                print(f"   {i}. {printer}")
            if len(PRINTERS) > 3:
                print(f"   ... 还有 {len(PRINTERS) - 3} 台打印机")
        else:
            print("       未检测到可用的物理打印机")
            print("       程序仍可运行，但打印功能可能受限")
            print("       请检查:")
            print("      - 打印机是否正确连接")
            print("      - 打印机驱动是否已安装")
            print("      - Windows打印机和扫描仪设置")
            
            # 显示打印机检测提示
            show_error_dialog(
                "打印机检测提示",
                "未检测到可用的物理打印机。\n\n"
                "请检查：\n"
                "• 打印机是否正确连接并开机\n"
                "• 打印机驱动程序是否已安装\n"
                "• Windows 设置 > 打印机和扫描仪中是否显示\n"
                "• 尝试重启程序或点击界面中的'刷新'按钮\n\n"
                "程序仍可正常运行，检测到打印机后即可使用。",
                is_critical=False
            )
        
        print(" 服务器将启动在: http://{}:{}".format(local_ip, port))
        print("=" * 60)
        
        # 检查Windows功能和服务
        issues, suggestions = check_windows_features()
        if issues:
            print(" 检测到以下问题：")
            for issue in issues:
                print(f"   - {issue}")
            print(" 建议解决方案：")
            for suggestion in suggestions:
                print(f"   - {suggestion}")
        
        # 检查端口是否被占用
        import socket
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            sock.bind(('localhost', port))
            sock.close()
        except socket.error:
            error_msg = f"""端口 {port} 已被占用！

可能的原因：
• 该端口被其他程序占用
• 之前的程序实例未完全关闭
• 系统服务占用了该端口

解决方案：
1. 更换端口：
   python print_server.py --port=5001
   
2. 查找占用进程：
   netstat -ano | findstr :{port}
   
3. 结束占用进程：
   taskkill /PID [进程ID] /F
   
4. 重启计算机后再试

如果问题持续，建议使用其他端口号（如5001-5010）"""
            
            show_error_dialog("端口占用错误", error_msg)
            sys.exit(1)
        
        # 启动定期清理线程
        service_manager.cleaner_thread = threading.Thread(target=clean_old_files, daemon=True)
        service_manager.cleaner_thread.start()
        
        # 启动服务监控线程
        service_manager.monitor_thread = threading.Thread(target=monitor_service_health, daemon=True)
        service_manager.monitor_thread.start()
        print("【OK】服务监控线程已启动")
        
        # 记录服务启动时间
        service_manager.start_time = time.time()
        
        # 判断是否为生产环境
        if os.environ.get('USE_WSGI', '').lower() == 'true':
            service_manager.flask_thread = threading.Thread(target=run_wsgi, daemon=True)
        else:
            service_manager.flask_thread = threading.Thread(target=run_flask, daemon=True)
        service_manager.flask_thread.start()
        
        # 等待Flask服务启动
        print(" 正在启动Web服务...")
        time.sleep(2)
        
        # 显示启动成功提示
        if local_ip != '127.0.0.1' and len(PRINTERS) > 0:
            print(" 启动完成！可以开始使用打印服务了")
            
            # 检测网络模式并显示相应提示
            network_mode = detect_network_mode()
            external_ip = get_external_ip()
            
            print("  访问地址：http://{}:{}".format(local_ip, port))
            
            # 根据网络模式给出不同提示
            if network_mode == "internal_tunnel" and external_ip:
                print("🏠 局域网环境")
                print(f"   • 内网IP: {local_ip}")
                if external_ip:
                    print(f"   • 路由器公网IP: {external_ip}")
                    print(f"   • 如需外网访问，请手动配置端口转发")
            elif network_mode == "public":
                print(f" 公网环境 - 外部可直接访问")
            else:
                print(f" 局域网环境")
            
            print(" 右键托盘图标查看更多功能")
            
            # 启动成功提示已移除，程序静默启动
        
        setup_tray()
        
    except KeyboardInterrupt:
        print("\n 程序被用户中断 (Ctrl+C)，正在优雅退出...")
        try:
            # 使用相同的优雅退出逻辑
            service_manager.mark_service_stopped()
            service_manager.clear_restart()
            
            # 等待重要线程结束
            if service_manager.flask_thread and service_manager.flask_thread.is_alive():
                print("等待Web服务结束...")
                service_manager.flask_thread.join(timeout=1)

            print("【OK】优雅退出完成")
        except Exception as e:
            print(f"优雅退出失败: {e}")
        finally:
            # 强制退出
            import os
            os._exit(0)
    except Exception as e:
        # 获取更详细的系统信息用于诊断
        try:
            import platform
            import traceback
            
            system_info = {
                'system': platform.system(),
                'release': platform.release(),
                'version': platform.version(),
                'machine': platform.machine(),
                'processor': platform.processor(),
                'python_version': platform.python_version(),
            }
            
            # Win11特有错误分析
            win11_hints = []
            error_str = str(e).lower()
            
            if 'access' in error_str or 'permission' in error_str:
                win11_hints.append("权限问题：请以管理员身份运行程序")
            
            if 'import' in error_str or 'module' in error_str:
                win11_hints.append("依赖库缺失：程序打包可能不完整")
            
            if 'socket' in error_str or 'bind' in error_str:
                win11_hints.append("网络权限：检查防火墙和Windows Defender设置")
            
            if 'file' in error_str or 'path' in error_str:
                win11_hints.append("路径问题：避免中文路径，移动到英文目录")
                
            # 生成详细错误报告
            full_traceback = traceback.format_exc()
            
        except:
            system_info = {'error': '无法获取系统信息'}
            win11_hints = []
            full_traceback = str(e)
        
        error_msg = f"""程序启动时发生严重错误：

💥 错误信息: {str(e)}

🖥️ 系统信息:
• 系统: {system_info.get('system', 'Unknown')} {system_info.get('release', 'Unknown')}
• Python: {system_info.get('python_version', 'Unknown')}
• 架构: {system_info.get('machine', 'Unknown')}

🔍 Win11专用诊断:
""" + '\n'.join(f"• {hint}" for hint in win11_hints) + f"""

💡 解决方案：
1. 【立即尝试】右键程序图标 → "以管理员身份运行"
2. 【Win11专用】添加Windows Defender排除项：
   • 开始菜单搜索"Windows安全中心"
   • 病毒和威胁防护 → 管理设置 → 添加或删除排除项
   • 添加文件夹：程序所在目录
3. 【路径问题】移动程序到简单英文路径：
   • 例如：C:\\Tools\\PrintService\\
4. 【网络问题】检查防火墙设置：
   • Windows设置 → 隐私和安全性 → Windows安全中心
5. 【依赖问题】重新下载完整版程序

🔗 获取帮助：
• GitHub Issues: https://github.com/a937750307/lan-printing/issues
• 提交时请包含上述系统信息和错误详情

开发者：忆痕

--- 技术详情 (请复制给开发者) ---
{full_traceback}
系统详情: {system_info}
"""
        
        show_error_dialog("程序启动失败 - Win11兼容性", error_msg)
        print(f"\n💥 严重错误: {e}")
        print(f"📊 系统: {system_info}")
        if win11_hints:
            print(f"💡 Win11提示: {', '.join(win11_hints)}")
        print("\n--- 完整错误信息 ---")
        import traceback
        traceback.print_exc()
        sys.exit(1)
