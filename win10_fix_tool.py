# ===== Win10打印环境修复工具 1.6优化版 =====
# 作者：忆痕（yckj666@52PJ）
# 适用系统：Windows 10
# 版本：1.6优化版

import os
import sys
import platform
import subprocess
import ctypes
import threading
import time
import msvcrt

# ===== 通用工具函数 =====
def press_any_key():
    """等待用户按任意键退出"""
    print("\n按任意键退出...")
    msvcrt.getch()  # 真正的按任意键，不需要回车

def show_loading(seconds=3):
    """显示加载动画"""
    chars = "|/-\\"
    for i in range(seconds * 10):
        print(f"\r正在检测系统环境 {chars[i % len(chars)]}", end="", flush=True)
        time.sleep(0.1)
    print("\r检测完成！" + " " * 20)

def fix_updates_download():
    """修复Windows更新补丁问题"""
    print("\n正在为您打开Windows Update补丁下载页面...")
    try:
        # 打开Microsoft Update Catalog
        os.startfile('https://www.catalog.update.microsoft.com/Search.aspx?q=KB5007186')
        print("✓ 已在浏览器中打开补丁下载页面")
        print("请在页面中搜索并下载适用于您系统的补丁")
        return True
    except Exception as e:
        print(f"✗ 打开下载页面失败: {e}")
        print("请手动访问: https://www.catalog.update.microsoft.com")
        return False

# ===== 系统检查函数 =====
def is_win10():
    """检查是否为Windows 10系统"""
    return platform.system() == 'Windows' and platform.release() == '10'

def check_admin():
    """检查是否具有管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def check_spooler():
    """检查打印机后台处理程序服务状态"""
    try:
        result = subprocess.run(['sc', 'query', 'Spooler'], 
                              capture_output=True, text=True, timeout=5)
        return 'RUNNING' in result.stdout
    except Exception:
        return False

def check_vc_redist():
    """检查VC运行库是否安装（Win10兼容版本）"""
    try:
        import winreg
        # Win10适用的VC运行库版本
        keys = [
            r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",  # VC++ 2015-2022
            r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x86",
            r"SOFTWARE\Microsoft\VisualStudio\12.0\VC\Runtimes\x64",  # VC++ 2013
            r"SOFTWARE\Microsoft\VisualStudio\12.0\VC\Runtimes\x86",
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
    except Exception:
        return False

def check_dotnet():
    """检查.NET Framework是否安装（Win10适用版本）"""
    try:
        import winreg
        # 检查.NET Framework 4.5及以上版本
        key_path = r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full"
        try:
            hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            value, _ = winreg.QueryValueEx(hkey, "Release")
            if value >= 461808:  # .NET 4.7.2及以上（Win10推荐）
                return True
        except Exception:
            pass
        
        # 检查.NET Core/.NET 5+
        try:
            result = subprocess.run(['dotnet', '--version'], 
                                  capture_output=True, text=True, timeout=5)
            if result.returncode == 0:
                return True
        except Exception:
            pass
        
        return False
    except Exception:
        return False

def check_firewall():
    """检查Windows防火墙状态"""
    try:
        result = subprocess.run(['netsh', 'advfirewall', 'show', 'allprofiles', 'state'], 
                              capture_output=True, text=True, timeout=5)
        return 'ON' in result.stdout
    except Exception:
        return False

def check_updates():
    """检查Win10关键打印补丁是否已安装"""
    try:
        # Win10关键打印补丁
        critical_patches = ["KB5007186", "KB5006670", "KB5005565", "KB5003637"]
        installed_patches = 0
        
        output = subprocess.check_output(
            ["wmic", "qfe", "get", "HotFixID"], encoding="gbk", errors="ignore")
        installed = set([line.strip() for line in output.splitlines() if line.strip().startswith("KB")])
        
        for patch in critical_patches:
            if patch in installed:
                installed_patches += 1
        
        # 至少安装一个关键补丁即认为正常
        return installed_patches > 0
    except Exception:
        return False

def check_defender():
    """检查Windows Defender运行状态"""
    try:
        result = subprocess.run(['powershell', '-Command', 'Get-MpComputerStatus'], 
                              capture_output=True, text=True, timeout=10)
        return result.returncode == 0 and 'True' in result.stdout
    except Exception:
        return False

def check_group_policy():
    """检查打印相关组策略设置"""
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, 
                            r"SOFTWARE\Policies\Microsoft\Windows NT\Printers")
        winreg.CloseKey(key)
        return True
    except Exception:
        return False

def check_printer_connected():
    """检查是否有可用的打印机连接"""
    try:
        import win32print
        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        return len(printers) > 0
    except Exception:
        return False

def check_printer_driver():
    """检查是否安装了实际的打印机驱动（非虚拟打印机）"""
    try:
        import win32print
        printers = win32print.EnumPrinters(
            win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        for p in printers:
            if p[2] and p[2] != 'Microsoft XPS Document Writer':
                return True
        return False
    except Exception:
        return False

def check_windows_update():
    """检查Windows更新服务状态"""
    try:
        result = subprocess.run(['sc', 'query', 'wuauserv'], 
                              capture_output=True, text=True, timeout=5)
        return 'RUNNING' in result.stdout
    except Exception:
        return False

def check_system_time():
    """检查系统时间同步状态"""
    try:
        # 检查时间同步服务
        result = subprocess.run(['sc', 'query', 'w32time'], 
                              capture_output=True, text=True, timeout=5)
        return 'RUNNING' in result.stdout
    except Exception:
        return True

def check_disk_space():
    """检查系统磁盘可用空间"""
    try:
        import shutil
        total, used, free = shutil.disk_usage(
            os.environ.get('SystemDrive', 'C:') + '\\')
        # 至少需要500MB可用空间
        return free > 500 * 1024 * 1024
    except Exception:
        return True

def check_virtual_machine():
    """检查是否运行在虚拟机环境中"""
    try:
        platform_info = platform.platform().lower()
        vm_indicators = ['virtual', 'vmware', 'virtualbox', 'hyper-v', 'xen']
        return any(indicator in platform_info for indicator in vm_indicators)
    except Exception:
        return False

def check_security_software():
    """检查是否安装第三方安全软件"""
    try:
        import psutil
        processes = [p.name().lower() for p in psutil.process_iter()]
        security_processes = [
            '360tray.exe', 'kxetray.exe', 'rstray.exe', 'avp.exe', 
            'zhudongfangyu.exe', 'qqpcmgr.exe', 'kismain.exe'
        ]
        return any(proc in processes for proc in security_processes)
    except Exception:
        return False

# ===== 配置信息 =====
TOOL_INFO = {
    'title': 'Win10打印环境修复工具 1.6优化版',
    'author': '忆痕（yckj666@52PJ）',
    'system': 'Windows 10',
    'description': '自动检测并修复打印相关环境问题，帮助用户顺利使用打印服务',
    'version': '1.6优化版'
}

# ===== 检测项目配置 =====
REPAIR_ITEMS = [
    {
        'name': '打印机后台处理程序',
        'check': check_spooler,
        'fix': lambda: subprocess.run(['sc', 'start', 'Spooler'], timeout=10),
        'timeout': 10,
        'critical': True
    },
    {
        'name': 'VC++ 运行库',
        'check': check_vc_redist,
        'fix': lambda: os.startfile('https://aka.ms/vs/17/release/vc_redist.x64.exe'),
        'timeout': 5,
        'critical': True
    },
    {
        'name': '.NET Framework',
        'check': check_dotnet,
        'fix': lambda: os.startfile('https://dotnet.microsoft.com/download/dotnet-framework'),
        'timeout': 5,
        'critical': True
    },
    {
        'name': 'Win10关键打印补丁',
        'check': check_updates,
        'fix': lambda: fix_updates_download(),
        'timeout': 5,
        'critical': False
    },
    {
        'name': 'Windows Update服务',
        'check': check_windows_update,
        'fix': lambda: subprocess.run(['sc', 'start', 'wuauserv'], timeout=10),
        'timeout': 10,
        'critical': False
    },
    {
        'name': 'Windows Defender',
        'check': check_defender,
        'fix': lambda: print("请检查Windows Defender设置，确保实时保护已开启"),
        'timeout': 5,
        'critical': False
    }
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

def show_header():
    """显示工具标题和基本信息"""
    print("=" * 60)
    print(f"  {TOOL_INFO['title']}")
    print(f"  作者：{TOOL_INFO['author']}")
    print(f"  适用系统：{TOOL_INFO['system']}")
    print(f"  版本：{TOOL_INFO['version']}")
    print("=" * 60)
    print(f"\n【功能】{TOOL_INFO['description']}")
    print("\n【使用说明】")
    print("1. 请以管理员权限运行本工具（重要！）")
    print("2. 工具会自动检测并显示系统状态")
    print("3. 根据检测结果选择需要修复的项目")
    print("4. 按照提示进行相应的修复操作")
    print("5. 修复完成后建议重启系统")
    print("=" * 60)

def run_detection():
    """执行系统环境检测"""
    show_loading(2)
    results = {}
    
    print("\n【系统环境检测】")
    print("-" * 50)
    
    # 检测系统基本信息
    print(f"系统版本: {platform.system()} {platform.release()}")
    print(f"管理员权限: {'✓' if check_admin() else '✗'}")
    
    # 检测关键组件
    for item in REPAIR_ITEMS:
        status = item['check']()
        results[item['name']] = status
        status_symbol = '✓' if status else '✗'
        critical_mark = ' (关键)' if item.get('critical', False) else ''
        print(f"{item['name']}: {status_symbol}{critical_mark}")
    
    print("-" * 50)
    return results

def main():
    """主程序入口"""
    try:
        # 显示工具信息
        show_header()
        
        # 系统兼容性检查
        if not is_win10():
            print("\n⚠️  警告：当前系统不是Windows 10")
            print("建议使用对应版本的修复工具！")
            press_any_key()
            return
        
        # 权限检查提醒
        if not check_admin():
            print("\n⚠️  警告：检测到当前未以管理员权限运行")
            print("部分修复功能可能无法正常使用！")
            print("建议右键选择'以管理员身份运行'")
        
        # 执行检测
        results = run_detection()
        
        # 分析检测结果
        failed_items = [name for name, status in results.items() if not status]
        if not failed_items:
            print("\n🎉 恭喜！所有检测项目都正常，系统环境良好！")
            press_any_key()
            return
        
        print(f"\n发现 {len(failed_items)} 个问题需要修复")
        
        # 选择修复项目
        print("\n【选择修复项目】")
        print("0. 修复所有问题（推荐）")
        for idx, item in enumerate(REPAIR_ITEMS, 1):
            status = '✓' if results[item['name']] else '✗'
            critical_mark = ' (关键)' if item.get('critical', False) else ''
            print(f"{idx}. {item['name']} [{status}]{critical_mark}")
        
        choice = input("\n请输入选项（如: 0 或 1,3,5）: ").strip()
        
        # 解析用户选择
        if choice == '0':
            selected_items = [i for i, item in enumerate(REPAIR_ITEMS) if not results[item['name']]]
        else:
            selected_items = []
            for c in choice.split(','):
                try:
                    idx = int(c.strip()) - 1
                    if 0 <= idx < len(REPAIR_ITEMS):
                        selected_items.append(idx)
                except ValueError:
                    pass
        
        if not selected_items:
            print("未选择任何修复项目。")
            press_any_key()
            return
        
        # 执行修复
        print("\n【开始修复】")
        print("-" * 50)
        success_count = 0
        
        for idx in selected_items:
            item = REPAIR_ITEMS[idx]
            if results[item['name']]:  # 跳过已正常的项目
                continue
                
            print(f"\n正在修复: {item['name']}")
            try:
                fix_with_timeout(item['fix'], item['timeout'])
                success_count += 1
                print("✓ 修复操作已执行")
            except Exception as e:
                print(f"✗ 修复失败: {e}")
        
        print("-" * 50)
        print(f"\n修复完成！成功执行 {success_count} 个修复操作")
        print("\n【重要提醒】")
        print("1. 建议立即重启计算机以使修复生效")
        print("2. 重启后可再次运行本工具进行验证")
        print("3. 如问题仍未解决，请联系技术支持")
        
    except KeyboardInterrupt:
        print("\n\n用户中断操作。")
    except Exception as e:
        print(f"\n程序执行出错: {e}")
    finally:
        press_any_key()

if __name__ == '__main__':
    main()
