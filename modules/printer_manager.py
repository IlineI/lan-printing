#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""打印机管理：枚举、缓存、能力检测、队列管理、开机自启"""

import os
import sys
import time
import winreg

import win32print

from modules.config import (
    DC_DUPLEX, DC_COLORDEVICE, DC_PAPERS, DC_PAPERNAMES,
    DC_ENUMRESOLUTIONS, DEVICE_STATUS, VIRTUAL_PRINTERS, DEBUG_MODE
)


# ==================== 网络共享打印机连接 ====================

def ensure_printer_connection(pr_name):
    """确保对 UNC 网络共享打印机建立临时连接"""
    if not pr_name:
        return False
    pn = pr_name.strip()
    if pn.startswith('\\'):
        try:
            print(f"尝试连接网络共享打印机: {pn}")
            try:
                win32print.AddPrinterConnection(pn)
                print(f"已添加打印机连接: {pn}")
            except Exception as e:
                print(f"AddPrinterConnection 失败: {e}")
                try:
                    import subprocess
                    cmd = ['rundll32.exe', 'printui.dll,PrintUIEntry', '/in', '/n', pn]
                    subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW)
                    print(f"已尝试通过 printui 添加打印机: {pn}")
                except Exception as e2:
                    print(f"通过 printui 添加打印机失败: {e2}")
            if 'printer_cache' in globals():
                try:
                    printer_cache.refresh_cache()
                    print("打印机缓存已刷新")
                except Exception:
                    pass
        except Exception as e:
            print(f"ensure_printer_connection 内部错误: {e}")
            return False
    return True


# ==================== 虚拟打印机检测 ====================

def is_physical_printer(printer_name):
    """检查是否为真正的物理打印机"""
    if DEBUG_MODE:
        return True
    if printer_name in VIRTUAL_PRINTERS:
        return False
    virtual_keywords = ['pdf', 'fax', '传真', 'xps', 'onenote', 'virtual', '虚拟', 'send to', 'export', '导出']
    printer_lower = printer_name.lower()
    for keyword in virtual_keywords:
        if keyword in printer_lower:
            return False
    return True


# ==================== 打印机缓存管理 ====================

class PrinterCache:
    def __init__(self):
        self.cache_time = 0
        self.all_printers = []
        self.physical_printers = []
        self.default_printer = None
        self.cache_timeout = self._detect_cache_timeout()

    def _detect_cache_timeout(self):
        """根据Windows版本设置缓存超时"""
        import platform
        try:
            windows_version = platform.release()
            windows_build = getattr(getattr(sys, 'getwindowsversion', lambda: None)(), 'build', None)
            if windows_version == "7":
                print(" Win7打印机缓存：3分钟")
                return 180
            elif windows_build and windows_build >= 22000:
                print(" Win11打印机缓存：10分钟")
                return 600
            else:
                print(" Win10打印机缓存：5分钟")
                return 300
        except Exception as e:
            print(f"打印机缓存配置失败，使用默认5分钟: {e}")
            return 300

    def is_cache_valid(self):
        return (time.time() - self.cache_time) < self.cache_timeout

    def refresh_cache(self):
        try:
            self.all_printers = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)]
            if DEBUG_MODE:
                self.physical_printers = self.all_printers
                print(f"[调试模式] 显示所有打印机，包括虚拟打印机: {self.all_printers}")
            else:
                self.physical_printers = [p for p in self.all_printers if p not in VIRTUAL_PRINTERS]
            try:
                default = win32print.GetDefaultPrinter()
                self.default_printer = default if default in self.physical_printers else (self.physical_printers[0] if self.physical_printers else None)
            except:
                self.default_printer = self.physical_printers[0] if self.physical_printers else None
            self.cache_time = time.time()
            return True
        except Exception as e:
            print(f"刷新打印机缓存失败: {e}")
            return False

    def get_printers(self):
        if not self.is_cache_valid():
            self.refresh_cache()
        return self.physical_printers

    def get_default_printer(self):
        if not self.is_cache_valid():
            self.refresh_cache()
        return self.default_printer


# 创建全局打印机缓存并初始化
printer_cache = PrinterCache()
printer_cache.refresh_cache()
ALL_PRINTERS = printer_cache.all_printers
PRINTERS = printer_cache.physical_printers


def get_default_printer():
    """获取系统默认打印机"""
    return printer_cache.get_default_printer()


def refresh_printer_list():
    """刷新打印机列表"""
    global ALL_PRINTERS, PRINTERS
    try:
        success = printer_cache.refresh_cache()
        if success:
            ALL_PRINTERS = printer_cache.all_printers
            PRINTERS = printer_cache.physical_printers
            print(f"打印机列表已刷新，检测到 {len(PRINTERS)} 台物理打印机")
        return success
    except Exception as e:
        print(f"刷新打印机列表失败: {e}")
        return False


# ==================== 打印机能力检测 ====================

def get_printer_capabilities(printer_name):
    """获取指定打印机的功能参数"""
    try:
        print(f"正在获取打印机 '{printer_name}' 的实际参数...")
        
        if not printer_name or printer_name.strip() == "" or printer_name == "未检测到可用打印机":
            print("打印机名称无效")
            return {
                'duplex_support': False, 'color_support': False,
                'paper_sizes': ['A4'], 'quality_levels': ['normal'],
                'printer_status': '离线或不可用', 'driver_name': '未知'
            }
        
        printer_handle = win32print.OpenPrinter(printer_name)
        try:
            printer_info = win32print.GetPrinter(printer_handle, 2)
            driver_name = printer_info.get('pDriverName', '未知')
            port_name = printer_info.get('pPortName', '未知')
            status = printer_info.get('Status', 0)
            
            print(f"打印机驱动: {driver_name}")
            print(f"打印机端口: {port_name}")
            print(f"打印机状态码: {status}")
            
            printer_status = '在线'
            if status != 0:
                status_descriptions = {
                    0x00000001: '暂停', 0x00000002: '错误', 0x00000004: '正在删除',
                    0x00000008: '缺纸', 0x00000010: '缺纸', 0x00000020: '手动送纸',
                    0x00000040: '纸张故障', 0x00000080: '离线', 0x00000100: 'I/O 活动',
                    0x00000200: '忙', 0x00000400: '正在打印', 0x00000800: '输出槽满',
                    0x00001000: '不可用', 0x00002000: '等待', 0x00004000: '正在处理',
                    0x00008000: '正在初始化', 0x00010000: '正在预热', 0x00020000: '碳粉不足',
                    0x00040000: '没有碳粉', 0x00080000: '页面错误', 0x00100000: '用户干预',
                    0x00200000: '内存不足', 0x00400000: '门打开'
                }
                for status_bit, description in status_descriptions.items():
                    if status & status_bit:
                        printer_status = description
                        break
                else:
                    printer_status = f'未知状态 ({status})'
            
            duplex_support = False
            color_support = False
            papers = []
            resolutions_list = []
            duplex_modes = []
            
            try:
                try:
                    duplex_caps = win32print.DeviceCapabilities(printer_name, port_name, DC_DUPLEX, None)
                    duplex_support = duplex_caps > 0
                    if duplex_caps >= 1:
                        duplex_modes.append("long_edge")
                    if duplex_caps >= 2:
                        duplex_modes.append("short_edge")
                    print(f"双面打印支持: {duplex_support} (DeviceCapabilities返回: {duplex_caps})")
                    if duplex_modes:
                        print(f"支持的双面模式: {', '.join(duplex_modes)}")
                except Exception as e:
                    print(f"检查双面打印支持失败: {e}")
                
                try:
                    color_caps = win32print.DeviceCapabilities(printer_name, port_name, DC_COLORDEVICE, None)
                    color_support = color_caps == 1
                    print(f"颜色打印支持: {color_support} (DeviceCapabilities返回: {color_caps})")
                except Exception as e:
                    print(f"检查颜色支持失败: {e}")
                
                try:
                    paper_ids = win32print.DeviceCapabilities(printer_name, port_name, DC_PAPERS, None)
                    paper_names = win32print.DeviceCapabilities(printer_name, port_name, DC_PAPERNAMES, None)
                    if paper_ids and paper_names:
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
                
                try:
                    resolutions = win32print.DeviceCapabilities(printer_name, port_name, DC_ENUMRESOLUTIONS, None)
                    if resolutions:
                        for res in resolutions:
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
                'duplex_modes': duplex_modes,
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
        return {
            'duplex_support': False, 'duplex_modes': [],
            'color_support': False, 'papers': [],
            'resolutions': [], 'printer_status': '离线或不可用',
            'driver_name': '未知', 'port_name': ''
        }


# ==================== 打印队列管理 ====================

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
    uncancellable = (JOB_STATUS_PRINTED | JOB_STATUS_COMPLETE | JOB_STATUS_DELETED | JOB_STATUS_DELETING)
    return not bool(status & uncancellable)


def get_print_queue_jobs(printer_name=None):
    """获取指定打印机的打印队列任务"""
    try:
        jobs = []
        if printer_name:
            try:
                printer_handle = win32print.OpenPrinter(printer_name)
                job_list = win32print.EnumJobs(printer_handle, 0, -1, 1)
                for job in job_list:
                    jobs.append({
                        'job_id': job['JobId'], 'printer': printer_name,
                        'document': job['pDocument'], 'user': job['pUserName'],
                        'status': job['Status'], 'pages': job['PagesPrinted'],
                        'size': job['Size']
                    })
                win32print.ClosePrinter(printer_handle)
            except Exception as e:
                print(f"获取打印机 {printer_name} 队列失败: {e}")
        else:
            for printer in PRINTERS:
                try:
                    printer_handle = win32print.OpenPrinter(printer)
                    job_list = win32print.EnumJobs(printer_handle, 0, -1, 1)
                    for job in job_list:
                        jobs.append({
                            'job_id': job['JobId'], 'printer': printer,
                            'document': job['pDocument'], 'user': job['pUserName'],
                            'status': job['Status'], 'pages': job['PagesPrinted'],
                            'size': job['Size']
                        })
                    win32print.ClosePrinter(printer_handle)
                except Exception as e:
                    print(f"获取打印机 {printer} 队列失败: {e}")
        return jobs
    except Exception as e:
        print(f"获取打印队列失败: {e}")
        return []


def cancel_print_jobs_by_document(document_name, printer_name=None, cancel_active=False):
    """根据文档名取消打印任务"""
    # 延迟导入避免循环依赖
    from modules.scanner_manager import cleanup_port_and_restart_wia, force_release_wia_device
    
    try:
        cancelled_jobs = []
        skipped_jobs = []
        has_cancelled_any = False
        
        jobs = get_print_queue_jobs(printer_name)
        
        for job in jobs:
            if document_name.lower() in job['document'].lower() or \
               os.path.splitext(document_name)[0].lower() in job['document'].lower():
                
                job_status = job['status']
                status_desc = get_job_status_description(job_status)
                is_printing = is_job_actively_printing(job_status)
                is_cancellable = is_job_cancellable(job_status)
                
                print(f" 找到相关任务: {job['document']} (状态: {status_desc})")
                
                if not is_cancellable:
                    print(f"[SKIP] 跳过任务 {job['document']}: 任务已完成或正在删除")
                    skipped_jobs.append({
                        'job_id': job['job_id'], 'printer': job['printer'],
                        'document': job['document'], 'reason': '任务已完成或正在删除',
                        'status': status_desc
                    })
                    continue
                
                if is_printing and not cancel_active:
                    print(f"[SKIP] 跳过正在打印的任务: {job['document']} (状态: {status_desc})")
                    skipped_jobs.append({
                        'job_id': job['job_id'], 'printer': job['printer'],
                        'document': job['document'], 'reason': '正在打印，需要显式授权才能取消',
                        'status': status_desc
                    })
                    continue
                
                try:
                    printer_handle = win32print.OpenPrinter(job['printer'])
                    win32print.SetJob(printer_handle, job['job_id'], 0, None, win32print.JOB_CONTROL_CANCEL)
                    cancelled_jobs.append({
                        'job_id': job['job_id'], 'printer': job['printer'],
                        'document': job['document'], 'status': status_desc,
                        'was_printing': is_printing
                    })
                    action = "已强制取消" if is_printing else "已取消"
                    print(f" {action}打印任务: {job['document']} (任务ID: {job['job_id']}, 状态: {status_desc})")
                    win32print.ClosePrinter(printer_handle)
                    has_cancelled_any = True
                except Exception as e:
                    print(f" 取消打印任务失败: {job['document']} - {e}")
                    skipped_jobs.append({
                        'job_id': job['job_id'], 'printer': job['printer'],
                        'document': job['document'], 'reason': f'取消失败: {e}',
                        'status': status_desc
                    })
        
        if has_cancelled_any and DEVICE_STATUS['is_printing']:
            print("[RESET] 重置打印设备状态（已取消打印任务）")
            DEVICE_STATUS['is_printing'] = False
            DEVICE_STATUS['print_start_time'] = None
            DEVICE_STATUS['print_client'] = ''
            
            print("[CLEANUP] 强制清理后台占用资源...")
            try:
                from app import app as flask_app
                port = getattr(flask_app, 'current_port', 5000)
                cleanup_port_and_restart_wia(port)
            except Exception as e:
                print(f"[WARN] 端口清理异常（非致命）: {e}")
            
            print("[INFO] 释放WIA扫描设备以避免冲突...")
            try:
                force_release_wia_device()
            except Exception as e:
                print(f"[WARN] WIA设备释放异常（非致命）: {e}")
        
        return {
            'cancelled': cancelled_jobs, 'skipped': skipped_jobs,
            'total_found': len(cancelled_jobs) + len(skipped_jobs)
        }
    except Exception as e:
        print(f"取消打印任务失败: {e}")
        return {'cancelled': [], 'skipped': [], 'total_found': 0, 'error': str(e)}


def clear_all_print_queues():
    """清空所有打印机的打印队列"""
    from modules.scanner_manager import cleanup_port_and_restart_wia, force_release_wia_device
    
    try:
        cleared_count = 0
        for printer in PRINTERS:
            try:
                printer_handle = win32print.OpenPrinter(printer)
                job_list = win32print.EnumJobs(printer_handle, 0, -1, 1)
                for job in job_list:
                    try:
                        win32print.SetJob(printer_handle, job['JobId'], 0, None, win32print.JOB_CONTROL_CANCEL)
                        cleared_count += 1
                        print(f" 已取消: {printer} - {job['pDocument']} (任务ID: {job['JobId']})")
                    except Exception as e:
                        print(f" 取消任务失败: {job['pDocument']} - {e}")
                win32print.ClosePrinter(printer_handle)
            except Exception as e:
                print(f"清理打印机 {printer} 队列失败: {e}")
        
        if cleared_count > 0 and DEVICE_STATUS['is_printing']:
            print("[RESET] 重置打印设备状态（已清空所有打印队列）")
            DEVICE_STATUS['is_printing'] = False
            DEVICE_STATUS['print_start_time'] = None
            DEVICE_STATUS['print_client'] = ''
            
            print("[CLEANUP] 强制清理后台占用资源...")
            try:
                from app import app as flask_app
                port = getattr(flask_app, 'current_port', 5000)
                cleanup_port_and_restart_wia(port)
            except Exception as e:
                print(f"[WARN] 端口清理异常（非致命）: {e}")
            
            print("[INFO] 释放WIA扫描设备以避免冲突...")
            try:
                force_release_wia_device()
            except Exception as e:
                print(f"[WARN] WIA设备释放异常（非致命）: {e}")
        
        return cleared_count
    except Exception as e:
        print(f"清空打印队列失败: {e}")
        return 0


# ==================== 开机自启 ====================

def set_autostart(enable=True):
    """设置/取消开机自启"""
    exe_path = sys.executable
    key = r'Software\Microsoft\Windows\CurrentVersion\Run'
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
    """获取开机自启状态"""
    key = r'Software\Microsoft\Windows\CurrentVersion\Run'
    name = 'PrintServerApp'
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key, 0, winreg.KEY_READ) as regkey:
            val, _ = winreg.QueryValueEx(regkey, name)
            return bool(val)
    except FileNotFoundError:
        return False
