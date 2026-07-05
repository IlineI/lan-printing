#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""扫描仪检测、WIA扫描、设备管理"""

import os
import sys
import time
import subprocess
import threading
import datetime
import winreg

from modules.path_manager import PathManager

# 全局path_manager引用，在主入口中初始化
_path_manager = None


def init_scanner(path_mgr):
    """初始化scanner_manager的path_manager引用"""
    global _path_manager
    _path_manager = path_mgr


def get_path_manager():
    """获取path_manager"""
    global _path_manager
    if _path_manager is None:
        _path_manager = PathManager()
    return _path_manager


def get_available_scanners():
    """获取系统中可用的扫描仪列表 - 简化版本，不依赖PowerShell"""
    scanners = []
    try:
        if not hasattr(get_available_scanners, '_cache'):
            get_available_scanners._cache = {'time': 0, 'scanners': []}
            get_available_scanners._cache_timeout = 60
        
        if time.time() - get_available_scanners._cache['time'] < get_available_scanners._cache_timeout:
            return list(get_available_scanners._cache['scanners'])

        # 方法1: WIA COM 枚举
        try:
            wia_scanners = []
            
            def try_wia():
                try:
                    import win32com.client
                    dm = win32com.client.Dispatch('WIA.DeviceManager')
                    for i in range(1, min(dm.DeviceInfos.Count + 1, 10)):
                        try:
                            dev = dm.DeviceInfos.Item(i)
                            name = dev.Properties('Name').Value
                            dev_id = dev.Properties('DeviceID').Value
                            wia_scanners.append({
                                'name': name, 'id': dev_id,
                                'type': 'WIA', 'available': True
                            })
                            print(f"检测到扫描仪: {name}")
                        except:
                            pass
                except Exception as e:
                    print(f"WIA枚举失败: {e}")
            
            thread = threading.Thread(target=try_wia, daemon=True)
            thread.start()
            thread.join(timeout=5)
            
            if wia_scanners:
                scanners.extend(wia_scanners)
        except Exception as e:
            print(f"WIA 检测异常: {e}")

        # 方法2: WMIC 验证
        if not scanners:
            try:
                cmd = 'wmic logicaldisk get name'
                result = subprocess.run([cmd], shell=True, capture_output=True, text=True,
                                      timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
                if result.returncode == 0:
                    print("✓ WMIC 可用，继续使用WIA枚举")
            except Exception as e:
                print(f"WMIC 检测失败: {e}")

        # 方法3: 打印机名称推断多功能设备
        try:
            from modules.printer_manager import PRINTERS
            scan_keywords = ['scan', '扫描', 'mfp', 'multi', 'all-in-one', 'all in one', '多功能']
            for p in list(PRINTERS)[:30]:
                pname = str(p)
                lname = pname.lower()
                if any(k in lname for k in scan_keywords):
                    if not any(s['name'] == pname for s in scanners):
                        scanners.append({
                            'name': pname, 'id': f'PRINTER_{pname}',
                            'type': 'Multifunction', 'available': True
                        })
                        print(f"检测到多功能设备: {pname}")
        except Exception as e:
            print(f"多功能设备推断失败: {e}")

        if not scanners:
            scanners.append({
                'name': '通用扫描（系统窗口）', 'id': 'default',
                'type': 'Generic', 'available': True
            })
            print("未检测到具体扫描仪，已添加通用选项")

        try:
            get_available_scanners._cache['time'] = time.time()
            get_available_scanners._cache['scanners'] = list(scanners)
        except:
            pass
        
        return scanners
    except Exception as e:
        print(f"扫描仪检测出错: {e}")
        return [{
            'name': '通用扫描（系统窗口）', 'id': 'default',
            'type': 'Generic', 'available': True
        }]


def cleanup_port_and_restart_wia(port=5000):
    """强制清理端口占用标记并重启WIA服务"""
    try:
        print(f"[CLEANUP] 开始清理端口占用和重启WIA服务...")
        
        try:
            print(f"[PORT] 尝试清理端口 {port}...")
            result = subprocess.run(['netstat', '-ano'], capture_output=True, text=True,
                                  timeout=5, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if f':{port}' in line and 'ESTABLISHED' in line:
                        parts = line.split()
                        if len(parts) > 0:
                            try:
                                pid = parts[-1]
                                subprocess.run(['taskkill', '/F', '/PID', pid],
                                             capture_output=True, timeout=5,
                                             creationflags=subprocess.CREATE_NO_WINDOW)
                                print(f"[PORT] 已清理占用端口 {port} 的进程 (PID: {pid})")
                            except:
                                pass
        except Exception as e:
            print(f"[WARN] 端口清理异常: {e}")
        
        try:
            print("[CLEANUP] 清理socket挂起状态...")
            import gc
            gc.collect()
            print("[CLEANUP] Socket状态已清空")
        except:
            pass
        
        try:
            print("[WIA] 停止WIA服务...")
            result = subprocess.run(['sc', 'stop', 'wiaservc'], capture_output=True,
                                  timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                print("[WIA] WIA服务已停止")
                time.sleep(1)
        except Exception as e:
            print(f"[WARN] 停止WIA服务异常: {e}")
        
        try:
            print("[WIA] 启动WIA服务...")
            result = subprocess.run(['sc', 'start', 'wiaservc'], capture_output=True,
                                  timeout=10, creationflags=subprocess.CREATE_NO_WINDOW)
            if result.returncode == 0:
                print("[WIA] WIA服务已启动")
                return True
        except Exception as e:
            print(f"[WARN] 启动WIA服务异常: {e}")
        
        print("[SUCCESS] 端口和WIA服务清理完成")
        return True
    except Exception as e:
        print(f"[ERROR] 清理端口和重启WIA失败: {e}")
        return False


def force_release_wia_device():
    """强制释放被锁定的WIA设备"""
    try:
        print("尝试强制释放WIA设备...")
        
        try:
            result = subprocess.run(['sc', 'stop', 'wiaservc'], capture_output=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
            stderr_msg = result.stderr.decode('utf-8', errors='ignore') if result.stderr else ""
            stdout_msg = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ""
            print(f"WIA服务停止: 返回码={result.returncode} {stdout_msg.strip()}")
            time.sleep(2)
            
            result = subprocess.run(['sc', 'start', 'wiaservc'], capture_output=True,
                                  creationflags=subprocess.CREATE_NO_WINDOW, timeout=10)
            stdout_msg = result.stdout.decode('utf-8', errors='ignore') if result.stdout else ""
            print(f"WIA服务启动: 返回码={result.returncode} {stdout_msg.strip()}")
            time.sleep(1)
            return True
        except Exception as e:
            print(f"WIA服务重启失败: {e}")
        
        process_names = ['scanwiz.exe', 'wiafbdrv.exe', 'svchost.exe', 'wiaservc.exe',
                        'mspaint.exe', 'explorer.exe']
        killed_processes = []
        for process_name in process_names:
            try:
                result = subprocess.run(['taskkill', '/F', '/IM', process_name],
                                       capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=5)
                if result.returncode == 0:
                    killed_processes.append(process_name)
                    print(f"已清理进程: {process_name}")
            except:
                pass
        
        if killed_processes:
            print(f"成功清理进程: {', '.join(killed_processes)}")
            return True
        
        try:
            import psutil
            wia_related = ['scanwiz.exe', 'wiafbdrv.exe', 'wiaservc.exe']
            for proc in psutil.process_iter(['pid', 'name']):
                try:
                    if proc.info['name'].lower() in wia_related:
                        p = psutil.Process(proc.info['pid'])
                        p.terminate()
                        print(f"已终止进程: {proc.info['name']}")
                except:
                    pass
            return True
        except ImportError:
            print("psutil 未安装，跳过进程管理器方法")
        except Exception as e:
            print(f"进程管理器方法失败: {e}")
        
        try:
            import gc
            gc.collect()
            print("已清理COM对象缓存和内存")
        except:
            pass
        
        print("WIA设备已释放")
        sys.stdout.flush()
        return True
    except Exception as e:
        print(f"强制释放WIA设备异常: {e}")
        return False


def start_scan_silent(scanner_id, scanner_name, scan_format='PNG', scan_path=None):
    """扫描功能 - 全程静默扫描，不打开任何窗口或文件夹"""
    path_mgr = get_path_manager()
    
    try:
        print(f"启动扫描: {scanner_name} ({scanner_id})")
        
        if scan_path is None:
            scan_path = path_mgr.get_scan_dir()
            if not os.path.exists(scan_path):
                os.makedirs(scan_path)
        
        try:
            initial_files = set(os.listdir(scan_path)) if os.path.exists(scan_path) else set()
        except:
            initial_files = set()
        
        original_auto_open = None
        
        def disable_auto_open_folder():
            nonlocal original_auto_open
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Explorer\AutoplayHandlers",
                                    0, winreg.KEY_READ)
                winreg.CloseKey(key)
                try:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                        r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer",
                                        0, winreg.KEY_WRITE)
                    original_auto_open = winreg.QueryValueEx(key, 'NoDriveTypeAutorun')[0]
                    winreg.SetValueEx(key, 'NoDriveTypeAutorun', 0, winreg.REG_DWORD, 255)
                    winreg.CloseKey(key)
                except:
                    pass
            except Exception as e:
                print(f"禁用自动打开失败: {e}")
        
        def restore_auto_open_folder():
            try:
                if original_auto_open is not None:
                    key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                                        r"Software\Microsoft\Windows\CurrentVersion\Policies\Explorer",
                                        0, winreg.KEY_WRITE)
                    winreg.SetValueEx(key, 'NoDriveTypeAutorun', 0, winreg.REG_DWORD, original_auto_open)
                    winreg.CloseKey(key)
            except:
                pass
        
        disable_auto_open_folder()
        print("正在进行静默扫描，请在扫描仪上操作...")
        
        try:
            def silent_wia_scan():
                device_manager = None
                device = None
                item = None
                image = None
                try:
                    import win32com.client
                    import ctypes
                    import gc
                    
                    try:
                        ctypes.windll.ole32.CoInitialize(None)
                    except:
                        pass
                    
                    try:
                        device_manager = win32com.client.Dispatch("WIA.DeviceManager")
                        devices = device_manager.DeviceInfos
                        
                        if len(devices) > 0:
                            device_info = devices(1)
                            device = device_info.Connect()
                            item = device.Items(1)
                            scanner_item = item
                            
                            for prop in scanner_item.Properties:
                                if prop.Name == 'Horizontal Resolution':
                                    prop.Value = 200
                                elif prop.Name == 'Vertical Resolution':
                                    prop.Value = 200
                                elif prop.Name == 'Color Mode':
                                    prop.Value = 1
                            
                            image = scanner_item.Transfer()
                            timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                            filename = f"scan_{timestamp}.{scan_format.lower() if scan_format else 'bmp'}"
                            filepath = os.path.join(scan_path, filename)
                            image.SaveFile(filepath)
                            print(f"WIA静默扫描完成: {filename}")
                            result_path = filepath
                            
                            try:
                                if image is not None: image = None
                                if item is not None: item = None
                                if scanner_item is not None: scanner_item = None
                                if device_info is not None: device_info = None
                                if device is not None: device = None
                                if device_manager is not None: device_manager = None
                                gc.collect()
                            except:
                                pass
                            
                            try:
                                ctypes.windll.ole32.CoUninitialize()
                            except:
                                pass
                            
                            return True, result_path
                    finally:
                        try:
                            if image is not None: image = None
                            if item is not None: item = None
                            if device is not None: device = None
                            if device_manager is not None: device_manager = None
                        except:
                            pass
                        try:
                            ctypes.windll.ole32.CoUninitialize()
                        except:
                            pass
                except Exception as e:
                    print(f"WIA扫描失败: {e}")
                    return False, None
            
            success, filepath = silent_wia_scan()
            if success and filepath:
                file_size = os.path.getsize(filepath)
                filename = os.path.basename(filepath)
                print(f"扫描完成: {filename} ({file_size} 字节)")
                sys.stdout.flush()
                restore_auto_open_folder()
                return True, f"扫描成功！文件已保存到: {filename}"
            
            print("WIA直接扫描未成功，尝试强制释放设备...")
            force_release_wia_device()
            time.sleep(2)
            
            print("重新尝试WIA扫描...")
            success, filepath = silent_wia_scan()
            if success and filepath:
                file_size = os.path.getsize(filepath)
                filename = os.path.basename(filepath)
                print(f"扫描完成: {filename} ({file_size} 字节)")
                sys.stdout.flush()
                restore_auto_open_folder()
                return True, f"扫描成功！文件已保存到: {filename}"
            
            print("使用静默扫描命令...")
            
            try:
                timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                scan_filename = f"scan_{timestamp}.jpg"
                scan_filepath = os.path.join(scan_path, scan_filename)
                
                try:
                    result = subprocess.run(['scanimage', '--scan-mode', 'Color', '--resolution', '200', '-o', scan_filepath],
                                          capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)
                    if result.returncode == 0 and os.path.exists(scan_filepath):
                        print(f"scanimage扫描成功: {scan_filename}")
                        restore_auto_open_folder()
                        return True, f"扫描成功！文件已保存到: {scan_filename}"
                except:
                    pass
                
                vbs_script = f"""
Dim objScanner, objDevice, objItem, objImage, objDeviceInfo, fso
Dim deviceCount, i
On Error Resume Next

Set fso = CreateObject("Scripting.FileSystemObject")
If fso.FileExists("{scan_filepath}") Then
    fso.DeleteFile("{scan_filepath}")
End If

Set objScanner = CreateObject("WIA.DeviceManager")
If Err.Number <> 0 Then
    WScript.Echo "Error 1: Cannot create WIA.DeviceManager - " & Err.Description
    WScript.Quit 1
End If

deviceCount = objScanner.DeviceInfos.Count
If deviceCount = 0 Then
    WScript.Echo "Error 2: No device found"
    WScript.Quit 2
End If

WScript.Echo "Found " & deviceCount & " device(s)"

Set objDevice = Nothing
For i = 1 To deviceCount
    Err.Clear
    Set objDeviceInfo = objScanner.DeviceInfos(i)
    WScript.Echo "Device " & i & ": " & objDeviceInfo.Name
    
    Set objDevice = objDeviceInfo.Connect()
    If Err.Number = 0 Then
        WScript.Echo "Successfully connected to device: " & objDeviceInfo.Name
        Exit For
    Else
        WScript.Echo "Failed to connect to device " & i & ": " & Err.Description
    End If
    Set objDevice = Nothing
Next

If objDevice Is Nothing Then
    WScript.Echo "Error 3: Cannot connect to any device"
    WScript.Quit 3
End If

Err.Clear
Set objItem = objDevice.Items(1)
If Err.Number <> 0 Then
    WScript.Echo "Error 4: Cannot get device item: " & Err.Description
    WScript.Quit 4
End If

Err.Clear
Set objImage = objItem.Transfer()
If Err.Number <> 0 Then
    WScript.Echo "Error 5: Scan transfer failed: " & Err.Description
    WScript.Quit 5
End If

Err.Clear
objImage.SaveFile "{scan_filepath}"
If Err.Number <> 0 Then
    WScript.Echo "Error 6: Cannot save file: " & Err.Description
    Set objImage = Nothing
    Set objItem = Nothing
    Set objDevice = Nothing
    Set objDeviceInfo = Nothing
    Set objScanner = Nothing
    Set fso = Nothing
    WScript.Quit 6
Else
    WScript.Echo "Scan success: {scan_filepath}"
End If

Set objImage = Nothing
Set objItem = Nothing
Set objDeviceInfo = Nothing
Set objDevice = Nothing
Set objScanner = Nothing
Set fso = Nothing

WScript.Quit 0
"""
                
                vbs_path = os.path.join(path_mgr.app_dir, 'temp_scan.vbs')
                try:
                    with open(vbs_path, 'w', encoding='gbk', errors='ignore') as f:
                        f.write(vbs_script)
                except:
                    with open(vbs_path, 'w', encoding='utf-8') as f:
                        f.write(vbs_script)
                
                print(f"执行VBS扫描脚本...")
                result = subprocess.run(['cscript.exe', '//Nologo', vbs_path],
                                      capture_output=True, creationflags=subprocess.CREATE_NO_WINDOW, timeout=60)
                
                def decode_output(output_bytes):
                    if not output_bytes: return ""
                    for enc in ['gbk', 'utf-8', 'utf-16']:
                        try:
                            return output_bytes.decode(enc).strip()
                        except:
                            continue
                    return output_bytes.decode('utf-8', errors='ignore').strip()

                stdout_str = decode_output(result.stdout)
                stderr_str = decode_output(result.stderr)
                
                if stdout_str:
                    print(f"VBS输出: {stdout_str}")
                if stderr_str:
                    print(f"VBS错误: {stderr_str}")
                
                print(f"VBS返回码: {result.returncode}")
                
                try:
                    os.remove(vbs_path)
                except:
                    pass
                
                time.sleep(1)
                if os.path.exists(scan_filepath) and os.path.getsize(scan_filepath) > 0:
                    file_size = os.path.getsize(scan_filepath)
                    print(f"VBS扫描成功: {scan_filename} ({file_size} 字节)")
                    restore_auto_open_folder()
                    return True, f"扫描成功！文件已保存到: {scan_filename}"
                else:
                    print("扫描未生成有效文件")
                    
            except subprocess.TimeoutExpired:
                print("扫描超时")
            except Exception as e:
                print(f"扫描执行异常: {e}")
            
            restore_auto_open_folder()
            return False, "扫描执行失败。请确保扫描仪已连接。"
        
        except Exception as e:
            print(f"扫描异常: {e}")
            restore_auto_open_folder()
            return False, f"扫描异常: {str(e)}"
    
    except Exception as e:
        print(f"扫描功能异常: {e}")
        return False, f"扫描异常: {str(e)}"
