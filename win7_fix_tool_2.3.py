# ===== Win7打印及扫描环境修复工具 2.3版 =====
# 作者：忆痕（yckj666@52PJ）
# 适用系统：Windows 7 SP1
# 版本：2.3 - 优化版本，支持打印及扫描功能修复，性能和稳定性提升

import os
import sys
import platform
import subprocess
import ctypes
import threading
import time
import msvcrt
import winreg
from functools import wraps

# ===== 系统检查函数 =====
def safe_check(func):
    """装饰器：安全执行检查函数，捕获所有异常"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            # 静默处理异常，返回False表示检查失败
            return False
    return wrapper

@safe_check
def is_win7():
    """检查是否为Windows 7系统"""
    return platform.system() == "Windows" and platform.release() == "7"

@safe_check
def check_admin():
    """检查是否具有管理员权限"""
    return ctypes.windll.shell32.IsUserAnAdmin()

@safe_check
def check_service_running(service_name):
    """检查Windows服务是否正在运行"""
    result = subprocess.run(['sc', 'query', service_name], capture_output=True, text=True, timeout=5)
    return 'RUNNING' in result.stdout

def check_spooler():
    """检查打印服务(Spooler)是否正在运行"""
    return check_service_running('Spooler')

@safe_check
def check_vc_redist():
    """检查VC运行库是否安装（Win7兼容版本）"""
    # Win7适用的VC运行库版本
    keys = [
        r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",  # VC++ 2015
        r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x86",
        r"SOFTWARE\Microsoft\VisualStudio\12.0\VC\Runtimes\x64",  # VC++ 2013
        r"SOFTWARE\Microsoft\VisualStudio\12.0\VC\Runtimes\x86",
        r"SOFTWARE\Microsoft\VisualStudio\11.0\VC\Runtimes\x64",  # VC++ 2012
        r"SOFTWARE\Microsoft\VisualStudio\11.0\VC\Runtimes\x86",
        r"SOFTWARE\Microsoft\VisualStudio\10.0\VC\Runtimes\x64",  # VC++ 2010
        r"SOFTWARE\Microsoft\VisualStudio\10.0\VC\Runtimes\x86",
    ]
    for key in keys:
        try:
            hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key)
            value, _ = winreg.QueryValueEx(hkey, "Installed")
            if value == 1:
                return True
        except Exception:
            continue
    return False

@safe_check
def check_dotnet():
    """检查.NET Framework是否安装（Win7适用版本）"""
    # 检查.NET Framework 4.0及以上版本
    try:
        hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full")
        value, _ = winreg.QueryValueEx(hkey, "Release")
        if value >= 378389:  # .NET 4.5及以上
            return True
    except Exception:
        pass
    
    # 检查.NET Framework 3.5（Win7默认）
    try:
        hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v3.5")
        value, _ = winreg.QueryValueEx(hkey, "Install")
        if value == 1:
            return True
    except Exception:
        pass
    
    # 检查.NET Framework 2.0（Win7基础版本）
    try:
        hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v2.0.50727")
        value, _ = winreg.QueryValueEx(hkey, "Install")
        if value == 1:
            return True
    except Exception:
        pass
    
    return False

def check_wia_service():
    """检查WIA扫描服务是否正常运行"""
    return check_service_running('stisvc')

@safe_check
def check_printer_driver():
    """检查是否安装了物理打印机驱动"""
    import win32print
    printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
    for p in printers:
        # 过滤虚拟打印机
        if p[2] and p[2] not in ['Microsoft XPS Document Writer', 'Microsoft Print to PDF', 'Send To OneNote']:
            return True
    return False

@safe_check
def check_scanner_driver():
    """检查是否安装了扫描仪驱动（通过注册表检测）"""
    # 检查WIA设备注册表项
    key_paths = [
        r"SYSTEM\CurrentControlSet\Control\Class\{6bdd1fc6-810f-11d0-bec7-08002be2092f}",  # 图像设备
        r"SYSTEM\CurrentControlSet\Services\usbscan\Enum",  # USB扫描设备
    ]
    
    for key_path in key_paths:
        try:
            hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            # 如果能打开且有子项，说明有扫描设备
            try:
                subkey = winreg.EnumKey(hkey, 0)
                if subkey:
                    return True
            except:
                pass
            winreg.CloseKey(hkey)
        except Exception:
            continue
    return False

@safe_check
def check_wia_components():
    """检查WIA核心组件是否完整"""
    import comtypes.client
    # 尝试创建WIA设备管理器对象
    device_manager = comtypes.client.CreateObject("WIA.DeviceManager")
    return device_manager is not None

@safe_check
def check_win7_sp1():
    """检查Win7是否安装了SP1补丁包"""
    key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
    try:
        value, _ = winreg.QueryValueEx(hkey, "CSDVersion")
        return "Service Pack 1" in value
    except:
        return False

def check_windows_update():
    """检查Windows Update服务状态"""
    return check_service_running('wuauserv')

def check_win7_theme_service():
    """检查Win7主题服务是否正常（影响打印界面显示）"""
    return check_service_running('Themes')

@safe_check
def check_disk_space():
    """检查磁盘空间是否充足"""
    import shutil
    total, used, free = shutil.disk_usage(os.environ.get('SystemDrive', 'C:') + '\\')
    # Win7至少需要1GB空闲空间
    return free > 1024*1024*1024

@safe_check
def check_virtual_machine():
    """检查是否运行在虚拟机环境"""
    system_info = platform.platform().lower()
    vm_indicators = ['virtual', 'vmware', 'virtualbox', 'qemu', 'xen']
    return any(indicator in system_info for indicator in vm_indicators)

@safe_check
def check_security_software():
    """检查是否有安全软件可能影响打印"""
    try:
        import psutil
        processes = [p.name().lower() for p in psutil.process_iter()]
        # Win7常见安全软件
        security_apps = [
            '360tray.exe', 'kxetray.exe', 'rstray.exe', 'avp.exe', 
            'zhudongfangyu.exe', 'qqpcmgr.exe', 'kismain.exe',
            'msmpeng.exe', 'msseces.exe'  # Windows Defender (Win7版本)
        ]
        for app in security_apps:
            if app in processes:
                return True
        return False
    except:
        return False

@safe_check
def check_group_policy():
    """检查组策略是否禁用打印功能"""
    policies_to_check = [
        (r"SOFTWARE\Policies\Microsoft\Windows NT\Printers", "DisablePrint"),
        (r"SOFTWARE\Policies\Microsoft\Windows NT\Printers\PointAndPrint", "RestrictDriverInstallationToAdministrators")
    ]
    
    for key_path, value_name in policies_to_check:
        try:
            hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            value, _ = winreg.QueryValueEx(hkey, value_name)
            if value == 1:
                return True
        except Exception:
            continue
    return False

# ===== 辅助函数 =====
def press_any_key(message="按任意键继续..."):
    """真正的按任意键功能"""
    print(message, end='', flush=True)
    try:
        msvcrt.getch()  # Windows下真正的按任意键
        print()  # 换行
    except:
        # 如果msvcrt不可用，回退到input
        input()

def fix_with_timeout(fix_func, timeout=10):
    """在指定时间内执行修复操作"""
    result = {'done': False, 'error': None}
    
    def target():
        try:
            fix_func()
            result['done'] = True
        except Exception as e:
            result['error'] = str(e)
    
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(timeout)
    
    return result['done']

def start_service(service_name):
    """启动Windows服务"""
    try:
        subprocess.run(['net', 'start', service_name], 
                      capture_output=True, text=True, timeout=15)
        return True
    except:
        try:
            subprocess.run(['sc', 'start', service_name], 
                          capture_output=True, text=True, timeout=15)
            return True
        except:
            return False

# ===== 修复项目配置 =====
REPAIR_ITEMS = [
    {
        'name': '打印服务(Spooler)',
        'check': check_spooler,
        'fix': lambda: start_service('Spooler'),
        'timeout': 10,
        'critical': True
    },
    {
        'name': 'WIA扫描服务(STISVC)',
        'check': check_wia_service,
        'fix': lambda: start_service('stisvc'),
        'timeout': 10,
        'critical': True
    },
    {
        'name': 'VC++ 2015运行库',
        'check': check_vc_redist,
        'fix': lambda: os.startfile('https://aka.ms/vs/17/release/vc_redist.x86.exe'),
        'timeout': 5,
        'critical': True
    },
    {
        'name': '.NET Framework 4.0+',
        'check': check_dotnet,
        'fix': lambda: os.startfile('https://www.microsoft.com/zh-cn/download/details.aspx?id=17851'),
        'timeout': 5,
        'critical': True
    },
    {
        'name': 'Windows Update服务（非必要项）',
        'check': check_windows_update,
        'fix': lambda: start_service('wuauserv'),
        'timeout': 10,
        'critical': False
    },
    {
        'name': 'Win7主题服务（非必要项）',
        'check': check_win7_theme_service,
        'fix': lambda: start_service('Themes'),
        'timeout': 10,
        'critical': False
    }
]

# ===== 主程序 =====
def main():
    """主程序入口"""
    print("=" * 60)
    print("Win7打印及扫描环境修复工具 2.3版  by 忆痕（yckj666@52PJ）")
    print("适用系统：Windows 7 SP1")
    print("用途：自动检测并修复打印及扫描相关环境问题")
    print("=" * 60)
    
    # 系统版本检查
    if not is_win7():
        print("× 当前系统不是Windows 7，建议使用对应版本的修复工具！")
        press_any_key("按任意键退出...")
        sys.exit(1)
    
    print("\n【系统环境检测】")
    print("-" * 40)
    
    # 关键检测项
    admin_ok = check_admin()
    spooler_ok = check_spooler()
    wia_ok = check_wia_service()
    vc_ok = check_vc_redist()
    dotnet_ok = check_dotnet()
    driver_ok = check_printer_driver()
    scanner_ok = check_scanner_driver()
    wia_components_ok = check_wia_components()
    sp1_ok = check_win7_sp1()
    
    print(f"管理员权限：{'√正常' if admin_ok else '需要以管理员身份运行'}")
    print(f"Win7 SP1补丁：{'√已安装' if sp1_ok else '建议安装SP1'}")
    print(f"打印服务：{'√正常' if spooler_ok else '服务未启动'}")
    print(f"WIA扫描服务：{'√正常' if wia_ok else '扫描服务未启动'}")
    print(f"VC++运行库：{'√已安装' if vc_ok else '缺少必要组件'}")
    print(f".NET Framework：{'√已安装' if dotnet_ok else '缺少运行环境'}")
    print(f"打印机驱动：{'√已安装' if driver_ok else '未检测到物理打印机'}")
    print(f"扫描仪驱动：{'√已安装' if scanner_ok else '未检测到扫描设备'}")
    print(f"WIA组件：{'√正常' if wia_components_ok else 'WIA组件异常'}")
    
    # 次要检测项
    print(f"\n【环境状态检测】")
    print("-" * 40)
    wu_ok = check_windows_update()
    theme_ok = check_win7_theme_service()
    disk_ok = check_disk_space()
    vm_detected = check_virtual_machine()
    security_detected = check_security_software()
    policy_blocked = check_group_policy()
    
    print(f"更新服务：{'√正常' if wu_ok else '服务未启动'}")
    print(f"主题服务：{'√正常' if theme_ok else '服务异常'}")
    print(f"磁盘空间：{'√充足' if disk_ok else '空间不足'}")
    print(f"虚拟机环境：{'检测到' if vm_detected else '物理机'}")
    print(f"安全软件：{'可能影响' if security_detected else '无影响'}")
    print(f"组策略限制：{'被禁用' if policy_blocked else '无限制'}")
    
    # 问题统计
    critical_issues = sum([not admin_ok, not spooler_ok, not wia_ok, not vc_ok, not dotnet_ok, not wia_components_ok])
    
    if critical_issues == 0:
        print(f"\n检测完成！未发现关键问题，打印及扫描环境应该正常。")
    else:
        print(f"\n检测到 {critical_issues} 个关键问题需要修复。")
    
    # 显示可修复项目
    print(f"\n【可自动修复的项目】")
    print("-" * 40)
    for idx, item in enumerate(REPAIR_ITEMS, 1):
        status = '√' if item['check']() else '×'
        critical_mark = '🔴' if item['critical'] and not item['check']() else ''
        print(f"{idx}. {item['name']} [{status}] {critical_mark}")
    
    print(f"\n修复说明:")
    print("- 输入序号选择修复项目 (如: 1,3,5)")
    print("- 输入 0 修复所有异常项目")
    print("- 直接回车跳过修复环节")
    
    choice = input("\n请选择要修复的项目: ").strip()
    
    if not choice:
        print("跳过修复，程序结束。")
        press_any_key("按任意键退出...")
        return
    
    # 解析用户选择
    if choice == '0':
        # 只修复检测失败的项目
        selected = [i+1 for i, item in enumerate(REPAIR_ITEMS) if not item['check']()]
    else:
        selected = []
        for c in choice.split(','):
            try:
                n = int(c.strip())
                if 1 <= n <= len(REPAIR_ITEMS):
                    selected.append(n)
            except ValueError:
                continue
    
    if not selected:
        print("未选择有效的修复项目。")
        press_any_key("按任意键退出...")
        return
    
    # 执行修复
    print(f"\n开始修复 {len(selected)} 个项目...")
    print("-" * 40)
    success_count = 0
    
    for i in selected:
        item = REPAIR_ITEMS[i-1]
        print(f"正在修复: {item['name']}...", end=' ')
        
        if item['check']():
            print("已正常，跳过")
            success_count += 1
        else:
            success = fix_with_timeout(item['fix'], item['timeout'])
            if success:
                print("√ 完成")
                success_count += 1
            else:
                print("× 失败")
    
    print(f"\n修复完成: {success_count}/{len(selected)} 个项目成功")
    
    if success_count == len(selected):
        print("所有项目修复成功！建议重启电脑后测试打印及扫描功能。")
    else:
        print("部分项目修复失败，可能需要手动处理或联系技术支持。")
    
    print("\n技术支持:")
    print("- GitHub: https://github.com/a937750307/lan-printing")
    print("- 作者: 忆痕 (yckj666@52PJ)")
    
    press_any_key("\n按任意键退出...")

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断程序退出。")
    except Exception as e:
        print(f"\n\n程序发生异常: {e}")
        print("请联系技术支持或提交GitHub Issues。")
        press_any_key("按任意键退出...")