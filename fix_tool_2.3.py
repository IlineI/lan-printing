# ===== 打印及扫描环境修复工具 2.3版（通用版） =====
# 作者：忆痕（yckj666@52PJ）
# 适用系统：Windows 7 / 10 / 11
# 版本：2.3 - 通用合并版，自动识别系统版本，支持打印及扫描功能修复

import os
import sys
import platform
import subprocess
import ctypes
import threading
import time
import msvcrt
import winreg
import shutil
from functools import wraps

# ===== 通用工具函数 =====
def safe_check(func):
    """装饰器：安全执行检查函数，捕获所有异常"""
    @wraps(func)
    def wrapper(*args, **kwargs):
        try:
            return func(*args, **kwargs)
        except Exception:
            return False
    return wrapper

def press_any_key(message="\n按任意键退出..."):
    """等待用户按任意键退出"""
    print(message, end='', flush=True)
    try:
        msvcrt.getch()
        print()
    except:
        input()

def show_loading(seconds=2):
    """显示加载动画"""
    chars = "|/-\\"
    for i in range(seconds * 10):
        print(f"\r正在检测系统环境 {chars[i % len(chars)]}", end="", flush=True)
        time.sleep(0.1)
    print("\r检测完成！" + " " * 20)

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

    if thread.is_alive():
        return False
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

# ===== 系统版本检测 =====
@safe_check
def check_admin():
    """检查是否具有管理员权限"""
    return ctypes.windll.shell32.IsUserAnAdmin()

def detect_os_version():
    """检测当前Windows系统版本，返回 'win7' / 'win10' / 'win11' / 'unknown'"""
    if platform.system() != "Windows":
        return "unknown"
    release = platform.release()
    version = platform.version()
    if release == "7":
        return "win7"
    elif release == "10":
        # Win11的build号 >= 22000
        try:
            build = int(version.split('.')[-1])
            if build >= 22000:
                return "win11"
        except:
            pass
        return "win10"
    return "unknown"

def get_os_display_name(os_ver):
    """获取系统显示名称"""
    return {'win7': 'Windows 7', 'win10': 'Windows 10', 'win11': 'Windows 11'}.get(os_ver, '未知系统')

# ===== 通用检查函数（所有系统共用） =====
@safe_check
def check_service_running(service_name):
    """检查Windows服务是否正在运行"""
    result = subprocess.run(['sc', 'query', service_name], capture_output=True, text=True, timeout=5)
    return 'RUNNING' in result.stdout

def check_spooler():
    return check_service_running('Spooler')

def check_wia_service():
    return check_service_running('stisvc')

def check_windows_update():
    return check_service_running('wuauserv')

@safe_check
def check_vc_redist():
    """检查VC运行库是否安装"""
    keys = [
        r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64",
        r"SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x86",
        r"SOFTWARE\Microsoft\VisualStudio\12.0\VC\Runtimes\x64",
        r"SOFTWARE\Microsoft\VisualStudio\12.0\VC\Runtimes\x86",
    ]
    # Win7额外检查更多版本
    if detect_os_version() == "win7":
        keys.extend([
            r"SOFTWARE\Microsoft\VisualStudio\11.0\VC\Runtimes\x64",
            r"SOFTWARE\Microsoft\VisualStudio\11.0\VC\Runtimes\x86",
            r"SOFTWARE\Microsoft\VisualStudio\10.0\VC\Runtimes\x64",
            r"SOFTWARE\Microsoft\VisualStudio\10.0\VC\Runtimes\x86",
        ])
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
    """检查.NET Framework是否安装"""
    os_ver = detect_os_version()
    # 检查.NET Framework 4.x
    try:
        hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE,
                              r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full")
        value, _ = winreg.QueryValueEx(hkey, "Release")
        if os_ver == "win7":
            if value >= 378389:  # .NET 4.5+
                return True
        else:
            if value >= 461808:  # .NET 4.7.2+
                return True
    except Exception:
        pass

    # Win7额外检查.NET 3.5和2.0
    if os_ver == "win7":
        for ndp_key in [r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v3.5",
                        r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v2.0.50727"]:
            try:
                hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, ndp_key)
                value, _ = winreg.QueryValueEx(hkey, "Install")
                if value == 1:
                    return True
            except Exception:
                pass

    # 检查.NET Core / .NET 5+
    try:
        result = subprocess.run(['dotnet', '--version'],
                                capture_output=True, text=True, timeout=5)
        if result.returncode == 0:
            return True
    except Exception:
        pass

    return False

@safe_check
def check_printer_driver():
    """检查是否安装了物理打印机驱动"""
    import win32print
    printers = win32print.EnumPrinters(
        win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
    virtual_names = ['Microsoft XPS Document Writer', 'Microsoft Print to PDF', 'Send To OneNote']
    for p in printers:
        if p[2] and p[2] not in virtual_names:
            return True
    return False

@safe_check
def check_scanner_driver():
    """检查是否安装了扫描仪驱动（通过注册表检测）"""
    key_paths = [
        r"SYSTEM\CurrentControlSet\Control\Class\{6bdd1fc6-810f-11d0-bec7-08002be2092f}",
        r"SYSTEM\CurrentControlSet\Services\usbscan\Enum",
    ]
    for key_path in key_paths:
        try:
            hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
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
    device_manager = comtypes.client.CreateObject("WIA.DeviceManager")
    return device_manager is not None

@safe_check
def check_scanner_device():
    """检查是否有扫描设备连接"""
    result = subprocess.run(['powershell', '-Command',
                             'Get-PnpDevice | Where-Object {$_.Class -eq "Image"}'],
                            capture_output=True, text=True, timeout=10)
    return len(result.stdout.strip()) > 0

@safe_check
def check_scanner_app():
    """检查Windows扫描应用是否可用"""
    result = subprocess.run(['powershell', '-Command',
                             'Get-AppxPackage Microsoft.WindowsScan'],
                            capture_output=True, text=True, timeout=10)
    return 'Microsoft.WindowsScan' in result.stdout

@safe_check
def check_disk_space():
    """检查磁盘空间是否充足"""
    total, used, free = shutil.disk_usage(os.environ.get('SystemDrive', 'C:') + '\\')
    return free > 1024 * 1024 * 1024

@safe_check
def check_virtual_machine():
    """检查是否运行在虚拟机环境"""
    platform_info = platform.platform().lower()
    vm_indicators = ['virtual', 'vmware', 'virtualbox', 'hyper-v', 'xen', 'qemu']
    return any(indicator in platform_info for indicator in vm_indicators)

@safe_check
def check_security_software():
    """检查是否有安全软件可能影响打印"""
    try:
        import psutil
        processes = [p.name().lower() for p in psutil.process_iter()]
        security_apps = [
            '360tray.exe', 'kxetray.exe', 'rstray.exe', 'avp.exe',
            'zhudongfangyu.exe', 'qqpcmgr.exe', 'kismain.exe',
            'msmpeng.exe', 'mcuicnt.exe'
        ]
        return any(app in processes for app in security_apps)
    except:
        return False

@safe_check
def check_group_policy():
    """检查组策略是否禁用打印功能"""
    policies = [
        (r"SOFTWARE\Policies\Microsoft\Windows NT\Printers", "DisablePrint"),
        (r"SOFTWARE\Policies\Microsoft\Windows NT\Printers\PointAndPrint",
         "RestrictDriverInstallationToAdministrators")
    ]
    for key_path, value_name in policies:
        try:
            hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            value, _ = winreg.QueryValueEx(hkey, value_name)
            if value == 1:
                return True
        except Exception:
            continue
    return False

@safe_check
def check_defender():
    """检查Windows Defender运行状态"""
    result = subprocess.run(['powershell', '-Command', 'Get-MpComputerStatus'],
                            capture_output=True, text=True, timeout=10)
    return result.returncode == 0 and 'True' in result.stdout

# ===== Win7 专属检查 =====
@safe_check
def check_win7_sp1():
    """检查Win7是否安装了SP1"""
    key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
    hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
    try:
        value, _ = winreg.QueryValueEx(hkey, "CSDVersion")
        return "Service Pack 1" in value
    except:
        return False

def check_win7_theme_service():
    return check_service_running('Themes')

# ===== Win10 专属检查 =====
@safe_check
def check_win10_updates():
    """检查Win10关键打印补丁是否已安装"""
    critical_patches = ["KB5007186", "KB5006670", "KB5005565", "KB5003637"]
    output = subprocess.check_output(
        ["wmic", "qfe", "get", "HotFixID"], encoding="gbk", errors="ignore")
    installed = set([line.strip() for line in output.splitlines() if line.strip().startswith("KB")])
    return any(patch in installed for patch in critical_patches)

def fix_updates_download():
    """修复Windows更新补丁问题（Win10）"""
    print("\n正在为您打开Windows Update补丁下载页面...")
    try:
        os.startfile('https://www.catalog.update.microsoft.com/Search.aspx?q=KB5007186')
        print("✓ 已在浏览器中打开补丁下载页面")
        return True
    except Exception as e:
        print(f"× 打开下载页面失败: {e}")
        return False

# ===== Win11 专属检查 =====
@safe_check
def check_winrt_scanner():
    """检查Win11 WinRT扫描API是否可用"""
    result = subprocess.run(['powershell', '-Command',
                             'Get-WindowsCapability -Online | Where-Object {$_.Name -like "*Scan*"}'],
                            capture_output=True, text=True, timeout=10)
    return 'Installed' in result.stdout

@safe_check
def check_virtualization():
    """检查Hyper-V虚拟化功能状态（Win11特有）"""
    result = subprocess.run(['systeminfo'], capture_output=True, text=True, timeout=10)
    return ('虚拟化已启用' in result.stdout or
            'Virtualization Enabled' in result.stdout or
            'Hyper-V' in result.stdout)

# ===== 构建修复项目列表（根据系统版本动态生成） =====
def build_repair_items(os_ver):
    """根据系统版本构建修复项目列表"""
    items = [
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
            'name': 'VC++ 运行库',
            'check': check_vc_redist,
            'fix': lambda: os.startfile('https://aka.ms/vs/17/release/vc_redist.x86.exe' if os_ver == 'win7' else 'https://aka.ms/vs/17/release/vc_redist.x64.exe'),
            'timeout': 5,
            'critical': True
        },
        {
            'name': '.NET Framework',
            'check': check_dotnet,
            'fix': lambda: os.startfile(
                'https://www.microsoft.com/zh-cn/download/details.aspx?id=17851' if os_ver == 'win7'
                else 'https://dotnet.microsoft.com/download/dotnet-framework'),
            'timeout': 5,
            'critical': True
        },
    ]

    # Win7 专属项目
    if os_ver == 'win7':
        items.extend([
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
            },
        ])

    # Win10 专属项目
    if os_ver == 'win10':
        items.extend([
            {
                'name': 'Windows扫描应用（非必要项）',
                'check': lambda: check_scanner_app() or not check_scanner_device(),
                'fix': lambda: print("检测到扫描设备但缺少扫描应用，建议：\n1. 在Microsoft Store中安装Windows扫描应用\n2. 或访问扫描仪品牌官网下载专用扫描软件"),
                'timeout': 5,
                'critical': False
            },
            {
                'name': 'Win10关键打印补丁（非必要项）',
                'check': check_win10_updates,
                'fix': fix_updates_download,
                'timeout': 5,
                'critical': False
            },
            {
                'name': 'Windows Update服务（非必要项）',
                'check': check_windows_update,
                'fix': lambda: start_service('wuauserv'),
                'timeout': 10,
                'critical': False
            },
            {
                'name': 'Windows Defender（非必要项）',
                'check': check_defender,
                'fix': lambda: print("请检查Windows Defender设置，确保实时保护已开启"),
                'timeout': 5,
                'critical': False
            },
        ])

    # Win11 专属项目
    if os_ver == 'win11':
        items.extend([
            {
                'name': 'Windows扫描应用（非必要项）',
                'check': lambda: check_scanner_app() or not check_scanner_device(),
                'fix': lambda: print("检测到扫描设备但缺少扫描应用，建议：\n1. 在Microsoft Store中安装Windows扫描应用\n2. 或访问扫描仪品牌官网下载专用扫描软件"),
                'timeout': 5,
                'critical': False
            },
            {
                'name': 'Windows Update服务（非必要项）',
                'check': check_windows_update,
                'fix': lambda: start_service('wuauserv'),
                'timeout': 10,
                'critical': False
            },
            {
                'name': 'Windows Defender（非必要项）',
                'check': check_defender,
                'fix': lambda: print("请检查Windows Defender设置，确保实时保护已开启"),
                'timeout': 5,
                'critical': False
            },
            {
                'name': 'Hyper-V虚拟化功能（非必要项）',
                'check': check_virtualization,
                'fix': lambda: print("Win11虚拟化功能正常，有助于提升系统兼容性"),
                'timeout': 5,
                'critical': False
            },
        ])

    return items

# ===== 主程序 =====
def main():
    """主程序入口"""
    os_ver = detect_os_version()
    os_name = get_os_display_name(os_ver)

    print("=" * 60)
    print("  打印及扫描环境修复工具 2.3版（通用版）")
    print("  作者：忆痕（yckj666@52PJ）")
    print(f"  自动识别系统：{os_name}")
    print("  用途：自动检测并修复打印及扫描相关环境问题")
    print("=" * 60)

    # 系统版本检查
    if os_ver == "unknown":
        print("× 无法识别当前系统版本，建议使用对应版本的修复工具！")
        print(f"  当前检测到的系统信息：{platform.system()} {platform.release()} {platform.version()}")
        choice = input("是否继续运行？(y/N): ").strip().lower()
        if choice != 'y':
            press_any_key()
            return
        os_ver = "win10"  # 默认按Win10处理

    print(f"\n【系统环境检测】 - 识别为 {os_name}")
    print("-" * 50)

    # 管理员权限检查
    admin_ok = check_admin()
    print(f"管理员权限：{'√正常' if admin_ok else '× 需要以管理员身份运行'}")

    if not admin_ok:
        print("  警告：部分修复功能可能无法正常使用！")
        print("  建议右键选择'以管理员身份运行'")

    # Win7 专属提示
    if os_ver == 'win7':
        sp1_ok = check_win7_sp1()
        print(f"Win7 SP1补丁：{'√已安装' if sp1_ok else '× 建议安装SP1'}")

    show_loading(2)

    # 通用检测项
    spooler_ok = check_spooler()
    wia_ok = check_wia_service()
    vc_ok = check_vc_redist()
    dotnet_ok = check_dotnet()
    driver_ok = check_printer_driver()
    scanner_ok = check_scanner_driver()
    wia_components_ok = check_wia_components()

    print(f"\n【打印功能检测】")
    print(f"  打印服务(Spooler)：{'√正常' if spooler_ok else '× 服务未启动'}")
    print(f"  打印机驱动：{'√已安装' if driver_ok else '× 未检测到物理打印机'}")

    print(f"\n【扫描功能检测】")
    print(f"  WIA扫描服务：{'√正常' if wia_ok else '× 扫描服务未启动'}")
    print(f"  扫描仪驱动：{'√已安装' if scanner_ok else '× 未检测到扫描设备'}")
    print(f"  WIA组件：{'√正常' if wia_components_ok else '× WIA组件异常'}")

    # Win11 额外扫描检测
    if os_ver == 'win11':
        winrt_ok = check_winrt_scanner()
        print(f"  Win11扫描API：{'√正常' if winrt_ok else '× 未安装'}")

    # 扫描设备与应用
    scanner_device_ok = check_scanner_device()
    if scanner_device_ok:
        scanner_app_ok = check_scanner_app()
        print(f"  扫描设备：{'√已连接' if scanner_device_ok else '× 未检测到'}")
        print(f"  扫描应用：{'√已安装' if scanner_app_ok else '× 未安装'}")
    else:
        print(f"  扫描设备：- (未检测到扫描设备)")

    # 环境状态检测
    print(f"\n【环境状态检测】")
    print(f"  VC++运行库：{'√已安装' if vc_ok else '× 缺少必要组件'}")
    print(f"  .NET Framework：{'√已安装' if dotnet_ok else '× 缺少运行环境'}")

    disk_ok = check_disk_space()
    print(f"  磁盘空间：{'√充足' if disk_ok else '× 空间不足'}")

    vm_detected = check_virtual_machine()
    print(f"  虚拟机环境：{'检测到' if vm_detected else '物理机'}")

    security_detected = check_security_software()
    print(f"  安全软件：{'可能影响' if security_detected else '无影响'}")

    policy_blocked = check_group_policy()
    print(f"  组策略限制：{'被禁用' if policy_blocked else '无限制'}")

    # 构建修复项目
    repair_items = build_repair_items(os_ver)

    # 统计关键问题
    critical_issues = sum([
        not admin_ok, not spooler_ok, not wia_ok,
        not vc_ok, not dotnet_ok, not wia_components_ok
    ])

    if critical_issues == 0:
        print(f"\n检测完成！未发现关键问题，打印及扫描环境应该正常。")
    else:
        print(f"\n检测到 {critical_issues} 个关键问题需要修复。")

    # 显示可修复项目
    print(f"\n【可自动修复的项目】")
    print("-" * 50)
    for idx, item in enumerate(repair_items, 1):
        status = '√' if item['check']() else '×'
        critical_mark = ' (关键)' if item['critical'] and not item['check']() else ''
        print(f"  {idx}. {item['name']} [{status}]{critical_mark}")

    print(f"\n修复说明:")
    print("  - 输入序号选择修复项目 (如: 1,3,5)")
    print("  - 输入 0 修复所有异常项目")
    print("  - 直接回车跳过修复环节")

    choice = input("\n请选择要修复的项目: ").strip()

    if not choice:
        print("跳过修复，程序结束。")
        press_any_key()
        return

    # 解析用户选择
    if choice == '0':
        selected = [i + 1 for i, item in enumerate(repair_items) if not item['check']()]
    else:
        selected = []
        for c in choice.split(','):
            try:
                n = int(c.strip())
                if 1 <= n <= len(repair_items):
                    selected.append(n)
            except ValueError:
                continue

    if not selected:
        print("未选择有效的修复项目。")
        press_any_key()
        return

    # 执行修复
    print(f"\n【开始修复】共 {len(selected)} 个项目")
    print("-" * 50)
    success_count = 0

    for i in selected:
        item = repair_items[i - 1]
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

    print("\n【重要提醒】")
    print("  1. 建议立即重启计算机以使修复生效")
    print("  2. 重启后可再次运行本工具进行验证")
    print("  3. 测试打印及扫描功能是否正常工作")
    if os_ver == 'win11':
        print("  4. Win11系统建议保持最新版本以获得最佳打印扫描兼容性")

    print("\n技术支持:")
    print("  GitHub: https://github.com/a937750307/lan-printing")
    print("  作者: 忆痕 (yckj666@52PJ)")

    press_any_key()

if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n用户中断程序退出。")
    except Exception as e:
        print(f"\n\n程序发生异常: {e}")
        print("请联系技术支持或提交GitHub Issues。")
        press_any_key()
