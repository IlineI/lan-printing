#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""文件清理、上传管理、日志管理"""

import os
import math
import time
import threading
from datetime import datetime, timedelta

from modules import config
from modules.config import ALLOWED_EXT, logger


def allowed_file(filename):
    """检查文件类型是否允许"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


def format_file_size(size_bytes):
    """格式化文件大小"""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB"]
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_names[i]}"


def get_client_info():
    """获取客户端设备信息"""
    try:
        from flask import request
        client_ip = request.remote_addr or '未知IP'
        device_name = None
        
        # 方法0: 优先检查表单中的设备名
        try:
            form_device = request.form.get('device_name') if hasattr(request, 'form') and request.form else None
            if form_device:
                device_name = form_device.strip()
        except Exception:
            pass
        
        # 方法0.5: 检查自定义请求头
        if not device_name:
            custom_device = request.headers.get('X-Device-Name') or request.headers.get('Device-Name')
            if custom_device:
                try:
                    import urllib.parse
                    device_name = urllib.parse.unquote(custom_device.strip())
                except Exception:
                    device_name = custom_device.strip()
        
        # 方法1: User-Agent
        user_agent = request.headers.get('User-Agent', '')
        
        # 方法2: IP反向解析
        try:
            import socket
            if client_ip and client_ip != '127.0.0.1' and client_ip != 'localhost':
                try:
                    hostname = socket.gethostbyaddr(client_ip)[0]
                    if hostname and hostname != client_ip:
                        try:
                            if any(ord(c) > 127 for c in hostname):
                                hostname_safe = hostname.encode('utf-8', errors='ignore').decode('utf-8', errors='ignore')
                                if hostname_safe:
                                    device_name = hostname_safe
                                else:
                                    device_name = hostname
                                print(f"检测到中文计算机名: {hostname}")
                            else:
                                device_name = hostname
                        except Exception as e:
                            print(f"计算机名编码处理异常: {e}，使用原值")
                            device_name = hostname
                except socket.herror:
                    print(f"无法通过DNS反向解析获取计算机名 (IP: {client_ip})")
                except UnicodeDecodeError as e:
                    print(f"计算机名可能包含中文字符，解码失败: {e}")
                except Exception as e:
                    print(f"获取计算机名异常: {type(e).__name__}: {e}")
        except Exception as e:
            print(f"socket操作异常: {type(e).__name__}: {e}")
        
        # 方法3: 从User-Agent中提取设备信息
        if user_agent:
            import re
            if 'android' in user_agent.lower():
                patterns = [
                    r'Android.*?;\s*([^)]+?)\s*Build/',
                    r'Android.*?;\s*(.*?)\)',
                    r'\(([^;]+);\s*wv\)',
                ]
                for pattern in patterns:
                    match = re.search(pattern, user_agent)
                    if match:
                        model = match.group(1).strip()
                        model = re.sub(r'^\w+\s*', '', model)
                        if model and len(model) > 2 and model not in ['Mobile', 'Mobile Safari', 'Safari']:
                            device_name = model
                            break
            elif 'iphone' in user_agent.lower():
                iphone_match = re.search(r'iPhone\s*OS\s*[\d_]+.*?\)', user_agent)
                if iphone_match:
                    cpu_match = re.search(r'iPhone(\d+,\d+)', user_agent)
                    if cpu_match:
                        device_name = f"iPhone({cpu_match.group(1)})"
                    else:
                        device_name = "iPhone"
                else:
                    device_name = "iPhone"
            elif 'ipad' in user_agent.lower():
                ipad_match = re.search(r'iPad(\d+,\d+)', user_agent)
                if ipad_match:
                    device_name = f"iPad({ipad_match.group(1)})"
                else:
                    device_name = "iPad"
            elif 'windows' in user_agent.lower():
                win_match = re.search(r'Windows NT ([\d.]+)', user_agent)
                if win_match:
                    version = win_match.group(1)
                    version_names = {'10.0': 'Win10/11', '6.3': 'Win8.1', '6.2': 'Win8', '6.1': 'Win7'}
                    win_version = version_names.get(version, f'Windows NT {version}')
                    if not device_name:
                        device_name = f"{win_version}电脑"
                else:
                    if not device_name:
                        device_name = "Windows电脑"
            elif 'mac' in user_agent.lower() or 'macintosh' in user_agent.lower():
                mac_match = re.search(r'Mac OS X ([\d_]+)', user_agent)
                if mac_match:
                    mac_version = mac_match.group(1).replace('_', '.')
                    if not device_name:
                        device_name = f"macOS {mac_version}"
                else:
                    if not device_name:
                        device_name = "Mac电脑"
            elif 'linux' in user_agent.lower():
                if not device_name:
                    device_name = "Linux电脑"
        
        if not device_name:
            device_name = "未知设备"
        
        return f"{client_ip}({device_name})"
    except Exception as e:
        return f"未知客户端(获取信息失败: {e})"


def log_print(filename, printer, copies, duplex, papersize, quality, client_info=None):
    """记录打印日志"""
    duplex_text = {
        1: "单面",
        2: "双面(长边翻转)",
        3: "双面(短边翻转)"
    }.get(int(duplex), f"未知({duplex})")
    
    if client_info is None:
        try:
            client_info = get_client_info()
        except:
            client_info = "未知客户端"
    
    try:
        filename_safe = filename.encode('utf-8', errors='replace').decode('utf-8')
        printer_safe = printer.encode('utf-8', errors='replace').decode('utf-8')
        client_info_safe = client_info.encode('utf-8', errors='replace').decode('utf-8')
        
        logger.info(f"客户端: {client_info_safe} 打印: {filename_safe} 打印机: {printer_safe} 份数: {copies} 模式: {duplex_text} 纸张: {papersize} 质量: {quality}")
    except Exception as e:
        logger.warning(f"日志写入失败: {e}")


def log_scan(scanner_name, scan_format, client_info, message):
    """记录扫描操作日志"""
    try:
        logger.info(f"客户端: {client_info} 扫描: 扫描仪={scanner_name} 格式={scan_format} 结果={message}")
    except Exception as e:
        logger.warning(f"记录扫描日志失败: {e}")


def get_scanned_files(path_mgr):
    """获取扫描文件列表"""
    files = []
    try:
        scan_folder = path_mgr.get_scan_dir()
        if not os.path.exists(scan_folder):
            os.makedirs(scan_folder)
            return files
        
        for filename in os.listdir(scan_folder):
            filepath = os.path.join(scan_folder, filename)
            if os.path.isfile(filepath) and not filename.startswith('.'):
                try:
                    stat_result = os.stat(filepath)
                    file_size = stat_result.st_size
                    created_time = datetime.fromtimestamp(stat_result.st_ctime)
                    file_ext = os.path.splitext(filename)[1].lower()
                    
                    if file_ext in ['.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif']:
                        file_type = 'image'
                    elif file_ext == '.pdf':
                        file_type = 'pdf'
                    else:
                        file_type = 'other'
                    
                    files.append({
                        'filename': filename,
                        'filepath': filepath,
                        'size': file_size,
                        'size_str': format_file_size(file_size),
                        'created': created_time.strftime('%Y-%m-%d %H:%M:%S'),
                        'type': file_type,
                        'extension': file_ext
                    })
                except Exception as e:
                    print(f"读取扫描文件 {filename} 信息失败: {e}")
                    continue
        
        files.sort(key=lambda x: x['created'], reverse=True)
    except Exception as e:
        print(f"获取扫描文件列表失败: {e}")
    
    return files


def get_file_list():
    """获取上传文件夹中的文件列表（包含详细信息）"""
    file_list = []
    try:
        if not config.UPLOAD_FOLDER or not os.path.exists(config.UPLOAD_FOLDER):
            return file_list
        
        for filename in os.listdir(config.UPLOAD_FOLDER):
            filepath = os.path.join(config.UPLOAD_FOLDER, filename)
            if os.path.isfile(filepath):
                try:
                    stat = os.stat(filepath)
                    file_size = stat.st_size
                    upload_time = datetime.fromtimestamp(stat.st_mtime)
                    
                    if file_size < 1024:
                        size_str = f"{file_size} B"
                    elif file_size < 1024 * 1024:
                        size_str = f"{file_size / 1024:.1f} KB"
                    else:
                        size_str = f"{file_size / (1024 * 1024):.1f} MB"
                    
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
                    file_list.append({
                        'name': filename,
                        'size': 0,
                        'size_str': 'Unknown',
                        'upload_time': 'Unknown',
                        'extension': 'unknown'
                    })
        
        file_list.sort(key=lambda x: x['upload_time'], reverse=True)
    except Exception as e:
        print(f"获取文件列表时出错: {e}")
    
    return file_list


# ==================== 日志管理 ====================

def get_logs():
    """获取最近的日志"""
    if not config.LOG_FILE or not os.path.exists(config.LOG_FILE):
        return []
    with open(config.LOG_FILE, 'r', encoding='utf-8') as f:
        return f.readlines()[-50:][::-1]


def clean_old_logs():
    """清理旧的打印日志，保留最近的记录"""
    try:
        if not config.LOG_FILE or not os.path.exists(config.LOG_FILE):
            return
            
        file_size = os.path.getsize(config.LOG_FILE)
        max_size = 5 * 1024 * 1024  # 5MB限制
        
        if file_size > max_size:
            print(f"日志文件过大({file_size/1024/1024:.1f}MB)，开始清理...")
            with open(config.LOG_FILE, 'r', encoding='utf-8') as f:
                lines = f.readlines()
            
            keep_lines = 1000
            if len(lines) > keep_lines:
                new_lines = lines[-keep_lines:]
                with open(config.LOG_FILE, 'w', encoding='utf-8') as f:
                    f.writelines(new_lines)
                removed_count = len(lines) - keep_lines
                print(f" 日志清理完成，删除了 {removed_count} 条旧记录，保留最新 {keep_lines} 条")
    except Exception as e:
        print(f"日志清理失败: {e}")


def clean_old_logs_by_date():
    """按日期清理日志，删除7天前的记录"""
    try:
        if not config.LOG_FILE or not os.path.exists(config.LOG_FILE):
            return
            
        cutoff_date = datetime.now() - timedelta(days=7)
        new_lines = []
        removed_count = 0
        
        with open(config.LOG_FILE, 'r', encoding='utf-8') as f:
            for line in f:
                try:
                    if line.strip():
                        date_str = line[:19]
                        log_date = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
                        if log_date >= cutoff_date:
                            new_lines.append(line)
                        else:
                            removed_count += 1
                except:
                    new_lines.append(line)
        
        if removed_count > 0:
            with open(config.LOG_FILE, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            print(f"按日期清理日志完成，删除了 {removed_count} 条7天前的记录")
    except Exception as e:
        print(f"按日期清理日志失败: {e}")


def periodic_log_cleanup():
    """定期日志清理任务"""
    while True:
        try:
            time.sleep(86400)  # 24小时
            current_hour = datetime.now().hour
            
            if current_hour == 15:
                print(" 执行定时日志清理...")
                clean_old_logs()
                clean_old_logs_by_date()
            else:
                now = datetime.now()
                target_time = now.replace(hour=15, minute=0, second=0, microsecond=0)
                if now.hour >= 15:
                    target_time += timedelta(days=1)
                sleep_seconds = (target_time - now).total_seconds()
                print(f" 日志清理将在 {target_time.strftime('%Y-%m-%d %H:%M')} 执行")
                time.sleep(sleep_seconds)
        except Exception as e:
            print(f"定期日志清理异常: {e}")
            time.sleep(3600)


# ==================== 文件清理 ====================

def clean_old_files(path_mgr, service_mgr):
    """定期清理指定目录下超过expire_seconds的文件，并启动日志清理 - 优化I/O版本"""
    folder = path_mgr.get_upload_dir()
    
    # 启动日志清理线程（只启动一次）
    if not hasattr(clean_old_files, 'log_cleanup_started'):
        log_cleanup_thread = threading.Thread(target=periodic_log_cleanup, daemon=True)
        log_cleanup_thread.start()
        clean_old_files.log_cleanup_started = True
        print("日志自动清理功能已启动")
    
    # 启动扫描文件清理线程（只启动一次）
    if not hasattr(clean_old_files, 'scan_cleanup_started'):
        scan_cleanup_thread = threading.Thread(target=periodic_scan_cleanup, args=(path_mgr,), daemon=True)
        scan_cleanup_thread.start()
        clean_old_files.scan_cleanup_started = True
        print("扫描文件自动清理功能已启动（30分钟过期）")
    
    last_cleanup_time = 0
    cleanup_interval = 300
    
    while True:
        current_time = time.time()
        if current_time - last_cleanup_time < cleanup_interval:
            time.sleep(30)
            continue
            
        try:
            if os.path.exists(folder):
                files_to_check = []
                try:
                    for fname in os.listdir(folder):
                        fpath = os.path.join(folder, fname)
                        if os.path.isfile(fpath):
                            files_to_check.append((fpath, fname))
                except (OSError, PermissionError) as e:
                    print(f" 扫描上传目录失败: {e}")
                    time.sleep(60)
                    continue
                
                deleted_count = 0
                for fpath, fname in files_to_check:
                    try:
                        file_age = current_time - os.path.getmtime(fpath)
                        if file_age > 600:  # 10分钟
                            os.remove(fpath)
                            deleted_count += 1
                    except (OSError, FileNotFoundError):
                        continue
                    except Exception as e:
                        print(f" 删除文件 {fname} 失败: {e}")
                
                if deleted_count > 0:
                    print(f"文件清理: 删除了 {deleted_count} 个过期文件")
                
                last_cleanup_time = current_time
            else:
                try:
                    os.makedirs(folder, exist_ok=True)
                except Exception as e:
                    print(f" 创建上传目录失败: {e}")
        except Exception as e:
            print(f"文件清理异常: {e}")
            
        uptime = current_time - (service_mgr.start_time or current_time)
        if uptime > 7200:
            cleanup_interval = 600
        elif uptime > 3600:
            cleanup_interval = 450
        
        time.sleep(cleanup_interval)


def periodic_scan_cleanup(path_mgr):
    """定期清理扫描文件 - 30分钟过期策略"""
    scan_folder = path_mgr.get_scan_dir()
    expire_seconds = 1800
    last_cleanup_time = 0
    cleanup_interval = 300
    
    while True:
        current_time = time.time()
        if current_time - last_cleanup_time < cleanup_interval:
            time.sleep(30)
            continue
        
        try:
            if os.path.exists(scan_folder):
                files_to_check = []
                try:
                    for fname in os.listdir(scan_folder):
                        fpath = os.path.join(scan_folder, fname)
                        if os.path.isfile(fpath):
                            files_to_check.append((fpath, fname))
                except (OSError, PermissionError) as e:
                    print(f" 扫描文件夹失败: {e}")
                    time.sleep(60)
                    continue
                
                deleted_count = 0
                for fpath, fname in files_to_check:
                    try:
                        file_age = current_time - os.path.getmtime(fpath)
                        if file_age > expire_seconds:
                            os.remove(fpath)
                            deleted_count += 1
                    except (OSError, FileNotFoundError):
                        continue
                    except Exception as e:
                        print(f" 删除扫描文件 {fname} 失败: {e}")
                
                if deleted_count > 0:
                    print(f"扫描文件清理: 删除了 {deleted_count} 个过期文件（30分钟以上）")
                
                last_cleanup_time = current_time
        except Exception as e:
            print(f"扫描文件清理异常: {e}")
        
        time.sleep(cleanup_interval)
