import os
import sys
import platform
import subprocess
import ctypes

def is_win10():
    return platform.system() == 'Windows' and platform.release() == '10'

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
    # 检查是否安装了打印相关补丁（仅KB5007186）
    patch_kb = "KB5007186"
    try:
        output = subprocess.check_output(
            ["wmic", "qfe", "get", "HotFixID"], encoding="gbk", errors="ignore")
        installed = set([line.strip() for line in output.splitlines() if line.strip().startswith("KB")])
        if patch_kb in installed:
            print(f"已安装打印相关补丁：{patch_kb}。")
            return True
        else:
            print(f"缺少打印相关补丁：{patch_kb}")
            return False
    except Exception as e:
        print("补丁检测失败：", e)
        return False

def check_defender():
    try:
        result = subprocess.run(['powershell', '-Command', 'Get-MpComputerStatus'], capture_output=True, text=True, timeout=10)
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

print("========================================")
print("Win10打印环境修复工具  by 忆痕（yckj666@52PJ）")
print("适用系统：Windows 10")
print("用途：自动检测并修复打印相关环境问题，帮助用户顺利使用打印服务。")
print("")
print("【使用方法】")
print("1. 请右键以管理员身份运行本工具（否则部分修复操作可能失败）。")
print("2. 工具会自动检测系统环境并尝试修复常见问题。")
print("3. 检测结果和修复建议会详细显示在窗口中。")
print("4. 如有下载链接，请复制到浏览器下载并安装。")
print("5. 如遇不懂的地方，可联系技术支持或反馈GitHub Issues。")
print("========================================")

REPAIR_ITEMS = [
    {
        'name': 'VC运行库',
        'check': check_vc_redist,
        'fix': lambda: os.startfile('https://aka.ms/vs/17/release/vc_redist.x64.exe'),
        'timeout': 10
    },
    {
        'name': '.NET Framework',
        'check': check_dotnet,
        'fix': lambda: os.startfile('https://www.microsoft.com/zh-cn/download/details.aspx?id=30653'),
        'timeout': 10
    },
    {
        'name': 'Win10打印补丁（KB5007186）',
        'check': check_updates,
        'fix': lambda: print("请访问以下链接下载并安装KB5007186补丁：\n"
                              "https://www.catalog.update.microsoft.com/Search.aspx?q=KB5007186"),
        'timeout': 10
    },
    {
        'name': 'Windows Update服务',
        'check': check_windows_update,
        'fix': lambda: subprocess.run(['sc', 'start', 'wuauserv']),
        'timeout': 10
    },
]

import threading

def fix_with_timeout(fix_func, timeout=10):
    result = {'done': False}
    def target():
        try:
            fix_func()
            result['done'] = True
        except Exception as e:
            print(f'修复时出错: {e}')
    t = threading.Thread(target=target)
    t.start()
    t.join(timeout)
    if t.is_alive():
        print('修复超时，可能未完成。')
        return False
    return result['done']

def main():
    print("\n========================================")
    print("Win10打印环境修复工具  by 忆痕(yckj666@52PJ)")
    print("适用系统: Windows 10")
    print("用途: 自动检测并修复打印相关环境问题，帮助用户顺利使用打印服务。")
    print("\n【使用方法】")
    print("1. 请右键以管理员身份运行本工具(否则部分修复操作可能失败)。")
    print("2. 工具会自动检测系统环境并尝试修复常见问题。")
    print("3. 检测结果和修复建议会详细显示在窗口中。")
    print("4. 如有下载链接，请复制到浏览器下载并安装。")
    print("5. 如遇不懂的地方，可联系技术支持或反馈GitHub Issues。")
    print("========================================\n")
    if not is_win10():
        print("当前系统不是Windows 10，建议使用对应版本修复工具！")
        sys.exit(1)
    print("请选择需要修复的项目（可多选，逗号分隔，或输入0全部修复）：")
    for idx, item in enumerate(REPAIR_ITEMS, 1):
        status = '√' if item['check']() else '×'
        print(f"{idx}. {item['name']} [{status}]")
    choice = input("输入序号，如 1,3 或 0：").strip()
    if choice == '0':
        selected = list(range(1, len(REPAIR_ITEMS)+1))
    else:
        selected = []
        for c in choice.split(','):
            try:
                n = int(c)
                if 1 <= n <= len(REPAIR_ITEMS):
                    selected.append(n)
            except:
                pass
    print("\n开始修复...")
    for idx in selected:
        item = REPAIR_ITEMS[idx-1]
        print(f"修复：{item['name']} ...", end='')
        ok = fix_with_timeout(item['fix'], item['timeout'])
        print("完成" if ok else "失败")
    print("\n修复流程结束，建议重启电脑后再次检测。按任意键退出...")
    input()

if __name__ == '__main__':
    main()
