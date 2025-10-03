import os
import sys
import platform
import subprocess
import ctypes
import threading
import time

def is_win11():
    return platform.system() == 'Windows' and platform.release() == '10' and '22000' in platform.version()

def check_admin():
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def check_spooler():
    try:
        result = subprocess.run(['sc', 'query', 'Spooler'], capture_output=True, text=True, timeout=5)
        return 'RUNNING' in result.stdout
    except:
        return False

def check_vc_redist():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64")
        return True
    except:
        return False

def check_dotnet():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full")
        value, _ = winreg.QueryValueEx(key, "Release")
        return value >= 378389
    except:
        return False

def check_firewall():
    try:
        result = subprocess.run(['netsh', 'advfirewall', 'show', 'allprofiles', 'state'], capture_output=True, text=True, timeout=5)
        return 'ON' in result.stdout
    except:
        return False

def check_updates():
    # 目前官网无Win11专用打印补丁，直接返回True
    return True

def check_defender():
    try:
        result = subprocess.run(['powershell', '-Command', 'Get-MpComputerStatus'], capture_output=True, text=True, timeout=10)
        return 'RealTimeProtectionEnabled' in result.stdout
    except:
        return False

def check_virtualization():
    try:
        result = subprocess.run(['systeminfo'], capture_output=True, text=True, timeout=10)
        return '虚拟化已启用' in result.stdout or 'Virtualization Enabled' in result.stdout
    except:
        return False

def check_group_policy():
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\\Policies\\Microsoft\\Windows NT\\Printers")
        return True
    except:
        return False

def check_printer_connected():
    try:
        import win32print
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        return len(printers) > 0
    except:
        return False

def check_printer_driver():
    try:
        import win32print
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        for p in printers:
            if p[2] and p[2] != 'Microsoft XPS Document Writer':
                return True
        return False
    except:
        return False

def check_windows_update():
    try:
        result = subprocess.run(['sc', 'query', 'wuauserv'], capture_output=True, text=True, timeout=5)
        return 'RUNNING' in result.stdout
    except:
        return False

def check_system_time():
    # 检查系统时间是否与网络时间相差过大（网络不可用时仅参考本地时间，不影响主流程）
    try:
        import time
        local_time = time.time()
        net_time = None
        try:
            import requests
            net_time = requests.get('http://worldtimeapi.org/api/ip', timeout=3).json()['unixtime']
        except Exception:
            print("未检测到网络时间，仅参考本地时间。")
            return True  # 网络不可用时不影响主流程
        if net_time:
            diff = abs(local_time - net_time)
            return diff < 300  # 误差5分钟以内
        return True
    except Exception:
        return True

def check_disk_space():
    try:
        import shutil
        total, used, free = shutil.disk_usage(os.environ.get('SystemDrive', 'C:') + '\\')
        return free > 500*1024*1024
    except:
        return True

def check_virtual_machine():
    try:
        import platform
        if 'Virtual' in platform.platform() or 'VMware' in platform.platform():
            return True
        return False
    except:
        return False

def check_security_software():
    try:
        import psutil
        processes = [p.name().lower() for p in psutil.process_iter()]
        for name in ['360tray.exe', 'kxetray.exe', 'rstray.exe', 'avp.exe', 'zhudongfangyu.exe', 'firefox.exe', 'qqpcmgr.exe']:
            if name in processes:
                return True
        return False
    except:
        return False

def fix_with_timeout(func, timeout=10):
    """带超时的修复操作"""
    result = [None]
    def target():
        try:
            result[0] = func()
        except Exception as e:
            result[0] = f"异常: {e}"
    t = threading.Thread(target=target)
    t.start()
    t.join(timeout)
    if t.is_alive():
        return "超时未完成"
    return result[0]

REPAIR_ITEMS = [
    ("打印服务(Spooler)", check_spooler, lambda: os.system('sc start Spooler')),
    ("VC运行库", check_vc_redist, lambda: os.system('start https://aka.ms/vs/17/release/vc_redist.x64.exe')),
    (".NET Framework", check_dotnet, lambda: os.system('start https://www.microsoft.com/zh-cn/download/details.aspx?id=30653')),
    ("打印机连接", check_printer_connected, None),
    ("打印机驱动", check_printer_driver, None),
    # ("Win11打印补丁", check_updates, None),  # 暂无专用补丁，保留占位
    ("Windows Update服务", check_windows_update, lambda: os.system('sc start wuauserv')),
    ("系统时间", check_system_time, None),
    ("磁盘空间", check_disk_space, None),
    ("虚拟机/远程桌面环境", check_virtual_machine, None),
    ("安全软件拦截", check_security_software, None),
]

def main():
    print("""
========================================
Win11打印环境修复工具  by 忆痕（yckj666@52PJ）
适用系统：Windows 11
用途：自动检测并修复打印相关环境问题，帮助用户顺利使用打印服务。
========================================
""")
    if not is_win11():
        print("当前系统不是Windows 11，建议使用对应版本修复工具！")
        sys.exit(1)
    print("当前系统：Windows 11")
    print("\n【可选修复项】")
    for idx, (name, check_func, repair_func) in enumerate(REPAIR_ITEMS):
        status = check_func()
        print(f"{idx+1}. {name}：{'正常' if status else '异常'}")
    print("\n请选择要修复的项目（如 1,3,5 或 all 全部修复），直接回车跳过：")
    sel = input("输入序号（逗号分隔）：").strip()
    if not sel:
        print("未选择任何修复项，直接退出。")
        return
    if sel.lower() == 'all':
        indices = list(range(len(REPAIR_ITEMS)))
    else:
        indices = []
        for s in sel.split(','):
            try:
                i = int(s)-1
                if 0 <= i < len(REPAIR_ITEMS):
                    indices.append(i)
            except:
                pass
    print("\n【开始自动修复】")
    for i in indices:
        name, check_func, repair_func = REPAIR_ITEMS[i]
        print(f"修复[{i+1}] {name} ...", end='')
        if repair_func:
            result = fix_with_timeout(repair_func, timeout=10)
            print(f"结果: {result}")
        else:
            print("无需自动修复，请手动处理或参考检测结果。")
        time.sleep(1)
    print("\n修复流程结束，可根据结果进一步排查。\n按任意键退出...")
    input()

if __name__ == '__main__':
    main()
