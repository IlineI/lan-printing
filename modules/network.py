#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""网络相关功能：IP获取、静态IP/DHCP设置、网络模式检测"""

import os
import socket
import subprocess
import time

from modules.config import IP_CONFIG_STATE


def get_local_ip():
    """获取本机IP地址 - 支持内网穿透"""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(2)
        s.connect(('8.8.8.8', 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        try:
            hostname = socket.gethostname()
            ip = socket.gethostbyname(hostname)
            if ip and ip != '127.0.0.1':
                return ip
        except Exception:
            pass
        
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(('8.8.8.8', 80))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith('127.') and not ip.startswith('169.254.'):
                return ip
        except Exception:
            pass
        return '127.0.0.1'


def get_external_ip():
    """获取公网IP地址（用于内网穿透检测）"""
    import urllib.request
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
                if external_ip and '.' in external_ip and not external_ip.startswith(('192.168.', '10.', '172.')):
                    return external_ip
        except Exception:
            continue
    return None


def detect_network_mode():
    """检测网络模式：内网/公网/内网穿透"""
    local_ip = get_local_ip()
    is_private = (local_ip.startswith(('192.168.', '10.', '172.')) or local_ip == '127.0.0.1')
    if not is_private:
        return "public"
    elif local_ip == '127.0.0.1':
        return "private"
    else:
        return "private"


def get_current_ip_config():
    """获取当前IP配置状态 - 极简版本"""
    try:
        current_ip = get_local_ip()
        if current_ip and current_ip != '127.0.0.1':
            dhcp_enabled = not IP_CONFIG_STATE.get('is_static', False)
            return {
                'index': '1',
                'description': '网络适配器',
                'ip': current_ip,
                'subnet': '255.255.255.0',
                'gateway': '',
                'dhcp_enabled': dhcp_enabled
            }
        else:
            return {}
    except Exception as e:
        print(f"获取IP配置失败: {e}")
        return {}


def set_static_ip(ip_address, subnet_mask='255.255.255.0', gateway=''):
    """设置静态IP地址 - 简易版本"""
    global IP_CONFIG_STATE
    try:
        if not gateway:
            ip_parts = ip_address.split('.')
            if len(ip_parts) == 4:
                gateway = f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.1"
        print(f"设置静态IP: {ip_address}, 网关: {gateway}")
        adapter_names = ['以太网', 'Ethernet', '本地连接', 'WLAN', 'Wi-Fi']
        for name in adapter_names:
            try:
                cmd = f'netsh interface ip set address name="{name}" static {ip_address} {subnet_mask} {gateway}'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='gbk')
                if result.returncode == 0:
                    print(f"设置成功: {name}")
                    IP_CONFIG_STATE['is_static'] = True
                    IP_CONFIG_STATE['last_set_ip'] = ip_address
                    time.sleep(2)
                    return True, f"静态IP设置成功"
            except Exception:
                continue
        return False, "未找到可用的网络适配器或设置失败"
    except Exception as e:
        return False, f"设置失败: {str(e)}"


def set_dhcp():
    """启用DHCP动态获取IP - 简易版本"""
    global IP_CONFIG_STATE
    try:
        print("启用DHCP...")
        adapter_names = ['以太网', 'Ethernet', '本地连接', 'WLAN', 'Wi-Fi']
        for name in adapter_names:
            try:
                cmd = f'netsh interface ip set address name="{name}" dhcp'
                result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='gbk')
                if result.returncode == 0:
                    print(f"DHCP设置成功: {name}")
                    IP_CONFIG_STATE['is_static'] = False
                    IP_CONFIG_STATE['last_set_ip'] = None
                    time.sleep(3)
                    return True, f"已启用DHCP动态获取IP"
            except Exception:
                continue
        return False, "未找到可用的网络适配器或启用DHCP失败"
    except Exception as e:
        return False, f"启用DHCP失败: {str(e)}"


def suggest_static_ip():
    """建议一个可用的静态IP地址"""
    current_ip = get_local_ip()
    if current_ip and current_ip != '127.0.0.1':
        ip_parts = current_ip.split('.')
        if len(ip_parts) == 4:
            return f"{ip_parts[0]}.{ip_parts[1]}.{ip_parts[2]}.100"
    return "192.168.1.100"


def detect_remote_desktop():
    """检测是否在远程桌面环境中运行"""
    try:
        session_name = os.environ.get('SESSIONNAME', '')
        if session_name.startswith('RDP-Tcp'):
            return True
        
        client_name = os.environ.get('CLIENTNAME', '')
        if client_name and client_name != os.environ.get('COMPUTERNAME', ''):
            return True
        
        ts_session = os.environ.get('TS_SESSION_ID', '')
        if ts_session and ts_session != '0':
            return True
            
        try:
            import ctypes
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
