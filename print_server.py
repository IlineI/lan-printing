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
from PIL import Image
import socket
import winreg
import time

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
UPLOAD_FOLDER = os.path.join(os.path.expanduser('~'), 'Desktop', 'lan-printing-uploads')
LOG_FILE = 'print_log.txt'
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
        .form-control { display: block; width: 100%; padding: 6px 12px; font-size: 14px; line-height: 1.42857143; color: #555; background-color: #fff; border: 1px solid #ccc; border-radius: 4px; box-sizing: border-box; }
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
                            已过滤虚拟打印机，自动选择默认打印机，可手动刷新列表
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
                    <label class="form-label">选择文件（支持PDF/JPG/PNG/DOC/DOCX/PPT/PPTX/XLS/XLSX/TXT，支持多选）</label>
                    <input type="file" name="file" multiple class="form-control">
                </div>
                <div class="col-12 text-end">
                    {% if printers %}
                        <button type="submit" class="btn btn-primary px-4">上传并打印</button>
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
            
            <!-- 智能打印机检测 -->
            <div class="alert alert-success">
                <h6><i class="bi bi-check-circle"></i> 智能参数应用</h6>
                <p class="mb-0 small">系统现在完全使用获取到的真实打印机参数：</p>
                <ul class="mb-0 small mt-2">
                    <li><strong>实时检测:</strong> 切换打印机时自动获取其支持的纸张大小、打印质量等参数</li>
                    <li><strong>参数应用:</strong> 直接使用您选择的打印设置，包括双面、纸张大小、打印质量</li>
                    <li><strong>智能匹配:</strong> 只显示当前打印机实际支持的选项，确保参数有效</li>
                    <li><strong>设备模式:</strong> 通过Windows设备模式直接设置打印参数</li>
                    <li><strong>离线支持:</strong> 即使在未联网状态下，程序也能正常工作并使用默认配置</li>
                </ul>
            </div>

            <h4 class="mt-4">打印队列</h4>
            <table class="table table-sm table-hover align-middle">
                <thead class="table-light"><tr><th>文件名</th><th>操作</th></tr></thead>
                <tbody>
                {% for f in files %}
                    <tr>
                        <td>{{f}}</td>
                        <td><a href="/preview/{{f}}" target="_blank" class="btn btn-outline-secondary btn-sm">预览</a></td>
                    </tr>
                {% endfor %}
                </tbody>
            </table>

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
                        <strong>子网掩码:</strong> {{ip_config.subnet}}
                    </div>
                    <div class="col-md-6">
                        <strong>默认网关:</strong> {{ip_config.gateway}}
                    </div>
                    <div class="col-md-6">
                        <strong>网络适配器:</strong> {{ip_config.description[:30]}}...
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
                                           value="{{suggested_ip}}" placeholder="192.168.1.100">
                                    <div class="form-text">建议使用当前网段的固定IP</div>
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">子网掩码</label>
                                    <input type="text" name="subnet_mask" class="form-control" 
                                           value="255.255.255.0">
                                </div>
                                <div class="mb-3">
                                    <label class="form-label">默认网关</label>
                                    <input type="text" name="gateway" class="form-control" 
                                           placeholder="自动推导（可选）">
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
    if (uploadForm) {
        uploadForm.addEventListener('submit', function(e) {
            const printerSelect = document.getElementById('printerSelect');
            const selectedPrinter = printerSelect ? printerSelect.value : '';
            
            // 检查是否选择了有效的打印机
            if (!selectedPrinter || selectedPrinter === '' || selectedPrinter === '未检测到可用打印机') {
                e.preventDefault();
                alert('请先选择一个有效的打印机！\n\n如果没有看到打印机，请检查：\n1. 打印机是否正确连接\n2. 打印机驱动是否安装\n3. 打印机是否处于联机状态');
                return false;
            }
            
            // 检查是否选择了文件
            const fileInput = document.querySelector('input[type="file"]');
            if (fileInput && fileInput.files.length === 0) {
                e.preventDefault();
                alert('请选择要打印的文件！');
                return false;
            }
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
    """使用ShellExecute进行应用程序调用打印"""
    try:
        success_count = 0
        for i in range(copies):
            try:
                # 使用关联的应用程序打印
                result = win32api.ShellExecute(
                    0,  # hwnd
                    'print',  # operation
                    filepath,  # file
                    None,  # parameters
                    None,  # directory
                    0  # show command (SW_HIDE)
                )
                
                if result > 32:  # ShellExecute成功
                    success_count += 1
                    time.sleep(1)  # 给应用程序时间处理
                else:
                    print(f"ShellExecute失败，错误代码: {result}")
                    
            except Exception as e:
                print(f"打印第{i+1}份时出错: {e}")
                
        if success_count > 0:
            return True, f"通过关联应用程序打印已发送 ({success_count}/{copies}份)"
        else:
            return False, "所有打印尝试都失败了"
            
    except Exception as e:
        return False, f"ShellExecute打印失败: {str(e)}"

def print_file_silent_fallback(filepath, printer_name, copies=1):
    """备用的静默打印方案"""
    try:
        # 方案1: 使用ShellExecute的静默打印
        for i in range(copies):
            win32api.ShellExecute(
                0, 
                'print', 
                filepath, 
                f'/d:"{printer_name}"', 
                '.', 
                win32con.SW_HIDE  # 隐藏窗口
            )
        return True, f"静默打印任务已发送到 {printer_name} ({copies}份)"
        
    except Exception as e1:
        try:
            # 方案2: 使用命令行静默打印
            import tempfile
            
            # 创建批处理文件进行静默打印
            bat_content = f'''@echo off
for /L %%i in (1,1,{copies}) do (
    start /min "" "{filepath}"
)
'''
            with tempfile.NamedTemporaryFile(mode='w', suffix='.bat', delete=False) as bat_file:
                bat_file.write(bat_content)
                bat_file_path = bat_file.name
            
            # 静默执行批处理文件
            subprocess.run([bat_file_path], 
                         creationflags=subprocess.CREATE_NO_WINDOW,
                         shell=True)
            
            # 清理临时文件
            try:
                os.unlink(bat_file_path)
            except:
                pass
                
            return True, f"静默打印任务已发送 ({copies}份) - 备用方案"
            
        except Exception as e2:
            try:
                # 方案3: 最基础的静默方式
                for i in range(copies):
                    subprocess.run(['rundll32.exe', 'mshtml.dll,PrintHTML', filepath],
                                 creationflags=subprocess.CREATE_NO_WINDOW)
                return True, f"基础静默打印已执行 ({copies}份)"
            except Exception as e3:
                return False, f"所有静默打印方案都失败: {str(e3)}"

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
            # 方案2: 使用默认PDF阅读器
            try:
                for i in range(copies):
                    # 使用系统默认PDF阅读器打印
                    result = win32api.ShellExecute(0, 'print', filepath, None, None, 0)
                    if result <= 32:
                        raise Exception(f"ShellExecute失败，错误代码: {result}")
                    time.sleep(3)  # 给应用程序更多时间
                return True, f"默认PDF阅读器打印已发送到 {printer_name} ({copies}份)"
            except Exception as e:
                print(f"默认PDF阅读器打印失败: {e}")
        
        # 方案3: 使用PowerShell和COM对象
        try:
            ps_script = f'''
try {{
    Add-Type -AssemblyName System.Drawing
    Add-Type -AssemblyName System.Windows.Forms
    
    # 尝试使用Edge WebView2打印PDF
    $filepath = "{filepath.replace(chr(92), chr(92)+chr(92))}"
    $printer = "{printer_name}"
    
    for ($i = 1; $i -le {copies}; $i++) {{
        Start-Process -FilePath $filepath -Verb Print -WindowStyle Hidden
        Start-Sleep -Seconds 3
    }}
    
    Write-Output "PDF PowerShell打印完成"
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
                return True, f"PDF PowerShell打印已执行 ({copies}份)"
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
    """简化TXT静默打印：调用ShellExecute进行打印"""
    try:
        sent = 0
        for i in range(copies):
            r = win32api.ShellExecute(0, 'printto', filepath, f'"{printer_name}"', None, 0)
            if r > 32:
                sent += 1
                time.sleep(1)
            else:
                # 回退到普通print
                r2 = win32api.ShellExecute(0, 'print', filepath, None, None, 0)
                if r2 > 32:
                    sent += 1
                    time.sleep(1)
        if sent:
            return True, f"TXT静默打印已发送到 {printer_name} ({sent}/{copies}份)"
        return False, "TXT静默打印失败"
    except Exception as e:
        return False, f"TXT静默打印异常: {e}"

def print_image_silent(filepath, printer_name, copies=1):
    """专门用于图片文件的静默打印，尝试多种方式"""
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
            except Exception:
                pass
            # 方法3：ShellExecute 'print'（默认打印机）
            try:
                r = win32api.ShellExecute(0, 'print', filepath, None, None, 0)
                if r > 32:
                    success_total += 1
                    time.sleep(2)
                    continue
            except Exception:
                pass
        if success_total > 0:
            return True, f"图片静默打印已发送到 {printer_name} ({success_total}/{copies}份)"
        return False, "图片静默打印失败"
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
 
@app.route('/', methods=['GET', 'POST'])
def upload_file():
    files = os.listdir(UPLOAD_FOLDER)
    logs = get_logs()
    
    # 获取IP配置信息
    ip_config = get_current_ip_config()
    suggested_ip = suggest_static_ip()
    
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
    
    return render_template_string(HTML, printers=PRINTERS, files=files, logs=logs, 
                                ip_config=ip_config, suggested_ip=suggested_ip, 
                                printer_caps=printer_caps, default_printer=default_printer)
 
@app.route('/preview/<filename>')
def preview_file(filename):
    fpath = os.path.join(UPLOAD_FOLDER, filename)
    if not os.path.exists(fpath):
        return f'<div class="alert alert-danger">文件未找到或已被自动清理！</div>', 404
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in {'jpg', 'jpeg', 'png'}:
        return send_from_directory(UPLOAD_FOLDER, filename, mimetype=f'image/{ext}')
    elif ext == 'pdf':
        return send_from_directory(UPLOAD_FOLDER, filename, mimetype='application/pdf')
    elif ext == 'txt':
        with open(fpath, 'r', encoding='utf-8') as f:
            return f'<pre>{f.read()}</pre>'
    else:
        return '<div class="alert alert-warning">不支持预览该文件类型</div>'
 
 
def run_flask():
    # 开发环境使用 Flask 内置服务器
    app.run(host='0.0.0.0', port=5000)

def run_wsgi():
    # 生产环境推荐使用 waitress
    try:
        from waitress import serve
        serve(app, host='0.0.0.0', port=5000)
    except ImportError:
        print("Waitress未安装，使用Flask内置服务器")
        app.run(host='0.0.0.0', port=5000)
 
 
def on_quit(icon, item):
    icon.stop()
    # 优雅退出：尝试终止所有后台线程
    import threading
    for t in threading.enumerate():
        if t is not threading.current_thread():
            try:
                t.join(timeout=2)
            except Exception:
                pass
    sys.exit(0)
 
def on_toggle_autostart(icon, item):
    current = get_autostart()
    set_autostart(not current)
    # 刷新菜单
    icon.menu = build_menu(icon)

def on_show_ip_config(icon, item):
    """在浏览器中打开网络配置页面"""
    import webbrowser
    ip = get_local_ip()
    port = 5000
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

def build_menu(icon):
    autostart = get_autostart()
    ip = get_local_ip()
    port = 5000
    ip_config = get_current_ip_config()
    
    # 构建IP状态显示文本
    ip_status = f"当前IP: {ip}"
    if ip_config:
        if ip_config['dhcp_enabled']:
            ip_status += " (DHCP)"
        else:
            ip_status += " (静态)"
    
    return pystray.Menu(
        pystray.MenuItem(f'服务地址: {ip}:{port}', on_show_ip_config),
        pystray.MenuItem(ip_status, None, enabled=False),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('网络配置', pystray.Menu(
            pystray.MenuItem('打开配置页面', on_show_ip_config),
            pystray.MenuItem('设置建议静态IP', on_set_static_ip),
            pystray.MenuItem('启用DHCP', on_enable_dhcp),
        )),
        pystray.MenuItem('开机自启：' + ('已开启' if autostart else '未开启'), on_toggle_autostart),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem('退出', on_quit)
    )
 
def setup_tray():
    # 只使用logo.ico文件作为托盘图标
    try:
        # 加载logo.ico文件
        logo_path = resource_path('logo.ico')
        print(f"尝试加载图标: {logo_path}")
        
        if not os.path.exists(logo_path):
            print(f"错误：logo.ico文件不存在于路径: {logo_path}")
            return
            
        image = Image.open(logo_path)
        print(f"成功加载logo.ico文件，尺寸: {image.size}")
        
        # 创建系统托盘图标
        icon = pystray.Icon('print_server', image, '内网打印服务')
        icon.menu = build_menu(icon)
        print("系统托盘启动成功")
        icon.run()
        
    except Exception as e:
        print(f"系统托盘启动失败: {e}")
        # 如果系统托盘失败，至少保持程序运行
        print("程序将继续运行，但没有系统托盘图标")
        # 保持主线程不退出
        import time
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("程序被用户中断")
            sys.exit(0)

if __name__ == '__main__':
    print("=" * 50)
    print("内网打印服务启动中...")
    print("=" * 50)
    
    # 检测网络状态
    local_ip = get_local_ip()
    if local_ip == '127.0.0.1':
        print("⚠️  网络状态: 离线模式")
        print("   - 程序仍可正常工作")
        print("   - 使用默认打印机配置")
        print("   - 界面样式可能简化")
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
    
    print("🌐 服务器将启动在: http://{}:5000".format(local_ip))
    print("=" * 50)
    
    # 启动定期清理线程
    cleaner_thread = threading.Thread(target=clean_old_files, daemon=True)
    cleaner_thread.start()
    # 判断是否为生产环境
    if os.environ.get('USE_WSGI', '').lower() == 'true':
        flask_thread = threading.Thread(target=run_wsgi, daemon=True)
    else:
        flask_thread = threading.Thread(target=run_flask, daemon=True)
    flask_thread.start()
    setup_tray()
