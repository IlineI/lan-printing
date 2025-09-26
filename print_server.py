#!/usr/bin/env python
# -*- coding: utf-8 -*-
#作者：忆痕
#仓库地址：https://github.com/a937750307/lan-printing
 
import os
from flask import Flask, request, render_template_string, send_from_directory, redirect, url_for, flash, jsonify
# 打印相关
import win32print
import win32api
import win32gui
import win32con
import subprocess
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
def clean_old_files(folder=None, expire_seconds=3600):
    """定期清理指定目录下超过expire_seconds的文件"""
    if folder is None:
        folder = UPLOAD_FOLDER
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
 
# 配置文件路径 - 保存在程序同级目录下
def get_config_file_path():
    """获取配置文件路径，兼容源码和打包后的情况"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller打包后，配置文件保存在exe文件同级目录
        return os.path.join(os.path.dirname(sys.executable), 'config.json')
    else:
        # 源码运行时，配置文件保存在脚本同级目录
        return os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

CONFIG_FILE = get_config_file_path()

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

# 兼容PyInstaller打包和源码运行的资源路径
def resource_path(relative_path):
    if hasattr(sys, '_MEIPASS'):
        return os.path.join(sys._MEIPASS, relative_path)
    return os.path.join(os.path.abspath("."), relative_path)
 
# 获取本机局域网IP
def get_local_ip():
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

# 兼容PyInstaller打包的路径处理
def get_app_dir():
    """获取程序运行目录，兼容源码和打包后的情况"""
    if hasattr(sys, '_MEIPASS'):
        # PyInstaller打包后，使用exe文件所在目录
        return os.path.dirname(sys.executable)
    else:
        # 源码运行时，使用脚本所在目录
        return os.path.dirname(os.path.abspath(__file__))

# 文件夹和文件路径配置
APP_DIR = get_app_dir()
UPLOAD_FOLDER = os.path.join(APP_DIR, 'uploads')
LOG_FILE = os.path.join(APP_DIR, 'print_log.txt')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

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
<html lang="zh-cn">
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
    
    <!-- 导航标签 -->
    <ul class="nav nav-pills justify-content-center mb-4" id="pills-tab" role="tablist">
        <li class="nav-item" role="presentation">
            <button class="nav-link active" id="pills-print-tab" data-bs-toggle="pill" data-bs-target="#pills-print" type="button" role="tab">打印管理</button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link" id="pills-network-tab" data-bs-toggle="pill" data-bs-target="#pills-network" type="button" role="tab">网络配置</button>
        </li>
        <li class="nav-item" role="presentation">
            <button class="nav-link" id="pills-repair-tab" data-bs-toggle="pill" data-bs-target="#pills-repair" type="button" role="tab">系统修复</button>
        </li>
    </ul>

    <div class="tab-content" id="pills-tabContent">
        <!-- 打印管理标签页 -->
        <div class="tab-pane fade show active" id="pills-print" role="tabpanel">
            <form method="post" enctype="multipart/form-data" class="row g-3 mb-4">
                <input type="hidden" name="action" value="print">
                <div class="col-md-6">
                    <label class="form-label">选择打印机 
                        <button type="button" class="btn btn-sm btn-outline-secondary ms-2" onclick="refreshPrinterList()" title="刷新打印机列表">
                            🔄 刷新
                        </button>
                    </label>
                    <select name="printer" class="form-select" id="printerSelect">
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
                    <select name="copies" class="form-select">
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
                    <label class="form-label">单双面</label>
                    <select name="duplex" class="form-select">
                        <option value="1">单面</option>
                        {% if printer_caps and printer_caps.get('duplex_support') %}
                        <option value="2">长边翻转双面</option>
                        <option value="3">短边翻转双面</option>
                        {% endif %}
                    </select>
                    {% if printer_caps and not printer_caps.get('duplex_support') %}
                    <div class="form-text text-muted">当前打印机可能不支持双面打印</div>
                    {% endif %}
                </div>
                <div class="col-md-4">
                    <label class="form-label">纸张大小</label>
                    <select name="papersize" class="form-select" id="paperSelect">
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
                    <select name="quality" class="form-select" id="qualitySelect">
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
                        <input type="file" name="file" multiple class="form-control" id="fileInput" style="display: none;">
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
                    <li><strong>📄 PDF文件:</strong> 优先使用Adobe Reader进行静默打印，效果最佳</li>
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
                    <li><strong>🗑️ 删除文件:</strong> 点击删除按钮可以从队列中移除单个文件，避免误打印</li>
                    <li><strong>📁 清空队列:</strong> 可以一键清空所有待打印文件，节省时间</li>
                    <li><strong>👁️ 文件预览:</strong> 打印前可以预览文件内容，确保正确性</li>
                    <li><strong>📊 文件信息:</strong> 显示文件大小、类型和上传时间，便于管理</li>
                    <li><strong>⏰ 自动清理:</strong> 文件会在10分钟后自动清理，无需手动删除</li>
                    <li><strong>💡 使用建议:</strong> 打印前检查队列，删除不需要的文件可以节省纸张</li>
                </ul>
            </div>
            
            <div class="alert alert-info">
                <h6><i class="bi bi-lightbulb"></i> 新功能特性</h6>
                <ul class="mb-0 small">
                    <li><strong>🖱️ 拖拽上传:</strong> 支持直接拖拽文件到上传区域，无需点击选择</li>
                    <li><strong>📁 多文件上传:</strong> 可同时选择多个文件进行批量打印</li>
                    <li><strong>🔄 动态端口:</strong> 支持通过托盘图标更改服务端口</li>
                    <li><strong>🛡️ 智能检测:</strong> 自动检测虚拟打印机并过滤，只显示物理打印机</li>
                    <li><strong>💾 自动清理:</strong> 上传的文件会在10分钟后自动清理，节省磁盘空间</li>
                    <li><strong>📱 移动友好:</strong> 响应式设计，支持手机、平板访问</li>
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

        <!-- 网络配置标签页 -->
        <div class="tab-pane fade" id="pills-network" role="tabpanel">
            <!-- 当前IP状态 -->
            <div class="ip-status">
                <h5><i class="bi bi-network"></i> 当前网络状态</h5>
                {% if ip_config %}
                <div class="row">
                    <div class="col-md-6">
                        <strong>IP地址:</strong> {{ip_config.ip}} 
                        {% if ip_config.dhcp_enabled %}
                            <span class="badge bg-success">DHCP</span>
                        {% else %}
                            <span class="badge bg-primary">静态</span>
                        {% endif %}
                    </div>
                    <div class="col-md-6">
                        <strong>服务端口:</strong> {{current_port}}
                        {% if port_from_config %}
                            <span class="badge bg-success">已保存</span>
                        {% else %}
                            <span class="badge bg-warning">默认</span>
                        {% endif %}
                    </div>
                    <div class="col-md-6">
                        <strong>子网掩码:</strong> {{ip_config.subnet}}
                    </div>
                    <div class="col-md-6">
                        <strong>默认网关:</strong> {{ip_config.gateway}}
                    </div>
                    <div class="col-12">
                        <strong>网络适配器:</strong> {{ip_config.description[:50]}}...
                    </div>
                </div>
                {% else %}
                <div class="alert alert-warning">未检测到网络连接</div>
                {% endif %}
            </div>

            <!-- IP配置表单 -->
            <div class="row">
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            <h6><i class="bi bi-gear"></i> 设置静态IP</h6>
                        </div>
                        <div class="card-body">
                            <form method="post">
                                <input type="hidden" name="action" value="set_static_ip">
                                <div class="mb-3">
                                    <label class="form-label">IP地址</label>
                                    <input type="text" name="ip_address" class="form-control" 
                                           value="{{suggested_ip}}" placeholder="192.168.1.100" 
                                           spellcheck="false" autocomplete="off" autocorrect="off">
                                    <div class="form-text">建议使用当前网段的固定IP</div>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">子网掩码</label>
                                    <input type="text" name="subnet_mask" class="form-control" 
                                           value="255.255.255.0" spellcheck="false" autocomplete="off" autocorrect="off">
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">默认网关</label>
                                    <input type="text" name="gateway" class="form-control" 
                                           placeholder="自动推导（可选）" spellcheck="false" autocomplete="off" autocorrect="off">
                                    <div class="form-text">留空将自动推导网关地址</div>
                                </div>
                                <button type="submit" class="btn btn-primary">设置静态IP</button>
                            </form>
                        </div>
                    </div>
                </div>
                <div class="col-md-6">
                    <div class="card">
                        <div class="card-header">
                            <h6><i class="bi bi-arrow-repeat"></i> 启用DHCP</h6>
                        </div>
                        <div class="card-body">
                            <p>恢复使用DHCP自动获取IP地址。这将取消当前的静态IP设置。</p>
                            <form method="post">
                                <input type="hidden" name="action" value="enable_dhcp">
                                <button type="submit" class="btn btn-warning">启用DHCP</button>
                            </form>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 网络信息说明 -->
            <div class="alert alert-info mt-4">
                <h6><i class="bi bi-info-circle"></i> 使用说明</h6>
                <ul class="mb-0">
                    <li><strong>静态IP:</strong> 固定IP地址，重启后不变，便于局域网其他设备连接</li>
                    <li><strong>DHCP:</strong> 动态获取IP地址，可能会在重启后发生变化</li>
                    <li><strong>建议:</strong> 为打印服务器设置静态IP，方便其他设备记住访问地址</li>
                    <li><strong>注意:</strong> 修改网络配置需要管理员权限，可能会暂时中断网络连接</li>
                </ul>
            </div>
        </div>

        <!-- 系统修复标签页 -->
        <div class="tab-pane fade" id="pills-repair" role="tabpanel">
            <div class="container-fluid">
                <div class="row">
                    <div class="col-12">
                        <div class="alert alert-primary">
                            <h5><i class="bi bi-tools"></i> 系统修复工具</h5>
                            <p class="mb-0">自动检测和修复常见的系统兼容性问题，支持 Windows 7/10/11</p>
                        </div>
                    </div>
                </div>

                <!-- 系统信息显示 -->
                <div class="row mb-4">
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">
                                <h6><i class="bi bi-info-circle"></i> 系统信息</h6>
                            </div>
                            <div class="card-body">
                                <div id="system-info">
                                    <div class="text-center">
                                        <div class="spinner-border spinner-border-sm" role="status">
                                            <span class="visually-hidden">Loading...</span>
                                        </div>
                                        <span class="ms-2">正在获取系统信息...</span>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                    <div class="col-md-6">
                        <div class="card">
                            <div class="card-header">
                                <h6><i class="bi bi-shield-check"></i> 诊断状态</h6>
                            </div>
                            <div class="card-body">
                                <div id="diagnosis-status">
                                    <div class="text-center text-muted">
                                        <i class="bi bi-clock"></i> 等待诊断
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 诊断和修复控制 -->
                <div class="row mb-4">
                    <div class="col-12">
                        <div class="card">
                            <div class="card-header">
                                <h6><i class="bi bi-gear"></i> 操作面板</h6>
                            </div>
                            <div class="card-body">
                                <div class="row g-3">
                                    <div class="col-md-4">
                                        <button class="btn btn-primary w-100" id="start-diagnosis">
                                            <i class="bi bi-search"></i> 开始诊断
                                        </button>
                                    </div>
                                    <div class="col-md-4">
                                        <button class="btn btn-success w-100" id="apply-fixes" disabled>
                                            <i class="bi bi-tools"></i> 应用修复
                                        </button>
                                    </div>
                                    <div class="col-md-4">
                                        <button class="btn btn-warning w-100" id="run-repair-tool">
                                            <i class="bi bi-terminal"></i> 运行修复工具
                                        </button>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 问题列表 -->
                <div class="row">
                    <div class="col-12">
                        <div class="card">
                            <div class="card-header">
                                <h6><i class="bi bi-list-check"></i> 诊断结果</h6>
                            </div>
                            <div class="card-body">
                                <div id="issues-list">
                                    <div class="text-center text-muted">
                                        <i class="bi bi-clipboard-data"></i>
                                        <p class="mb-0">请先运行诊断以查看结果</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>

                <!-- 版本特定说明 -->
                <div class="alert alert-info mt-4">
                    <h6><i class="bi bi-info-circle"></i> 系统兼容性说明</h6>
                    <div class="row">
                        <div class="col-md-4">
                            <h6 class="text-success">Windows 11</h6>
                            <ul class="mb-0 small">
                                <li>Windows Defender排除设置</li>
                                <li>SmartScreen配置</li>
                                <li>路径兼容性检查</li>
                            </ul>
                        </div>
                        <div class="col-md-4">
                            <h6 class="text-primary">Windows 10</h6>
                            <ul class="mb-0 small">
                                <li>实时保护配置</li>
                                <li>防火墙规则设置</li>
                                <li>权限问题修复</li>
                            </ul>
                        </div>
                        <div class="col-md-4">
                            <h6 class="text-warning">Windows 7</h6>
                            <ul class="mb-0 small">
                                <li>.NET Framework检查</li>
                                <li>系统更新建议</li>
                                <li>兼容性模式设置</li>
                            </ul>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
<script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.2/dist/js/bootstrap.bundle.min.js" onerror="console.log('Bootstrap JS 加载失败，使用备用方案')"></script>
<!-- 离线JavaScript备用方案 -->
<script>
// 简单的标签页切换功能（如果Bootstrap JS加载失败）
if (typeof bootstrap === 'undefined') {
    document.addEventListener('DOMContentLoaded', function() {
        // 标签页切换功能
        const tabButtons = document.querySelectorAll('[data-bs-toggle="pill"]');
        const tabPanes = document.querySelectorAll('.tab-pane');
        
        tabButtons.forEach(button => {
            button.addEventListener('click', function(e) {
                e.preventDefault();
                
                // 移除所有active类
                tabButtons.forEach(btn => btn.classList.remove('active'));
                tabPanes.forEach(pane => {
                    pane.classList.remove('show', 'active');
                });
                
                // 添加active到当前按钮
                this.classList.add('active');
                
                // 显示对应的标签页内容
                const targetId = this.getAttribute('data-bs-target');
                const targetPane = document.querySelector(targetId);
                if (targetPane) {
                    targetPane.classList.add('show', 'active');
                }
            });
        });
        
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
}

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
                'Content-Type': 'application/json',
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
            showAlert('danger', '❌ 删除文件时发生网络错误');
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
                'Content-Type': 'application/json',
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
            showAlert('danger', '❌ 批量删除时发生网络错误');
        });
    }
}

// ==================== 系统修复工具功能 ====================
let currentDiagnosis = null;

// 系统信息获取和显示
function loadSystemInfo() {
    const systemInfoDiv = document.getElementById('system-info');
    
    // 显示基本系统信息
    const userAgent = navigator.userAgent;
    const platform = navigator.platform;
    const language = navigator.language;
    
    let systemInfo = `
        <div class="small">
            <div><strong>浏览器:</strong> ${getBrowserInfo()}</div>
            <div><strong>平台:</strong> ${platform}</div>
            <div><strong>语言:</strong> ${language}</div>
            <div><strong>时间:</strong> ${new Date().toLocaleString()}</div>
        </div>
    `;
    
    systemInfoDiv.innerHTML = systemInfo;
}

function getBrowserInfo() {
    const userAgent = navigator.userAgent;
    if (userAgent.indexOf("Chrome") > -1) return "Chrome";
    if (userAgent.indexOf("Firefox") > -1) return "Firefox";
    if (userAgent.indexOf("Safari") > -1) return "Safari";
    if (userAgent.indexOf("Edge") > -1) return "Edge";
    return "Unknown";
}

// 开始系统诊断
function startDiagnosis() {
    const diagnosisBtn = document.getElementById('start-diagnosis');
    const diagnosisStatus = document.getElementById('diagnosis-status');
    const issuesList = document.getElementById('issues-list');
    const applyFixesBtn = document.getElementById('apply-fixes');
    
    // 禁用按钮，显示加载状态
    diagnosisBtn.disabled = true;
    diagnosisBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 诊断中...';
    
    diagnosisStatus.innerHTML = `
        <div class="text-primary">
            <div class="spinner-border spinner-border-sm"></div>
            <span class="ms-2">正在进行系统诊断...</span>
        </div>
    `;
    
    // 调用系统诊断API
    fetch('/api/system_diagnosis')
        .then(response => response.json())
        .then(data => {
            diagnosisBtn.disabled = false;
            diagnosisBtn.innerHTML = '<i class="bi bi-search"></i> 重新诊断';
            
            if (data.success) {
                currentDiagnosis = data;
                displayDiagnosisResults(data);
                
                if (data.fixes_available) {
                    applyFixesBtn.disabled = false;
                    diagnosisStatus.innerHTML = `
                        <div class="text-warning">
                            <i class="bi bi-exclamation-triangle"></i>
                            <span class="ms-2">发现 ${data.issues.length} 个问题</span>
                        </div>
                    `;
                } else {
                    diagnosisStatus.innerHTML = `
                        <div class="text-success">
                            <i class="bi bi-check-circle"></i>
                            <span class="ms-2">系统状态良好</span>
                        </div>
                    `;
                }
            } else {
                diagnosisStatus.innerHTML = `
                    <div class="text-danger">
                        <i class="bi bi-x-circle"></i>
                        <span class="ms-2">诊断失败</span>
                    </div>
                `;
                showAlert('danger', `诊断失败: ${data.error}`);
            }
        })
        .catch(error => {
            diagnosisBtn.disabled = false;
            diagnosisBtn.innerHTML = '<i class="bi bi-search"></i> 开始诊断';
            diagnosisStatus.innerHTML = `
                <div class="text-danger">
                    <i class="bi bi-x-circle"></i>
                    <span class="ms-2">诊断出错</span>
                </div>
            `;
            showAlert('danger', `诊断出错: ${error.message}`);
            console.error('诊断错误:', error);
        });
}

// 显示诊断结果
function displayDiagnosisResults(data) {
    const issuesList = document.getElementById('issues-list');
    
    if (!data.issues || data.issues.length === 0) {
        issuesList.innerHTML = `
            <div class="text-center text-success">
                <i class="bi bi-check-circle display-6"></i>
                <h5 class="mt-3">系统检查通过</h5>
                <p class="text-muted">未发现兼容性问题</p>
            </div>
        `;
        return;
    }
    
    let issuesHtml = '';
    data.issues.forEach((issue, index) => {
        const severityClass = {
            'high': 'danger',
            'medium': 'warning', 
            'low': 'info'
        };
        
        const severityIcon = {
            'high': 'exclamation-triangle-fill',
            'medium': 'exclamation-triangle',
            'low': 'info-circle'
        };
        
        issuesHtml += `
            <div class="alert alert-${severityClass[issue.severity]} alert-dismissible" role="alert">
                <h6 class="alert-heading">
                    <i class="bi bi-${severityIcon[issue.severity]}"></i>
                    ${issue.title}
                </h6>
                <p class="mb-2">${issue.description}</p>
                ${issue.details ? `<small class="text-muted">详情: ${issue.details}</small>` : ''}
                <div class="form-check mt-2">
                    <input class="form-check-input" type="checkbox" value="${issue.fix}" id="fix-${index}" checked>
                    <label class="form-check-label" for="fix-${index}">
                        应用此修复
                    </label>
                </div>
            </div>
        `;
    });
    
    issuesList.innerHTML = issuesHtml;
}

// 应用修复
function applyFixes() {
    const applyFixesBtn = document.getElementById('apply-fixes');
    
    if (!currentDiagnosis || !currentDiagnosis.issues) {
        showAlert('warning', '请先运行诊断');
        return;
    }
    
    // 获取选中的修复项目
    const selectedFixes = [];
    currentDiagnosis.issues.forEach((issue, index) => {
        const checkbox = document.getElementById(`fix-${index}`);
        if (checkbox && checkbox.checked) {
            selectedFixes.push(issue.fix);
        }
    });
    
    if (selectedFixes.length === 0) {
        showAlert('warning', '请选择要应用的修复项目');
        return;
    }
    
    // 禁用按钮，显示加载状态
    applyFixesBtn.disabled = true;
    applyFixesBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 修复中...';
    
    // 调用修复API
    fetch('/api/apply_fixes', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            fixes: selectedFixes
        })
    })
    .then(response => response.json())
    .then(data => {
        applyFixesBtn.disabled = false;
        applyFixesBtn.innerHTML = '<i class="bi bi-tools"></i> 重新修复';
        
        if (data.success) {
            showAlert('success', data.message);
            
            // 显示修复结果详情
            let resultDetails = '<br><strong>修复结果:</strong><br>';
            Object.entries(data.results).forEach(([fixType, result]) => {
                const status = result.success ? '✅' : '❌';
                resultDetails += `${status} ${fixType}: ${result.message}<br>`;
            });
            
            showAlert('info', `修复完成<br>${resultDetails}`);
            
            // 建议重新诊断
            setTimeout(() => {
                if (confirm('修复完成！是否重新运行诊断以查看结果？')) {
                    startDiagnosis();
                }
            }, 2000);
        } else {
            showAlert('danger', `修复失败: ${data.error}`);
        }
    })
    .catch(error => {
        applyFixesBtn.disabled = false;
        applyFixesBtn.innerHTML = '<i class="bi bi-tools"></i> 应用修复';
        showAlert('danger', `修复出错: ${error.message}`);
        console.error('修复错误:', error);
    });
}

// 运行修复工具
function runRepairTool() {
    const runToolBtn = document.getElementById('run-repair-tool');
    
    runToolBtn.disabled = true;
    runToolBtn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> 启动中...';
    
    fetch('/api/run_repair_tool')
        .then(response => response.json())
        .then(data => {
            runToolBtn.disabled = false;
            runToolBtn.innerHTML = '<i class="bi bi-terminal"></i> 运行修复工具';
            
            if (data.success) {
                showAlert('success', '修复工具已启动！请查看新打开的窗口。');
            } else {
                showAlert('danger', `启动失败: ${data.error}`);
            }
        })
        .catch(error => {
            runToolBtn.disabled = false;
            runToolBtn.innerHTML = '<i class="bi bi-terminal"></i> 运行修复工具';
            showAlert('danger', `启动出错: ${error.message}`);
            console.error('启动错误:', error);
        });
}

// 页面加载完成后绑定事件
document.addEventListener('DOMContentLoaded', function() {
    // 加载系统信息
    loadSystemInfo();
    
    // 绑定按钮事件
    const startDiagnosisBtn = document.getElementById('start-diagnosis');
    const applyFixesBtn = document.getElementById('apply-fixes');
    const runRepairToolBtn = document.getElementById('run-repair-tool');
    
    if (startDiagnosisBtn) {
        startDiagnosisBtn.addEventListener('click', startDiagnosis);
    }
    
    if (applyFixesBtn) {
        applyFixesBtn.addEventListener('click', applyFixes);
    }
    
    if (runRepairToolBtn) {
        runRepairToolBtn.addEventListener('click', runRepairTool);
    }
    
    // 监听标签页切换，在系统修复标签激活时自动运行诊断
    const repairTab = document.getElementById('pills-repair-tab');
    if (repairTab) {
        repairTab.addEventListener('shown.bs.tab', function() {
            if (!currentDiagnosis) {
                setTimeout(startDiagnosis, 500); // 延迟执行，确保页面渲染完成
            }
        });
    }
});

// 错误处理 - 在出现错误时自动提示用户使用修复工具
window.addEventListener('error', function(event) {
    console.error('页面错误:', event.error);
    
    // 如果是网络相关错误或权限错误，提示用户使用修复工具
    const errorMessage = event.error ? event.error.message : event.message;
    if (errorMessage && (
        errorMessage.includes('网络') || 
        errorMessage.includes('权限') || 
        errorMessage.includes('拒绝') ||
        errorMessage.includes('failed') ||
        errorMessage.includes('error')
    )) {
        setTimeout(() => {
            if (confirm('检测到可能的系统兼容性问题。是否打开系统修复工具进行诊断？')) {
                // 切换到修复标签页
                const repairTab = document.getElementById('pills-repair-tab');
                if (repairTab) {
                    repairTab.click();
                }
            }
        }, 1000);
    }
});
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
 
def log_print(filename, printer, copies, duplex, papersize, quality):
    with open(LOG_FILE, 'a', encoding='utf-8') as f:
        f.write(f"{datetime.now()} 打印: {filename} 打印机: {printer} 份数: {copies} 单双面: {duplex} 纸张: {papersize} 质量: {quality}\n")

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
            
            # 设置双面打印
            if duplex > 1:
                if duplex == 2:
                    devmode.Duplex = win32con.DMDUP_VERTICAL  # 长边翻转
                    print("设置双面打印: 长边翻转")
                elif duplex == 3:
                    devmode.Duplex = win32con.DMDUP_HORIZONTAL  # 短边翻转
                    print("设置双面打印: 短边翻转")
            
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
    """使用设置参数打印PDF文件"""
    try:
        print(f"打印PDF文件: {filepath}")
        
        # 尝试使用Adobe Reader静默打印
        adobe_paths = [
            r"C:\\Program Files\\Adobe\\Acrobat DC\\Acrobat\\Acrobat.exe",
            r"C:\\Program Files (x86)\\Adobe\\Acrobat Reader DC\\Reader\\AcroRd32.exe",
            r"C:\\Program Files\\Adobe\\Acrobat Reader DC\\Reader\\AcroRd32.exe"
        ]
        
        for adobe_path in adobe_paths:
            if os.path.exists(adobe_path):
                try:
                    # 构建Adobe Reader打印命令
                    cmd = f'"{adobe_path}" /p /h "{filepath}"'
                    print(f"使用Adobe Reader打印: {cmd}")
                    
                    # 尝试应用打印设置（部分阅读器可能不生效）
                    _ = apply_printer_settings(printer_name, copies, duplex, papersize, quality)
                    
                    # 执行打印命令
                    result = os.system(cmd)
                    if result == 0:
                        print("Adobe Reader打印命令执行成功")
                        return True
                except Exception as e:
                    print(f"Adobe Reader打印失败: {e}")
                    continue
        
        # 如果Adobe Reader不可用，回退到简单打印
        return print_pdf_silent(filepath, printer_name, copies)
        
    except Exception as e:
        print(f"PDF打印失败: {e}")
        return False

def print_with_shell_execute(filepath, printer_name, copies):
    """使用ShellExecute进行应用程序调用打印，确保使用指定打印机"""
    try:
        success_count = 0
        for i in range(copies):
            try:
                # 首先尝试使用printto指定打印机
                result = win32api.ShellExecute(
                    0,  # hwnd
                    'printto',  # operation - 使用printto而不是print
                    filepath,  # file
                    f'"{printer_name}"',  # parameters - 指定打印机名称
                    None,  # directory
                    0  # show command (SW_HIDE)
                )
                
                if result > 32:  # ShellExecute成功
                    success_count += 1
                    time.sleep(1)  # 给应用程序时间处理
                else:
                    print(f"printto到{printer_name}失败，错误代码: {result}")
                    # 如果printto失败，不再回退到默认打印机
                    
            except Exception as e:
                print(f"打印第{i+1}份时出错: {e}")
                
        if success_count > 0:
            return True, f"通过关联应用程序打印已发送到 {printer_name} ({success_count}/{copies}份)"
        else:
            return False, f"无法打印到指定打印机 {printer_name}，请检查打印机状态"
            
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
                    return False, f"所有打印方案都失败，无法打印到指定打印机 {printer_name}"
            except Exception as e3:
                return False, f"所有静默打印方案都失败: {str(e3)}"

def print_text_direct_to_printer(filepath, printer_name, copies=1):
    """使用WIN32 API直接将文本文件发送到指定打印机"""
    try:
        import win32print
        
        # 读取文本文件内容
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
        except UnicodeDecodeError:
            with open(filepath, 'r', encoding='gbk') as f:
                content = f.read()
        
        # 打开指定的打印机
        printer_handle = win32print.OpenPrinter(printer_name)
        
        try:
            success_count = 0
            for i in range(copies):
                # 开始打印作业
                job_id = win32print.StartDocPrinter(printer_handle, 1, ("Text Document", None, "RAW"))
                
                try:
                    win32print.StartPagePrinter(printer_handle)
                    
                    # 发送文本内容到打印机
                    win32print.WritePrinter(printer_handle, content.encode('utf-8'))
                    
                    win32print.EndPagePrinter(printer_handle)
                    win32print.EndDocPrinter(printer_handle)
                    success_count += 1
                    
                except Exception as e:
                    print(f"打印作业 {i+1} 失败: {e}")
                    win32print.AbortPrinter(printer_handle)
                
            return True, f"直接打印到 {printer_name} 成功 ({success_count}/{copies}份)"
            
        finally:
            win32print.ClosePrinter(printer_handle)
            
    except Exception as e:
        return False, f"直接打印失败: {str(e)}"

def print_pdf_silent(filepath, printer_name, copies=1):
    """专门用于PDF文件的静默打印"""
    try:
        # 方案1: 使用Adobe Reader的命令行静默打印
        adobe_paths = [
            r"C:\Program Files\Adobe\Acrobat DC\Acrobat\Acrobat.exe",
            r"C:\Program Files (x86)\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
            r"C:\Program Files\Adobe\Acrobat Reader DC\Reader\AcroRd32.exe",
            r"C:\Program Files (x86)\Adobe\Reader 11.0\Reader\AcroRd32.exe",
        ]
        
        adobe_found = False
        for adobe_path in adobe_paths:
            if os.path.exists(adobe_path):
                adobe_found = True
                try:
                    for i in range(copies):
                        # 使用/t参数进行静默打印
                        cmd = [adobe_path, '/t', filepath, printer_name]
                        result = subprocess.run(cmd, 
                                              capture_output=True, 
                                              creationflags=subprocess.CREATE_NO_WINDOW,
                                              timeout=30)  # 30秒超时
                        time.sleep(2)  # 给打印机时间处理
                    return True, f"Adobe PDF静默打印已发送到 {printer_name} ({copies}份)"
                except subprocess.TimeoutExpired:
                    return False, "Adobe Reader打印超时"
                except Exception as e:
                    print(f"Adobe Reader打印失败: {e}")
                    break
        
        if not adobe_found:
            # 方案2: 使用printto指定打印机，避免使用默认打印机
            try:
                for i in range(copies):
                    # 首先尝试使用printto指定打印机
                    result = win32api.ShellExecute(0, 'printto', filepath, f'"{printer_name}"', None, 0)
                    if result <= 32:
                        # 如果printto失败，记录错误但不回退到默认打印机
                        print(f"printto失败，错误代码: {result}")
                        raise Exception(f"无法打印到指定打印机 {printer_name}")
                    time.sleep(3)  # 给应用程序更多时间
                return True, f"PDF打印已发送到指定打印机 {printer_name} ({copies}份)"
            except Exception as e:
                print(f"指定打印机打印失败: {e}")
                # 不再回退到默认打印机，而是继续尝试其他方案
        
        # 方案3: 使用PowerShell和COM对象，设置正确的打印机
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
        return print_file_silent_fallback(filepath, printer_name, copies)
        
    except Exception as e:
        print(f"PDF打印完全失败: {e}")
        return print_file_silent_fallback(filepath, printer_name, copies)

def print_text_file_simple(filepath, printer_name, copies=1):
    """简化TXT静默打印：调用ShellExecute进行打印到指定打印机"""
    try:
        sent = 0
        for i in range(copies):
            r = win32api.ShellExecute(0, 'printto', filepath, f'"{printer_name}"', None, 0)
            if r > 32:
                sent += 1
                time.sleep(1)
            else:
                # 如果printto失败，不再回退到默认打印机
                print(f"printto到{printer_name}失败，错误代码: {r}")
                
        if sent:
            return True, f"TXT静默打印已发送到 {printer_name} ({sent}/{copies}份)"
        else:
            # 如果printto完全失败，尝试直接API打印
            return print_text_direct_to_printer(filepath, printer_name, copies)
    except Exception as e:
        return False, f"TXT静默打印异常: {e}"

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
    """专门用于Office文档的静默打印"""
    try:
        file_ext = os.path.splitext(filepath)[1].lower()
        
        # 根据文件类型选择相应的Office应用程序
        if file_ext in ['.doc', '.docx']:
            # Word文档
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
            # Excel文档
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
            # 如果找不到Office，尝试使用PowerShell的COM对象
            return print_office_com(filepath, printer_name, copies, file_ext)
        
    except Exception as e:
        # 如果Office专用方法失败，使用通用方法
        return print_file_silent_fallback(filepath, printer_name, copies)

def print_office_com(filepath, printer_name, copies, file_ext):
    """使用COM对象打印Office文档"""
    try:
        abs_filepath = os.path.abspath(filepath).replace('\\', '\\\\')
        
        if file_ext in ['.doc', '.docx']:
            # 使用Word COM对象
            ps_script = f'''
try {{
    $word = New-Object -ComObject Word.Application
    $word.Visible = $false
    $word.DisplayAlerts = $false
    $doc = $word.Documents.Open("{abs_filepath}")
    
    # 设置打印机
    try {{
        $word.ActivePrinter = "{printer_name}"
    }} catch {{
        Write-Host "无法设置打印机，使用默认打印机"
    }}
    
    # 循环打印指定份数
    for ($i = 1; $i -le {copies}; $i++) {{
        $doc.PrintOut([ref]$false, [ref]$false, [ref]0, [ref]"", [ref]1, [ref]1, [ref]"", [ref]1)
        Start-Sleep -Seconds 2
    }}
    
    $doc.Close([ref]$false)
    $word.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($word) | Out-Null
    Write-Host "Word文档打印完成"
}} catch {{
    Write-Host "Word打印失败: $_"
    if ($word) {{
        try {{ $word.Quit() }} catch {{}}
    }}
    exit 1
}}
'''
        elif file_ext in ['.xls', '.xlsx']:
            # 使用Excel COM对象
            ps_script = f'''
try {{
    $excel = New-Object -ComObject Excel.Application
    $excel.Visible = $false
    $excel.DisplayAlerts = $false
    $workbook = $excel.Workbooks.Open("{abs_filepath}")
    
    # 设置打印机
    try {{
        $excel.ActivePrinter = "{printer_name}"
    }} catch {{
        Write-Host "无法设置打印机，使用默认打印机"
    }}
    
    # 循环打印指定份数
    for ($i = 1; $i -le {copies}; $i++) {{
        $workbook.PrintOut()
        Start-Sleep -Seconds 2
    }}
    
    $workbook.Close([ref]$false)
    $excel.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($excel) | Out-Null
    Write-Host "Excel文档打印完成"
}} catch {{
    Write-Host "Excel打印失败: $_"
    if ($excel) {{
        try {{ $excel.Quit() }} catch {{}}
    }}
    exit 1
}}
'''
        elif file_ext in ['.ppt', '.pptx']:
            # 使用PowerPoint COM对象
            ps_script = f'''
try {{
    $ppt = New-Object -ComObject PowerPoint.Application
    $ppt.Visible = $false
    $presentation = $ppt.Presentations.Open("{abs_filepath}")
    
    # 设置打印机（PowerPoint）
    try {{
        # PowerPoint使用ActivePrinter属性
        $ppt.ActivePrinter = "{printer_name}"
    }} catch {{
        Write-Host "PowerPoint无法设置打印机，使用默认打印机"
    }}
    
    # 循环打印指定份数
    for ($i = 1; $i -le {copies}; $i++) {{
        $presentation.PrintOut()
        Start-Sleep -Seconds 2
    }}
    
    $presentation.Close()
    $ppt.Quit()
    [System.Runtime.Interopservices.Marshal]::ReleaseComObject($ppt) | Out-Null
    Write-Host "PowerPoint文档打印完成"
}} catch {{
    Write-Host "PowerPoint打印失败: $_"
    if ($ppt) {{
        try {{ $ppt.Quit() }} catch {{}}
    }}
    exit 1
}}
'''
        else:
            return print_file_silent_fallback(filepath, printer_name, copies)
        
        # 执行PowerShell脚本，添加超时和错误处理
        result = subprocess.run(['powershell', '-WindowStyle', 'Hidden', '-Command', ps_script],
                              capture_output=True, text=True,
                              creationflags=subprocess.CREATE_NO_WINDOW,
                              timeout=120)  # 2分钟超时
        
        if result.returncode == 0:
            return True, f"Office文档COM打印完成 ({copies}份)"
        else:
            print(f"PowerShell COM打印失败: {result.stderr}")
            return print_file_silent_fallback(filepath, printer_name, copies)
        
    except subprocess.TimeoutExpired:
        return False, "Office COM打印超时"
    except Exception as e:
        print(f"COM打印异常: {e}")
        return print_file_silent_fallback(filepath, printer_name, copies)

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
    Write-Host "HTML打印失败: $_"
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
                    duplex_support = duplex_caps == 1
                    print(f"双面打印支持: {duplex_support} (DeviceCapabilities返回: {duplex_caps})")
                except Exception as e:
                    print(f"检查双面打印支持失败: {e}")
                    duplex_support = False
                
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
        data = request.get_json()
        if not data or 'filename' not in data:
            return jsonify({'success': False, 'error': '未提供文件名'})
        
        filename = data['filename']
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        
        # 检查文件是否存在
        if not os.path.exists(filepath):
            return jsonify({'success': False, 'error': '文件不存在或已被删除'})
        
        # 删除文件
        os.remove(filepath)
        
        # 记录删除日志
        log_message = f"{datetime.now()} 用户删除文件: {filename}"
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_message + "\n")
        
        return jsonify({
            'success': True,
            'message': f'文件 {filename} 已删除'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': str(e)
        })

@app.route('/api/delete_all_files', methods=['POST'])
def delete_all_files_api():
    """API端点：清空队列中的所有文件"""
    try:
        files = os.listdir(UPLOAD_FOLDER)
        deleted_count = 0
        
        for filename in files:
            try:
                filepath = os.path.join(UPLOAD_FOLDER, filename)
                if os.path.isfile(filepath):
                    os.remove(filepath)
                    deleted_count += 1
            except Exception as e:
                print(f"删除文件 {filename} 时出错: {e}")
        
        # 记录删除日志
        log_message = f"{datetime.now()} 用户清空队列: 删除了 {deleted_count} 个文件"
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(log_message + "\n")
        
        return jsonify({
            'success': True,
            'count': deleted_count,
            'message': f'已删除 {deleted_count} 个文件'
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

@app.route('/api/system_diagnosis')
def system_diagnosis():
    """系统诊断API"""
    try:
        # 导入修复工具
        from windows_repair_tool import WindowsFixTool
        
        tool = WindowsFixTool()
        diagnosis = tool.diagnose()
        
        return jsonify({
            'success': True,
            'system_info': diagnosis['system_info'],
            'issues': diagnosis['issues'],
            'fixes_available': diagnosis['fixes_available']
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'系统诊断失败: {str(e)}'
        })

@app.route('/api/apply_fixes', methods=['POST'])
def apply_fixes():
    """应用修复API"""
    try:
        from windows_repair_tool import WindowsFixTool
        
        data = request.get_json() or {}
        fix_types = data.get('fixes', [])
        
        tool = WindowsFixTool()
        # 先诊断获取问题列表
        tool.diagnose()
        
        # 应用修复
        results = tool.apply_fixes(fix_types if fix_types else None)
        
        return jsonify({
            'success': True,
            'results': results,
            'message': f'修复完成，成功应用 {sum(1 for r in results.values() if r.get("success"))} 项修复'
        })
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'应用修复失败: {str(e)}'
        })

@app.route('/api/run_repair_tool')
def run_repair_tool():
    """运行修复工具"""
    try:
        import subprocess
        import sys
        
        repair_script = os.path.join(os.path.dirname(__file__), 'windows_repair_tool.py')
        
        if not os.path.exists(repair_script):
            return jsonify({
                'success': False,
                'error': '修复工具脚本不存在'
            })
        
        # 在新窗口中运行修复工具
        if os.name == 'nt':  # Windows
            subprocess.Popen([sys.executable, repair_script], 
                           creationflags=subprocess.CREATE_NEW_CONSOLE)
        else:
            subprocess.Popen([sys.executable, repair_script])
        
        return jsonify({
            'success': True,
            'message': '修复工具已启动'
        })
        
    except Exception as e:
        return jsonify({
            'success': False,
            'error': f'启动修复工具失败: {str(e)}'
        })
 
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
    
    # 获取IP配置信息
    ip_config = get_current_ip_config()
    suggested_ip = suggest_static_ip()
    
    # 检查环境状态
    env_status = None
    try:
        missing_modules, missing_components = check_system_requirements()
        if missing_components:
            env_status = {
                'type': 'warning',
                'icon': 'exclamation-triangle',
                'title': '系统组件提醒',
                'message': f"""检测到可能缺少以下组件：{', '.join(missing_components)}<br>
如果遇到问题，建议安装：<br>
• <a href="https://aka.ms/vs/17/release/vc_redist.x64.exe" target="_blank">Microsoft Visual C++ Redistributable x64</a><br>
• <a href="https://dotnet.microsoft.com/download/dotnet-framework/net48" target="_blank">.NET Framework 4.8</a>"""
            }
        elif hasattr(sys, '_MEIPASS'):
            env_status = {
                'type': 'info',
                'icon': 'info-circle',
                'title': 'exe版本运行中',
                'message': '当前使用的是打包版本，如遇问题请确保以管理员权限运行，并检查杀毒软件设置。'
            }
    except Exception:
        pass
    
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
        action = request.form.get('action', 'print')
        
        if action == 'set_static_ip':
            # 处理设置静态IP请求
            ip_address = request.form.get('ip_address', '').strip()
            subnet_mask = request.form.get('subnet_mask', '255.255.255.0').strip()
            gateway = request.form.get('gateway', '').strip()
            
            if not ip_address:
                flash("请输入有效的IP地址", "danger")
            else:
                # 验证IP地址格式
                try:
                    import ipaddress
                    ipaddress.IPv4Address(ip_address)
                    if subnet_mask:
                        ipaddress.IPv4Address(subnet_mask)
                    if gateway:
                        ipaddress.IPv4Address(gateway)
                    
                    success, message = set_static_ip(ip_address, subnet_mask, gateway)
                    if success:
                        flash(message, "success")
                        # 更新IP配置信息
                        time.sleep(2)  # 等待网络配置生效
                        ip_config = get_current_ip_config()
                    else:
                        flash(message, "danger")
                        
                except Exception as e:
                    flash(f"IP地址格式无效: {str(e)}", "danger")
            
            return redirect(url_for('upload_file'))
            
        elif action == 'enable_dhcp':
            # 处理启用DHCP请求
            success, message = set_dhcp()
            if success:
                flash(message, "success")
                # 更新IP配置信息
                time.sleep(2)  # 等待网络配置生效
                ip_config = get_current_ip_config()
            else:
                flash(message, "danger")
            
            return redirect(url_for('upload_file'))
            
        elif action == 'print':
            # 处理打印请求（原有逻辑）
            printer = request.form.get('printer')
            copies = int(request.form.get('copies', 1))
            duplex = int(request.form.get('duplex', 1))
            papersize = request.form.get('papersize', '9')  # 默认A4 ID
            quality = request.form.get('quality', '600x600')
            uploaded_files = request.files.getlist('file')
            
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
             
            for f in uploaded_files:
                if f and allowed_file(f.filename):
                    # 确保文件名唯一，避免覆盖
                    filename = f.filename
                    filepath = os.path.join(UPLOAD_FOLDER, filename)
                    counter = 1
                    max_attempts = 100
                    while os.path.exists(filepath) and counter <= max_attempts:
                        name, ext = os.path.splitext(filename)
                        filepath = os.path.join(UPLOAD_FOLDER, f"{name}_{counter}{ext}")
                        counter += 1
                    if os.path.exists(filepath):
                        flash("文件名唯一性尝试超过最大次数，请重命名后再上传！", "danger")
                        return redirect(url_for('upload_file'))
                     
                    # 保存文件到uploads文件夹
                    f.save(filepath)
                     
                    try:
                        # 根据文件类型选择最佳的静默打印方案
                        file_ext = os.path.splitext(filepath)[1].lower()
                        
                        if file_ext == '.pdf':
                            # PDF文件使用专门的静默打印方法
                            success, message = print_pdf_silent(filepath, printer, copies)
                        elif file_ext in ['.jpg', '.jpeg', '.png']:
                            # 图片文件使用专门的静默打印方法
                            success, message = print_image_silent(filepath, printer, copies)
                        elif file_ext in ['.doc', '.docx', '.xls', '.xlsx', '.ppt', '.pptx']:
                            # Office文档使用专门的静默打印方法
                            success, message = print_office_silent(filepath, printer, copies)
                        else:
                            # 其他文件使用通用静默打印方法
                            success, message = print_file_with_settings(
                                filepath, printer, copies, duplex, papersize, quality
                            )
                        
                        if success:
                            flash(f"✅ {os.path.basename(filepath)} {message}", "success")
                            log_print(os.path.basename(filepath), printer, copies, duplex, papersize, quality)
                        else:
                            flash(f"❌ 打印失败: {message}", "danger")
                            log_print(os.path.basename(filepath) + f" 失败: {message}", printer, copies, duplex, papersize, quality)
                            
                    except Exception as e:
                        error_msg = f"打印异常: {str(e)}"
                        log_print(os.path.basename(filepath) + " " + error_msg, printer, copies, duplex, papersize, quality)
                        flash(f"⚠️ {error_msg}", "danger")
             
            return redirect(url_for('upload_file'))
    
    # 获取默认打印机
    default_printer = get_default_printer()
    
    # 获取端口配置信息
    current_port = getattr(app, 'current_port', 5000)
    config_port = get_config_port()
    port_from_config = (current_port == config_port)
    
    return render_template_string(HTML, printers=PRINTERS, files=files, logs=logs, 
                                ip_config=ip_config, suggested_ip=suggested_ip, 
                                printer_caps=printer_caps, default_printer=default_printer,
                                env_status=env_status, current_port=current_port,
                                port_from_config=port_from_config)
 
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
    app.run(host='0.0.0.0', port=port)

def run_wsgi():
    # 生产环境推荐使用 waitress
    try:
        from waitress import serve
        port = getattr(app, 'current_port', 5000)
        serve(app, host='0.0.0.0', port=port)
    except ImportError:
        print("Waitress未安装，使用Flask内置服务器")
        port = getattr(app, 'current_port', 5000)
        app.run(host='0.0.0.0', port=port)
 
 
def on_quit(icon, item):
    print("🔄 正在退出程序...")
    
    # 停止托盘图标
    icon.stop()
    
    # 尝试优雅关闭Flask应用（如果有全局引用的话）
    try:
        if hasattr(app, 'shutdown'):
            app.shutdown()
    except:
        pass
    
    # 强制终止所有线程
    import threading
    import os
    
    # 获取所有活跃线程
    active_threads = threading.enumerate()
    print(f"发现 {len(active_threads)} 个活跃线程")
    
    for t in active_threads:
        if t is not threading.current_thread():
            thread_name = getattr(t, 'name', 'Unknown')
            print(f"正在等待线程: {thread_name}")
            try:
                # 给每个线程1秒时间完成
                t.join(timeout=1)
                if t.is_alive():
                    print(f"线程 {thread_name} 未能在1秒内退出")
            except Exception as e:
                print(f"等待线程退出时出错: {e}")
    
    # 强制退出进程
    print("✅ 强制退出程序")
    try:
        # 使用os._exit确保立即退出，不执行清理代码
        os._exit(0)
    except:
        # 如果os._exit失败，使用sys.exit
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
    """在浏览器中打开网络配置页面"""
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
• 端口设置会在程序重启后自动应用
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
                    f"将端口从 {current_port} 更改为 {new_port}\n"
                    f"需要重启服务才能生效，是否继续？"
                )
                
                if result:
                    # 保存新端口到配置文件
                    if save_port_config(new_port):
                        messagebox.showinfo(
                            "端口更改成功", 
                            f"端口已更改为: {new_port}\n"
                            f"新的访问地址: http://{get_local_ip()}:{new_port}\n"
                            f"配置已保存，下次启动将自动使用新端口\n"
                            f"程序将在3秒后重启..."
                        )
                    else:
                        messagebox.showwarning(
                            "端口更改成功", 
                            f"端口已更改为: {new_port}，但配置保存失败\n"
                            f"下次启动可能恢复默认端口\n"
                            f"程序将在3秒后重启..."
                        )
                    
                    # 重启程序
                    import subprocess
                    import sys
                    root.destroy()
                    icon.stop()
                    
                    # 启动新的实例（不再需要传递端口参数，因为已保存到配置文件）
                    subprocess.Popen([sys.executable] + sys.argv)
                    sys.exit(0)
                    
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
        pystray.MenuItem('开机自启：' + ('已开启' if autostart else '未开启'), on_toggle_autostart),
        pystray.Menu.SEPARATOR,
        # 只有在exe模式下才显示控制台控制选项
        *([pystray.MenuItem(
            '控制台：' + ('已显示' if CONSOLE_VISIBLE else '已隐藏'), 
            toggle_console_window
        ), pystray.Menu.SEPARATOR] if hasattr(sys, '_MEIPASS') else []),
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
                resource_path('logo.ico'),  # 打包内的资源
                os.path.join(os.path.dirname(sys.executable), 'logo.ico'),  # exe同级目录
            ])
        else:
            # 源码运行时的路径
            candidate_paths.extend([
                resource_path('logo.ico'),
                os.path.join(os.path.dirname(os.path.abspath(__file__)), 'logo.ico'),
                os.path.join(os.getcwd(), 'logo.ico'),
            ])
        
        # 通用备选路径
        candidate_paths.extend([
            'logo.ico',  # 当前工作目录
            os.path.join(APP_DIR, 'logo.ico'),  # 程序目录
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

def check_system_requirements():
    """检查系统要求和环境"""
    missing_modules = []
    missing_system_components = []
    
    # 检查Python模块
    try:
        import win32print
        import win32api
        import win32gui
        import win32con
    except ImportError:
        missing_modules.append("pywin32")
    
    try:
        import pystray
        from PIL import Image
    except ImportError:
        missing_modules.append("pystray 和 Pillow")
    
    try:
        from flask import Flask
    except ImportError:
        missing_modules.append("flask")
    
    # 检查Microsoft Visual C++ Redistributable
    try:
        import ctypes
        import ctypes.util
        
        # 尝试加载常见的VC++运行库
        vc_libs = [
            'msvcr120.dll',  # Visual C++ 2013
            'vcruntime140.dll',  # Visual C++ 2015-2022
            'msvcp140.dll',  # Visual C++ 2015-2022
            'api-ms-win-crt-runtime-l1-1-0.dll'  # Universal CRT
        ]
        
        missing_vc = []
        for lib in vc_libs:
            if not ctypes.util.find_library(lib.replace('.dll', '')):
                try:
                    ctypes.windll.LoadLibrary(lib)
                except:
                    if lib not in missing_vc:
                        missing_vc.append(lib)
        
        if missing_vc:
            missing_system_components.append("Microsoft Visual C++ Redistributable")
    
    except Exception:
        # 如果检测失败，建议用户检查
        missing_system_components.append("Microsoft Visual C++ Redistributable (检测失败，建议检查)")
    
    # 检查.NET Framework (某些功能可能需要)
    try:
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                              r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full") as key:
                version, _ = winreg.QueryValueEx(key, "Version")
                if not version or version < "4.6":
                    missing_system_components.append(".NET Framework 4.6 或更高版本")
        except FileNotFoundError:
            missing_system_components.append(".NET Framework 4.6 或更高版本")
    except Exception:
        pass
    
    # 检查Windows版本
    try:
        import platform
        windows_version = platform.version()
        major_version = int(windows_version.split('.')[0])
        if major_version < 10:  # Windows 10 = version 10.0
            missing_system_components.append("Windows 10 或更高版本 (当前版本可能不完全兼容)")
    except Exception:
        pass
    
    return missing_modules, missing_system_components

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

def show_startup_tips():
    """显示启动提示和常见问题解决方案"""
    tips_msg = """🚀 内网打印服务启动成功！

� 开发者：忆痕
🔗 项目地址：https://github.com/a937750307/lan-printing

�📝 使用提示：
• 在浏览器中访问服务地址进行打印
• 右键托盘图标可进行更多设置
• 支持拖拽文件到网页进行打印

❗ 如果遇到问题：

1. 无法访问网页？
   • 检查防火墙设置
   • 确认IP地址和端口正确
   • 尝试使用 http://127.0.0.1:端口号

2. 找不到打印机？
   • 确保打印机已连接并开机
   • 检查打印机驱动是否安装
   • 点击网页中的"刷新"按钮

3. 打印失败？
   • 确认打印机状态正常
   • 检查是否选择了虚拟打印机
   • 尝试重启打印机和程序

4. 程序无法启动？
   • 安装 Microsoft Visual C++ Redistributable
   • 以管理员权限运行
   • 检查杀毒软件是否误报

💡 更多帮助：https://github.com/a937750307/lan-printing
📧 问题反馈：请在GitHub Issues中提交"""
    
    show_error_dialog("启动成功 - 使用提示", tips_msg, is_critical=False)

def check_exe_environment():
    """检查exe运行环境，针对PyInstaller打包的程序，特别针对Win11兼容性"""
    if not hasattr(sys, '_MEIPASS'):  # 不是PyInstaller打包的exe
        return []
    
    issues = []
    
    try:
        # Win11兼容性检查
        import platform
        windows_version = platform.platform()
        print(f"🖥️ 系统信息: {windows_version}")
        
        # 检查是否为Windows 11
        if "Windows-11" in windows_version or "Windows-10" in windows_version:
            try:
                # Win11特有检查：Windows Defender和SmartScreen
                import subprocess
                
                # 检查程序是否被Windows Defender隔离
                try:
                    result = subprocess.run(['powershell', '-Command', 'Get-MpThreatDetection'], 
                                          capture_output=True, text=True, timeout=10)
                    if result.returncode == 0 and 'print_server' in result.stdout.lower():
                        issues.append("程序可能被Windows Defender隔离，请添加到排除列表")
                except:
                    pass
                
                # 检查数字签名问题（Win11常见）
                exe_path = sys.executable if hasattr(sys, '_MEIPASS') else __file__
                print(f"📁 程序路径: {exe_path}")
                
                # 检查路径中是否包含中文或特殊字符
                try:
                    exe_path.encode('ascii')
                except UnicodeEncodeError:
                    issues.append("程序路径包含中文字符，可能在Win11下引起兼容性问题")
                
            except Exception as e:
                print(f"⚠️ Win11兼容性检查部分失败: {e}")
        
        # 检查依赖库是否完整
        critical_imports = [
            ('win32print', 'pywin32'),
            ('win32api', 'pywin32'),
            ('win32gui', 'pywin32'),
            ('pystray', 'pystray'),
            ('PIL', 'Pillow'),
            ('flask', 'Flask')
        ]
        
        missing_libs = []
        for lib, package in critical_imports:
            try:
                __import__(lib)
                print(f"✅ {lib} 库加载成功")
            except ImportError:
                missing_libs.append(package)
                print(f"❌ {lib} 库缺失")
        
        if missing_libs:
            issues.append(f"缺少关键依赖库: {', '.join(missing_libs)}")
    
    except Exception as e:
        print(f"⚠️ 依赖库检查失败: {e}")
    
    try:
        # 检查程序目录是否有写入权限
        app_dir = get_app_dir()
        print(f"📁 程序目录: {app_dir}")
        test_file = os.path.join(app_dir, 'test_write.tmp')
        try:
            with open(test_file, 'w') as f:
                f.write('test')
            os.remove(test_file)
            print("✅ 程序目录写入权限正常")
        except Exception as e:
            issues.append(f"程序目录 {app_dir} 无写入权限: {e}")
            print(f"❌ 程序目录写入权限异常: {e}")
    
    except Exception as e:
        print(f"⚠️ 目录权限检查失败: {e}")
    
    try:
        # 检查临时目录权限
        temp_dir = os.environ.get('TEMP', 'C:\\temp')
        print(f"📁 临时目录: {temp_dir}")
        test_temp = os.path.join(temp_dir, 'print_server_test.tmp')
        try:
            with open(test_temp, 'w') as f:
                f.write('test')
            os.remove(test_temp)
            print("✅ 临时目录访问正常")
        except Exception as e:
            issues.append(f"临时目录访问受限: {e}")
            print(f"❌ 临时目录访问异常: {e}")
    
    except Exception as e:
        print(f"⚠️ 临时目录检查失败: {e}")
    
    try:
        # 检查网络权限
        import socket
        test_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        test_socket.bind(('127.0.0.1', 0))  # 绑定任意可用端口
        test_port = test_socket.getsockname()[1]
        test_socket.close()
        print(f"✅ 网络端口 {test_port} 绑定测试成功")
        
    except Exception as e:
        issues.append(f"网络权限受限，无法绑定端口: {e}")
        print(f"❌ 网络权限检查失败: {e}")
    
    try:
        # 检查防火墙设置（Win11常见问题）
        import subprocess
        
        # 检查程序是否在防火墙例外列表中
        try:
            result = subprocess.run(['netsh', 'advfirewall', 'firewall', 'show', 'rule', 'name=all'], 
                                  capture_output=True, text=True, timeout=10)
            if result.returncode != 0:
                print("⚠️ 无法检查防火墙设置，可能需要管理员权限")
            else:
                print("✅ 防火墙设置检查完成")
        except:
            print("⚠️ 防火墙检查跳过")
            
    except Exception as e:
        print(f"⚠️ 防火墙检查失败: {e}")
    
    # 输出检查结果摘要
    if issues:
        print(f"\n⚠️ 发现 {len(issues)} 个潜在问题:")
        for i, issue in enumerate(issues, 1):
            print(f"   {i}. {issue}")
    else:
        print(f"\n✅ 环境检查通过，未发现明显问题")
    
    return issues

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
            
            exe_issues = check_exe_environment()
            if exe_issues:
                error_msg = """exe文件运行环境检查发现问题：

问题：
""" + '\n'.join(f"• {issue}" for issue in exe_issues) + """

🔧 Win11用户专用解决方案：
1. 【首选】右键程序图标 → "以管理员身份运行"
2. 【重要】检查Windows Defender设置：
   • 打开"Windows安全中心"
   • 选择"病毒和威胁防护"
   • 点击"管理设置"
   • 添加"排除项" → "文件或文件夹" → 选择程序目录
3. 【路径问题】将程序移动到英文路径：
   • 避免中文文件夹名称
   • 推荐路径：C:\\Tools\\PrintService\\
4. 【SmartScreen】如遇"Windows已保护你的电脑"：
   • 点击"更多信息" → "仍要运行"
   • 或在"应用和浏览器控制"中调整设置

🔧 通用解决方案：
5. 安装最新的 Microsoft Visual C++ Redistributable
6. 检查杀毒软件是否误报
7. 重启计算机后再次运行
8. 使用"兼容性疑难解答"

💾 下载链接：
• VC++ x64: https://aka.ms/vs/17/release/vc_redist.x64.exe
• VC++ x86: https://aka.ms/vs/17/release/vc_redist.x86.exe

📞 如果问题持续，请携带错误信息联系：
GitHub Issues: https://github.com/a937750307/lan-printing/issues

开发者：忆痕"""
                
                show_error_dialog("exe运行环境检查", error_msg, is_critical=False)
        
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
        print(f"📂 程序目录: {APP_DIR}")
        print(f"📂 上传目录: {UPLOAD_FOLDER}")
        print(f"📂 配置文件: {CONFIG_FILE}")
        print(f"📂 日志文件: {LOG_FILE}")
        if hasattr(sys, '_MEIPASS'):
            print(f"📦 运行模式: PyInstaller打包 (资源目录: {sys._MEIPASS})")
        else:
            print(f"📦 运行模式: 源码运行")
        
        # 显示端口信息
        config_port = get_config_port()
        if port == config_port:
            print(f"🔧 使用配置端口: {port}")
        else:
            print(f"🔧 使用临时端口: {port} (配置端口: {config_port})")
        
        # 检查系统要求
        missing_modules, missing_components = check_system_requirements()
        
        if missing_modules or missing_components:
            error_parts = []
            
            if missing_modules:
                error_parts.append(f"""Python依赖包缺失：
缺少的包: {', '.join(missing_modules)}

安装方法：
pip install pywin32 pystray pillow flask""")
            
            if missing_components:
                error_parts.append(f"""系统组件缺失：
缺少的组件: {', '.join(missing_components)}

下载链接：
• Microsoft Visual C++ Redistributable:
  https://aka.ms/vs/17/release/vc_redist.x64.exe
  
• .NET Framework 4.8:
  https://dotnet.microsoft.com/download/dotnet-framework/net48""")
            
            error_msg = f"""运行此程序需要以下组件：

{chr(10).join(error_parts)}

完整解决方案：
1. 【推荐】下载完整的exe版本（已包含所有依赖）
   下载地址：https://github.com/a937750307/lan-printing/releases

2. 【手动修复】按上述链接安装缺失组件
   - 以管理员权限运行安装程序
   - 重启计算机后重新运行本程序

3. 【开发环境】如果使用Python源码：
   pip install -r requirements.txt

常见问题：
• 如果是exe文件报错，通常是缺少VC++运行库
• Windows 7用户需要额外安装更新补丁
• 杀毒软件可能误报，请添加信任

技术支持：https://github.com/a937750307/lan-printing"""
            
            show_error_dialog("系统环境检查", error_msg)
            
            # 即使有缺失组件，也尝试继续运行（可能部分功能可用）
            if missing_modules:  # 如果缺少Python模块，则必须退出
                sys.exit(1)
            else:
                print("⚠️ 检测到系统组件缺失，但将尝试继续运行...")
                print("   如果遇到问题，请按提示安装缺失组件")
        else:
            print("✅ 系统环境检查通过")
        
        # 检测网络状态
        local_ip = get_local_ip()
        if local_ip == '127.0.0.1':
            print("⚠️  网络状态: 离线模式")
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
            print(f"✅ 网络状态: 在线 (IP: {local_ip})")
            print("   - 完整功能可用")
            print("   - 可获取实时打印机参数")
        
        print(f"🖨️  检测到 {len(PRINTERS)} 台物理打印机")
        if PRINTERS:
            for i, printer in enumerate(PRINTERS[:3], 1):  # 只显示前3台
                print(f"   {i}. {printer}")
            if len(PRINTERS) > 3:
                print(f"   ... 还有 {len(PRINTERS) - 3} 台打印机")
        else:
            print("   ⚠️  未检测到可用的物理打印机")
            print("   ℹ️  程序仍可运行，但打印功能可能受限")
            print("   💡 请检查:")
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
        
        print("🌐 服务器将启动在: http://{}:{}".format(local_ip, port))
        print("=" * 60)
        
        # 检查Windows功能和服务
        issues, suggestions = check_windows_features()
        if issues:
            print("⚠️ 检测到以下问题：")
            for issue in issues:
                print(f"   - {issue}")
            print("💡 建议解决方案：")
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
        cleaner_thread = threading.Thread(target=clean_old_files, daemon=True)
        cleaner_thread.start()
        
        # 判断是否为生产环境
        if os.environ.get('USE_WSGI', '').lower() == 'true':
            flask_thread = threading.Thread(target=run_wsgi, daemon=True)
        else:
            flask_thread = threading.Thread(target=run_flask, daemon=True)
        flask_thread.start()
        
        # 等待Flask服务启动
        print("⏳ 正在启动Web服务...")
        time.sleep(2)
        
        # 显示启动成功提示
        if local_ip != '127.0.0.1' and len(PRINTERS) > 0:
            print("🎉 启动完成！可以开始使用打印服务了")
            print(" 访问地址：http://{}:{}".format(local_ip, port))
            print("💡 右键托盘图标查看更多功能")
            
            # 首次启动时显示详细提示
            startup_tip_file = os.path.join(APP_DIR, '.startup_tip_shown')
            if not os.path.exists(startup_tip_file):
                show_startup_tips()
                # 创建标记文件，避免每次启动都显示
                try:
                    with open(startup_tip_file, 'w') as f:
                        f.write('shown')
                except:
                    pass
        
        setup_tray()
        
    except KeyboardInterrupt:
        print("\n🔄 程序被用户中断，正在退出...")
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
