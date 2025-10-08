# ===== Win7打印环境修复工具 1.6优化版 =====
# 作者：忆痕（yckj666@52PJ）
# 适用系统：Windows 7 SP1
# 版本：1.6优化版

import os
import sys
import platform
import subprocess
import ctypes
import threading
import time
import msvcrt

# ===== 系统检查函数 =====
def is_win7():
    """检查是否为Windows 7系统"""
    return platform.system() == "Windows" and platform.release() == "7"

def check_admin():
    """检查是否具有管理员权限"""
    try:
        return ctypes.windll.shell32.IsUserAnAdmin()
    except:
        return False

def check_spooler():
    """检查打印服务(Spooler)是否正在运行"""
    try:
        result = subprocess.run(['sc', 'query', 'Spooler'], capture_output=True, text=True, timeout=5)
        return 'RUNNING' in result.stdout
    except:
        return False

def check_vc_redist():
    """检查VC运行库是否安装（Win7兼容版本）"""
    try:
        import winreg
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
    except Exception:
        return False

def check_dotnet():
    """检查.NET Framework是否安装（Win7适用版本）"""
    try:
        import winreg
        # 检查.NET Framework 4.0及以上版本
        key_path = r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v4\Full"
        try:
            hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            value, _ = winreg.QueryValueEx(hkey, "Release")
            if value >= 378389:  # .NET 4.5及以上
                return True
        except Exception:
            pass
        
        # 检查.NET Framework 3.5（Win7默认）
        key_path_35 = r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v3.5"
        try:
            hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path_35)
            value, _ = winreg.QueryValueEx(hkey, "Install")
            if value == 1:
                return True
        except Exception:
            pass
        
        # 检查.NET Framework 2.0（Win7基础版本）
        key_path_20 = r"SOFTWARE\Microsoft\NET Framework Setup\NDP\v2.0.50727"
        try:
            hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path_20)
            value, _ = winreg.QueryValueEx(hkey, "Install")
            if value == 1:
                return True
        except Exception:
            pass
        
        return False
    except Exception:
        return False

def check_printer_driver():
    """检查是否安装了物理打印机驱动"""
    try:
        import win32print
        printers = win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS)
        for p in printers:
            # 过滤虚拟打印机
            if p[2] and p[2] not in ['Microsoft XPS Document Writer', 'Microsoft Print to PDF', 'Send To OneNote']:
                return True
        return False
    except:
        return False

def check_updates():
    """检查Win7关键安全补丁是否已安装"""
    try:
        import winreg
        # 检查多个关键补丁
        critical_patches = ["KB3033929", "KB3125574", "KB4474419", "KB4490628"]
        installed_patches = 0
        
        key_path = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Component Based Servicing\Packages"
        try:
            hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
            count = winreg.QueryInfoKey(hkey)[0]
            for i in range(count):
                subkey = winreg.EnumKey(hkey, i)
                for patch in critical_patches:
                    if patch in subkey:
                        try:
                            sub_hkey = winreg.OpenKey(hkey, subkey)
                            value, _ = winreg.QueryValueEx(sub_hkey, "CurrentState")
                            if value == 112:  # 已安装
                                installed_patches += 1
                                break
                        except Exception:
                            continue
        except Exception:
            pass
        
        # 至少安装一个关键补丁即认为正常
        return installed_patches > 0
    except Exception:
        return False

def check_windows_update():
    """检查Windows Update服务状态"""
    try:
        result = subprocess.run(['sc', 'query', 'wuauserv'], capture_output=True, text=True, timeout=5)
        return 'RUNNING' in result.stdout
    except:
        return False

def check_win7_sp1():
    """检查Win7是否安装了SP1补丁包"""
    try:
        import winreg
        key_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion"
        hkey = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path)
        try:
            value, _ = winreg.QueryValueEx(hkey, "CSDVersion")
            return "Service Pack 1" in value
        except:
            return False
    except:
        return False

def check_win7_theme_service():
    """检查Win7主题服务是否正常（影响打印界面显示）"""
    try:
        result = subprocess.run(['sc', 'query', 'Themes'], capture_output=True, text=True, timeout=5)
        return 'RUNNING' in result.stdout
    except:
        return False

def check_disk_space():
    """检查磁盘空间是否充足"""
    try:
        import shutil
        total, used, free = shutil.disk_usage(os.environ.get('SystemDrive', 'C:') + '\\')
        # Win7至少需要1GB空闲空间
        return free > 1024*1024*1024
    except:
        return True

def check_virtual_machine():
    """检查是否运行在虚拟机环境"""
    try:
        system_info = platform.platform().lower()
        vm_indicators = ['virtual', 'vmware', 'virtualbox', 'qemu', 'xen']
        return any(indicator in system_info for indicator in vm_indicators)
    except:
        return False

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

def check_group_policy():
    """检查组策略是否禁用打印功能"""
    try:
        import winreg
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
    except Exception:
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

# ===== 修复辅助函数 =====
def fix_with_timeout(fix_func, timeout=10):
    """在指定时间内执行修复操作"""
    result = {'done': False, 'error': None}
    
    def target():
        try:
            fix_func()
            result['done'] = True
        except Exception as e:
            result['error'] = str(e)
    
    thread = threading.Thread(target=target)
    thread.daemon = True
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
        'name': 'Win7关键安全补丁',
        'check': check_updates,
        'fix': lambda: os.startfile('https://www.catalog.update.microsoft.com/Search.aspx?q=KB3033929'),
        'timeout': 5,
        'critical': False
    },
    {
        'name': 'Windows Update服务',
        'check': check_windows_update,
        'fix': lambda: start_service('wuauserv'),
        'timeout': 10,
        'critical': False
    },
    {
        'name': 'Win7主题服务',
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
    print("Win7打印环境修复工具 1.6版  by 忆痕（yckj666@52PJ）")
    print("适用系统：Windows 7 SP1")
    print("用途：自动检测并修复打印相关环境问题")
    print("=" * 60)
    
    # 系统版本检查
    if not is_win7():
        print("❌ 当前系统不是Windows 7，建议使用对应版本的修复工具！")
        press_any_key("按任意键退出...")
        sys.exit(1)
    
    print("\n🔍 【系统环境检测】")
    print("-" * 40)
    
    # 关键检测项
    admin_ok = check_admin()
    spooler_ok = check_spooler()
    vc_ok = check_vc_redist()
    dotnet_ok = check_dotnet()
    driver_ok = check_printer_driver()
    sp1_ok = check_win7_sp1()
    
    print(f"管理员权限：{'✅ 正常' if admin_ok else '❌ 需要以管理员身份运行'}")
    print(f"Win7 SP1补丁：{'✅ 已安装' if sp1_ok else '⚠️ 建议安装SP1'}")
    print(f"打印服务：{'✅ 正常' if spooler_ok else '❌ 服务未启动'}")
    print(f"VC++运行库：{'✅ 已安装' if vc_ok else '❌ 缺少必要组件'}")
    print(f".NET Framework：{'✅ 已安装' if dotnet_ok else '❌ 缺少运行环境'}")
    print(f"打印机驱动：{'✅ 已安装' if driver_ok else '⚠️ 未检测到物理打印机'}")
    
    # 次要检测项
    print(f"\n🔧 【环境状态检测】")
    print("-" * 40)
    update_ok = check_updates()
    wu_ok = check_windows_update()
    theme_ok = check_win7_theme_service()
    disk_ok = check_disk_space()
    vm_detected = check_virtual_machine()
    security_detected = check_security_software()
    policy_blocked = check_group_policy()
    
    print(f"安全补丁：{'✅ 已安装关键补丁' if update_ok else '⚠️ 缺少安全补丁'}")
    print(f"更新服务：{'✅ 正常' if wu_ok else '⚠️ 服务未启动'}")
    print(f"主题服务：{'✅ 正常' if theme_ok else '⚠️ 服务异常'}")
    print(f"磁盘空间：{'✅ 充足' if disk_ok else '⚠️ 空间不足'}")
    print(f"虚拟机环境：{'⚠️ 检测到' if vm_detected else '✅ 物理机'}")
    print(f"安全软件：{'⚠️ 可能影响' if security_detected else '✅ 无影响'}")
    print(f"组策略限制：{'❌ 被禁用' if policy_blocked else '✅ 无限制'}")
    
    # 问题统计
    critical_issues = sum([not admin_ok, not spooler_ok, not vc_ok, not dotnet_ok])
    
    if critical_issues == 0:
        print(f"\n🎉 检测完成！未发现关键问题，打印环境应该正常。")
    else:
        print(f"\n⚠️ 检测到 {critical_issues} 个关键问题需要修复。")
    
    # 显示可修复项目
    print(f"\n🛠️ 【可自动修复的项目】")
    print("-" * 40)
    for idx, item in enumerate(REPAIR_ITEMS, 1):
        status = '✅' if item['check']() else '❌'
        critical_mark = '🔴' if item['critical'] and not item['check']() else ''
        print(f"{idx}. {item['name']} [{status}] {critical_mark}")
    
    print(f"\n💡 修复说明:")
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
    print(f"\n🔄 开始修复 {len(selected)} 个项目...")
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
                print("✅ 完成")
                success_count += 1
            else:
                print("❌ 失败")
    
    print(f"\n📊 修复完成: {success_count}/{len(selected)} 个项目成功")
    
    if success_count == len(selected):
        print("🎉 所有项目修复成功！建议重启电脑后测试打印功能。")
    else:
        print("⚠️ 部分项目修复失败，可能需要手动处理或联系技术支持。")
    
    print("\n📞 技术支持:")
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